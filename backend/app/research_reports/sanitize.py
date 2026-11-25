from __future__ import annotations

import re
from typing import Any

NOT_AVAILABLE = "NOT AVAILABLE"
NOT_EVALUATED = "NOT EVALUATED"

_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)"),
    re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    re.compile(r"(?i)\b[a-z]?\d{6,}\b"),
    re.compile(
        r"(?i)\b(?:patient|subject|mrn|hospital|medical|record|nhs|identifier|private)[-_ ]?"
        r"[a-z0-9-]*\d{2,}\b"
    ),
    re.compile(r"(?i)\b[A-Za-z]:[\\/][^\s]+|/(?:home|users|var|tmp)/[^\s]+"),
]


def clean_text(value: Any, *, default: str = NOT_AVAILABLE, limit: int = 400) -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    for pattern in _PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def clean_label(value: Any) -> str:
    return clean_text(value, default="unnamed", limit=90)


def clean_number(value: Any, *, default: str = NOT_AVAILABLE) -> str:
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return default
        return f"{value:g}" if isinstance(value, float) else str(value)
    return clean_text(value, default=default, limit=80)


def safe_column_name(value: Any) -> str:
    text = clean_text(value, default="unnamed", limit=120)
    lowered = text.lower()
    if any(
        token in lowered
        for token in ("patient", "subject", "mrn", "hospital", "identifier", "record_id", "nhs", "email", "phone")
    ):
        return "[REDACTED]"
    return text
