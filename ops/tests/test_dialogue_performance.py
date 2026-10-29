"""Contratos do benchmark sem carregar contas ou executar consultas em banco."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.db.test_safety import UnsafeTestDatabase

from ops import dialogue_performance as performance


class DialoguePerformanceTests(unittest.TestCase):
    def test_page_contract_preserves_order_and_cursor(self):
        self.assertEqual(performance.page_ids({"items": [], "next_cursor": None}), ([], None))
        self.assertEqual(
            performance.page_ids({"items": [{"id": 3}, {"id": 1}], "next_cursor": "next"}),
            ([3, 1], "next"),
        )

    def test_page_contract_rejects_malformed_ids_and_missing_cursor(self):
        for value in (
            None,
            [],
            {"items": {}},
            {"items": []},
            *(
                {"items": [{"id": identity}], "next_cursor": None}
                for identity in (None, True, False, -1, 0, 1.0, "1")
            ),
            *({"items": [], "next_cursor": cursor} for cursor in (True, 1, "", [])),
            {"items": [None], "next_cursor": None},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                performance.page_ids(value)

    def test_samples_outside_limits_stop_before_environment_or_database(self):
        for samples in (0, 9, 201):
            with (
                patch.object(performance.sys, "argv", ["benchmark", "--samples", str(samples)]),
                patch("app.db.test_safety.configure_test_environment") as configure,
                patch.object(performance, "run", new_callable=AsyncMock) as run,
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                performance.main()
            self.assertEqual(raised.exception.code, 2)
            configure.assert_not_called()
            run.assert_not_called()

    def test_unsafe_environment_does_not_run_or_write_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            with (
                patch.object(performance.sys, "argv", ["benchmark", "--output", str(output)]),
                patch(
                    "app.db.test_safety.configure_test_environment",
                    side_effect=UnsafeTestDatabase("synthetic refusal"),
                ),
                patch.object(performance, "run", new_callable=AsyncMock) as run,
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                performance.main()
            self.assertEqual(raised.exception.code, 2)
            run.assert_not_called()
            self.assertFalse(output.exists())

    def test_cli_writes_report_and_signals_failed_latency_target(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            for passed in (False, True):
                report = {"p95_pass": passed, "datasets": {"1000": {"p95_pass": passed}}}
                with (
                    patch.object(performance.sys, "argv", ["benchmark", "--output", str(output)]),
                    patch("app.db.test_safety.configure_test_environment"),
                    patch.object(
                        performance, "run", new_callable=AsyncMock, return_value=report
                    ) as run,
                ):
                    if passed:
                        performance.main()
                    else:
                        with self.assertRaises(SystemExit) as raised:
                            performance.main()
                        self.assertEqual(raised.exception.code, 1)
                run.assert_awaited_once_with(30)
                self.assertEqual(json.loads(output.read_text()), report)
            stdout = io.StringIO()
            with (
                patch.object(performance.sys, "argv", ["benchmark"]),
                patch("app.db.test_safety.configure_test_environment"),
                patch.object(performance, "run", new_callable=AsyncMock, return_value=report),
                redirect_stdout(stdout),
            ):
                performance.main()
            self.assertEqual(json.loads(stdout.getvalue()), report)

    def test_history_explain_compiles_with_asyncpg_dialect_without_connection(self):
        from app.pagination import TimeIdCursor
        from app.services.dialogue_history import history_query
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine("postgresql+asyncpg://synthetic:unused@127.0.0.1:1/unused")
        query = history_query(123, 50, TimeIdCursor(datetime(2026, 1, 1, tzinfo=UTC), 456))
        compiled = str(
            query.compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True})
        )
        self.assertIn("speaking_dialogue.user_id = 123", compiled)
        self.assertIn("LIMIT 51", compiled)
        self.assertIn("speaking_dialogue.started_at DESC, speaking_dialogue.id DESC", compiled)
        self.assertNotIn("$1", compiled)
