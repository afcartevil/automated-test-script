import unittest

from checklist_scmp_sync.resolve import pick_unique_spec


class PickUniqueSpecTests(unittest.TestCase):
    def test_picks_exact_tos_version(self):
        match = pick_unique_spec(
            [
                {
                    "name": "X6879_H785",
                    "bid": "p1",
                    "specs": [
                        {"bid": "sid-16", "tosVersion": "16.3.0", "marketList": ["OP"]},
                        {"bid": "sid-162", "tosVersion": "16.2.0", "marketList": ["OP"]},
                    ],
                },
                {
                    "name": "X6879_H785(Android 17)",
                    "bid": "p2",
                    "specs": [
                        {"bid": "sid-17", "tosVersion": "17.0.0", "marketList": ["OP", "RU"]},
                    ],
                },
            ],
            "17.0.0",
        )
        self.assertEqual(match.spec_bid, "sid-17")
        self.assertEqual(match.spd_project, "X6879_H785(Android 17)")

    def test_does_not_fall_back_to_nearby_version(self):
        with self.assertRaisesRegex(ValueError, "未找到 tosVersion=16.3.0"):
            pick_unique_spec(
                [
                    {
                        "name": "X6879_H785",
                        "bid": "p1",
                        "specs": [{"bid": "sid-161", "tosVersion": "16.1.0"}],
                    }
                ],
                "16.3.0",
            )

    def test_multiple_specs_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "多个"):
            pick_unique_spec(
                [
                    {
                        "name": "X6879_H785",
                        "bid": "p1",
                        "specs": [{"bid": "a", "tosVersion": "16.3.0"}],
                    },
                    {
                        "name": "X6879_H999",
                        "bid": "p2",
                        "specs": [{"bid": "b", "tosVersion": "16.3.0"}],
                    },
                ],
                "16.3.0",
            )


if __name__ == "__main__":
    unittest.main()
