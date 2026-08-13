from __future__ import annotations

import time
from pathlib import Path

from .collectors.system import SystemCollector
from .collectors.vici import IkeObservation, ViciCollector
from .collectors.xfrm import XfrmCollector, XfrmState
from .grpc import telemetry_pb2
from .run_context import RunContext
from .spool import LocalSpool


class EventCollector:
    def __init__(self, context: RunContext, spool: LocalSpool) -> None:
        self.context = context
        self.spool = spool
        self.vici = ViciCollector()
        self.xfrm = XfrmCollector()
        self.system = SystemCollector()

    def _persist(self, event: telemetry_pb2.TelemetryEvent) -> int:
        sequence = self.spool.append(event.SerializeToString())
        event.sequence_number = sequence
        self.spool.replace(sequence, event.SerializeToString())
        return sequence

    def base(self, event_type: int) -> telemetry_pb2.TelemetryEvent:
        return telemetry_pb2.TelemetryEvent(
            run_id=self.context.run_id, node_id=self.context.node_id,
            timestamp_ns=time.time_ns(), type=event_type,
        )

    def emit_ike(self, observation: IkeObservation) -> int:
        event = self.base(telemetry_pb2.IKE_EVENT)
        event.ike.CopyFrom(telemetry_pb2.IkeEvent(
            event=observation.event, ike_sa_id=observation.ike_sa_id,
            child_sa_id=observation.child_sa_id, proposal=observation.proposal,
            authentication=observation.authentication,
        ))
        return self._persist(event)

    def collect_events(self) -> list[int]:
        return [self.emit_ike(item) for item in self.vici.collect_events()]

    def collect_metrics(self) -> list[int]:
        sequences = []
        system = self.system.collect()
        event = self.base(telemetry_pb2.SYSTEM_METRIC)
        event.system.CopyFrom(telemetry_pb2.SystemMetric(
            cpu_percent=system.cpu_percent, memory_bytes=system.memory_bytes,
            charon_cpu_percent=system.charon_cpu_percent,
            charon_memory_bytes=system.charon_memory_bytes,
        ))
        sequences.append(self._persist(event))
        for state in self.xfrm.collect():
            event = self.base(telemetry_pb2.XFRM_METRIC)
            event.xfrm.CopyFrom(telemetry_pb2.XfrmMetric(
                spi=state.spi, packets=state.packets, bytes=state.bytes,
                lifetime_seconds=state.lifetime_seconds,
                replay_errors=state.replay_errors, integrity_errors=state.integrity_errors,
                state=state.state,
            ))
            sequences.append(self._persist(event))
        return sequences

    def emit_test_event(self, name: str) -> int:
        return self.emit_ike(IkeObservation(name))

