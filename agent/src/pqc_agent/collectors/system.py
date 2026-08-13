from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(frozen=True, slots=True)
class SystemSample:
    cpu_percent: float
    memory_bytes: int
    charon_cpu_percent: float
    charon_memory_bytes: int


class SystemCollector:
    def collect(self) -> SystemSample:
        virtual = psutil.virtual_memory()
        charon_cpu = 0.0
        charon_memory = 0
        for process in psutil.process_iter(("name", "cmdline", "memory_info")):
            try:
                command = " ".join(process.info.get("cmdline") or [])
                if process.info.get("name") == "charon" or "/charon" in command:
                    charon_cpu += process.cpu_percent(interval=None)
                    charon_memory += process.info["memory_info"].rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return SystemSample(psutil.cpu_percent(interval=None), virtual.used,
                            charon_cpu, charon_memory)

