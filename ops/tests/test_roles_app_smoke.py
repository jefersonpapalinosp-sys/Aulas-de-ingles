"""Contratos HTTP do smoke de papéis, com transporte e subprocessos simulados."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from ops import roles_app_smoke as smoke

LAB_ENV = {
    "DATABASE_PURPOSE": "runtime",
    "DATABASE_URL": "postgresql+asyncpg://synthetic@db:5432/aulas_roles_lab",
}


class RolesAppSmokeTests(unittest.TestCase):
    def test_request_uses_loopback_json_token_and_timeout(self):
        reply = MagicMock()
        reply.__enter__.return_value = io.BytesIO(b'{"id":1}')
        with patch.object(smoke.urllib.request, "urlopen", return_value=reply) as urlopen:
            result = smoke.object_request("/probe", {"value": 42}, "POST", "synthetic-token")
        self.assertEqual(result, {"id": 1})
        sent = urlopen.call_args.args[0]
        self.assertEqual(sent.full_url, "http://127.0.0.1:8000/api/probe")
        self.assertEqual(sent.method, "POST")
        self.assertEqual(sent.get_header("Authorization"), "Bearer synthetic-token")
        self.assertEqual(json.loads(sent.data), {"value": 42})
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)

    def test_shapes_distinguish_objects_and_lists(self):
        for value in (None, [], "private-value", 3, {1: "invalid-key"}):
            with self.subTest(value=value), self.assertRaises(ValueError) as raised:
                smoke.as_object(value)
            self.assertNotIn("private-value", str(raised.exception))
        for value in ({}, None, [None], [[{}]], ["private-value"]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                smoke.object_list(value)
        self.assertEqual(smoke.object_list([{"id": 1}]), [{"id": 1}])
        self.assertEqual(smoke.object_list([]), [])
        with patch.object(smoke, "request", return_value=[]), self.assertRaises(ValueError):
            smoke.object_request("/health")

    def test_wrong_environment_stops_before_starting_server(self):
        for environment in (
            {**LAB_ENV, "DATABASE_PURPOSE": "worker"},
            {**LAB_ENV, "DATABASE_URL": "postgresql+asyncpg://synthetic@db:5432/study"},
        ):
            with (
                patch.dict(smoke.os.environ, environment),
                patch.object(smoke.subprocess, "Popen") as server,
                self.assertRaises(AssertionError),
            ):
                smoke.main()
            server.assert_not_called()

    def test_unavailable_server_has_bounded_retry_and_is_stopped(self):
        output = io.StringIO()
        with (
            patch.dict(smoke.os.environ, LAB_ENV),
            patch.object(smoke.subprocess, "Popen") as server,
            patch.object(smoke, "request", side_effect=URLError("synthetic")) as request,
            patch.object(smoke.time, "sleep"),
            redirect_stdout(output),
            self.assertRaisesRegex(RuntimeError, "não ficou pronta"),
        ):
            smoke.main()
        self.assertEqual(request.call_count, 100)
        server.return_value.terminate.assert_called_once_with()
        server.return_value.wait.assert_called_once_with(timeout=10)
        self.assertEqual(output.getvalue(), "")

    def test_bad_registration_token_stops_before_lesson_or_writes(self):
        for token in (None, [], 1, ""):
            with (
                patch.dict(smoke.os.environ, LAB_ENV),
                patch.object(smoke.subprocess, "Popen") as server,
                patch.object(
                    smoke, "request", side_effect=[{"db": "up"}, {"access_token": token}]
                ) as request,
                self.assertRaises(AssertionError),
            ):
                smoke.main()
            self.assertEqual(request.call_count, 2)
            server.return_value.terminate.assert_called_once_with()

    def test_complete_flow_and_replay_disagreement(self):
        for divergent in (False, True):
            calls = []
            grade_count = 0

            def request(
                path, payload=None, method="GET", token=None, *, calls=calls, divergent=divergent
            ):
                nonlocal grade_count
                calls.append((path, payload, method, token))
                if path not in {"/health", "/auth/register", "/lessons/31"}:
                    self.assertEqual(token, "synthetic-token")
                if path.endswith("/grade"):
                    grade_count += 1
                    return {"id": 1, "revision": grade_count if divergent else 1}
                return {
                    "/health": {"db": "up"},
                    "/auth/register": {"access_token": "synthetic-token"},
                    "/lessons/31": {
                        "id": 31, "exercises": [{"id": 1}], "media": [{"id": 2}],
                        "writing_prompts": [{"id": 3}], "vocab": [{"id": 4}],
                    },
                    "/exercises/1/attempt": {"attempt_id": 5},
                    "/me/history/exercise/5/content": {
                        "status": "available", "content": {
                            "source_id": 1, "editorial_identity_contract": "explicit_uuid_v1",
                            "editorial_key": "00000000-0000-0000-0000-000000000001",
                        },
                    },
                    "/me/activity/sessions": {"session_id": "synthetic"},
                    "/me/activity/events": {"credited_ms": 1},
                    "/media/2/position": {"revision": 1},
                    "/me/today": {"time_measurement": "active_intervals_v1"},
                    "/me/export": {"activity_events": [{}]},
                    "/writing/prompts/3/draft": payload,
                    "/writing/prompts/3/versions": {},
                    "/writing/prompts/3/feedback": {"id": 6},
                    "/me/history/writing/6/content": {"status": "available"},
                    "/assist/status": {"reserved_today": 0},
                    "/auth/me": {},
                    "/review/items/4": {},
                    "/review/due": [{"id": 7, "revision": 0}],
                }[path]

            output = io.StringIO()
            with (
                self.subTest(divergent=divergent),
                patch.dict(smoke.os.environ, LAB_ENV),
                patch.object(smoke.subprocess, "Popen") as server,
                patch.object(smoke, "request", side_effect=request),
                redirect_stdout(output),
            ):
                if divergent:
                    with self.assertRaises(AssertionError):
                        smoke.main()
                else:
                    smoke.main()
            events = [call for call in calls if call[0] == "/me/activity/events"]
            grades = [call for call in calls if call[0] == "/review/7/grade"]
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0], events[1])
            self.assertEqual(len(grades), 2)
            self.assertEqual(grades[0], grades[1])
            self.assertIn("127.0.0.1", server.call_args.args[0])
            server.return_value.terminate.assert_called_once_with()
            server.return_value.wait.assert_called_once_with(timeout=10)
            self.assertEqual("aprovados" in output.getvalue(), not divergent)
