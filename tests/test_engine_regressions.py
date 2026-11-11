from datetime import datetime, timedelta, timezone

from aether.baseline import builder
from aether.detect.engine import detect
from aether.models import Event


def _quiet_baseline():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    since = now - timedelta(hours=72)
    normal = [Event(since + timedelta(minutes=30 * i), "app", "tick ok") for i in range(144)]
    return builder.build_baseline(normal, since, now, 72), now


def test_new_message_window_is_ordered_even_if_events_are_not():
    base, now = _quiet_baseline()
    events = [
        Event(now + timedelta(minutes=50), "x", "boom"),
        Event(now + timedelta(minutes=5), "x", "boom"),
    ]
    found = [a for a in detect(base, events, now, now + timedelta(hours=1)) if a.kind == "new_message"]
    assert found
    assert found[0].window_start <= found[0].window_end


def test_single_error_burst_is_one_anomaly():
    base, now = _quiet_baseline()
    events = [
        Event(now + timedelta(seconds=6 * i), "app", "disk failure", severity="err")
        for i in range(300)
    ]
    bursts = [a for a in detect(base, events, now, now + timedelta(hours=1)) if a.kind == "error_burst"]
    assert len(bursts) == 1
    assert bursts[0].evidence["errors"] == 300


def test_few_events_in_short_window_are_not_a_volume_spike():
    base, now = _quiet_baseline()
    events = [Event(now + timedelta(seconds=40 * i), "app", "tick ok") for i in range(3)]
    found = detect(base, events, now, now + timedelta(minutes=2))
    assert not [a for a in found if a.kind.startswith("volume")]


def test_rare_message_is_not_reported_missing():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    since = now - timedelta(hours=72)
    rare = [Event(since + timedelta(minutes=20 * i), "cron", "job ran") for i in range(216)]
    base = builder.build_baseline(rare, since, now, 72)  # ~3 per hour
    other = [Event(now + timedelta(minutes=1), "x", "other")]
    found = detect(base, other, now, now + timedelta(hours=1))
    assert not [a for a in found if a.kind == "missing_message"]


def test_single_new_message_without_errors_is_info():
    base, now = _quiet_baseline()
    events = [Event(now + timedelta(minutes=3), "x", "hello once")]
    found = [a for a in detect(base, events, now, now + timedelta(hours=1)) if a.kind == "new_message"]
    assert found and found[0].level.value == "info"
