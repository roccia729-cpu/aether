import json
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from typing import Iterator

from ..models import Event

PRIORITIES = ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]
DEFAULT_TIMEOUT = 300  # seconds


class JournalError(RuntimeError):
    pass


def _fmt(dt: datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _text(value) -> str:
    if isinstance(value, list):
        return bytes(value).decode("utf-8", "replace")
    return str(value)


def read_journal(
    since: datetime,
    until: datetime | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Iterator[Event]:
    cmd = ["journalctl", "-o", "json", "--no-pager", "-q", "--since", _fmt(since)]
    if until:
        cmd += ["--until", _fmt(until)]

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errfile:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=errfile,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            raise JournalError("journalctl not found (is this a systemd machine?)") from exc

        timed_out = threading.Event()

        def _kill() -> None:
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout, _kill)
        timer.daemon = True
        timer.start()

        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                try:
                    d = json.loads(line)
                    ts = datetime.fromtimestamp(
                        int(d["__REALTIME_TIMESTAMP"]) / 1e6, tz=timezone.utc
                    )
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
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            if proc.stdout:
                proc.stdout.close()

        if timed_out.is_set():
            raise JournalError(f"journalctl timed out after {timeout}s")
        if proc.returncode != 0:
            errfile.seek(0)
            err = errfile.read().strip()
            raise JournalError(f"journalctl failed (code {proc.returncode}): {err[:200]}")
