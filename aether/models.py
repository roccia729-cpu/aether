from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Level(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"info": 0, "warning": 1, "critical": 2}[self.value]


ERROR_SEVERITIES = {"emerg", "alert", "crit", "err"}

_PATTERNS = [
    (re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b"), "<UUID>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<IP>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"\b[0-9a-fA-F]{16,}\b"), "<HEX>"),
    (re.compile(r"\b\d+\b"), "<N>"),
]


def normalize_message(message: str) -> str:
    for pattern, repl in _PATTERNS:
        message = pattern.sub(repl, message)
    return message.strip()[:200]


@dataclass
class Event:
    timestamp: datetime  # timezone-aware
    source: str
    message: str
    severity: str | None = None
    host: str | None = None

    @property
    def is_error(self) -> bool:
        return self.severity in ERROR_SEVERITIES

    @property
    def template(self) -> str:
        return f"{self.source}: {normalize_message(self.message)}"


@dataclass
class Anomaly:
    kind: str
    level: Level
    window_start: datetime
    window_end: datetime
    description: str
    evidence: dict = field(default_factory=dict)


@dataclass
class Baseline:
    created_at: datetime
    period_hours: int
    window_start: datetime
    window_end: datetime
    total_events: int
    error_total: int
    hourly_mean: dict[int, float]
    hourly_std: dict[int, float]
    templates: dict[str, int]

    @property
    def window_hours(self) -> float:
        secs = (self.window_end - self.window_start).total_seconds()
        return max(secs / 3600, 1.0)

    @property
    def avg_per_hour(self) -> float:
        return self.total_events / self.window_hours
