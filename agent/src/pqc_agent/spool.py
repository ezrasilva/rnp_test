from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Iterable


class LocalSpool:
    """Transactional, per-run/node store-and-forward queue."""

    def __init__(self, root: Path, run_id: str, node_id: str) -> None:
        self.directory = root / run_id / node_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "spool.db"
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, payload BLOB NOT NULL, acked INTEGER NOT NULL DEFAULT 0)")
        self._db.commit()

    def append(self, payload: bytes) -> int:
        with self._lock, self._db:
            row = self._db.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM events").fetchone()
            sequence = int(row[0])
            self._db.execute("INSERT INTO events(sequence, payload) VALUES (?, ?)", (sequence, payload))
            return sequence

    def replace(self, sequence: int, payload: bytes) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE events SET payload=? WHERE sequence=?", (payload, sequence))

    def pending(self, limit: int = 1000) -> list[tuple[int, bytes]]:
        with self._lock:
            return [(int(row[0]), bytes(row[1])) for row in self._db.execute(
                "SELECT sequence, payload FROM events WHERE acked=0 ORDER BY sequence LIMIT ?", (limit,)
            )]

    def acknowledge(self, last_sequence: int, missing: Iterable[int] = ()) -> None:
        missing_values = tuple(int(value) for value in missing)
        with self._lock, self._db:
            self._db.execute("UPDATE events SET acked=1 WHERE sequence <= ?", (last_sequence,))
            if missing_values:
                placeholders = ",".join("?" for _ in missing_values)
                self._db.execute(f"UPDATE events SET acked=0 WHERE sequence IN ({placeholders})", missing_values)

    def pending_count(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM events WHERE acked=0").fetchone()[0])

    def close(self) -> None:
        self._db.close()

