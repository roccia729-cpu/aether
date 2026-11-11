from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, pstdev
from typing import Iterable

from ..models import Baseline, Event


def hour_floor(ts: datetime) -> datetime:
    return ts.astimezone().replace(minute=0, second=0, microsecond=0)


def build_baseline(
    events: Iterable[Event], since: datetime, until: datetime, period_hours: int
) -> Baseline:
    counts: dict[datetime, int] = defaultdict(int)
    templates: dict[str, int] = defaultdict(int)
    total = errors = 0

    for ev in events:
        counts[hour_floor(ev.timestamp)] += 1
        templates[ev.template] += 1
        total += 1
        if ev.is_error:
            errors += 1

    # only full hours, zeros included
    by_hour: dict[int, list[int]] = defaultdict(list)
    cur = hour_floor(since)
    if cur < since:
        cur += timedelta(hours=1)
    while cur + timedelta(hours=1) <= until:
        by_hour[cur.astimezone().hour].append(counts.get(cur, 0))
        cur += timedelta(hours=1)

    return Baseline(
        created_at=datetime.now().astimezone(),
        period_hours=period_hours,
        window_start=since,
        window_end=until,
        total_events=total,
        error_total=errors,
        hourly_mean={h: mean(v) for h, v in by_hour.items()},
        hourly_std={h: (pstdev(v) if len(v) > 1 else 0.0) for h, v in by_hour.items()},
        templates=dict(templates),
    )
