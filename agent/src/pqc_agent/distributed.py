from __future__ import annotations

import json
import logging
import platform
import signal
import subprocess
import threading
import time
from pathlib import Path

from . import __version__
from .grpc.client import GrpcTelemetryClient
from .run_context import RunContext
from .spool import LocalSpool
from .telemetry import EventCollector


class PQCExperimentAgent:
    def __init__(self, context: RunContext, spool_root: Path, sample_interval: float,
                 collector: str | None, insecure: bool, ca: Path | None,
                 cert: Path | None, key: Path | None) -> None:
        self.context = context
        self.interval = sample_interval
        self.spool = LocalSpool(spool_root, context.run_id, context.node_id)
        self.collectors = EventCollector(context, self.spool)
        self.stop = threading.Event()
        self.client = (GrpcTelemetryClient(collector, self.spool, insecure=insecure,
                                           ca=ca, cert=cert, key=key) if collector else None)
        self.log = logging.LoggerAdapter(logging.getLogger("pqc_agent"), {
            "run_id": context.run_id, "node_id": context.node_id,
        })

    def write_local_manifest(self) -> None:
        path = self.spool.directory / "manifest.json"
        path.write_text(json.dumps({
            "run_id": self.context.run_id, "node_id": self.context.node_id,
            "mode": self.context.mode, "agent_version": __version__,
            "kernel_version": platform.release(), "sample_interval_seconds": self.interval,
            "agent_enabled": True, "collector_enabled": self.client is not None,
        }, indent=2) + "\n")

    @staticmethod
    def strongswan_version() -> str:
        try:
            result = subprocess.run(["swanctl", "--version"], text=True,
                                    capture_output=True, check=False, timeout=2)
            match = next((word for word in result.stdout.split() if word[0:1].isdigit()), "")
            return match
        except (OSError, subprocess.SubprocessError):
            return ""

    def run(self, duration: float | None = None, test_event: str | None = None) -> None:
        self.write_local_manifest()
        self.collectors.emit_node_metadata(
            mode=self.context.mode, kernel_version=platform.release(),
            agent_version=__version__, strongswan_version=self.strongswan_version(),
            sample_interval=self.interval, collector_enabled=self.client is not None,
        )
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: self.stop.set())
        sender = None
        if self.client:
            sender = threading.Thread(target=self.client.flush_with_retry,
                                      args=(self.stop,), daemon=True)
            sender.start()
        if test_event:
            self.collectors.emit_test_event(test_event)
        started = time.monotonic()
        deadline = started
        while not self.stop.is_set() and (duration is None or time.monotonic() - started < duration):
            self.collectors.collect_events()
            if time.monotonic() >= deadline:
                self.collectors.collect_metrics()
                deadline = time.monotonic() + self.interval
            self.stop.wait(0.2)
        if self.client:
            try:
                self.client.flush_once()
            except Exception:
                self.log.warning("shutdown with pending telemetry count=%d", self.spool.pending_count())
        self.stop.set()
        if sender:
            sender.join(timeout=2)
        self.spool.close()
