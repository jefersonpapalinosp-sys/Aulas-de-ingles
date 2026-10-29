import contextlib
import io
import os
import unittest
from unittest.mock import patch

from ops.observability_check import Thresholds, _url, evaluate, main


def readiness(schema="compatible"):
    return {"status": "ok" if schema == "compatible" else "degraded", "schema": schema}


def metrics():
    return {
        "assist_costs": {
            "daily": {"cost_microusd": 400, "unknown_cost_reservations": 0},
            "monthly": {"cost_microusd": 1000, "unknown_cost_reservations": 0},
        },
        "requests": {"requests_total": 100, "responses_5xx_total": 1},
        "database": {"waiting_locks": 0},
        "transcription_queue": {
            "oldest_queued_seconds": 2,
            "worker_age_seconds": 5,
            "maintenance_age_seconds": 30,
        },
        "account_deletions": {"failed": 0},
        "legacy_review": {"unlinked_cards": 0, "mismatched_links": 0},
        "media": {"filesystem_available": True, "filesystem_free_bytes": 2_000_000_000},
        "dialogue": {
            "turns": 12,
            "provider_failures": 0,
            "cost_microusd": 400,
            "quota_limit": 24,
            "quota_used": 12,
            "quota_exhausted_accounts": 0,
        },
    }


def configured_thresholds():
    return Thresholds(
        assist_daily_budget_microusd=100_000, assist_monthly_budget_microusd=1_000_000
    )


class ObservabilityGateTests(unittest.TestCase):
    def test_healthy_snapshot_passes_with_fixed_owners_and_actions(self):
        report = evaluate(readiness(), metrics(), configured_thresholds())
        self.assertEqual(report["status"], "ok")
        self.assertTrue(all(item["owner"] and item["action"] for item in report["checks"]))

    def test_each_threshold_can_block_release(self):
        mutations = [
            ("schema", lambda ready, data: ready.update(readiness("incompatible"))),
            (
                "error",
                lambda ready, data: data["requests"].update(responses_5xx_total=10),
            ),
            (
                "queue",
                lambda ready, data: data["transcription_queue"].update(oldest_queued_seconds=301),
            ),
            (
                "worker",
                lambda ready, data: data["transcription_queue"].update(worker_age_seconds=None),
            ),
            (
                "maintenance",
                lambda ready, data: data["transcription_queue"].update(
                    maintenance_age_seconds=7201
                ),
            ),
            ("locks", lambda ready, data: data["database"].update(waiting_locks=1)),
            (
                "deletion",
                lambda ready, data: data["account_deletions"].update(failed=1),
            ),
            (
                "legacy-review",
                lambda ready, data: data["legacy_review"].update(unlinked_cards=1),
            ),
            (
                "storage",
                lambda ready, data: data["media"].update(filesystem_free_bytes=1),
            ),
            (
                "dialogue-cost",
                lambda ready, data: data["dialogue"].update(cost_microusd=50_001),
            ),
            (
                "dialogue-failures",
                lambda ready, data: data["dialogue"].update(provider_failures=4),
            ),
            # API anterior ao INFRA-46: a seção não existe, e o gate precisa
            # dizer que é diferença de versão em vez de passar como se a
            # conversa estivesse saudável.
            ("dialogue-absent", lambda ready, data: data.pop("dialogue")),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                ready, data = readiness(), metrics()
                mutate(ready, data)
                report = evaluate(ready, data, configured_thresholds())
                self.assertEqual(report["status"], "critical")
                self.assertIn("critical", {item["state"] for item in report["checks"]})

    def test_error_rate_waits_for_minimum_sample(self):
        data = metrics()
        data["requests"].update(requests_total=2, responses_5xx_total=2)
        report = evaluate(readiness(), data, configured_thresholds())
        error = next(item for item in report["checks"] if item["name"] == "request_error_rate")
        self.assertEqual(error["state"], "ok")

    def test_url_rejects_credentials_query_and_non_http(self):
        for value in ("file:///tmp/x", "http://user:pass@host", "http://host?token=x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _url(value, "/api/health")
        self.assertEqual(
            _url("https://example.test/", "/api/health"),
            "https://example.test/api/health",
        )


class DialogueGateTests(unittest.TestCase):
    """INFRA-46: o aceite pede alerta de worker parado e custo no painel."""

    def test_worker_parado_por_dois_minutos_gera_alerta(self):
        data = metrics()
        data["transcription_queue"].update(worker_age_seconds=120)
        report = evaluate(readiness(), data, configured_thresholds())
        self.assertEqual(report["status"], "critical")
        parado = next(item for item in report["checks"] if item["name"] == "worker_age_seconds")
        self.assertEqual(parado["state"], "critical")
        self.assertEqual(parado["observed"], 120)

    def test_falha_de_provedor_espera_amostra_minima(self):
        data = metrics()
        # Uma falha em duas tentativas é 50%, mas duas tentativas não dizem nada.
        data["dialogue"].update(turns=2, provider_failures=1)
        self.assertEqual(evaluate(readiness(), data, configured_thresholds())["status"], "ok")
        data["dialogue"].update(turns=10, provider_failures=5)
        self.assertEqual(evaluate(readiness(), data, configured_thresholds())["status"], "critical")

    def test_custo_do_dia_aparece_no_relatorio_sem_texto_de_aluno(self):
        data = metrics()
        data["dialogue"].update(cost_microusd=1_234)
        report = evaluate(readiness(), data, configured_thresholds())
        custo = next(
            item for item in report["checks"] if item["name"] == "dialogue_cost_microusd_today"
        )
        self.assertEqual(custo["observed"], 1_234)
        self.assertEqual(custo["state"], "ok")
        # O relatório inteiro é número, nome de check, responsável e ação.
        self.assertNotIn("transcript", repr(report))


class AssistBudgetTests(unittest.TestCase):
    def test_exact_budget_boundaries_for_both_periods(self):
        for period in ("daily", "monthly"):
            for cost, state in (
                (79, "ok"),
                (80, "warning"),
                (99, "warning"),
                (100, "critical"),
                (101, "critical"),
            ):
                with self.subTest(period=period, cost=cost):
                    data = metrics()
                    for window in data["assist_costs"].values():
                        window["cost_microusd"] = 0
                    data["assist_costs"][period]["cost_microusd"] = cost
                    report = evaluate(
                        readiness(),
                        data,
                        Thresholds(
                            assist_daily_budget_microusd=100,
                            assist_monthly_budget_microusd=100,
                        ),
                    )
                    check = next(
                        c for c in report["checks"] if c["name"] == f"assist_{period}_budget"
                    )
                    self.assertEqual(check["state"], state)
                    self.assertEqual(report["status"], state)

    def test_missing_budget_warns_instead_of_assuming_approval(self):
        report = evaluate(readiness(), metrics(), Thresholds())
        self.assertEqual(report["status"], "warning")
        self.assertTrue(
            all(c["state"] == "warning" for c in report["checks"] if c["name"].endswith("_budget"))
        )

    def test_missing_unknown_or_invalid_cost_does_not_pass(self):
        for change in (
            lambda d: d.pop("assist_costs"),
            lambda d: d["assist_costs"].pop("daily"),
            lambda d: d["assist_costs"]["monthly"].update(unknown_cost_reservations=1),
            lambda d: d["assist_costs"]["daily"].update(cost_microusd=None),
            lambda d: d["assist_costs"]["daily"].update(cost_microusd=-1),
            lambda d: d["assist_costs"]["daily"].update(cost_microusd=True),
        ):
            data = metrics()
            change(data)
            self.assertEqual(
                evaluate(readiness(), data, configured_thresholds())["status"],
                "critical",
            )

    def test_cli_budget_environment_and_warning_exit_code(self):
        env = {
            "OPERATIONS_TOKEN": "private-token",
            "OPERATIONS_ASSIST_DAILY_BUDGET_MICROUSD": "500",
            "OPERATIONS_ASSIST_MONTHLY_BUDGET_MICROUSD": "2000",
        }
        output = io.StringIO()
        with (
            patch.dict(os.environ, env, clear=True),
            patch("ops.observability_check.fetch", side_effect=[readiness(), metrics()]) as fetch,
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(main([]), 1)  # 400/500 = 80%, alerta sai para o cron.
            self.assertEqual(fetch.call_args_list[0].args[1], "/api/operations/readiness")
            self.assertEqual(fetch.call_args_list[0].kwargs, {"token": "private-token"})
        self.assertIn('"status": "warning"', output.getvalue())
        self.assertNotIn("private-token", output.getvalue())

    def test_invalid_budget_fails_before_network(self):
        for value in ("-1", "0", "1.5", "invalid"):
            with (
                patch.dict(
                    os.environ,
                    {
                        "OPERATIONS_TOKEN": "private-token",
                        "OPERATIONS_ASSIST_DAILY_BUDGET_MICROUSD": value,
                    },
                    clear=True,
                ),
                patch("ops.observability_check.fetch") as fetch,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main([]), 2)
                fetch.assert_not_called()
