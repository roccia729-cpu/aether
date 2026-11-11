from collections import Counter
from datetime import datetime, timedelta, timezone

from ..baseline.builder import hour_floor
from ..models import Anomaly, Baseline, Event, Level, normalize_message

BIN = 300  # seconds, for error bursts
MAX_NEW = 15
MAX_MISSING = 10


def detect(baseline: Baseline, events: list[Event], since: datetime, until: datetime) -> list[Anomaly]:
    found: list[Anomaly] = []
    found += _volume(baseline, events, since, until)
    found += _new_templates(baseline, events, since, until)
    found += _missing_templates(baseline, events, since, until)
    found += _error_bursts(baseline, events)
    found.sort(key=lambda a: (-a.level.rank, a.window_start))
    return found


def _volume(b: Baseline, events, since, until) -> list[Anomaly]:
    """Confronta tassi (eventi/ora) tenendo conto della durata reale della finestra."""
    counts = Counter(hour_floor(e.timestamp) for e in events)
    out = []
    cur = hour_floor(since)

    while cur < until:
        end = cur + timedelta(hours=1)
        w_start = max(cur, since)
        w_end = min(end, until)

        duration_h = max((w_end - w_start).total_seconds() / 3600.0, 1e-6)
        n = counts.get(cur, 0)
        rate = n / duration_h

        h = cur.astimezone().hour
        mean = b.hourly_mean.get(h, b.avg_per_hour)
        std = b.hourly_std.get(h, 0.0)
        threshold = max(mean + 3 * std, mean * 3, 20)

        evidence = {
            "events": n,
            "duration_min": round(duration_h * 60, 1),
            "rate_per_hour": round(rate, 1),
            "baseline_avg": round(mean, 1),
            "threshold": round(threshold, 1),
        }

        if rate >= threshold:
            level = Level.CRITICAL if rate >= 2 * threshold else Level.WARNING
            out.append(Anomaly(
                "volume_spike",
                level,
                w_start,
                w_end,
                f"Log volume spike: {n} events in {duration_h*60:.0f} min (≈{rate:.0f}/h vs ~{mean:.0f} expected)",
                evidence,
            ))
        elif duration_h >= 0.75 and mean >= 50 and rate < mean * 0.2:
            out.append(Anomaly(
                "volume_drop",
                Level.WARNING,
                w_start,
                w_end,
                f"Log volume drop: {n} events in {duration_h*60:.0f} min (≈{rate:.0f}/h vs ~{mean:.0f} expected)",
                evidence,
            ))

        cur = end

    return out


def _new_templates(
    b: Baseline,
    events: list[Event],
    since: datetime,
    until: datetime
) -> list[Anomaly]:
    """
    Detects log message templates that were never observed
    in the historical baseline.
    """

    seen = Counter()
    errors = Counter()
    first = {}
    last = {}

    # Consider only events inside the requested time window
    for event in events:
        if not (since <= event.timestamp < until):
            continue

        template = event.template

        # Ignore templates already present in the baseline
        if template in b.templates:
            continue

        seen[template] += 1

        if event.is_error:
            errors[template] += 1

        if template not in first:
            first[template] = event.timestamp

        last[template] = event.timestamp

    anomalies = []

    # Prioritize the most frequently observed new templates
    for template, count in seen.most_common(MAX_NEW):

        error_count = errors[template]

        level = (
            Level.CRITICAL
            if error_count >= 5
            else Level.WARNING
        )

        evidence = {
            "template": template,
            "occurrences": count,
            "error_occurrences": error_count,
            "first_seen": first[template].isoformat(),
            "last_seen": last[template].isoformat(),
            "baseline_occurrences": 0,
        }

        anomalies.append(
            Anomaly(
                kind="new_message",
                level=level,
                window_start=first[template],
                window_end=last[template],
                description=(
                    f"New log template detected: "
                    f"{template[:100]} "
                    f"({count} occurrences, "
                    f"{error_count} errors)"
                ),
                evidence=evidence,
            )
        )

    return anomalies
