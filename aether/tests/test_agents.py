from datetime import datetime, timedelta, timezone
from pathlib import Path

from aether.detect.agent_rules import find_risky_actions
from aether.ingest.claude_code import parse_line
from aether.models import Event, Level
from aether.redact import redact


def test_redact_secrets():
    s = redact("token=abc123password and Bearer supersecretvalue")
    assert "abc123password" not in s
    assert "supersecretvalue" not in s
    assert "REDACTED" in s or "Bearer" in s


def test_parse_claude_line_basic():
    line = '{"timestamp":"2026-11-12T12:00:00+00:00","attributes":{"tool":"bash","command":"ls -la","status":"ok"}}'
    ev = parse_line(line)
    assert ev is not None
    assert ev.source == "bash"
    assert "ls" in ev.message


def test_risky_rm():
    now = datetime.now(tz=timezone.utc)
    events = [
        Event(timestamp=now, source="bash", message="rm -rf /tmp/project", severity=None),
    ]
    found = find_risky_actions(events, now - timedelta(hours=1), now + timedelta(hours=1))
    assert any(a.kind == "risky_action" for a in found)
    assert any(a.level == Level.CRITICAL for a in found)
