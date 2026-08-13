#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Endpoint-local OpenRAN PQC telemetry agent")
    root.add_argument("--node-id", required=True)
    root.add_argument("--run-id", required=True)
    root.add_argument("--mode", default="unknown")
    destination = root.add_mutually_exclusive_group(required=True)
    destination.add_argument("--collector")
    destination.add_argument("--offline", action="store_true")
    root.add_argument("--spool-dir", type=Path, default=Path("/var/lib/pqc-agent/spool"))
    root.add_argument("--sample-interval", type=float, default=1.0)
    root.add_argument("--duration", type=float)
    root.add_argument("--test-event")
    root.add_argument("--insecure", action="store_true")
    root.add_argument("--ca", type=Path)
    root.add_argument("--cert", type=Path)
    root.add_argument("--key", type=Path)
    return root


def main() -> None:
    from .distributed import PQCExperimentAgent
    from .run_context import RunContext

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parser().parse_args()
    try:
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
    except Exception as exc:
        logging.getLogger("pqc_agent").error("agent failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
