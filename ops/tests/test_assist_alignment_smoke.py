"""HTTP e limpeza do smoke com sessões e transporte simulados, sem banco ou provedor."""

import io
import json
import unittest
from contextlib import ExitStack, contextmanager, redirect_stdout
from email.message import Message
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.error import HTTPError, URLError

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import Delete

from ops import assist_alignment_smoke as smoke

ENV = {
    "APP_ENV": "dev",
    "DATABASE_PURPOSE": "",
    "ASSISTED_FEATURES_ENABLED": "false",
    "DATABASE_URL": "postgresql+asyncpg://synthetic:unused@assist-check-db/aulas_ingles_restore",
}


class AssistSmokeTransportTests(unittest.TestCase):
    def test_json_transport_uses_loopback_timeout_and_given_token(self):
        opener, reply = MagicMock(), MagicMock()
        reply.__enter__.return_value = reply
        reply.status, reply.headers = 200, Message()
        reply.read.return_value = b'{"revision":1}'
        opener.open.return_value = reply
        status, _, body = smoke.request(
            opener, "/api/probe", {"Authorization": "Bearer synthetic"}, {"value": 3}, "PUT"
        )
        self.assertEqual((status, body), (200, {"revision": 1}))
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8000/api/probe")
        self.assertEqual(request.method, "PUT")
        self.assertEqual(request.get_header("Authorization"), "Bearer synthetic")
        self.assertEqual(json.loads(request.data), {"value": 3})
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 30)
        reply.__exit__.assert_called_once()

    def test_http_error_keeps_status_for_unauthenticated_check_and_closes_body(self):
        payload = io.BytesIO(b'{"detail":"synthetic"}')
        error = HTTPError("http://127.0.0.1/api/probe", 401, "unauthorized", Message(), payload)
        opener = MagicMock()
        opener.open.side_effect = error
        status, _, body = smoke.request(opener, "/api/probe")
        self.assertEqual(status, 401)
        self.assertEqual(body, {"detail": "synthetic"})
        self.assertTrue(payload.closed)
        self.assertIsNone(opener.open.call_args.args[0].get_header("Authorization"))

    def test_malformed_shapes_are_refused_without_content_in_message(self):
        for value in (None, [], "private-value", 2, {1: "wrong"}):
            with self.assertRaises(ValueError) as raised:
                smoke.json_object(value)
            self.assertNotIn("private-value", str(raised.exception))
        for value in (None, {}, [None], ["private-value"]):
            with self.assertRaises(ValueError):
                smoke.object_list(value)


class AssistSmokeCleanupTests(unittest.IsolatedAsyncioTestCase):
    @contextmanager
    def fixture(self, *, http_failure=False, malformed=False, cleanup_failure=False):
        users, deleted = [], []
        engine = MagicMock()

        async def flush():
            users[-1].id = 123

        async def execute(statement):
            params = statement.compile().params
            self.assertIn(users[0].email, params.values())
            result = MagicMock()
            if isinstance(statement, Delete):
                self.assertIn(123, params.values())
                self.assertEqual(len(params), 2)
                self.assertIn(" AND ", str(statement))
                self.assertIn("RETURNING app_user.id", str(statement))
                deleted.append(statement)
                result.scalar_one.return_value = -1 if cleanup_failure else 123
            else:
                result.first.return_value = None
            return result

        def session_factory(*args, **kwargs):
            session = MagicMock(spec=AsyncSession)
            session.__aenter__.return_value = session
            session.add.side_effect = users.append
            session.flush.side_effect = flush
            session.execute.side_effect = execute
            return session

        headers = Message()
        headers["cache-control"] = "private, no-store"
        payloads = [
            (401, headers, {}),
            (200, headers, {}),
            (200, headers, []),
            (200, headers, []),
            (200, headers, [] if malformed else {"writing_prompts": [{"id": 7}]}),
            (200, headers, {"revision": 1}),
            (200, headers, {"analysis_mode": "deterministic"}),
            (200, headers, [{}]),
            (200, headers, {"used_today": 0}),
            (200, headers, {"reserved_today": 1}),
            (200, headers, {"consumed_today": 1, "reserved_today": 0, "cost_incomplete": False}),
        ]
        output = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(patch.dict(smoke.os.environ, ENV))
            stack.enter_context(patch("app.db.session.get_engine", return_value=engine))
            dispose = stack.enter_context(
                patch("app.db.session.dispose_engine", new_callable=AsyncMock)
            )
            stack.enter_context(
                patch("sqlalchemy.ext.asyncio.AsyncSession", side_effect=session_factory)
            )
            stack.enter_context(
                patch("app.core.security.criar_token", return_value=("synthetic", None))
            )
            stack.enter_context(
                patch(
                    "app.services.assist_quota.reserve",
                    new_callable=AsyncMock,
                    return_value=(SimpleNamespace(id=9), True),
                )
            )
            consume = stack.enter_context(
                patch(
                    "app.services.assist_quota.consume", new_callable=AsyncMock, return_value=True
                )
            )
            cost = stack.enter_context(
                patch("app.services.assist_quota.record_cost", new_callable=AsyncMock)
            )
            request = stack.enter_context(
                patch.object(
                    smoke,
                    "request",
                    side_effect=URLError("private-value") if http_failure else payloads,
                )
            )
            stack.enter_context(redirect_stdout(output))
            yield SimpleNamespace(
                engine=engine,
                dispose=dispose,
                deleted=deleted,
                output=output,
                request=request,
                consume=consume,
                cost=cost,
            )

    async def test_success_checks_quota_cleans_exact_account_and_disposes(self):
        with self.fixture() as state:
            await smoke.smoke()
            self.assertEqual(
                json.loads(state.output.getvalue()),
                {
                    "verified": True,
                    "mode": "http-clone",
                    "checks": 11,
                    "synthetic_user_remaining": 0,
                    "provider_calls": 0,
                },
            )
            self.assertEqual(len(state.deleted), 1)
            state.dispose.assert_awaited_once_with()
            self.assertEqual(state.request.call_count, 11)
            self.assertEqual(state.consume.await_args.args[1], 9)
            self.assertEqual(state.cost.await_args.args[1:], (9, 0))

    async def test_http_failure_still_cleans_account_and_disposes_without_success(self):
        with self.fixture(http_failure=True) as state:
            with self.assertRaises(URLError):
                await smoke.smoke()
            self.assertEqual(len(state.deleted), 1)
            state.dispose.assert_awaited_once_with()
            self.assertEqual(state.output.getvalue(), "")

    async def test_malformed_lesson_still_cleans_account_without_quota_use(self):
        with self.fixture(malformed=True) as state:
            with self.assertRaises(ValueError):
                await smoke.smoke()
            self.assertEqual(len(state.deleted), 1)
            state.consume.assert_not_awaited()
            state.dispose.assert_awaited_once_with()
            self.assertEqual(state.output.getvalue(), "")

    async def test_cleanup_failure_disposes_and_never_reports_success(self):
        with self.fixture(cleanup_failure=True) as state:
            with self.assertRaises(AssertionError):
                await smoke.smoke()
            state.dispose.assert_awaited_once_with()
            self.assertEqual(state.output.getvalue(), "")

    async def test_connection_failure_still_disposes_engine(self):
        with self.fixture() as state:
            state.engine.connect.return_value.__aenter__.side_effect = RuntimeError("unavailable")
            with self.assertRaises(RuntimeError):
                await smoke.smoke()
            self.assertEqual(state.deleted, [])
            state.dispose.assert_awaited_once_with()
            self.assertEqual(state.output.getvalue(), "")

    async def test_invalid_environment_stops_before_engine(self):
        with self.fixture() as state, patch.dict(smoke.os.environ, {"APP_ENV": "prod"}):
            with self.assertRaises(ValueError):
                await smoke.smoke()
            state.engine.connect.assert_not_called()
            state.dispose.assert_not_awaited()
