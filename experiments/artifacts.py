#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import time
from datetime import datetime, timezone
from pathlib import Path


SAFE_PROFILE_KEYS = {"MODE", "SCTP_COUNT", "SCTP_RATE", "SCTP_PORT"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_profile(path: Path) -> dict[str, object]:
    values: dict[str, object] = {}
    for line in path.read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in SAFE_PROFILE_KEYS:
            values[key.lower()] = int(value) if value.isdigit() else value
    return values


def event(args: argparse.Namespace) -> None:
    record = {"utc": utc_now(), "monotonic_ns": time.monotonic_ns(),
              "event": args.name, "endpoint": args.endpoint}
    with Path(args.output).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")


def manifest(args: argparse.Namespace) -> None:
    topology, profile = Path(args.topology).resolve(), Path(args.profile).resolve()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "schema_version": 2, "run_id": args.run_id, "mode": args.mode,
        "experiment_kind": args.experiment_kind, "created_utc": utc_now(),
        "telemetry_architecture": "distributed-grpc",
        "agent_enabled": True, "sample_interval_seconds": 1.0,
        "host": {"kernel": platform.release(), "architecture": platform.machine(),
                 "python": platform.python_version(), "cpu_count": os.cpu_count()},
        "clock": {"duration_clock": "CLOCK_MONOTONIC", "wall_clock": "UTC"},
        "image": {"name": args.image},
        "topology": {"path": str(topology), "sha256": sha256(topology)},
        "profile": read_profile(profile), "nodes": ["ric", "du"],
    }, indent=2, sort_keys=True) + "\n")


def finalize(args: argparse.Namespace) -> None:
    result_dir, telemetry_dir = Path(args.result_dir), Path(args.telemetry_dir)
    events = [json.loads(line) for line in (result_dir / "events.jsonl").read_text().splitlines()]
    by_name = {item["event"]: item["monotonic_ns"] for item in events}
    durations = {}
    for label, start, end in (("ike_establishment", "ike_start", "child_sa_installed"),
                              ("ike_rekey", "ike_rekey_start", "ike_rekey_end"),
                              ("child_rekey", "child_rekey_start", "child_rekey_end"),
                              ("traffic", "traffic_start", "traffic_end")):
        if start in by_name and end in by_name:
            durations[f"{label}_ns"] = by_name[end] - by_name[start]
    telemetry_summary = json.loads((telemetry_dir / "summary.json").read_text())
    samples = 0
    for node in ("ric", "du"):
        with (telemetry_dir / node / "metrics.csv").open(newline="", encoding="utf-8") as stream:
            samples += sum(1 for _ in csv.DictReader(stream))
    summary_path = result_dir / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary.update({"durations": durations, "metric_samples": samples,
                    "telemetry": telemetry_summary, "agent_schema_version": 2})
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


def validate(args: argparse.Namespace) -> None:
    result_dir, telemetry_dir = Path(args.result_dir), Path(args.telemetry_dir)
    required = ("manifest.json", "events.jsonl", "summary.json", "capture.pcap")
    missing = [name for name in required if not (result_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"missing artifacts: {', '.join(missing)}")
    summary = json.loads((result_dir / "summary.json").read_text())
    manifest_data = json.loads((result_dir / "manifest.json").read_text())
    if manifest_data["run_id"] != summary["run_id"] or summary["status"] != "pass":
        raise RuntimeError("manifest/summary integrity check failed")
    nodes = summary.get("telemetry", {}).get("nodes", {})
    if set(nodes) != {"ric", "du"} or any(node.get("has_gaps") for node in nodes.values()):
        raise RuntimeError("distributed telemetry is incomplete or has sequence gaps")
    if not telemetry_dir.is_dir():
        raise RuntimeError("distributed telemetry directory is missing")
    material = b"\n".join(path.read_bytes() for path in result_dir.iterdir()
                            if path.is_file() and path.suffix != ".pcap")
    if re.search(rb"secret\s*=|aead .*0x[0-9a-f]{32}", material, re.I):
        raise RuntimeError("possible secret material in artifacts")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Experiment artifact utilities")
    commands = root.add_subparsers(dest="command", required=True)
    item = commands.add_parser("event")
    item.add_argument("--output", required=True); item.add_argument("--name", required=True)
    item.add_argument("--endpoint"); item.set_defaults(handler=event)
    item = commands.add_parser("manifest")
    for name in ("output", "run-id", "mode", "experiment-kind", "image", "topology", "profile"):
        item.add_argument(f"--{name}", required=True)
    item.set_defaults(handler=manifest)
    for name, handler in (("finalize", finalize), ("validate", validate)):
        item = commands.add_parser(name); item.add_argument("--result-dir", required=True)
        item.add_argument("--telemetry-dir", required=True); item.set_defaults(handler=handler)
    return root


if __name__ == "__main__":
    args = parser().parse_args()
    args.handler(args)
