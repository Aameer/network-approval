"""Copilot guardrails: DLP output scrub for SYSTEM secrets.

Redacts infrastructure/system credentials (API keys, service creds, the Fernet key)
from anything the copilot emits — so even a prompt-injected model can't exfiltrate them.

This deliberately does NOT redact the *business* secrets an admin can legitimately
query (mcc passwords, payment cards) — those are RBAC-gated, not system credentials.
"""
from __future__ import annotations

import re

from ..config import (
    ANTHROPIC_API_KEY,
    GCMS_PASSWORD,
    GOOGLE_CLIENT_SECRET,
    PARSER_PASSWORD,
    SECRETS_KEY,
)

_REDACT = "«redacted-system-secret»"

# Secret-shaped tokens (provider API keys, cloud creds).
_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    re.compile(r"ya29\.[0-9A-Za-z_\-]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def _known_system_secrets() -> list[str]:
    return [v for v in (ANTHROPIC_API_KEY, SECRETS_KEY, GCMS_PASSWORD,
                        PARSER_PASSWORD, GOOGLE_CLIENT_SECRET) if v and len(v) >= 8]


def scrub(text: str | None) -> str | None:
    if not text:
        return text
    for sec in _known_system_secrets():
        if sec in text:
            text = text.replace(sec, _REDACT)
    for pat in _PATTERNS:
        text = pat.sub(_REDACT, text)
    return text
