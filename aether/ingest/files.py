import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Iterator

from ..models import Event

# Formati supportati:
# 1. Syslog classico:  "Nov 11 14:32:01 hostname prog[123]: message"
# 2. ISO + host/prog:  "2026-11-11T14:32:01+01:00 hostname prog: message"
# 3. ISO semplice:     "2026-11-11T14:32:01+01:00 message"  (senza host/prog)
# 4. Syslog senza host (alcuni container / applicazioni)

_SYSLOG_TS = r"(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s\d{2}:\d{2}:\d{2})"
_ISO_TS = r"(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?)"

# Con host + programma
SYSLOG_FULL = re.compile(
    rf"^{_SYSLOG_TS}\s+(?P<host>\S+)\s+(?P<prog>[^\s:\[]+)(?:\[\d+\])?:\s*(?P<msg>.*)$"
)
ISO_FULL = re.compile(
    rf"^{_ISO_TS}\s+(?P<host>\S+)\s+(?P<prog>[^\s:\[]+)(?:\[\d+\])?:\s*(?P<msg>.*)$"
)

# Senza host (prog + messaggio)
SYSLOG_NO_HOST = re.compile(
    rf"^{_SYSLOG_TS}\s+(?P<prog>[^\s:\[]+)(?:\[\d+\])?:\s*(?P<msg>.*)$"
)
ISO_NO_HOST = re.compile(
    rf"^{_ISO_TS}\s+(?P<prog>[^\s:\[]+)(?:\[\d+\])?:\s*(?P<msg>.*)$"
)

# Solo timestamp + messaggio (fallback)
ISO_MSG_ONLY = re.compile(rf"^{_ISO_TS}\s+(?P<msg>.*)$")
SYSLOG_MSG_ONLY = re.compile(rf"^{_SYSLOG_TS}\s+(?P<msg>.*)$")

ERROR_RE = re.compile(
    r"\b(error|fail(?:ed|ure|ures)?|fatal|critical|denied|panic|segfault|oom|killed)\b",
    re.I,
)


def _parse_ts(raw: str, iso: bool) -> datetime | None:
    try:
        if iso:
            # gestisce anche 'Z'
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            return datetime.fromisoformat(raw).astimezone()
        now = datetime.now().astimezone()
        ts = datetime.strptime(f"{now.year} {raw}", "%Y %b %d %H:%M:%S").astimezone()
        # se il timestamp è nel futuro di più di 1 giorno, probabilmente è dell'anno scorso
        if ts > now + timedelta(days=1):
            ts = ts.replace(year=now.year - 1)
        return ts
    except ValueError:
        return None


def parse_line(line: str) -> Event | None:
    line = line.rstrip("\n")
    if not line or line.startswith("#"):
        return None

    patterns = [
        (ISO_FULL, True, True),        # iso + host + prog
        (SYSLOG_FULL, False, True),    # syslog + host + prog
        (ISO_NO_HOST, True, False),    # iso + prog
        (SYSLOG_NO_HOST, False, False),# syslog + prog
        (ISO_MSG_ONLY, True, False),   # iso + solo messaggio
        (SYSLOG_MSG_ONLY, False, False),
    ]

    for regex, is_iso, has_host in patterns:
        m = regex.match(line)
        if not m:
            continue

        ts = _parse_ts(m["ts"], is_iso)
        if ts is None:
            return None

        msg = m.groupdict().get("msg") or ""
        prog = m.groupdict().get("prog") or "unknown"
        host = m.groupdict().get("host") if has_host else None

        return Event(
            timestamp=ts,
            source=prog,
            message=msg,
            severity="err" if ERROR_RE.search(msg) else None,
            host=host,
        )

    return None


def read_files(paths: Iterable[Path], since: datetime, until: datetime) -> Iterator[Event]:
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    ev = parse_line(line)
                    if ev and since <= ev.timestamp <= until:
                        yield ev
        except (PermissionError, FileNotFoundError) as exc:
            print(f"[aether] skipped {path}: {exc.__class__.__name__}", file=sys.stderr)
