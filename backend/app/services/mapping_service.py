from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select

from app.etl.transform import COMMON_SCHEMA
from app.models.enums import JobStatus
from app.models.etl import ETLJob, ETLMappingDecision
from app.models.user import User
from app.schemas.etl import MappingDecisionInput
from app.services.audit_service import log_audit
from app.services.job_service import log_job


def _suggestions(job: ETLJob) -> dict[str, dict]:
    return {str(item.get("source")): item for item in job.suggested_mapping_json or []}


def _validate_decision(item: MappingDecisionInput, suggestions: dict[str, dict]) -> None:
    if item.source not in suggestions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown source column: {item.source}",
        )
    if item.decision == "Approved":
        if not item.target:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"An approved mapping for '{item.source}' must name a standard target",
            )
        if item.target not in COMMON_SCHEMA:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unsupported common-schema target: {item.target}",
            )


def record_mapping_decisions(
    db,
    *,
    job: ETLJob,
    decisions: list[MappingDecisionInput],
    actor: User,
) -> ETLJob:
    if job.status not in {JobStatus.AWAITING_REVIEW, JobStatus.APPROVED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Mapping decisions can only be recorded during review (current status: {job.status.value})",
        )
    suggestions = _suggestions(job)
    for item in decisions:
        _validate_decision(item, suggestions)

    existing = {
        decision.source: decision
        for decision in db.scalars(select(ETLMappingDecision).where(ETLMappingDecision.job_id == job.id))
    }
    for item in decisions:
        suggestion = suggestions[item.source]
        decision = existing.get(item.source)
        if decision is None:
            decision = ETLMappingDecision(
                job_id=job.id,
                source=item.source,
                decided_by_id=actor.id,
            )
            db.add(decision)
        decision.proposed_target = str(suggestion.get("target") or "")
        decision.target = item.target if item.decision == "Approved" else None
        decision.decision = item.decision
        decision.confidence = float(suggestion.get("confidence") or 0.0)
        decision.note = item.note
        decision.decided_by_id = actor.id
        decision.decided_at = datetime.now(UTC)
        log_audit(
            db,
            action="etl.mapping_decided",
            resource_type="etl_job",
            resource_id=job.id,
            actor_id=actor.id,
            details={
                "source": item.source,
                "proposed_target": decision.proposed_target,
                "target": decision.target,
                "decision": item.decision,
                "confidence": decision.confidence,
                "note": item.note,
            },
        )

    job.status = JobStatus.AWAITING_REVIEW
    job.approved_mapping_json = {}
    job.approved_at = None
    job.approved_by_id = None
    log_job(
        db,
        job,
        "transform",
        f"Recorded {len(decisions)} mapping decision(s). Suggestions are not treated as approvals.",
    )
    db.commit()
    db.refresh(job)
    return job


def approve_mappings(db, *, job: ETLJob, actor: User, note: str = "") -> ETLJob:
    if job.status != JobStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Mappings can only be approved while in review (current status: {job.status.value})",
        )
    suggestions = _suggestions(job)
    decisions = {decision.source: decision for decision in job.mapping_decisions}
    unreviewed = sorted(set(suggestions) - set(decisions))
    if unreviewed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Every source column needs a decision. Unreviewed: {', '.join(unreviewed)}",
        )

    mapping: dict[str, str | None] = {}
    for source in suggestions:
        decision = decisions[source]
        if decision.decision == "Approved":
            if not decision.target or decision.target not in COMMON_SCHEMA:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Approved mapping for '{source}' has an unsupported target",
                )
            mapping[source] = decision.target
        else:
            mapping[source] = None

    job.approved_mapping_json = mapping
    job.status = JobStatus.APPROVED
    job.current_stage = "review"
    job.progress = 75
    job.approved_at = datetime.now(UTC)
    job.approved_by_id = actor.id
    mapped_count = len([value for value in mapping.values() if value])
    log_job(
        db,
        job,
        "transform",
        f"Reviewer {actor.email} approved the mapping set ({mapped_count} mapped columns).",
    )
    log_audit(
        db,
        action="etl.mappings_approved",
        resource_type="etl_job",
        resource_id=job.id,
        actor_id=actor.id,
        details={"note": note, "mapping": mapping},
    )
    db.commit()
    db.refresh(job)
    return job
