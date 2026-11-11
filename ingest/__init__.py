import shutil
from datetime import datetime
from pathlib import Path

from .. import config
from ..models import Event
from . import files, journald


def collect(
    since: datetime,
    until: datetime,
    source: str = "auto",
    paths: list[Path] | None = None,
) -> list[Event]:
    if source == "auto":
        source = "journald" if shutil.which("journalctl") else "files"
    if source == "journald":
        return list(journald.read_journal(since, until))
    if source == "files":
        return list(files.read_files(paths or config.existing_log_files(), since, until))
    raise ValueError(f"Unknown source: {source}")
