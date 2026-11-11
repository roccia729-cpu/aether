from aether.ingest.files import parse_line


def test_parse_syslog_line():
    ev = parse_line("Nov 11 10:36:01 myhost sshd[123]: Failed password for root")
    assert ev is not None
    assert ev.source == "sshd"
    assert ev.host == "myhost"
    assert ev.is_error


def test_parse_iso_line():
    ev = parse_line("2026-11-11T10:36:01+00:00 myhost cron[9]: job started")
    assert ev is not None
    assert ev.source == "cron"
    assert not ev.is_error


def test_parse_garbage_returns_none():
    assert parse_line("not a log line") is None
