"""Ingest Claude Code OpenTelemetry-style JSON lines (file exporter)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..models import Event
from ..redact import redact


def _parse_ts(value) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            # assume ms or s
            ts = float(value)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OSError, OverflowError):
        return None
    return None


def _get(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def parse_line(line: str) -> Event | None:
    line = line.strip()
    if not line:
        return None
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        return None

    # Support a few common shapes from OTEL JSON / custom exporters
    body = d.get("body") if isinstance(d.get("body"), dict) else d
    attrs = d.get("attributes") or d.get("attr") or {}
    if isinstance(body, dict):
        attrs = {**attrs, **body}

    ts = (
        _parse_ts(_get(d, "timestamp", "time", "observedTimeUnixNano", "timeUnixNano"))
        or _parse_ts(_get(attrs, "timestamp", "time"))
        or datetime.now(tz=timezone.utc)
    )

    # Normalize nano timestamps if still huge
    if isinstance(ts, datetime) is False:
        return None

    tool = str(_get(attrs, "tool", "tool.name", "code.tool", "name", default="agent") or "agent")
    command = str(
        _get(attrs, "command", "tool.command", "input", "arguments", "code.command", default="") or ""
    )
    status = str(_get(attrs, "status", "result", "error", default="") or "").lower()
    message = command or str(_get(attrs, "message", "body", default="") or tool)

    severity = None
    if any(x in status for x in ("error", "fail", "denied")) or "error" in message.lower():
        severity = "err"

    return Event(
        timestamp=ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc),
        source=tool,
        message=redact(message)[:500],
        severity=severity,
        host=_get(attrs, "host", "host.name"),
    )


def read_claude_code_file(path: Path, since: datetime, until: datetime) -> Iterator[Event]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            ev = parse_line(line)
            if ev and since <= ev.timestamp <= until:
                yield ev
