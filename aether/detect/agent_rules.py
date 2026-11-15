"""Heuristic rules for risky agent actions."""

from __future__ import annotations

import re
from datetime import datetime

from ..models import Anomaly, Event, Level

_RISKY = [
    (re.compile(r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?(/|~|\.\.)"), "broad rm -rf style delete"),
    (re.compile(r"\bgit\s+push\s+.*--force"), "git force push"),
    (re.compile(r"\b(drop\s+(table|database)|truncate\s+table)\b", re.I), "destructive SQL"),
    (re.compile(r"\bterraform\s+destroy\b", re.I), "terraform destroy"),
    (re.compile(r"\b(aws|gcloud|az)\s+.*\b(delete|rm|remove)\b", re.I), "cloud delete"),
    (re.compile(r"\bchmod\s+-R\s+777\b"), "chmod -R 777"),
    (re.compile(r"\bcurl\s+[^\n]*\|\s*(sh|bash)\b"), "curl | sh"),
    (re.compile(r"\b(cat|printenv|env)\b.*\b(AWS_|SECRET|TOKEN|PASSWORD)\b", re.I), "credential access"),
]


def find_risky_actions(events: list[Event], since: datetime, until: datetime) -> list[Anomaly]:
    out: list[Anomaly] = []
    for e in events:
        msg = e.message or ""
        for rx, label in _RISKY:
            if rx.search(msg):
                out.append(
                    Anomaly(
                        kind="risky_action",
                        level=Level.CRITICAL,
                        window_start=e.timestamp,
                        window_end=e.timestamp,
                        description=f"Risky agent action: {label}",
                        evidence={"tool": e.source, "sample": msg[:200], "rule": label},
                    )
                )
                break
    return out
