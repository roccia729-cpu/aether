"""Anomaly detection: compare a recent window of events with the baseline."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from ..baseline.builder import hour_floor
from ..models import Anomaly, Baseline, Event, Level

BIN_SECONDS = 300  # error bursts are counted in 5-minute bins
BIN = BIN_SECONDS  # kept for backwards compatibility
MAX_NEW = 15  # max "new message" anomalies per scan
MAX_MISSING = 10  # max "missing message" anomalies per scan
MIN_SPIKE_EVENTS = 10  # a volume spike needs at least this many events
MIN_EXPECTED_MISSING = 10  # a message is "missing" only if >= this many were expected
MIN_BURST_ERRORS = 5  # an error burst needs at least this many errors per bin


def detect(
    baseline: Baseline,
    events: list[Event],
    since: datetime,
    until: datetime,
) -> list[Anomaly]:
    """Return anomalies found in [since, until), most severe first."""
    if until <= since:
        return []

    events = [e for e in events if since <= e.timestamp < until]

    found: list[Anomaly] = []
    found += _volume(baseline, events, since, until)
    found += _new_templates(baseline, events, since, until)
    found += _missing_templates(baseline, events, since, until)
    found += _error_bursts(baseline, events)
    found.sort(key=lambda a: (-a.level.rank, a.window_start))
    return found


def _volume(
    b: Baseline, events: list[Event], since: datetime, until: datetime
) -> list[Anomaly]:
    """Unusual increase or decrease of log volume, hour by hour."""
    counts = Counter(hour_floor(e.timestamp) for e in events)
    out: list[Anomaly] = []
    cur = hour_floor(since)

    while cur < until:
        end = cur + timedelta(hours=1)
        w_start, w_end = max(cur, since), min(end, until)
        hours = max((w_end - w_start).total_seconds() / 3600, 1e-6)
        minutes = round(hours * 60)

        count = counts.get(cur, 0)
        rate = count / hours
        hour = cur.astimezone().hour
        mean = b.hourly_mean.get(hour, b.avg_per_hour)
        std = b.hourly_std.get(hour, 0.0)
        threshold = max(mean + 3 * std, mean * 3, 20)

        evidence = {
            "events": count,
            "duration_min": minutes,
            "rate_per_hour": round(rate, 1),
            "baseline_avg_per_hour": round(mean, 1),
            "threshold_per_hour": round(threshold, 1),
        }

        if count >= MIN_SPIKE_EVENTS and rate >= threshold:
            level = Level.CRITICAL if rate >= 2 * threshold else Level.WARNING
            out.append(
                Anomaly(
                    "volume_spike",
                    level,
                    w_start,
                    w_end,
                    f"Log volume spike: {count} events in {minutes} min "
                    f"(~{rate:.0f}/h vs ~{mean:.0f}/h expected)",
                    evidence,
                )
            )
        elif hours >= 0.75 and mean >= 50 and rate < mean * 0.2:
            out.append(
                Anomaly(
                    "volume_drop",
                    Level.WARNING,
                    w_start,
                    w_end,
                    f"Log volume drop: {count} events in {minutes} min "
                    f"(~{rate:.0f}/h vs ~{mean:.0f}/h expected)",
                    evidence,
                )
            )
        cur = end
    return out


def _new_templates(
    b: Baseline, events: list[Event], since: datetime, until: datetime
) -> list[Anomaly]:
    """Message templates never seen in the baseline."""
    seen: Counter = Counter()
    errors: Counter = Counter()
    first: dict[str, datetime] = {}
    last: dict[str, datetime] = {}

    for e in events:
        if not (since <= e.timestamp < until):
            continue
        t = e.template
        if t in b.templates:
            continue
        seen[t] += 1
        if e.is_error:
            errors[t] += 1
        # min/max: events may arrive out of order (e.g. several log files)
        first[t] = min(first.get(t, e.timestamp), e.timestamp)
        last[t] = max(last.get(t, e.timestamp), e.timestamp)

    out: list[Anomaly] = []
    for t, n in seen.most_common(MAX_NEW):
        n_err = errors[t]
        if n_err >= 5:
            level = Level.CRITICAL
        elif n_err > 0 or n >= 10:
            level = Level.WARNING
        else:
            level = Level.INFO
        out.append(
            Anomaly(
                "new_message",
                level,
                first[t],
                last[t],
                f"New message never seen in baseline: {t[:100]} "
                f"({n} times, {n_err} errors)",
                {
                    "template": t,
                    "occurrences": n,
                    "error_occurrences": n_err,
                    "first_seen": first[t].isoformat(timespec="seconds"),
                    "last_seen": last[t].isoformat(timespec="seconds"),
                },
            )
        )
    return out


def _missing_templates(
    b: Baseline, events: list[Event], since: datetime, until: datetime
) -> list[Anomaly]:
    """Frequent baseline messages that did not appear at all in the window."""
    hours = (until - since).total_seconds() / 3600
    if hours <= 0 or b.window_hours <= 0:
        return []

    present = {e.template for e in events}
    candidates: list[tuple[float, str, int]] = []
    for t, count in b.templates.items():
        if count <= 0 or t in present:
            continue
        expected = count / b.window_hours * hours
        if expected >= MIN_EXPECTED_MISSING:
            candidates.append((expected, t, count))
    candidates.sort(reverse=True)

    return [
        Anomaly(
            "missing_message",
            Level.WARNING,
            since,
            until,
            f"Expected message disappeared: {t[:100]} "
            f"(~{expected:.0f} expected, 0 seen)",
            {
                "template": t,
                "expected_in_window": round(expected, 1),
                "baseline_count": count,
                "baseline_hours": round(b.window_hours, 1),
                "observation_hours": round(hours, 2),
                "seen": 0,
            },
        )
        for expected, t, count in candidates[:MAX_MISSING]
    ]


def _error_bursts(b: Baseline, events: list[Event]) -> list[Anomaly]:
    """Concentrations of errors in short windows; adjacent hot bins are merged."""
    bins: dict[int, list[Event]] = defaultdict(list)
    for e in events:
        if e.is_error:
            bins[int(e.timestamp.timestamp() // BIN_SECONDS)].append(e)
    if not bins:
        return []

    rate_per_hour = b.error_total / b.window_hours
    expected = rate_per_hour * BIN_SECONDS / 3600
    threshold = max(MIN_BURST_ERRORS, expected * 3)

    groups: list[list[int]] = []
    for k in sorted(k for k, v in bins.items() if len(v) >= threshold):
        if groups and k == groups[-1][-1] + 1:
            groups[-1].append(k)
        else:
            groups.append([k])

    out: list[Anomaly] = []
    for g in groups:
        evs = [e for k in g for e in bins[k]]
        total = len(evs)
        peak = max(len(bins[k]) for k in g)
        start = min(e.timestamp for e in evs)
        end = max(e.timestamp for e in evs)
        minutes = max(1, round((end - start).total_seconds() / 60))
        level = Level.CRITICAL if peak >= 4 * threshold else Level.WARNING
        services = Counter(e.source for e in evs).most_common(5)
        out.append(
            Anomaly(
                "error_burst",
                level,
                start,
                end,
                f"Error burst: {total} errors in {minutes} min "
                f"(peak {peak} per 5 min, ~{expected:.1f} expected)",
                {
                    "errors": total,
                    "peak_per_5min": peak,
                    "baseline_per_5min": round(expected, 2),
                    "threshold_per_5min": round(threshold, 1),
                    "affected_services": dict(services),
                },
            )
        )
    return out
