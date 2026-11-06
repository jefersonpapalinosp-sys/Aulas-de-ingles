import io
import json
import ssl
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from ops.public_probe import MAX_LATENCY_MS, TIMEOUT_SECONDS, evaluate, fetch, public_url


def corpo(status="ok", schema="compatible"):
    return {"status": status, "schema": schema}


class PublicProbeTests(unittest.TestCase):
    def test_fetch_identifica_probe_e_preserva_validacao_tls_e_timeout(self):
        url = public_url("https://aulas.exemplo.test")
        response = MagicMock()
        response.status = 200
        response.headers = {"Server": "cloudflare"}
        response.read.return_value = json.dumps(corpo()).encode()
        response.__enter__.return_value = response
        with patch("ops.public_probe.urllib.request.urlopen", return_value=response) as opener:
            report = evaluate(*fetch(url))
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, url)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("User-agent"), "Aulas-Public-Probe/1.0")
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(opener.call_args.kwargs["timeout"], TIMEOUT_SECONDS)
        context = opener.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        response.read.assert_called_once_with(100_001)
        self.assertEqual(report["status"], "ok")

    def test_fetch_com_identidade_explicita_nao_ignora_bloqueio_http(self):
        url = public_url("https://aulas.exemplo.test")
        blocked = urllib.error.HTTPError(
            url, 403, "Forbidden", {"Server": "cloudflare"},
            io.BytesIO(json.dumps(corpo()).encode()),
        )
        with patch("ops.public_probe.urllib.request.urlopen", side_effect=blocked):
            report = evaluate(*fetch(url))
        self.assertEqual(report["status"], "critical")
        status_probe = next(
            item for item in report["probes"] if item["name"] == "health_status_code"
        )
        self.assertEqual(status_probe["observed"], 403)
        self.assertEqual(status_probe["state"], "critical")

    def test_dominio_saudavel_passa_com_acao_em_cada_sonda(self):
        report = evaluate(200, corpo(), "nginx", 120)
        self.assertEqual(report["status"], "ok")
        self.assertTrue(all(item["action"] for item in report["probes"]))

    def test_cada_sonda_pode_reprovar_sozinha(self):
        casos = {
            "status": (503, corpo(), "nginx", 120),
            "payload": (200, corpo(schema="incompatible"), "nginx", 120),
            "versao-na-borda": (200, corpo(), "nginx/1.30.6", 120),
            "latencia": (200, corpo(), "nginx", MAX_LATENCY_MS + 1),
        }
        for nome, argumentos in casos.items():
            with self.subTest(nome=nome):
                self.assertEqual(evaluate(*argumentos)["status"], "critical")

    def test_resposta_sem_json_nao_passa_por_saudavel(self):
        self.assertEqual(evaluate(200, {}, "nginx", 10)["status"], "critical")

    def test_url_exige_https_e_recusa_credencial(self):
        self.assertEqual(
            public_url("https://aulas.exemplo.test"), "https://aulas.exemplo.test/api/health"
        )
        for invalida in (
            "http://aulas.exemplo.test",
            "https://u:s@aulas.exemplo.test",
            "https://aulas.exemplo.test?debug=1",
            "https://aulas.exemplo.test#frag",
            "ftp://aulas.exemplo.test",
            "aulas.exemplo.test",
        ):
            with self.subTest(url=invalida), self.assertRaises(ValueError):
                public_url(invalida)

    def test_relatorio_nao_carrega_url_nem_corpo(self):
        report = evaluate(
            200, {"status": "ok", "schema": "compatible", "extra": "segredo"}, "nginx", 10
        )
        texto = repr(report)
        self.assertNotIn("segredo", texto)
        self.assertNotIn("aulas.exemplo.test", texto)

    def test_detalhes_internos_no_health_publico_reprovam_sem_refletir_valores(self):
        for field in ("version", "env", "schema_current", "schema_required"):
            with self.subTest(field=field):
                report = evaluate(200, {**corpo(), field: "private-value"}, "nginx", 10)
                self.assertEqual(report["status"], "critical")
                self.assertNotIn("private-value", repr(report))
