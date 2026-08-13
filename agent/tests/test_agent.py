import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from pqc_agent.cli import parser  # noqa: E402


class AgentTests(unittest.TestCase):
    def test_cli_is_endpoint_local_only(self):
        args = parser().parse_args([
            "--node-id", "ric", "--run-id", "run-1",
            "--collector", "collector:50051", "--insecure",
        ])
        self.assertEqual(args.node_id, "ric")
        self.assertEqual(args.collector, "collector:50051")


if __name__ == "__main__":
    unittest.main()
