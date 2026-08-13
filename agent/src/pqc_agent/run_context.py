from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunContext:
    run_id: str
    node_id: str
    mode: str = "unknown"

    def __post_init__(self) -> None:
        for label, value in (("run_id", self.run_id), ("node_id", self.node_id)):
            if not value or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for char in value):
                raise ValueError(f"invalid {label}: {value!r}")

