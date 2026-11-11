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

        # durata reale della porzione di ora che stiamo analizzando (in ore)
        duration_h = max((w_end - w_start).total_seconds() / 3600.0, 1e-6)

        n = counts.get(cur, 0)
        # tasso osservato normalizzato a 1 ora
        rate = n / duration_h

        h = cur.astimezone().hour
        mean = b.hourly_mean.get(h, b.avg_per_hour)
        std = b.hourly_std.get(h, 0.0)

        # soglia basata sul tasso atteso per un'ora intera
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
            # drop solo se la finestra è abbastanza lunga (≥ 45 min)
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

def _new_templates(b: Baseline, events, since, until) -> list[Anomaly]:
    seen, errs, first, last, sample = Counter(), Counter(), {}, {}, {}
    for e in events:
        t = e.template
        if t in b.templates:
            continue
        seen[t] += 1
        errs[t] += int(e.is_error)
        first[t] = min(first.get(t, e.timestamp), e.timestamp)  
        last[t] = max(last.get(t, e.timestamp), e.timestamp)
        sample.setdefault(t, normalize_message(e.message))

    out = []
    for t, n in seen.most_common(MAX_NEW):
        level = Level.WARNING if errs[t] or n >= 10 else Level.INFO
        out.append(Anomaly("new_message", level, first[t], last[t],
                           f"New message never seen in baseline: {t[:90]}",
                           {"occurrences": n, "errors": errs[t], "sample": sample[t][:160]}))
    return out


def _missing_templates(b: Baseline, events, since, until) -> list[Anomaly]:
    span_h = max((until - since).total_seconds() / 3600, 1e-9)
    present = {e.template for e in events}
    candidates = []
    for t, c in b.templates.items():
        expected = c / b.window_hours * span_h
        if expected >= 5 and t not in present:
            candidates.append((expected, t, c))
    candidates.sort(reverse=True)
    return [
        Anomaly("missing_message", Level.WARNING, since, until,
                f"Expected message disappeared: {t[:90]}",
                {"expected_in_window": round(exp, 1), "baseline_count": c, "seen": 0})
        for exp, t, c in candidates[:MAX_MISSING]
    ]


def _error_bursts(b: Baseline, events) -> list[Anomaly]:
    bins = Counter(int(e.timestamp.timestamp()) // BIN for e in events if e.is_error)
    if not bins:
        return []
    per_bin = b.error_total / max(b.window_hours * 3600 / BIN, 1)
    threshold = max(10, 5 * per_bin)
    hot = sorted(k for k, n in bins.items() if n >= threshold)
    groups, cur = [], []
    for k in hot:
        if cur and k != cur[-1] + 1:
            groups.append(cur)
            cur = []
        cur.append(k)
    if cur:
        groups.append(cur)

    def to_dt(k: int) -> datetime:
        return datetime.fromtimestamp(k * BIN, tz=timezone.utc).astimezone()

    out = []
    for g in groups:
        total = sum(bins[k] for k in g)
        peak = max(bins[k] for k in g)
        level = Level.CRITICAL if peak >= 3 * threshold else Level.WARNING
        out.append(Anomaly("error_burst", level, to_dt(g[0]), to_dt(g[-1] + 1),
                           f"Error burst: {total} errors in {len(g) * BIN // 60} min",
                           {"errors": total, "peak_per_5min": peak,
                            "baseline_per_5min": round(per_bin, 2), "threshold": round(threshold, 1)}))
    return out
