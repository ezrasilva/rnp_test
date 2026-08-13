from __future__ import annotations

import logging
import re
from concurrent import futures
from pathlib import Path

import grpc
from google.protobuf.json_format import MessageToDict

from .grpc import telemetry_pb2, telemetry_pb2_grpc

from .storage import TelemetryStorage


IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class TelemetryService(telemetry_pb2_grpc.TelemetryServiceServicer):
    def __init__(self, storage: TelemetryStorage) -> None:
        self.storage = storage
        self.log = logging.getLogger("pqc_collector.ingestion")

    def StreamTelemetry(self, request_iterator, context):
        run_id = node_id = ""
        last = 0
        missing: list[int] = []
        for event in request_iterator:
            if (not IDENTIFIER_RE.fullmatch(event.run_id)
                    or not IDENTIFIER_RE.fullmatch(event.node_id)
                    or event.sequence_number < 1):
                context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                              "valid run_id, node_id and sequence are required")
            if run_id and (event.run_id != run_id or event.node_id != node_id):
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "one stream must contain a single run/node")
            run_id, node_id = event.run_id, event.node_id
            payload_name = event.WhichOneof("payload")
            if payload_name is None:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "telemetry payload is required")
            payload = MessageToDict(getattr(event, payload_name), preserving_proto_field_name=True)
            inserted, last, missing = self.storage.ingest(event, {payload_name: payload})
            self.log.info("telemetry run_id=%s node_id=%s sequence_number=%d duplicate=%s",
                          run_id, node_id, event.sequence_number, not inserted)
        return telemetry_pb2.StreamAck(run_id=run_id, node_id=node_id,
                                       last_sequence_received=last,
                                       missing_sequences=missing)


def create_server(listen: str, storage: TelemetryStorage, *, insecure: bool,
                  cert: Path | None = None, key: Path | None = None,
                  ca: Path | None = None) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    telemetry_pb2_grpc.add_TelemetryServiceServicer_to_server(TelemetryService(storage), server)
    if insecure:
        server.add_insecure_port(listen)
    else:
        if not cert or not key:
            raise ValueError("--cert and --key are required unless --insecure is used")
        credentials = grpc.ssl_server_credentials(
            [(key.read_bytes(), cert.read_bytes())],
            root_certificates=ca.read_bytes() if ca else None,
            require_client_auth=ca is not None,
        )
        server.add_secure_port(listen, credentials)
    return server
