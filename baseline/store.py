import sqlite3
from datetime import datetime
from pathlib import Path

from .. import config
from ..models import Baseline

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS hourly (hour INTEGER PRIMARY KEY, mean REAL, std REAL);
CREATE TABLE IF NOT EXISTS templates (template TEXT PRIMARY KEY, count INTEGER);
"""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def save(b: Baseline, path: Path | None = None) -> Path:
    path = Path(path) if path else config.db_path()
    conn = _connect(path)
    try:
        with conn:
            for t in ("meta", "hourly", "templates"):
                conn.execute(f"DELETE FROM {t}")
            meta = {
                "created_at": b.created_at.isoformat(),
                "period_hours": str(b.period_hours),
                "window_start": b.window_start.isoformat(),
                "window_end": b.window_end.isoformat(),
                "total_events": str(b.total_events),
                "error_total": str(b.error_total),
            }
            conn.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
            conn.executemany(
                "INSERT INTO hourly VALUES (?, ?, ?)",
                [(h, m, b.hourly_std.get(h, 0.0)) for h, m in b.hourly_mean.items()],
            )
            conn.executemany("INSERT INTO templates VALUES (?, ?)", b.templates.items())
    finally:
        conn.close()
    return path


def load(path: Path | None = None) -> Baseline | None:
    path = Path(path) if path else config.db_path()
    if not path.exists():
        return None
    conn = _connect(path)
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        if not meta:
            return None
        hourly = conn.execute("SELECT hour, mean, std FROM hourly").fetchall()
        templates = dict(conn.execute("SELECT template, count FROM templates").fetchall())
    finally:
        conn.close()
    return Baseline(
        created_at=datetime.fromisoformat(meta["created_at"]),
        period_hours=int(meta["period_hours"]),
        window_start=datetime.fromisoformat(meta["window_start"]),
        window_end=datetime.fromisoformat(meta["window_end"]),
        total_events=int(meta["total_events"]),
        error_total=int(meta["error_total"]),
        hourly_mean={h: m for h, m, _ in hourly},
        hourly_std={h: s for h, _, s in hourly},
        templates=templates,
    )
