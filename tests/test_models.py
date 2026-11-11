from datetime import datetime, timezone

from aether.models import Event, normalize_message


def test_normalize_replaces_numbers_and_ips():
    msg = "Failed password for root from 10.0.0.5 port 2222"
    assert normalize_message(msg) == "Failed password for root from <IP> port <N>"


def test_normalize_uuid_and_hex():
    assert "<UUID>" in normalize_message("id 123e4567-e89b-12d3-a456-426614174000")
    assert "<HEX>" in normalize_message("addr 0xdeadbeef")


def test_event_template_and_error():
    ev = Event(datetime.now(timezone.utc), "sshd", "pid 42 failed", severity="err")
    assert ev.is_error
    assert ev.template == "sshd: pid <N> failed"
