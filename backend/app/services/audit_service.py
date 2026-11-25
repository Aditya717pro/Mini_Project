from __future__ import annotations

import re
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import AuditLog

_SENSITIVE_KEYS = {
    "email",
    "email_address",
    "full_name",
    "name",
    "patient_name",
    "phone",
    "phone_number",
    "address",
    "street",
    "postal_code",
    "postcode",
    "filename",
    "file_name",
    "original_filename",
    "path",
    "file_path",
    "raw_file_path",
    "processed_file_path",
    "stored_path",
    "original_stored_path",
    "target",
    "target_column",
}


def _normalise_key(key: Any) -> str:
    text = re.sub(r"(?<!^)(?=[A-Z])", "_", str(key)).replace("-", "_").lower()
    return re.sub(r"_+", "_", text).strip("_")


def _is_sensitive(key: Any) -> bool:
    normalised = _normalise_key(key)
    return (
        normalised in _SENSITIVE_KEYS
        or normalised.endswith("_path")
        or normalised.endswith("_filename")
        or normalised.endswith("_file_path")
    )


def redact_audit_details(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _is_sensitive(key) else redact_audit_details(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_audit_details(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_audit_details(item) for item in value)
    return value


def log_audit(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    actor_id: str | None = None,
    details: dict | None = None,
    request: Request | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        details_json=redact_audit_details(details or {}),
        ip_address=request.client.host if request and request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:300] or None if request else None,
    )
    db.add(entry)
    return entry
