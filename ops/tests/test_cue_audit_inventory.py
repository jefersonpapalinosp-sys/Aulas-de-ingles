import unittest

from ops.cue_audit_inventory import inventory


def lesson():
    return {
        "course_slug": "test-course",
        "number": 3,
        "content_version": 2,
        "media": [
            {
                "position": 1,
                "editorial_key": "media-key",
                "cues": [
                    {
                        "position": 1,
                        "editorial_key": "cue-key",
                        "start_seconds": 1.0,
                        "end_seconds": 2.0,
                    }
                ],
            }
        ],
    }


class CueAuditInventoryTests(unittest.TestCase):
    def test_every_cue_is_individually_pending_by_default(self):
        report = inventory([lesson()], {"schema_version": 1, "decisions": {}})
        self.assertEqual(report["summary"], {"total": 1, "pending_human_listening": 1})
        self.assertEqual(report["items"][0]["lesson"], 3)
        self.assertEqual(report["items"][0]["content_version"], 2)
        self.assertEqual(report["items"][0]["status"], "pending_human_listening")
        self.assertNotIn("text_en", report["items"][0])

    def test_approved_decision_requires_reviewer_and_timestamp(self):
        key = "test-course:lesson-3:version-2:media-media-key:cue-cue-key"
        decision = {
            "status": "approved",
            "reviewer": "teacher",
            "reviewed_at": "2026-10-16T12:00:00Z",
            "note": "Timing conferido por escuta.",
        }
        report = inventory(
            [lesson()], {"schema_version": 1, "decisions": {key: decision}}
        )
        self.assertEqual(report["summary"], {"total": 1, "approved": 1})
        with self.assertRaises(ValueError):
            inventory(
                [lesson()],
                {"schema_version": 1, "decisions": {key: {"status": "approved"}}},
            )

    def test_stale_decision_is_rejected(self):
        with self.assertRaises(ValueError):
            inventory(
                [lesson()],
                {
                    "schema_version": 1,
                    "decisions": {
                        "removed-cue": {
                            "status": "rejected",
                            "reviewer": "teacher",
                            "reviewed_at": "2026-10-16T12:00:00Z",
                        }
                    },
                },
            )
