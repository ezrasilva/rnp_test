import unittest

from pqc_agent.collectors.system import SystemCollector


class SystemCollectorTests(unittest.TestCase):
    def test_reports_agent_overhead(self):
        collector = SystemCollector()
        sample = collector.collect()
        self.assertGreater(sample.agent_memory_bytes, 0)
        self.assertGreaterEqual(sample.agent_cpu_percent, 0.0)


if __name__ == "__main__":
    unittest.main()
