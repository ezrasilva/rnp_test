from __future__ import annotations

import logging
import time
from pathlib import Path

import grpc

from ..spool import LocalSpool
from . import telemetry_pb2, telemetry_pb2_grpc


class GrpcTelemetryClient:
    def __init__(self, target: str, spool: LocalSpool, *, insecure: bool,
                 ca: Path | None = None, cert: Path | None = None,
                 key: Path | None = None) -> None:
        self.target = target
        self.spool = spool
        self.insecure = insecure
        self.ca, self.cert, self.key = ca, cert, key
        self.log = logging.getLogger("pqc_agent.grpc")

    def channel(self) -> grpc.Channel:
        if self.insecure:
            return grpc.insecure_channel(self.target)
        if not self.ca:
            raise ValueError("--ca is required unless --insecure is used")
        credentials = grpc.ssl_channel_credentials(
            root_certificates=self.ca.read_bytes(),
            private_key=self.key.read_bytes() if self.key else None,
            certificate_chain=self.cert.read_bytes() if self.cert else None,
        )
        return grpc.secure_channel(self.target, credentials)

    def flush_once(self) -> int:
        pending = self.spool.pending()
        if not pending:
            return 0

        def events():
            for _sequence, payload in pending:
                event = telemetry_pb2.TelemetryEvent()
                event.ParseFromString(payload)
                yield event

        with self.channel() as channel:
            ack = telemetry_pb2_grpc.TelemetryServiceStub(channel).StreamTelemetry(
                events(), timeout=10
            )
        self.spool.acknowledge(ack.last_sequence_received, ack.missing_sequences)
        return len(pending)

    def flush_with_retry(self, stop, reconnect_interval: float = 1.0) -> None:
        while not stop.is_set():
            try:
                sent = self.flush_once()
                if sent == 0:
                    stop.wait(0.2)
            except grpc.RpcError as exc:
                self.log.warning("collector unavailable target=%s code=%s", self.target, exc.code())
                stop.wait(reconnect_interval)

