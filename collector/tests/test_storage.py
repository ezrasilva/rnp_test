import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path[:0] = [str(ROOT / "agent" / "src"), str(ROOT / "collector" / "src")]

from pqc_collector.grpc import telemetry_pb2  # noqa: E402
from pqc_collector.storage import TelemetryStorage  # noqa: E402


class StorageTests(unittest.TestCase):
    def test_deduplication_and_gap_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = TelemetryStorage(Path(directory))
            def event(sequence):
                return telemetry_pb2.TelemetryEvent(
                    run_id="run-1", node_id="ric", timestamp_ns=sequence,
                    sequence_number=sequence, type=telemetry_pb2.IKE_EVENT,
                    ike=telemetry_pb2.IkeEvent(event="TEST"),
                )
            self.assertEqual(storage.ingest(event(1), {"ike": {}}), (True, 1, []))
            self.assertEqual(storage.ingest(event(3), {"ike": {}}), (True, 3, [2]))
            self.assertEqual(storage.ingest(event(3), {"ike": {}}), (False, 3, [2]))
            self.assertEqual(storage.ingest(event(2), {"ike": {}}), (True, 3, []))
            self.assertEqual(storage.count("run-1", "ric"), 3)
            lines = (Path(directory) / "run-1" / "ric" / "telemetry.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 3)
            self.assertEqual({json.loads(line)["sequence_number"] for line in lines}, {1, 2, 3})

    def test_node_metadata_populates_central_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = TelemetryStorage(Path(directory))
            event = telemetry_pb2.TelemetryEvent(
                run_id="run-meta", node_id="ric", timestamp_ns=1,
                sequence_number=1, type=telemetry_pb2.NODE_METADATA,
                node_metadata=telemetry_pb2.NodeMetadata(
                    mode="M3", kernel_version="6.8.0", agent_version="0.3.0",
                    strongswan_version="6.0.7", sample_interval_seconds=1.0,
                    collector_enabled=True,
                ),
            )
            payload = {"node_metadata": {
                "mode": "M3", "kernel_version": "6.8.0", "agent_version": "0.3.0",
                "strongswan_version": "6.0.7", "sample_interval_seconds": 1.0,
                "collector_enabled": True,
            }}
            storage.ingest(event, payload)
            manifest = json.loads((Path(directory) / "run-meta" / "manifest.json").read_text())
            self.assertEqual(manifest["mode"], "M3")
            self.assertEqual(manifest["kernel_versions"], {"ric": "6.8.0"})
            self.assertEqual(manifest["agent_versions"], {"ric": "0.3.0"})
            self.assertEqual(manifest["strongswan_version"], "6.0.7")
            self.assertEqual(manifest["sample_interval_seconds"], 1.0)
            self.assertTrue(manifest["collector_enabled"]["ric"])
