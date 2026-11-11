import os
from pathlib import Path

DEFAULT_PERIOD_HOURS = 72
DEFAULT_SCAN_HOURS = 1
DEFAULT_LOG_FILES = [
    "/var/log/syslog",
    "/var/log/auth.log",
    "/var/log/messages",
    "/var/log/secure",
]


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "aether"


def db_path() -> Path:
    return data_dir() / "baseline.db"


def existing_log_files() -> list[Path]:
    return [Path(p) for p in DEFAULT_LOG_FILES if Path(p).exists()]
