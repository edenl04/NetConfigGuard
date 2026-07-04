from __future__ import annotations

import re


SECRET_PATTERNS = [
    re.compile(r"(?im)^(\s*snmp-server community\s+)(\S+)(.*)$"),
    re.compile(r"(?im)^(\s*username\s+\S+\s+(?:password|secret)\s+\d?\s*)(\S+)(.*)$"),
    re.compile(r"(?im)^(\s*(?:enable password|enable secret)\s+\d?\s*)(\S+)(.*)$"),
    re.compile(r"(?im)^(\s*(?:password|secret)\s+\d?\s*)(\S+)(.*)$"),
    re.compile(r"(?im)^(\s*crypto isakmp key\s+)(\S+)(.*)$"),
]


def redact_config(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(r"\1<redacted>\3", redacted)
    return redacted

