import unittest

from ops.observability_check import Thresholds, _url, evaluate


def readiness(schema="compatible"):
    return {"status": "ok" if schema == "compatible" else "degraded", "schema": schema}


def metrics():
    return {
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
    }


class ObservabilityGateTests(unittest.TestCase):
    def test_healthy_snapshot_passes_with_fixed_owners_and_actions(self):
        report = evaluate(readiness(), metrics(), Thresholds())
        self.assertEqual(report["status"], "ok")
        self.assertTrue(
            all(item["owner"] and item["action"] for item in report["checks"])
        )

    def test_each_threshold_can_block_release(self):
        mutations = [
            ("schema", lambda ready, data: ready.update(readiness("incompatible"))),
            (
                "error",
                lambda ready, data: data["requests"].update(responses_5xx_total=10),
            ),
            (
                "queue",
                lambda ready, data: data["transcription_queue"].update(
                    oldest_queued_seconds=301
                ),
            ),
            (
                "worker",
                lambda ready, data: data["transcription_queue"].update(
                    worker_age_seconds=None
                ),
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
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                ready, data = readiness(), metrics()
                mutate(ready, data)
                report = evaluate(ready, data, Thresholds())
                self.assertEqual(report["status"], "critical")
                self.assertIn("critical", {item["state"] for item in report["checks"]})

    def test_error_rate_waits_for_minimum_sample(self):
        data = metrics()
        data["requests"].update(requests_total=2, responses_5xx_total=2)
        report = evaluate(readiness(), data, Thresholds())
        error = next(
            item for item in report["checks"] if item["name"] == "request_error_rate"
        )
        self.assertEqual(error["state"], "ok")

    def test_url_rejects_credentials_query_and_non_http(self):
        for value in ("file:///tmp/x", "http://user:pass@host", "http://host?token=x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _url(value, "/api/health")
        self.assertEqual(
            _url("https://example.test/", "/api/health"),
            "https://example.test/api/health",
        )
