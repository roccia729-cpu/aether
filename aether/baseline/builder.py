from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, pstdev
from typing import Iterable

from ..models import Baseline, Event


def hour_floor(ts: datetime) -> datetime:
    """Arrotonda all'inizio dell'ora in timezone locale.
    Usa sempre il timezone del timestamp (deve essere aware).
    """
    if ts.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    local = ts.astimezone()
    return local.replace(minute=0, second=0, microsecond=0)


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

    # Aggregazione per ora del giorno (0-23) usando solo ore "piene"
    # Durante i cambi DST alcune ore possono essere saltate o ripetute:
    # prendiamo solo slot da 1 ora intera e usiamo l'ora locale risultante.
    by_hour: dict[int, list[int]] = defaultdict(list)

    cur = hour_floor(since)
    if cur < since:
        cur += timedelta(hours=1)

    while cur + timedelta(hours=1) <= until:
        next_hour = cur + timedelta(hours=1)

        # Se il salto non è di ~1 ora (cambio DST), saltiamo lo slot ambiguo
        delta = (next_hour - cur).total_seconds()
        if abs(delta - 3600) > 60:
            cur = next_hour
            continue

        hour_of_day = cur.hour  # già in timezone locale
        by_hour[hour_of_day].append(counts.get(cur, 0))
        cur = next_hour

    return Baseline(
        created_at=datetime.now().astimezone(),
        period_hours=period_hours,
        window_start=since,
        window_end=until,
        total_events=total,
        error_total=errors,
        hourly_mean={h: mean(v) for h, v in by_hour.items() if v},
        hourly_std={h: (pstdev(v) if len(v) > 1 else 0.0) for h, v in by_hour.items() if v},
        templates=dict(templates),
    )
