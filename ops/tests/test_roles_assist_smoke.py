"""Contabilidade de escrita e transcrição nos dois papéis, sem banco externo."""

import io
import unittest
from contextlib import ExitStack, redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from ops import roles_assist_smoke as smoke


class AssistRolesSmokeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = self.enterContext(ExitStack())
        self.env = self.enterContext(
            patch.dict(
                smoke.os.environ,
                {
                    "DATABASE_URL": "postgresql+asyncpg://synthetic@db:5432/aulas_roles_lab",
                    "DATABASE_PURPOSE": "runtime",
                },
            )
        )
        self.session = MagicMock()
        self.session.scalar = AsyncMock(return_value=42)
        self.factory = self.enterContext(patch.object(smoke, "get_sessionmaker"))
        self.factory.return_value.return_value.__aenter__.return_value = self.session
        self.dispose = self.enterContext(
            patch.object(smoke, "dispose_engine", new_callable=AsyncMock)
        )
        self.reserve = self.enterContext(
            patch.object(
                smoke.assist_quota,
                "reserve",
                new_callable=AsyncMock,
                return_value=(SimpleNamespace(id=7), True),
            )
        )
        self.consume = self.enterContext(
            patch.object(smoke.assist_quota, "consume", new_callable=AsyncMock, return_value=True)
        )
        self.cost = self.enterContext(
            patch.object(smoke.assist_quota, "record_cost", new_callable=AsyncMock)
        )
        self.output = self.enterContext(redirect_stdout(io.StringIO()))

    async def test_runtime_consumes_writing_and_leaves_transcription_reserved(self):
        await smoke.main()
        self.assertEqual(self.reserve.await_count, 2)
        writing, transcription = self.reserve.await_args_list
        self.assertEqual(writing.args[1], 42)
        self.assertTrue(writing.args[2].startswith("roles-writing-"))
        self.assertEqual(writing.args[4], "writing")
        self.assertTrue(transcription.args[2].startswith("roles-queue-"))
        self.assertEqual(transcription.args[4], "transcription")
        self.consume.assert_awaited_once_with(self.session, 7)
        self.cost.assert_awaited_once_with(self.session, 7, 1)
        self.dispose.assert_awaited_once()

    async def test_worker_only_consumes_reserved_queue_entry(self):
        self.env["DATABASE_PURPOSE"] = "worker"
        self.session.scalar.return_value = SimpleNamespace(id=9)
        await smoke.main()
        query = self.session.scalar.call_args.args[0].compile()
        self.assertIn("roles-queue-%", query.params.values())
        self.assertIn("reserved", query.params.values())
        self.reserve.assert_not_awaited()
        self.consume.assert_awaited_once_with(self.session, 9)
        self.cost.assert_awaited_once_with(self.session, 9, 2)

    async def test_invalid_target_or_role_never_opens_session(self):
        for field, value in (
            ("DATABASE_URL", "postgresql://synthetic@db:5432/study"),
            ("DATABASE_PURPOSE", "migrator"),
        ):
            with patch.dict(smoke.os.environ, {field: value}), self.assertRaises(AssertionError):
                await smoke.main()
        self.factory.assert_not_called()

    async def test_missing_user_or_reservation_never_records_cost(self):
        self.session.scalar.return_value = None
        for purpose in ("runtime", "worker"):
            self.env["DATABASE_PURPOSE"] = purpose
            with self.assertRaises(AssertionError):
                await smoke.main()
        self.reserve.assert_not_awaited()
        self.cost.assert_not_awaited()
        self.assertEqual(self.dispose.await_count, 2)
        self.assertEqual(self.output.getvalue(), "")

    async def test_failed_consumption_stops_cost_and_queue_creation(self):
        self.consume.return_value = False
        with self.assertRaises(AssertionError):
            await smoke.main()
        self.assertEqual(self.reserve.await_count, 1)
        self.cost.assert_not_awaited()
        self.dispose.assert_awaited_once()
        self.assertEqual(self.output.getvalue(), "")

    async def test_failed_ledger_write_exits_transaction_and_disposes(self):
        self.cost.side_effect = RuntimeError("synthetic ledger failure")
        with self.assertRaisesRegex(RuntimeError, "ledger"):
            await smoke.main()
        self.session.begin.return_value.__aexit__.assert_awaited_once()
        self.dispose.assert_awaited_once()
        self.assertEqual(self.output.getvalue(), "")
