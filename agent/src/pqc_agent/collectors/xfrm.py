from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class XfrmState:
    spi: str
    packets: int
    bytes: int
    lifetime_seconds: int
    replay_errors: int
    integrity_errors: int
    state: str = "installed"


class XfrmCollector:
    def collect(self) -> list[XfrmState]:
        result = subprocess.run(["ip", "-s", "xfrm", "state"], text=True,
                                capture_output=True, check=False)
        return self.parse(result.stdout) if result.returncode == 0 else []

    @staticmethod
    def parse(text: str) -> list[XfrmState]:
        states = []
        blocks = re.split(r"(?=^src \S+ dst \S+)", text, flags=re.MULTILINE)
        for block in blocks:
            spi = re.search(r"\bspi (0x[0-9a-f]+)", block, re.I)
            current = re.search(r"lifetime current:\s*\n\s*([0-9]+)\(bytes\), ([0-9]+)\(packets\)", block)
            if not spi or not current:
                continue
            added = re.search(r"\badd ([0-9]+)\(sec\)", block)
            replay = re.search(r"replay-window \d+ replay ([0-9]+) failed ([0-9]+)", block)
            states.append(XfrmState(
                spi=spi.group(1), bytes=int(current.group(1)), packets=int(current.group(2)),
                lifetime_seconds=int(added.group(1)) if added else 0,
                replay_errors=int(replay.group(1)) if replay else 0,
                integrity_errors=int(replay.group(2)) if replay else 0,
            ))
        return states

