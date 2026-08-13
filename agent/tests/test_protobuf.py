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

