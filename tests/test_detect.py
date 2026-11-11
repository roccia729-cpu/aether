from datetime import datetime, timedelta, timezone

from aether.baseline import builder
from aether.detect.engine import detect
from aether.models import Event


def test_new_message_and_spike_detected():
    until = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    since = until - timedelta(hours=24)
    normal = [
        Event(since + timedelta(minutes=10 * i), "app", "heartbeat ok")
        for i in range(24 * 6)
    ]
    base = builder.build_baseline(normal, since, until, 24)

    r_since = until
    r_until = until + timedelta(hours=1)
    recent = [
        Event(r_since + timedelta(seconds=i), "app", "disk failure on sda", severity="err")
        for i in range(100)
    ]
    kinds = {a.kind for a in detect(base, recent, r_since, r_until)}
    assert "new_message" in kinds
    assert "volume_spike" in kinds
    assert "missing_message" in kinds or "error_burst" in kinds
