from collections import Counter, defaultdict
from datetime import datetime, timedelta
from ..baseline.builder import hour_floor
from ..models import Anomaly, Baseline, Event, Level
BIN = 300  # 5-minute windows for error bursts
MAX_NEW = 15
MAX_MISSING = 10
# ============================================================
# MAIN DETECTION ENGINE
# ============================================================
def detect(
    baseline: Baseline,
    events: list[Event],
    since: datetime,
    until: datetime
) -> list[Anomaly]:
    if until <= since:
        return []
    # Analyze only events inside the requested time window.
    events = [
        event for event in events
        if since <= event.timestamp < until
    ]
    found: list[Anomaly] = []
    found.extend(_volume(baseline, events, since, until))
    found.extend(
        _new_templates(baseline, events, since, until)
    )
    found.extend(
        _missing_templates(baseline, events, since, until)
    )
    found.extend(
        _error_bursts(baseline, events)
    )
    found.sort(
        key=lambda anomaly: (
            -anomaly.level.rank,
            anomaly.window_start
        )
    )
    return found
# ============================================================
# VOLUME ANOMALIES
# ============================================================
def _volume(
    b: Baseline,
    events: list[Event],
    since: datetime,
    until: datetime
) -> list[Anomaly]:
    """Detect unusual increases or decreases in log volume."""
    counts = Counter(
        hour_floor(event.timestamp)
        for event in events
    )
    anomalies = []
    cur = hour_floor(since)
    while cur < until:
        end = cur + timedelta(hours=1)
        window_start = max(cur, since)
        window_end = min(end, until)
        duration_h = max(
            (window_end - window_start).total_seconds() / 3600,
            1e-6
        )
        count = counts.get(cur, 0)
        rate = count / duration_h
        hour = cur.astimezone().hour
        mean = b.hourly_mean.get(
            hour,
            b.avg_per_hour
        )
        std = b.hourly_std.get(hour, 0.0)
        threshold = max(
            mean + 3 * std,
            mean * 3,
            20
        )
        evidence = {
            "events": count,
            "duration_min": round(duration_h * 60, 1),
            "rate_per_hour": round(rate, 1),
            "baseline_avg": round(mean, 1),
            "threshold": round(threshold, 1),
        }
        # Unusual increase in log volume.
        if rate >= threshold:
            level = (
                Level.CRITICAL
                if rate >= 2 * threshold
                else Level.WARNING
            )
            anomalies.append(
                Anomaly(
                    "volume_spike",
                    level,
                    window_start,
                    window_end,
                    (
                        f"Log volume spike: {count} events "
                        f"in {duration_h * 60:.0f} minutes "
                        f"(approximately {rate:.0f}/h)"
                    ),
                    evidence,
                )
            )
        # Unusual decrease in log volume.
        elif duration_h >= 0.75 and mean >= 50 and rate < mean * 0.2:
            anomalies.append(
                Anomaly(
                    "volume_drop",
                    Level.WARNING,
                    window_start,
                    window_end,
                    (
                        f"Log volume drop: {count} events "
                        f"in {duration_h * 60:.0f} minutes "
                        f"(approximately {rate:.0f}/h)"
                    ),
                    evidence,
                )
            )
        cur = end
    return anomalies
# ============================================================
# NEW MESSAGE TEMPLATES
# ============================================================
def _new_templates(
    b: Baseline,
    events: list[Event],
    since: datetime,
    until: datetime
) -> list[Anomaly]:
    """
    Detect log message templates that were never
    observed in the historical baseline.
    """
    seen = Counter()
    errors = Counter()
    first = {}
    last = {}
    for event in events:
        if not (since <= event.timestamp < until):
            continue
        template = event.template
        # Ignore known templates.
        if template in b.templates:
            continue
        seen[template] += 1
        if event.is_error:
            errors[template] += 1
        if template not in first:
            first[template] = event.timestamp
        last[template] = event.timestamp
    anomalies = []
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
# ============================================================
# MISSING MESSAGE TEMPLATES
# ============================================================
def _missing_templates(
    b: Baseline,
    events: list[Event],
    since: datetime,
    until: datetime
) -> list[Anomaly]:
    """
    Detect normally recurring log templates that
    unexpectedly disappear from the observation window.
    """
    if until <= since:
        return []
    # Count currently observed templates.
    observed = Counter(
        event.template
        for event in events
        if since <= event.timestamp < until
    )
    # Actual observation duration.
    window_hours = (
        until - since
    ).total_seconds() / 3600
    # Historical baseline duration.
    baseline_hours = b.window_hours
    if baseline_hours <= 0:
        return []
    missing = []
    for template, historical_count in b.templates.items():
        if historical_count <= 0:
            continue
        # Expected occurrences in the current window.
        expected = (
            historical_count / baseline_hours
        ) * window_hours
        actual = observed.get(template, 0)
        # Ignore infrequent templates.
        if expected < 3:
            continue
        # Template is still present.
        if actual > 0:
            continue
        missing.append({
            "template": template,
            "expected": round(expected, 2),
            "actual": actual,
        })
    # Highest expected frequency first.
    missing.sort(
        key=lambda item: item["expected"],
        reverse=True
    )
    anomalies = []
    for item in missing[:MAX_MISSING]:
        template = item["template"]
        expected = item["expected"]
        evidence = {
            "template": template,
            "expected_occurrences": expected,
            "actual_occurrences": 0,
            "baseline_occurrences": b.templates[template],
            "baseline_hours": baseline_hours,
            "observation_hours": round(window_hours, 2),
        }
        anomalies.append(
            Anomaly(
                kind="missing_message",
                level=Level.WARNING,
                window_start=since,
                window_end=until,
                description=(
                    f"Expected log template disappeared: "
                    f"{template[:100]} "
                    f"(expected approximately {expected} occurrences)"
                ),
                evidence=evidence,
            )
        )
    return anomalies
# ============================================================
# ERROR BURST DETECTION
# ============================================================
def _error_bursts(
    b: Baseline,
    events: list[Event]
) -> list[Anomaly]:
    """
    Detect unusual concentrations of error events
    inside short time windows.
    """
    buckets = defaultdict(list)
    # Group errors into fixed 5-minute windows.
    for event in events:
        if not event.is_error:
            continue
        timestamp = event.timestamp.timestamp()
        bucket = int(timestamp // BIN)
        buckets[bucket].append(event)
    anomalies = []
    # Historical error rate per hour.
    baseline_hours = b.window_hours
    if baseline_hours <= 0:
        return []
    historical_error_rate = (
        b.error_total / baseline_hours
    )
    # Expected errors in a 5-minute window.
    expected_errors = (
        historical_error_rate * BIN / 3600
    )
    # Minimum threshold avoids alerts for isolated errors.
    threshold = max(
        5,
        expected_errors * 3
    )
    for bucket, bucket_events in buckets.items():
        count = len(bucket_events)
        if count < threshold:
            continue
        timestamps = [
            event.timestamp
            for event in bucket_events
        ]
        window_start = min(timestamps)
        window_end = max(timestamps)
        level = (
            Level.CRITICAL
            if count >= threshold * 2
            else Level.WARNING
        )
        # Identify affected services.
        services = Counter(
            event.source
            for event in bucket_events
        )
        evidence = {
            "error_count": count,
            "baseline_expected": round(expected_errors, 2),
            "threshold": round(threshold, 2),
            "baseline_error_rate": round(
                historical_error_rate,
                2
            ),
            "window_seconds": BIN,
            "affected_services": dict(services),
        }
        anomalies.append(
            Anomaly(
                kind="error_burst",
                level=level,
                window_start=window_start,
                window_end=window_end,
                description=(
                    f"Error burst detected: {count} errors "
                    f"within a {BIN // 60}-minute window "
                    f"(historical expectation: "
                    f"{expected_errors:.2f})"
                ),
                evidence=evidence,
            )
        )
    return anomalies
