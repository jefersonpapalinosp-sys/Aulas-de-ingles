"""Ensaios editoriais preservam o laboratório mesmo quando recibos divergem."""

import io
import unittest
from contextlib import ExitStack, contextmanager, redirect_stdout
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from ops import roles_archive_smoke as archive
from ops import roles_reorder_smoke as reorder


class EditorialSmokeTests(unittest.IsolatedAsyncioTestCase):
    @contextmanager
    def fixture(self, module):
        flag = "editorial_archive_enabled" if module is archive else "editorial_reorder_enabled"
        settings = SimpleNamespace(
            database_purpose="migrator",
            app_env="dev",
            database_url="postgresql+asyncpg://synthetic@db:5432/aulas_roles_lab",
            **{flag: False},
        )
        connection = MagicMock()
        connection.scalar = AsyncMock(side_effect=[7, 7])
        connection.rollback = AsyncMock()
        engine = MagicMock()
        engine.connect.return_value.__aenter__.return_value = connection
        receipt = {
            "db_actor": "aulas_owner",
            "db_login": "aulas_migrator",
            "replayed": False,
            "after_status": "archived",
            "changed_entities": 2,
        }
        plan = {
            "catalog_sha256": "catalog-hash",
            "database": "aulas_roles_lab",
            "allowed": True,
            "apply_available": False,
            "plan_sha256": "plan-hash",
        }
        with ExitStack() as stack:

            def replace(name, **kwargs):
                return stack.enter_context(patch.object(module, name, **kwargs))

            replace("get_settings", return_value=settings)
            get_engine = replace("get_engine", return_value=engine)
            factory = replace("async_sessionmaker")
            dispose = replace("dispose_engine", new_callable=AsyncMock)
            apply = replace(
                "archive_unit" if module is archive else "apply_editorial_reorder",
                new_callable=AsyncMock,
                side_effect=[receipt, {**receipt, "replayed": True}],
            )
            preview = replace(
                "collect_unit_archive" if module is archive else "preview_editorial_reorder",
                new_callable=AsyncMock,
                return_value=plan,
            )
            if module is reorder:
                replace("candidate", return_value=object())
                replace("get_sessionmaker")
            yield SimpleNamespace(**locals())
        self.assertFalse(getattr(settings, flag))

    async def test_success_reuses_operation_and_rolls_back_savepoints(self):
        for module in (archive, reorder):
            with self.subTest(module=module.__name__), self.fixture(module) as f:
                with redirect_stdout(io.StringIO()) as output:
                    await module.main()
                first, retry = f.apply.await_args_list
                self.assertEqual(first.kwargs, retry.kwargs)
                self.assertEqual(first.kwargs["confirm_database"], "aulas_roles_lab")
                self.assertTrue(first.kwargs["operation_key"])
                self.assertEqual(f.connection.rollback.await_count, 2)
                self.assertEqual(f.connection.scalar.await_count, 2)
                self.assertEqual(
                    f.factory.call_args.kwargs["join_transaction_mode"], "create_savepoint"
                )
                f.dispose.assert_awaited_once_with()
                self.assertIn("aprovados", output.getvalue())

    async def test_wrong_role_environment_or_database_stops_before_engine(self):
        for module in (archive, reorder):
            for name, value in (
                ("database_purpose", "runtime"),
                ("app_env", "prod"),
                ("database_url", "postgresql://synthetic@db:5432/study"),
            ):
                with self.subTest(module=module.__name__, field=name), self.fixture(module) as f:
                    setattr(f.settings, name, value)
                    with self.assertRaises(AssertionError):
                        await module.main()
                    f.get_engine.assert_not_called()
                    f.preview.assert_not_awaited()
                    f.apply.assert_not_awaited()

    async def test_bad_identity_or_replay_still_rolls_back_without_success(self):
        for module in (archive, reorder):
            for field, value in (
                ("db_actor", "unexpected"),
                ("db_login", "unexpected"),
                ("replayed", True),
                ("replay", False),
            ):
                with self.subTest(module=module.__name__, field=field), self.fixture(module) as f:
                    first, retry = dict(f.receipt), {**f.receipt, "replayed": True}
                    (retry if field == "replay" else first)[
                        "replayed" if field == "replay" else field
                    ] = value
                    f.apply.side_effect = [first, retry]
                    with (
                        redirect_stdout(io.StringIO()) as output,
                        self.assertRaises(AssertionError),
                    ):
                        await module.main()
                    self.assertEqual(f.connection.rollback.await_count, 2)
                    f.dispose.assert_awaited_once()
                    self.assertEqual(output.getvalue(), "")

    async def test_service_failure_rolls_back_and_count_drift_fails(self):
        for module in (archive, reorder):
            for service_error in (False, True):
                with (
                    self.subTest(module=module.__name__, service_error=service_error),
                    self.fixture(module) as f,
                ):
                    if service_error:
                        f.apply.side_effect = RuntimeError("synthetic failure")
                    else:
                        f.connection.scalar.side_effect = [7, 8]
                    with (
                        redirect_stdout(io.StringIO()) as output,
                        self.assertRaises(RuntimeError if service_error else AssertionError),
                    ):
                        await module.main()
                    self.assertEqual(f.connection.rollback.await_count, 2)
                    f.dispose.assert_awaited_once()
                    self.assertEqual(output.getvalue(), "")

    async def test_connection_and_preview_failures_dispose_engine(self):
        for module in (archive, reorder):
            with self.fixture(module) as f:
                f.engine.connect.return_value.__aenter__.side_effect = RuntimeError("connection")
                with self.assertRaisesRegex(RuntimeError, "connection"):
                    await module.main()
                f.dispose.assert_awaited_once()
        with self.fixture(reorder) as f:
            f.plan["allowed"] = False
            with self.assertRaises(AssertionError):
                await reorder.main()
            f.apply.assert_not_awaited()
            f.dispose.assert_awaited_once()

    def test_candidate_only_swaps_two_exercises_without_mutating_seed(self):
        courses = [{"slug": "synthetic"}]
        lessons = [
            {"exercises": [{"position": 1, "text": "first"}, {"position": 2, "text": "second"}]}
        ]
        original = deepcopy(lessons)
        with (
            patch.object(reorder.seed, "load_course_seed", return_value=courses),
            patch.object(reorder.seed, "load_seed", return_value=lessons),
            patch.object(reorder, "seed_graph") as graph,
        ):
            reorder.candidate()
        self.assertEqual(lessons, original)
        candidate = graph.call_args.args[1][0]
        self.assertEqual(
            candidate["exercises"],
            [{"position": 2, "text": "first"}, {"position": 1, "text": "second"}],
        )
        self.assertEqual(candidate["content_version"], 2)
        self.assertEqual(candidate["editorial_status"], "reviewed")
