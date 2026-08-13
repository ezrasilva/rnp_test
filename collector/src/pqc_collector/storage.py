from __future__ import annotations

import csv
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TelemetryStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / "index.db", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS received (run_id TEXT, node_id TEXT, sequence INTEGER, PRIMARY KEY(run_id,node_id,sequence))")
        self.db.commit()
        self.lock = threading.Lock()

    def ingest(self, event, payload: dict[str, Any]) -> tuple[bool, int, list[int]]:
        run_dir = self.root / event.run_id
        node_dir = run_dir / event.node_id
        node_dir.mkdir(parents=True, exist_ok=True)
        with self.lock, self.db:
            cursor = self.db.execute("INSERT OR IGNORE INTO received VALUES (?,?,?)",
                                     (event.run_id, event.node_id, event.sequence_number))
            inserted = cursor.rowcount == 1
            if inserted:
                record = {
                    "run_id": event.run_id, "node_id": event.node_id,
                    "timestamp_ns": event.timestamp_ns,
                    "sequence_number": event.sequence_number,
                    "event_type": event.type, "payload": payload,
                }
                with (node_dir / "telemetry.jsonl").open("a") as stream:
                    stream.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
                target = ("events.jsonl" if event.type == 1 else
                          None if event.type == 5 else "metrics.csv")
                if target and target.endswith("jsonl"):
                    with (node_dir / target).open("a") as stream:
                        stream.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
                elif target:
                    path = node_dir / target
                    with path.open("a", newline="") as stream:
                        writer = csv.DictWriter(stream, fieldnames=record.keys())
                        if path.stat().st_size == 0:
                            writer.writeheader()
                        writer.writerow(record)
                self._update_manifest(run_dir, event.run_id, event.node_id,
                                      payload.get("node_metadata"))
            sequences = [row[0] for row in self.db.execute(
                "SELECT sequence FROM received WHERE run_id=? AND node_id=? ORDER BY sequence",
                (event.run_id, event.node_id))]
            last = max(sequences, default=0)
            missing = sorted(set(range(1, last + 1)) - set(sequences))
            self._update_summary(run_dir, event.run_id)
            return inserted, last, missing

    def _update_manifest(self, run_dir: Path, run_id: str, node_id: str,
                         metadata: dict[str, Any] | None = None) -> None:
        path = run_dir / "manifest.json"
        manifest = json.loads(path.read_text()) if path.exists() else {
            "run_id": run_id, "start_time": datetime.now(timezone.utc).isoformat(),
            "mode": "unknown", "nodes": [], "kernel_versions": {},
            "agent_versions": {}, "strongswan_version": None,
            "sample_interval_seconds": None,
        }
        if node_id not in manifest["nodes"]:
            manifest["nodes"].append(node_id)
            manifest["nodes"].sort()
        if metadata:
            mode = metadata.get("mode")
            if mode and manifest["mode"] not in ("unknown", mode):
                raise ValueError("nodes reported inconsistent experiment modes")
            manifest["mode"] = mode or manifest["mode"]
            manifest["kernel_versions"][node_id] = metadata.get("kernel_version", "")
            manifest["agent_versions"][node_id] = metadata.get("agent_version", "")
            version = metadata.get("strongswan_version")
            if version:
                manifest["strongswan_version"] = version
            interval = metadata.get("sample_interval_seconds")
            if interval is not None:
                manifest["sample_interval_seconds"] = interval
            manifest.setdefault("collector_enabled", {})[node_id] = metadata.get(
                "collector_enabled", False)
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    def _update_summary(self, run_dir: Path, run_id: str) -> None:
        rows = self.db.execute(
            "SELECT node_id, COUNT(*), MIN(sequence), MAX(sequence) FROM received WHERE run_id=? GROUP BY node_id",
            (run_id,),
        ).fetchall()
        summary = {
            "run_id": run_id,
            "nodes": {row[0]: {"events_received": row[1], "first_sequence": row[2],
                                "last_sequence": row[3],
                                "has_gaps": row[1] != row[3] - row[2] + 1}
                      for row in rows},
        }
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    def count(self, run_id: str, node_id: str) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM received WHERE run_id=? AND node_id=?",
                                   (run_id, node_id)).fetchone()[0])
