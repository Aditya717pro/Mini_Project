from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.research_reports.collectors.common import flatten_values
from app.research_reports.sanitize import NOT_AVAILABLE, clean_label, clean_number, clean_text, safe_column_name
from app.research_reports.validation import ResolvedSources


def _value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if item.get(key) not in (None, ""):
            return item[key]
    return NOT_AVAILABLE


def collect(db: Session, settings: Settings, sources: ResolvedSources) -> dict[str, Any]:
    job = sources.etl_job
    if job is None:
        raise HTTPException(status_code=422, detail="A persisted ETL job is required for this report.")

    version = sources.dataset_version
    log = version.transformation_log_json if version else {}
    metadata: dict[str, Any] = {
        "ETL job ID": job.id,
        "Dataset ID": job.dataset_id,
        "Dataset version ID": job.dataset_version_id,
        "Status": clean_text(job.status.value if hasattr(job.status, "value") else job.status),
        "Current stage": job.current_stage,
        "Progress": job.progress,
        "Rows in": job.rows_in,
        "Rows out": job.rows_out,
        "Created at": job.created_at.isoformat() if job.created_at else NOT_AVAILABLE,
        "Completed at": job.completed_at.isoformat() if job.completed_at else NOT_AVAILABLE,
    }

    stages = [[job.current_stage, job.rows_in, job.rows_out, metadata["Status"]]]

    mappings = [
        [
            safe_column_name(decision.source),
            safe_column_name(decision.proposed_target),
            safe_column_name(decision.target or ""),
            decision.decision,
            decision.confidence,
        ]
        for decision in job.mapping_decisions
    ]
    if not mappings:
        mappings = [[NOT_AVAILABLE, NOT_AVAILABLE, NOT_AVAILABLE, "No recorded decisions", NOT_AVAILABLE]]

    transformations: list[list[Any]] = []
    for index, entry in enumerate(log.get("logs") or [], start=1):
        transformations.append(
            [
                index,
                clean_text(_value(entry, "action", "stage")),
                safe_column_name(_value(entry, "column", "field", "sourceColumn")),
                clean_text(_value(entry, "message", "detail", "msg"), default="No detail recorded"),
            ]
        )
    if not transformations:
        transformations.append([NOT_AVAILABLE, "No persisted transformation log", NOT_AVAILABLE, NOT_AVAILABLE])

    unit_conversions: list[list[Any]] = []
    for entry in log.get("unit_conversions") or []:
        unit_conversions.append(
            [
                safe_column_name(_value(entry, "sourceColumn", "field", "column")),
                clean_text(_value(entry, "fromUnit", "from_unit"), default="NOT RECORDED"),
                clean_text(_value(entry, "toUnit", "to_unit"), default="NOT RECORDED"),
                clean_number(_value(entry, "factor")),
                clean_text(_value(entry, "note", "detail"), default="No rationale recorded"),
            ]
        )
    if not unit_conversions:
        unit_conversions.append(
            [NOT_AVAILABLE, NOT_AVAILABLE, NOT_AVAILABLE, NOT_AVAILABLE, "No structured unit conversions recorded"]
        )

    logs = [
        [
            entry.created_at.isoformat() if entry.created_at else NOT_AVAILABLE,
            entry.stage,
            entry.level,
            clean_text(entry.message),
        ]
        for entry in job.logs
    ]
    if not logs:
        logs.append([NOT_AVAILABLE, NOT_AVAILABLE, NOT_AVAILABLE, "No execution logs recorded"])

    before_after: list[list[Any]] = []
    profile = job.profile_json or {}
    before = profile.get("before") if isinstance(profile, dict) else None
    after = profile.get("after") if isinstance(profile, dict) else None
    if isinstance(before, dict) and isinstance(after, dict):
        for label, value in flatten_values(before):
            before_after.append([label, value, after.get(label, NOT_AVAILABLE)])
    else:
        for label, value in flatten_values(profile):
            before_after.append([clean_label(label), value, NOT_AVAILABLE])
    if not before_after:
        before_after.append([NOT_AVAILABLE, "No persisted before/after profile", NOT_AVAILABLE])

    return {
        "metadata": metadata,
        "stages": stages,
        "mappings": mappings,
        "transformations": transformations,
        "unit_conversions": unit_conversions,
        "logs": logs,
        "before_after": before_after,
        "limitations": [
            "Mapping and transformation evidence is reproduced only from persisted ETL records.",
            "Source column names that appear identifier-like are redacted.",
            "ETL completion does not establish clinical validity or research readiness.",
        ],
    }
