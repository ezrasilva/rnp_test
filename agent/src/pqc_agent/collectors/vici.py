from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IkeObservation:
    event: str
    ike_sa_id: str = ""
    child_sa_id: str = ""
    proposal: str = ""
    authentication: str = ""


class ViciCollector:
    """Detects state transitions via the VICI-backed swanctl interface."""

    def __init__(self) -> None:
        self._known_ike: set[str] = set()
        self._known_child: set[str] = set()

    def collect_events(self) -> list[IkeObservation]:
        result = subprocess.run(["swanctl", "--list-sas", "--pretty"], text=True,
                                capture_output=True, check=False)
        if result.returncode:
            return []
        text = result.stdout
        ike = set(re.findall(r"uniqueid = ([0-9]+).*?state = ESTABLISHED", text, re.S))
        child = set(re.findall(r"child-sas \{.*?uniqueid = ([0-9]+).*?state = INSTALLED", text, re.S))
        proposal = "/".join(re.findall(r"(?:dh-group|ake1|encr-alg) = (\S+)", text))
        events = [IkeObservation("IKE_SA_ESTABLISHED", value, proposal=proposal)
                  for value in sorted(ike - self._known_ike)]
        events += [IkeObservation("CHILD_SA_INSTALLED", child_sa_id=value, proposal=proposal)
                   for value in sorted(child - self._known_child)]
        events += [IkeObservation("SA_DELETED", value) for value in sorted(self._known_ike - ike)]
        self._known_ike, self._known_child = ike, child
        return events

