#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_schedule(repetitions: int, seed: int) -> list[dict[str, Any]]:
    treatments = [
        ("M1", "steady"),
        ("M2", "steady"),
        ("M3", "steady"),
        ("M2", "establishment"),
        ("M3", "establishment"),
    ]
    schedule = [
        {"mode": mode, "kind": kind, "repetition": repetition}
        for repetition in range(1, repetitions + 1)
        for mode, kind in treatments
    ]
    random.Random(seed).shuffle(schedule)
    for order, item in enumerate(schedule, 1):
        item["order"] = order
    return schedule


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def describe(values: list[float], relative_precision: float) -> dict[str, Any]:
    mean = statistics.fmean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    margin = 1.96 * stdev / math.sqrt(len(values)) if values else 0.0
    target = abs(mean) * relative_precision
    recommended = math.ceil((1.96 * stdev / target) ** 2) if target > 0 else len(values)
    return {
        "n": len(values),
        "mean": mean,
        "median": statistics.median(values),
        "stdev": stdev,
        "p05": percentile(values, 0.05),
        "p95": percentile(values, 0.95),
        "ci95_normal": [mean - margin, mean + margin],
        "recommended_n_for_relative_ci_half_width": max(len(values), recommended),
    }


def sctp_rtt(result_dir: Path) -> float | None:
    path = result_dir / "sctp-client.jsonl"
    if not path.exists():
        return None
    for line in reversed(path.read_text().splitlines()):
        record = json.loads(line)
        if record.get("event") == "summary":
            return float(record["rtt_median_ns"])
    return None


def aggregate(project: Path, schedule: list[dict[str, Any]], relative_precision: float) -> dict[str, Any]:
    groups: dict[str, dict[str, list[float]]] = {}
    observations: dict[tuple[str, str, int], dict[str, float]] = {}
    failures = []
    for item in schedule:
        result_dir = project / "results" / "experiments" / item["run_id"]
        summary_path = result_dir / "summary.json"
        if not summary_path.exists():
            failures.append({**item, "reason": "missing summary"})
            continue
        summary = json.loads(summary_path.read_text())
        if summary.get("status") != "pass":
            failures.append({**item, "reason": "run did not pass"})
            continue
        key = f"{item['mode']}/{item['kind']}"
        metrics = groups.setdefault(key, {})
        candidates = {
            "ike_establishment_ns": summary.get("durations", {}).get("ike_establishment_ns"),
            "ike_rekey_ns": summary.get("durations", {}).get("ike_rekey_ns"),
            "child_rekey_ns": summary.get("durations", {}).get("child_rekey_ns"),
            "mlkem_exchange_ns": summary.get("mlkem_exchange_ns"),
            "sctp_rtt_median_ns": sctp_rtt(result_dir),
            "esp_packets": summary.get("esp_packets"),
        }
        for name, value in candidates.items():
            if value is not None:
                metrics.setdefault(name, []).append(float(value))
        observations[(item["mode"], item["kind"], item["repetition"])] = {
            name: float(value) for name, value in candidates.items() if value is not None
        }
    contrasts = {}
    for label, left, right in (
        ("ipsec_cost_steady_M2_minus_M1", ("M2", "steady"), ("M1", "steady")),
        ("pqc_incremental_steady_M3_minus_M2", ("M3", "steady"), ("M2", "steady")),
        ("pqc_incremental_establishment_M3_minus_M2",
         ("M3", "establishment"), ("M2", "establishment")),
    ):
        differences: dict[str, list[float]] = {}
        for repetition in sorted({item["repetition"] for item in schedule}):
            left_values = observations.get((*left, repetition), {})
            right_values = observations.get((*right, repetition), {})
            for metric in left_values.keys() & right_values.keys():
                differences.setdefault(metric, []).append(left_values[metric] - right_values[metric])
        contrasts[label] = {
            metric: describe(values, relative_precision)
            for metric, values in differences.items() if values
        }
    return {
        "groups": {
            group: {metric: describe(values, relative_precision)
                    for metric, values in metrics.items() if values}
            for group, metrics in groups.items()
        },
        "paired_contrasts": contrasts,
        "failures": failures,
        "passed": len(schedule) - len(failures),
        "total": len(schedule),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Randomized local M1/M2/M3 pilot campaign")
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--relative-precision", type=float, default=0.10,
                        help="desired 95%% CI half-width as a fraction of the mean")
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--plan-only", action="store_true",
                        help="write the randomized schedule without executing it")
    args = parser.parse_args()
    if args.repetitions < 10:
        parser.error("the pilot requires at least 10 repetitions")
    if not 0 < args.relative_precision < 1:
        parser.error("relative precision must be between 0 and 1")

    project = Path(__file__).resolve().parent.parent
    campaign_id = args.campaign_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-pilot")
    campaign_dir = project / "results" / "campaigns" / campaign_id
    campaign_dir.mkdir(parents=True, exist_ok=True)
    schedule_path = campaign_dir / "schedule.json"
    if schedule_path.exists():
        schedule = json.loads(schedule_path.read_text())
    else:
        schedule = build_schedule(args.repetitions, args.seed)
        for item in schedule:
            item["run_id"] = (f"{campaign_id}-{item['order']:03d}-"
                              f"{item['mode'].lower()}-{item['kind']}")
        schedule_path.write_text(json.dumps(schedule, indent=2) + "\n")
        manifest = {
            "schema_version": 1,
            "campaign_id": campaign_id,
            "type": "pilot",
            "created_utc": utc_now(),
            "seed": args.seed,
            "repetitions_per_treatment": args.repetitions,
            "relative_ci_half_width_target": args.relative_precision,
            "treatments": ["M1/steady", "M2/steady", "M3/steady",
                           "M2/establishment", "M3/establishment"],
            "schedule": "schedule.json",
        }
        (campaign_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    if args.plan_only:
        print(f"Planned {len(schedule)} runs in {campaign_dir}")
        return

    log_path = campaign_dir / "campaign.jsonl"
    for item in schedule:
        summary = project / "results" / "experiments" / item["run_id"] / "summary.json"
        if summary.exists() and json.loads(summary.read_text()).get("status") == "pass":
            print(f"SKIP {item['order']:03d}/{len(schedule)} {item['mode']} {item['kind']}")
            continue
        print(f"RUN  {item['order']:03d}/{len(schedule)} {item['mode']} {item['kind']}", flush=True)
        event = {"utc": utc_now(), "event": "run_start", **item}
        with log_path.open("a") as stream:
            stream.write(json.dumps(event) + "\n")
        environment = os.environ.copy()
        environment["RUN_ID"] = item["run_id"]
        environment["EXPERIMENT_KIND"] = item["kind"]
        result = subprocess.run([str(project / "experiments" / "run.sh"), item["mode"].lower()],
                                cwd=project, env=environment, check=False)
        with log_path.open("a") as stream:
            stream.write(json.dumps({"utc": utc_now(), "event": "run_end",
                                     "exit_code": result.returncode, **item}) + "\n")
        if result.returncode:
            print(f"Campaign stopped at order {item['order']}; rerun the same command to resume.",
                  file=sys.stderr)
            raise SystemExit(result.returncode)

    report = aggregate(project, schedule, args.relative_precision)
    (campaign_dir / "summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if report["failures"]:
        raise SystemExit("campaign has failed or missing runs")
    print(f"PASS: {report['passed']}/{report['total']} randomized pilot runs completed")
    print(f"Campaign evidence: {campaign_dir}")


if __name__ == "__main__":
    main()
