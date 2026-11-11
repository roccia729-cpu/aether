import json
import subprocess
from datetime import datetime, timezone
from typing import Iterator

from ..models import Event

PRIORITIES = ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]


class JournalError(RuntimeError):
    pass


def _fmt(dt: datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _text(value) -> str:
    if isinstance(value, list):
        return bytes(value).decode("utf-8", "replace")
    return str(value)


def read_journal(since: datetime, until: datetime | None = None) -> Iterator[Event]:
    cmd = ["journalctl", "-o", "json", "--no-pager", "-q", "--since", _fmt(since)]
    if until:
        cmd += ["--until", _fmt(until)]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise JournalError("journalctl not found (is this a systemd machine?)") from exc

    assert proc.stdout is not None
    for line in proc.stdout:
        try:
            d = json.loads(line)
            ts = datetime.fromtimestamp(int(d["__REALTIME_TIMESTAMP"]) / 1e6, tz=timezone.utc)
        except (ValueError, KeyError):
            continue
        prio = d.get("PRIORITY")
        severity = None
        if prio is not None and str(prio).isdigit() and int(prio) < len(PRIORITIES):
            severity = PRIORITIES[int(prio)]
        yield Event(
            timestamp=ts,
            source=_text(d.get("SYSLOG_IDENTIFIER") or d.get("_COMM") or "unknown"),
            message=_text(d.get("MESSAGE", "")),
            severity=severity,
            host=d.get("_HOSTNAME"),
        )
    proc.wait()
    if proc.returncode != 0:
        raise JournalError(f"journalctl exited with code {proc.returncode}")
