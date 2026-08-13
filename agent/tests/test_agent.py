import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from pqc_agent.cli import append_event, parse_size, read_profile  # noqa: E402


class AgentTests(unittest.TestCase):
    def test_parse_size_binary_and_decimal(self):
        self.assertEqual(parse_size("1MiB"), 1024 * 1024)
        self.assertEqual(parse_size("1.5MB"), 1_500_000)

    def test_profile_whitelists_secret_like_values(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "profile.env"
            profile.write_text("MODE=M3\nSCTP_COUNT=10\nPSK=must-not-leak\n")
            self.assertEqual(read_profile(profile), {"mode": "M3", "sctp_count": 10})

    def test_event_has_both_clocks(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "events.jsonl"
            append_event(output, "test", "ric", {"ok": True})
            event = json.loads(output.read_text())
            self.assertEqual(event["event"], "test")
            self.assertTrue(event["utc"].endswith("Z"))
            self.assertGreater(event["monotonic_ns"], 0)


if __name__ == "__main__":
    unittest.main()
