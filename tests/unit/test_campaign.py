import importlib.util
import unittest
from collections import Counter
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "experiments" / "campaign.py"
SPEC = importlib.util.spec_from_file_location("campaign", MODULE_PATH)
campaign = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(campaign)


class CampaignTests(unittest.TestCase):
    def test_schedule_is_deterministic_and_balanced(self):
        first = campaign.build_schedule(10, 42)
        second = campaign.build_schedule(10, 42)
        self.assertEqual(first, second)
        counts = Counter((item["mode"], item["kind"]) for item in first)
        self.assertEqual(set(counts.values()), {10})
        self.assertEqual(len(first), 50)

    def test_describe_recommends_at_least_pilot_size(self):
        result = campaign.describe([1.0, 2.0, 3.0, 4.0], 0.1)
        self.assertEqual(result["median"], 2.5)
        self.assertGreaterEqual(result["recommended_n_for_relative_ci_half_width"], 4)


if __name__ == "__main__":
    unittest.main()
