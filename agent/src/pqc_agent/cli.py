#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import platform
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SAFE_PROFILE_KEYS = {"MODE", "SCTP_COUNT", "SCTP_RATE", "SCTP_PORT"}
METRIC_FIELDS = (
    "utc", "monotonic_ns", "endpoint", "cpu_percent", "memory_bytes",
    "xfrm_packets", "xfrm_bytes", "ike_sas", "child_sas",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def run(*command: str, check: bool = True) -> str:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    if check and result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}: "
                           f"{result.stderr.strip()}")
    return result.stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_profile(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line in path.read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in SAFE_PROFILE_KEYS:
            continue
        values[key.lower()] = int(value) if value.isdigit() else value
    return values


def append_event(output: Path, event: str, endpoint: str | None,
                 details: dict[str, Any]) -> None:
    record = {
        "utc": utc_now(),
        "monotonic_ns": time.monotonic_ns(),
        "event": event,
        "endpoint": endpoint,
        "details": details,
    }
    with output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")


def command_manifest(args: argparse.Namespace) -> None:
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    topology = Path(args.topology).resolve()
    profile = Path(args.profile).resolve()
    image_id = run("docker", "image", "inspect", args.image,
                   "--format", "{{.Id}}").strip()
    versions = {}
    clock_offsets = {}
    clock_uncertainties = {}
    for endpoint in args.container:
        inventory = run("docker", "exec", endpoint, "head", "-n", "1",
                        "/usr/share/openran-pqc/components.txt").strip()
        versions[endpoint] = inventory.replace("strongSwan=", "strongSwan ")
        before = time.time_ns()
        remote = int(run("docker", "exec", endpoint, "date", "+%s%N").strip())
        after = time.time_ns()
        clock_offsets[endpoint] = remote - ((before + after) // 2)
        clock_uncertainties[endpoint] = (after - before) // 2
    resolution = time.get_clock_info("monotonic").resolution
    manifest = {
        "schema_version": 1,
        "run_id": args.run_id,
        "mode": args.mode,
        "experiment_kind": args.experiment_kind,
        "created_utc": utc_now(),
        "agent_version": "0.2.0",
        "host": {
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "clock": {
            "duration_clock": "CLOCK_MONOTONIC",
            "resolution_ns": int(resolution * 1_000_000_000),
            "wall_clock": "UTC",
            "endpoint_offsets_ns": clock_offsets,
            "measurement_uncertainty_ns": clock_uncertainties,
            "endpoint_clock_skew_ns": (max(clock_offsets.values()) - min(clock_offsets.values())
                                       if clock_offsets else 0),
        },
        "image": {"name": args.image, "id": image_id},
        "strongswan": versions,
        "topology": {"path": str(topology), "sha256": sha256(topology)},
        "profile": read_profile(profile),
        "endpoints": list(args.container),
    }
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def parse_size(value: str) -> int:
    number, unit = re.match(r"([0-9.]+)([A-Za-z]+)", value.strip()).groups()  # type: ignore[union-attr]
    scale = {"B": 1, "kB": 1000, "KB": 1000, "KiB": 1024, "MB": 1000**2,
             "MiB": 1024**2, "GB": 1000**3, "GiB": 1024**3}
    return int(float(number) * scale[unit])


def xfrm_totals(container: str) -> tuple[int, int]:
    text = run("docker", "exec", container, "ip", "-s", "xfrm", "state", check=False)
    packets = sum(int(value) for value in re.findall(r"([0-9]+)\(packets\)", text))
    byte_count = sum(int(value) for value in re.findall(r"([0-9]+)\(bytes\)", text))
    return packets, byte_count


def vici_counts(container: str) -> tuple[int, int]:
    text = run("docker", "exec", container, "swanctl", "--list-sas", "--pretty", check=False)
    return text.count("state = ESTABLISHED"), text.count("state = INSTALLED")


def collect_metrics(containers: list[str]) -> list[dict[str, Any]]:
    stats_text = run("docker", "stats", "--no-stream", "--format", "{{json .}}", *containers)
    stats = {item["Name"]: item for item in map(json.loads, stats_text.splitlines())}
    rows = []
    now_utc, now_mono = utc_now(), time.monotonic_ns()
    for container in containers:
        item = stats[container]
        packets, byte_count = xfrm_totals(container)
        ike_sas, child_sas = vici_counts(container)
        rows.append({
            "utc": now_utc,
            "monotonic_ns": now_mono,
            "endpoint": container,
            "cpu_percent": float(item["CPUPerc"].rstrip("%")),
            "memory_bytes": parse_size(item["MemUsage"].split("/", 1)[0]),
            "xfrm_packets": packets,
            "xfrm_bytes": byte_count,
            "ike_sas": ike_sas,
            "child_sas": child_sas,
        })
    return rows


def command_monitor(args: argparse.Namespace) -> None:
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stop = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    first_write = not output.exists() or output.stat().st_size == 0
    with output.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=METRIC_FIELDS)
        if first_write:
            writer.writeheader()
        while not stop:
            try:
                writer.writerows(collect_metrics(args.container))
                stream.flush()
            except Exception as exc:
                print(f"metrics warning: {exc}", file=sys.stderr, flush=True)
            deadline = time.monotonic() + args.interval
            while not stop and time.monotonic() < deadline:
                time.sleep(min(0.1, deadline - time.monotonic()))


def command_event(args: argparse.Namespace) -> None:
    details = json.loads(args.details) if args.details else {}
    append_event(Path(args.output), args.name, args.endpoint, details)


def command_finalize(args: argparse.Namespace) -> None:
    result_dir = Path(args.result_dir)
    summary_path = result_dir / "summary.json"
    events = [json.loads(line) for line in (result_dir / "events.jsonl").read_text().splitlines()]
    by_name = {event["event"]: event["monotonic_ns"] for event in events}
    durations = {}
    for label, start, end in (
        ("ike_establishment", "ike_start", "child_sa_installed"),
        ("ike_rekey", "ike_rekey_start", "ike_rekey_end"),
        ("child_rekey", "child_rekey_start", "child_rekey_end"),
        ("traffic", "traffic_start", "traffic_end"),
    ):
        if start in by_name and end in by_name:
            durations[f"{label}_ns"] = by_name[end] - by_name[start]
    with (result_dir / "metrics.csv").open(newline="", encoding="utf-8") as stream:
        samples = sum(1 for _ in csv.DictReader(stream))
    summary = json.loads(summary_path.read_text())
    summary["durations"] = durations
    summary["metric_samples"] = samples
    summary["agent_schema_version"] = 1
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


def command_validate(args: argparse.Namespace) -> None:
    result_dir = Path(args.result_dir)
    required = ("manifest.json", "events.jsonl", "metrics.csv", "summary.json", "capture.pcap")
    missing = [name for name in required if not (result_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"missing artifacts: {', '.join(missing)}")
    manifest = json.loads((result_dir / "manifest.json").read_text())
    summary = json.loads((result_dir / "summary.json").read_text())
    if manifest["run_id"] != summary["run_id"] or summary["status"] != "pass":
        raise RuntimeError("manifest/summary integrity check failed")
    if re.search(rb"secret\s*=|aead .*0x[0-9a-f]{32}",
                 b"\n".join(path.read_bytes() for path in result_dir.iterdir()
                             if path.is_file() and path.suffix != ".pcap"), re.I):
        raise RuntimeError("possible secret material in artifacts")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="OpenRAN PQC experimental agent")
    commands = root.add_subparsers(dest="command", required=True)
    manifest = commands.add_parser("manifest")
    manifest.add_argument("--output", required=True)
    manifest.add_argument("--run-id", required=True)
    manifest.add_argument("--mode", required=True)
    manifest.add_argument("--experiment-kind", required=True)
    manifest.add_argument("--image", required=True)
    manifest.add_argument("--topology", required=True)
    manifest.add_argument("--profile", required=True)
    manifest.add_argument("--container", action="append", required=True)
    manifest.set_defaults(handler=command_manifest)
    event = commands.add_parser("event")
    event.add_argument("--output", required=True)
    event.add_argument("--name", required=True)
    event.add_argument("--endpoint")
    event.add_argument("--details")
    event.set_defaults(handler=command_event)
    monitor = commands.add_parser("monitor")
    monitor.add_argument("--output", required=True)
    monitor.add_argument("--interval", type=float, default=0.5)
    monitor.add_argument("--container", action="append", required=True)
    monitor.set_defaults(handler=command_monitor)
    finalize = commands.add_parser("finalize")
    finalize.add_argument("--result-dir", required=True)
    finalize.set_defaults(handler=command_finalize)
    validate = commands.add_parser("validate")
    validate.add_argument("--result-dir", required=True)
    validate.set_defaults(handler=command_validate)
    distributed = commands.add_parser("run")
    distributed.add_argument("--node-id", required=True)
    distributed.add_argument("--run-id", required=True)
    distributed.add_argument("--mode", default="unknown")
    destination = distributed.add_mutually_exclusive_group(required=True)
    destination.add_argument("--collector")
    destination.add_argument("--offline", action="store_true")
    distributed.add_argument("--spool-dir", type=Path, default=Path("/var/lib/pqc-agent/spool"))
    distributed.add_argument("--sample-interval", type=float, default=1.0)
    distributed.add_argument("--duration", type=float)
    distributed.add_argument("--test-event")
    distributed.add_argument("--insecure", action="store_true")
    distributed.add_argument("--ca", type=Path)
    distributed.add_argument("--cert", type=Path)
    distributed.add_argument("--key", type=Path)
    distributed.set_defaults(handler=command_distributed_run)
    return root


def command_distributed_run(args: argparse.Namespace) -> None:
    from .distributed import PQCExperimentAgent
    from .run_context import RunContext

    if args.sample_interval < 0.1:
        raise ValueError("sample interval must be at least 0.1 seconds")
    if args.collector and not args.insecure and not args.ca:
        raise ValueError("use --insecure explicitly or provide --ca")
    agent = PQCExperimentAgent(
        RunContext(args.run_id, args.node_id, args.mode), args.spool_dir,
        args.sample_interval, args.collector, args.insecure,
        args.ca, args.cert, args.key,
    )
    agent.run(args.duration, args.test_event)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parser().parse_args()
    try:
        args.handler(args)
    except Exception as exc:
        logging.getLogger("pqc_agent").error("command failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
