import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]


class ManagementPathTests(unittest.TestCase):
    def test_collector_has_no_experimental_link(self):
        topology = (ROOT / "lab" / "openran-pqc.clab.yml").read_text()
        self.assertIn('endpoints: ["ric:eth1", "du:eth1"]', topology)
        self.assertNotIn("collector:eth1", topology)

    def test_runtime_gate_rejects_grpc_on_eth1(self):
        runner = (ROOT / "experiments" / "run.sh").read_text()
        self.assertIn("tcp.port == 50051", runner)
        self.assertIn("gRPC collector traffic crossed the experimental eth1 link", runner)


if __name__ == "__main__":
    unittest.main()
