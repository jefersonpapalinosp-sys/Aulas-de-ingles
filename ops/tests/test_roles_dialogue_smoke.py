"""Roteiro e Guiado exigem evidências completas e restauram o provedor local."""

import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from ops import roles_dialogue_smoke as smoke


class DialogueRolesSmokeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = self.enterContext(
            patch.dict(
                smoke.os.environ,
                {
                    "DATABASE_URL": "postgresql+asyncpg://synthetic@db:5432/aulas_roles_lab",
                    "DATABASE_PURPOSE": "runtime",
                },
            )
        )
        self.settings = SimpleNamespace(assisted_features_enabled=False, assist_dialogue_url=None)
        self.replace(smoke, "get_settings", return_value=self.settings)
        self.original_provider = smoke.assistance.call_dialogue_provider
        self.session = MagicMock()
        for name in ("scalar", "scalars", "flush", "refresh"):
            setattr(self.session, name, AsyncMock())
        self.session.scalar.return_value = 12
        self.session.scalars.return_value = MagicMock()
        self.session.scalars.return_value.one.return_value = SimpleNamespace(id=31)
        self.factory = self.replace(smoke, "get_sessionmaker")
        self.factory.return_value.return_value.__aenter__.return_value = self.session
        self.dispose = self.replace(smoke, "dispose_engine", new_callable=AsyncMock)
        self.create = self.replace(
            smoke.dialogue,
            "create_dialogue",
            new_callable=AsyncMock,
            side_effect=lambda *args, **kwargs: (SimpleNamespace(mode=kwargs["mode"]), None),
        )
        self.admit = self.replace(
            smoke.dialogue,
            "admit_turn",
            new_callable=AsyncMock,
            side_effect=lambda session, conversation, *args, **kwargs: (
                SimpleNamespace(state="completed" if conversation.mode == "script" else "pending"),
                None if conversation.mode == "script" else object(),
            ),
        )
        self.resolve = self.replace(smoke.dialogue, "resolve_turn", new_callable=AsyncMock)
        self.replace(smoke.dialogue, "lesson_for_dialogue", new_callable=AsyncMock)
        self.replace(smoke.dialogue, "brief_for_lesson", new_callable=AsyncMock)
        self.output = self.enterContext(redirect_stdout(io.StringIO()))

    def replace(self, owner, name, **kwargs):
        return self.enterContext(patch.object(owner, name, **kwargs))

    def assert_restored(self):
        self.dispose.assert_awaited_once()
        self.assertIs(smoke.assistance.call_dialogue_provider, self.original_provider)
        self.assertFalse(self.settings.assisted_features_enabled)
        self.assertIsNone(self.settings.assist_dialogue_url)

    def worker(self):
        self.env["DATABASE_PURPOSE"] = "worker"
        self.session.scalars.return_value.one.return_value = SimpleNamespace(
            id=1, lesson_id=31, user_id=42
        )
        turns = [
            SimpleNamespace(transcript="synthetic", check_details={"target_terms": ["term"]})
            for _ in range(12)
        ]
        self.session.scalars.return_value.all.return_value = turns
        self.session.scalar.side_effect = [24, 2]
        return turns

    async def test_runtime_creates_twelve_turns_per_mode_and_unique_retry_keys(self):
        await smoke.main()
        self.assertEqual(
            [c.kwargs["mode"] for c in self.create.await_args_list], ["script", "guided"]
        )
        self.assertEqual([c.args[2] for c in self.admit.await_args_list], list(range(1, 13)) * 2)
        self.assertEqual(len({c.kwargs["idempotency_key"] for c in self.admit.await_args_list}), 24)
        self.resolve.assert_not_awaited()
        self.assert_restored()

    async def test_runtime_refuses_wrong_turn_state(self):
        self.admit.side_effect = None
        self.admit.return_value = (SimpleNamespace(state="pending"), None)
        with self.assertRaises(AssertionError):
            await smoke.main()
        self.assertEqual(self.admit.await_count, 1)
        self.assert_restored()
        self.assertEqual(self.output.getvalue(), "")

    async def test_worker_resolves_all_turns_before_verifying_evidence_and_review(self):
        turns = self.worker()
        await smoke.main()
        self.assertEqual([c.args[1] for c in self.resolve.await_args_list], turns)
        self.assertEqual(self.session.refresh.await_count, 12)
        self.assertEqual(self.session.scalar.await_count, 2)
        self.create.assert_not_awaited()
        self.assert_restored()

    async def test_worker_refuses_incomplete_conversation(self):
        self.worker().pop()
        with self.assertRaises(AssertionError):
            await smoke.main()
        self.resolve.assert_not_awaited()
        self.assert_restored()

    async def test_worker_requires_target_term_details(self):
        self.worker()[0].check_details = {"target_terms": []}
        with self.assertRaises(AssertionError):
            await smoke.main()
        self.session.scalar.assert_not_awaited()
        self.assert_restored()
        self.assertEqual(self.output.getvalue(), "")

    async def test_missing_evidence_or_review_cannot_report_success(self):
        self.worker()
        for counts in ([23, 2], [24, 1]):
            self.session.scalar.side_effect = counts
            with self.assertRaises(AssertionError):
                await smoke.main()
        self.assertEqual(self.output.getvalue(), "")
        self.assertIs(smoke.assistance.call_dialogue_provider, self.original_provider)

    async def test_connection_failure_restores_global_configuration(self):
        self.factory.return_value.return_value.__aenter__.side_effect = RuntimeError("connection")
        with self.assertRaisesRegex(RuntimeError, "connection"):
            await smoke.main()
        self.assert_restored()

    async def test_invalid_target_or_role_cannot_replace_provider_or_connect(self):
        for field, value in (
            ("DATABASE_URL", "postgresql://synthetic@db:5432/study"),
            ("DATABASE_PURPOSE", "migrator"),
        ):
            with patch.dict(smoke.os.environ, {field: value}), self.assertRaises(AssertionError):
                await smoke.main()
        self.factory.assert_not_called()
        self.assertIs(smoke.assistance.call_dialogue_provider, self.original_provider)
        self.assertFalse(self.settings.assisted_features_enabled)

    def test_synthetic_provider_has_explicit_known_cost(self):
        result = smoke.provider()
        self.assertTrue(result.cost_known)
        self.assertEqual(result.cost_microusd, 1)
        self.assertEqual(result.raw["hints"], [])
