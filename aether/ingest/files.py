import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Iterator

from ..models import Event

_TAIL = r"\s+(?P<host>\S+)\s+(?P<prog>[^\s:\[]+)(?:\[\d+\])?:\s*(?P<msg>.*)$"
SYSLOG_RE = re.compile(r"^(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s\d{2}:\d{2}:\d{2})" + _TAIL)
ISO_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z))" + _TAIL
)
ERROR_RE = re.compile(
    r"\b(error|fail(?:ed|ure|ures)?|fatal|critical|denied|panic|segfault)\b", re.I
)


def _parse_ts(raw: str, iso: bool) -> datetime | None:
    try:
        if iso:
            return datetime.fromisoformat(raw).astimezone()
        now = datetime.now().astimezone()
        ts = datetime.strptime(f"{now.year} {raw}", "%Y %b %d %H:%M:%S").astimezone()
        if ts > now + timedelta(days=1):  # log from last year
            ts = ts.replace(year=now.year - 1)
        return ts
    except ValueError:
        return None


def parse_line(line: str) -> Event | None:
    iso = True
    m = ISO_RE.match(line)
    if not m:
        iso = False
        m = SYSLOG_RE.match(line)
    if not m:
        return None
    ts = _parse_ts(m["ts"], iso)
    if ts is None:
        return None
    msg = m["msg"]
    return Event(
        timestamp=ts,
        source=m["prog"],
        message=msg,
        severity="err" if ERROR_RE.search(msg) else None,
        host=m["host"],
    )


def read_files(paths: Iterable[Path], since: datetime, until: datetime) -> Iterator[Event]:
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    ev = parse_line(line.rstrip("\n"))
                    if ev and since <= ev.timestamp <= until:
                        yield ev
        except (PermissionError, FileNotFoundError) as exc:
            print(f"[aether] skipped {path}: {exc.__class__.__name__}", file=sys.stderr)
