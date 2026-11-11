from datetime import datetime, timedelta, timezone

from aether.baseline import builder, store
from aether.models import Event


def _events(n, start):
    return [
        Event(start + timedelta(minutes=i), "app", f"request {i} ok")
        for i in range(n)
    ]


def test_build_and_roundtrip(tmp_path):
    until = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    since = until - timedelta(hours=5)
    base = builder.build_baseline(_events(120, since), since, until, 5)
    assert base.total_events == 120
    assert "app: request <N> ok" in base.templates

    path = store.save(base, tmp_path / "b.db")
    loaded = store.load(path)
    assert loaded is not None
    assert loaded.total_events == 120
    assert loaded.templates == base.templates


def test_load_missing_returns_none(tmp_path):
    assert store.load(tmp_path / "nope.db") is None
