# Aether

<img width="1280" height="640" alt="image" src="https://github.com/user-attachments/assets/1a7f44f6-297b-4f26-a898-bc2235b08046" />

Behavioral log analysis for Linux. Detects when a machine starts behaving differently.

## The problem
Logs are huge and mostly noise. Grep finds what you already know to look for; it misses what changed. Aether learns what "normal" looks like on a machine and flags deviations from it.

## What it does
- Reads journald and classic log files (`/var/log/syslog`, `auth.log`, ...)
- Builds a local baseline in SQLite: hourly volume, recurring message templates, error rate
- Detects volume spikes and drops, new messages, vanished messages, error bursts
- Prints a terminal report sorted by severity, with numeric evidence for each anomaly

## Example output
Run on synthetic logs (`examples/demo.py`): 58 hours of regular heartbeat messages as baseline, then 300 disk errors in the last half hour.

```
Aether scan
  Events scanned   300
  Anomalies        1 critical · 3 warning · 0 info

#1 CRITICAL · error_burst
  Error burst: 300 errors in 30 min
  errors: 300 · peak_per_5min: 60 · threshold: 10

#2 WARNING · volume_spike
  Log volume spike: 140 events vs ~40 expected

#3 WARNING · missing_message
  Expected message disappeared: app: heartbeat <N> ok

#4 WARNING · new_message
  New message never seen in baseline: app: disk failure on sda
```
*(Abridged. Numbers vary with the time you run the demo.)*

## Installation
```
git clone https://github.com/roccia729-cpu/aether
cd aether
pip install -e .
```
Requires Python 3.11+ and Linux.

## Usage
```
aether baseline build --hours 72   # learn normal behavior
aether baseline show               # inspect the baseline
aether scan --hours 1              # compare recent logs to the baseline
```
Reading system logs may require membership in the `systemd-journal` group or root. If you use `sudo`, make sure Aether is installed for that user's Python.

Options: `--source auto|journald|files` and `--file PATH` (repeatable) to choose the log source.

Try it without real logs:
```
python3 examples/demo.py
```

## How it works
Each log line becomes an event (timestamp, source, severity, message, host). Numbers, IPs, UUIDs and hex values are masked to produce message templates. The baseline stores per-hour-of-day volume (mean and standard deviation) and template counts in SQLite. A scan compares the recent window against it using statistical thresholds. No machine learning.

## Current limitations
- Linux only, single host
- Hourly statistics are computed in the machine's local timezone. Behavior around DST transitions may be less precise.
- Validated on Ubuntu with injected events; not yet validated on long-running production hosts.
- Thresholds are heuristic and not yet configurable
- The baseline groups by hour of day only (no weekday/weekend split, no per-service baselines)
- Baseline should be built while the machine is healthy
- Error detection on plain files is keyword-based
- Message templates are masked for numbers/IPs/UUIDs, but usernames, emails and tokens are not redacted. Treat reports and the baseline database as sensitive
- journald ingestion is not yet validated on large real-world systems
- No alerting yet

## Roadmap
- Configurable thresholds and per-service baselines
- Weekday-aware baselines and periodic messages
- Redaction rules for sensitive data
- Alerting (email, Telegram)
- PyPI package

## Free vs Pro
Free: scan, terminal report, baseline up to 72h.
Pro (planned): longer baseline retention, JSON export, alerting, priority support.

## License
MIT

