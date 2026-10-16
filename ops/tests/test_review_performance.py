import unittest

from ops.review_performance import distribution, percentile, summarize_plan


class ReviewPerformanceTest(unittest.TestCase):
    def test_nearest_rank_distribution_is_deterministic(self):
        values = [float(value) for value in range(1, 21)]

        self.assertEqual(percentile(values, 0.50), 10)
        self.assertEqual(percentile(values, 0.95), 19)
        self.assertEqual(
            distribution(values),
            {"min": 1.0, "p50": 10.0, "p95": 19.0, "max": 20.0},
        )

    def test_percentile_rejects_empty_sample(self):
        with self.assertRaises(ValueError):
            percentile([], 0.95)

    def test_plan_summary_collects_indexes_and_buffers(self):
        plan = [
            {
                "Planning Time": 0.1254,
                "Execution Time": 1.9996,
                "Plan": {
                    "Node Type": "Limit",
                    "Actual Rows": 51,
                    "Shared Hit Blocks": 2,
                    "Shared Read Blocks": 1,
                    "Plans": [
                        {
                            "Node Type": "Index Scan",
                            "Index Name": "ix_candidate",
                            "Shared Hit Blocks": 3,
                            "Shared Read Blocks": 4,
                        }
                    ],
                },
            }
        ]

        self.assertEqual(
            summarize_plan(plan),
            {
                "planning_ms": 0.125,
                "execution_ms": 2.0,
                "root_node": "Limit",
                "actual_rows": 51,
                "shared_hit_blocks_sum": 5,
                "shared_read_blocks_sum": 5,
                "node_types": ["Limit", "Index Scan"],
                "indexes": ["ix_candidate"],
            },
        )


if __name__ == "__main__":
    unittest.main()
