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


def _ensure_secure_dir(path: Path) -> None:
    """Crea la directory con permessi 0700 e, se esiste già, li forza."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass  # su alcuni filesystem/FS remoti può fallire


def _connect(path: Path) -> sqlite3.Connection:
    _ensure_secure_dir(path.parent)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)

    # Forza permessi 0600 sul database
    try:
        path.chmod(0o600)
    except OSError:
        pass

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


class BaselineError(Exception):
    """Baseline corrotta o non leggibile."""


def load(path: Path | None = None) -> Baseline | None:
    path = Path(path) if path else config.db_path()
    if not path.exists():
        return None

    try:
        conn = _connect(path)
        try:
            meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
            if not meta:
                return None

            required = {"created_at", "period_hours", "window_start", "window_end", "total_events", "error_total"}
            if not required.issubset(meta.keys()):
                raise BaselineError("Baseline metadata incompleti o corrotti")

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
    except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        raise BaselineError(f"Impossibile leggere la baseline: {exc}") from exc
