"""Minimal redaction of secrets in command strings and messages."""

from __future__ import annotations

import re

_PATTERNS = [
    # common key=value secrets
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)\s*[=:]\s*\S+"), r"\1=<REDACTED>"),
    # Bearer tokens
    (re.compile(r"(?i)\bbearer\s+[a-z0-9._\-]+"), "Bearer <REDACTED>"),
    # long hex / base64-looking strings
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "<HEX>"),
    (re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"), "<B64>"),
]


def redact(text: str) -> str:
    if not text:
        return text
    out = text
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    return out
