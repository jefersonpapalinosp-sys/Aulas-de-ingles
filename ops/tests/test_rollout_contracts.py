"""Provas históricas recusam inventários ambíguos e identificadores injetados."""

import unittest
from unittest.mock import patch

from ops import rollout
from ops.recovery_archive import RecoveryError


class RolloutContracts(unittest.TestCase):
    def test_count_rejects_non_integer_or_negative_values(self):
        for count in (True, -1, 1.5, "1", None):
            with self.subTest(count=count), self.assertRaises(RecoveryError):
                rollout.checked_count(count)

    def test_untrusted_table_names_are_rejected_before_reading_rows(self):
        for name in ("table;DROP TABLE app_user", "public.app_user", "UPPER"):
            with self.subTest(name=name), patch.object(
                rollout.recovery, "query", return_value=[name]
            ) as query:
                with self.assertRaises(RecoveryError):
                    rollout.fingerprints(object())
                self.assertEqual(query.call_count, 1)

    def test_fingerprints_ignore_order_but_detect_content_changes(self):
        rows = [{"id": 1, "value": "first"}, {"id": 2, "value": "second"}]

        def query(target, sql):
            return ["app_user"] if "pg_tables" in sql else rows

        with patch.object(rollout.recovery, "query", side_effect=query):
            first = rollout.fingerprints(object())
            rows.reverse()
            self.assertEqual(rollout.fingerprints(object()), first)
            rows[0]["value"] = "changed"
            self.assertNotEqual(rollout.fingerprints(object()), first)
            self.assertEqual(first["app_user"]["count"], 2)
