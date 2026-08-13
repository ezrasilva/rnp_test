import unittest

from pqc_agent.grpc import telemetry_pb2


class ProtobufTests(unittest.TestCase):
    def test_round_trip(self):
        event = telemetry_pb2.TelemetryEvent(
            run_id="run-1", node_id="du", timestamp_ns=123,
            sequence_number=7, type=telemetry_pb2.XFRM_METRIC,
            xfrm=telemetry_pb2.XfrmMetric(spi="0x100", packets=3, bytes=192),
        )
        restored = telemetry_pb2.TelemetryEvent.FromString(event.SerializeToString())
        self.assertEqual(restored.sequence_number, 7)
        self.assertEqual(restored.WhichOneof("payload"), "xfrm")
        self.assertEqual(restored.xfrm.spi, "0x100")

    def test_node_metadata_round_trip(self):
        event = telemetry_pb2.TelemetryEvent(
            run_id="run-1", node_id="ric", timestamp_ns=1, sequence_number=1,
            type=telemetry_pb2.NODE_METADATA,
            node_metadata=telemetry_pb2.NodeMetadata(
                mode="M3", kernel_version="6.8", agent_version="0.3.0",
                strongswan_version="6.0.7", sample_interval_seconds=1.0,
                collector_enabled=True,
            ),
        )
        restored = telemetry_pb2.TelemetryEvent.FromString(event.SerializeToString())
        self.assertEqual(restored.WhichOneof("payload"), "node_metadata")
        self.assertEqual(restored.node_metadata.strongswan_version, "6.0.7")
        self.assertTrue(restored.node_metadata.collector_enabled)
