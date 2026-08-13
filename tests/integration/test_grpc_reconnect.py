from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path[:0] = [str(ROOT / "agent" / "src"), str(ROOT / "collector" / "src")]

from pqc_agent.grpc.client import GrpcTelemetryClient  # noqa: E402
from pqc_agent.run_context import RunContext  # noqa: E402
from pqc_agent.spool import LocalSpool  # noqa: E402
from pqc_agent.telemetry import EventCollector  # noqa: E402
from pqc_collector.server import create_server  # noqa: E402
from pqc_collector.storage import TelemetryStorage  # noqa: E402


class ReconnectTests(unittest.TestCase):
    def test_two_agents_store_forward_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = TelemetryStorage(root / "runs")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            target = f"127.0.0.1:{port}"
            spools = {node: LocalSpool(root / "spool", "run-e2e", node)
                      for node in ("ric", "du")}
            collectors = {node: EventCollector(RunContext("run-e2e", node), spool)
                          for node, spool in spools.items()}
            for collector in collectors.values():
                collector.emit_test_event("BEFORE_OUTAGE")

            server = create_server(target, storage, insecure=True)
            server.start()
            clients = {node: GrpcTelemetryClient(target, spool, insecure=True)
                       for node, spool in spools.items()}
            for client in clients.values():
                client.flush_once()
            server.stop(0).wait()

            for collector in collectors.values():
                collector.emit_test_event("DURING_OUTAGE")
            for client in clients.values():
                with self.assertRaises(Exception):
                    client.flush_once()

            server = create_server(target, storage, insecure=True)
            server.start()
            for client in clients.values():
                client.flush_once()
                # Replay the same acknowledged event directly must remain idempotent.
                self.assertEqual(spools[client.spool.directory.name].pending_count(), 0)
            server.stop(0).wait()
            for node in ("ric", "du"):
                self.assertEqual(storage.count("run-e2e", node), 2)
                spools[node].close()


if __name__ == "__main__":
    unittest.main()

