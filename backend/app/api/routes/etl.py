from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.api.deps import CurrentUser, get_app_settings, require_roles
from app.core.config import Settings
from app.db.session import get_db
from app.models.enums import JobStatus, UserRole
from app.models.etl import ETLJob
from app.models.user import User
from app.schemas.etl import (
    EtlJobResponse,
    EtlLogResponse,
    EtlStageResponse,
    JobDecisionInput,
    MappingApprovalInput,
    MappingDecisionInput,
    MappingSuggestionResponse,
    RunJobResponse,
)
from app.schemas.reports import ReadinessRequest
from app.services.audit_service import log_audit
from app.services.dataset_service import iso
from app.services.etl_service import run_etl
from app.services.mapping_service import approve_mappings, record_mapping_decisions
from app.services.profiling_service import profile_job

router = APIRouter(prefix="/etl", tags=["etl"])


def _accessible_job(db: Session, job_id: str, user: User) -> ETLJob:
    job = db.scalar(
        select(ETLJob)
        .options(
            selectinload(ETLJob.dataset),
            selectinload(ETLJob.dataset_version),
            selectinload(ETLJob.logs),
            selectinload(ETLJob.mapping_decisions),
        )
        .where(ETLJob.id == job_id)
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ETL job not found")
    if user.role != UserRole.ADMINISTRATOR and job.dataset.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this ETL job")
    return job


def _stages(job: ETLJob) -> list[EtlStageResponse]:
    states: dict[JobStatus, tuple[str, str, str]] = {
        JobStatus.QUEUED: ("Queued", "Queued", "Queued"),
        JobStatus.PROFILING: ("Running", "Queued", "Queued"),
        JobStatus.AWAITING_REVIEW: ("Completed", "Awaiting review", "Queued"),
        JobStatus.APPROVED: ("Completed", "Completed", "Queued"),
        JobStatus.RUNNING: ("Completed", "Running", "Queued"),
        JobStatus.COMPLETED: ("Completed", "Completed", "Completed"),
        JobStatus.FAILED: ("Completed", "Failed", "Queued"),
        JobStatus.CANCELLED: ("Queued", "Queued", "Queued"),
        JobStatus.REJECTED: ("Queued", "Queued", "Queued"),
    }
    issue_count = len((job.profile_json or {}).get("issues") or [])
    details = (
        f"{job.rows_in:,} rows extracted; {issue_count} profiling finding(s).",
        f"{len(job.suggested_mapping_json or [])} suggestion(s); reviewer decisions are required.",
        "Processed output is written atomically and remains subject to governance review.",
    )
    return [
        EtlStageResponse(key=key, label=label, state=state, detail=detail)
        for key, label, state, detail in zip(
            ("extract", "transform", "load"),
            ("Extract", "Transform", "Load"),
            states[job.status],
            details,
            strict=True,
        )
    ]


def _mappings(job: ETLJob) -> list[MappingSuggestionResponse]:
    decisions = {decision.source: decision for decision in job.mapping_decisions}
    types = {
        str(column.get("name")): str(column.get("inferred_type", ""))
        for column in (job.profile_json or {}).get("columns", [])
    }
    result: list[MappingSuggestionResponse] = []
    for suggestion in job.suggested_mapping_json or []:
        source = str(suggestion.get("source", ""))
        decision = decisions.get(source)
        status_value = decision.decision if decision else str(suggestion.get("status", "Suggested"))
        if decision:
            target = decision.target if decision.decision == "Approved" else ""
        else:
            target = str(suggestion.get("target") or "")
        result.append(
            MappingSuggestionResponse(
                source=source,
                target=target,
                confidence=float(suggestion.get("confidence", 0.0)),
                status=status_value,
                note=decision.note if decision and decision.note else str(suggestion.get("note", "")),
                inferredType=types.get(source, ""),
                proposedTarget=str(suggestion.get("target") or ""),
                decision=decision.decision if decision else None,
                decidedBy=decision.decided_by.email if decision and decision.decided_by else None,
                decidedAt=iso(decision.decided_at) if decision and decision.decided_at else None,
            )
        )
    return result


def to_job_response(job: ETLJob) -> EtlJobResponse:
    summary = {}
    if job.dataset_version is not None:
        log = job.dataset_version.transformation_log_json or {}
        summary = {
            "rowsIn": log.get("rows_in"),
            "rowsOut": log.get("rows_out"),
            "errors": log.get("error_counts", {}),
            "warnings": log.get("warning_counts", {}),
            "duplicates": log.get("duplicate_count"),
            "rowIssues": log.get("row_issues", []),
            "profileIssues": log.get("profile_issues", []),
        }
    return EtlJobResponse(
        id=job.id,
        datasetId=job.dataset_id,
        datasetTitle=job.dataset.title if job.dataset else "Unknown dataset",
        status=job.status,
        currentStage=job.current_stage,
        progress=job.progress,
        stages=_stages(job),
        logs=[
            EtlLogResponse(
                time=iso(log.created_at),
                level=log.level,
                stage=log.stage,
                message=log.message,
                details=log.details_json or {},
            )
            for log in sorted(job.logs, key=lambda value: value.created_at)
        ],
        startedAt=iso(job.started_at or job.created_at),
        finishedAt=iso(job.completed_at) if job.completed_at else None,
        rowsIn=job.rows_in,
        rowsOut=job.rows_out,
        mappings=_mappings(job),
        profile=job.profile_json or {},
        errorMessage=job.error_message,
        approvedAt=iso(job.approved_at) if job.approved_at else None,
        approvedBy=job.approver.email if job.approver else None,
        rejectionReason=job.rejection_reason,
        transformationSummary=summary,
    )


@router.get("/jobs", response_model=list[EtlJobResponse])
def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> list[EtlJobResponse]:
    statement = select(ETLJob).options(
        selectinload(ETLJob.dataset),
        selectinload(ETLJob.dataset_version),
        selectinload(ETLJob.logs),
        selectinload(ETLJob.mapping_decisions),
    )
    if user.role != UserRole.ADMINISTRATOR:
        statement = statement.join(ETLJob.dataset).where(ETLJob.dataset.has(owner_id=user.id))
    jobs = db.scalars(statement.order_by(ETLJob.created_at.desc())).unique()
    return [to_job_response(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=EtlJobResponse)
def get_job(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> EtlJobResponse:
    return to_job_response(_accessible_job(db, job_id, user))


@router.post("/jobs/{job_id}/profile", response_model=EtlJobResponse)
def start_profiling(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> EtlJobResponse:
    job = profile_job(db, settings=settings, job=_accessible_job(db, job_id, user))
    return to_job_response(job)


@router.post("/jobs/{job_id}/mappings", response_model=EtlJobResponse)
def save_mapping_decisions(
    job_id: str,
    decisions: list[MappingDecisionInput],
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> EtlJobResponse:
    job = record_mapping_decisions(db, job=_accessible_job(db, job_id, user), decisions=decisions, actor=user)
    return to_job_response(job)


@router.post("/jobs/{job_id}/approve", response_model=EtlJobResponse)
def approve_mapping_set(
    job_id: str,
    payload: MappingApprovalInput | None,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> EtlJobResponse:
    job = approve_mappings(
        db,
        job=_accessible_job(db, job_id, user),
        actor=user,
        note=payload.note if payload else "",
    )
    return to_job_response(job)


@router.post("/jobs/{job_id}/run", response_model=RunJobResponse)
def run_job(
    job_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
    payload: ReadinessRequest | None = None,
) -> RunJobResponse:
    job = _accessible_job(db, job_id, user)
    mapping = job.approved_mapping_json or {}
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mappings must be reviewed and approved before ETL can run",
        )
    run_etl(
        db,
        settings=settings,
        job=job,
        actor=user,
        approved_mapping=mapping,
        research_task=payload.task if payload else None,
        request=request,
    )
    return RunJobResponse(
        jobId=job.id,
        status=JobStatus.COMPLETED.value,
        message="ETL completed; dataset is pending governance review.",
    )


@router.post("/jobs/{job_id}/cancel", response_model=EtlJobResponse)
def cancel_job(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> EtlJobResponse:
    job = _accessible_job(db, job_id, user)
    cancellable = {
        JobStatus.QUEUED,
        JobStatus.PROFILING,
        JobStatus.AWAITING_REVIEW,
        JobStatus.APPROVED,
        JobStatus.FAILED,
    }
    if job.status not in cancellable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Jobs in status {job.status.value} cannot be cancelled",
        )
    result = db.execute(
        update(ETLJob)
        .where(ETLJob.id == job.id, ETLJob.status.in_(cancellable))
        .values(status=JobStatus.CANCELLED, current_stage="cancelled", progress=100)
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job status changed concurrently")
    log_audit(db, action="etl.cancelled", resource_type="etl_job", resource_id=job.id, actor_id=user.id)
    db.commit()
    db.refresh(job)
    return to_job_response(job)


@router.post("/jobs/{job_id}/reject", response_model=EtlJobResponse)
def reject_job(
    job_id: str,
    payload: JobDecisionInput | None,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_roles(UserRole.ADMINISTRATOR))],
) -> EtlJobResponse:
    job = _accessible_job(db, job_id, user)
    if job.status in {JobStatus.RUNNING, JobStatus.COMPLETED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Completed or running jobs cannot be rejected")
    job.status = JobStatus.REJECTED
    job.current_stage = "rejected"
    job.rejection_reason = payload.reason if payload else ""
    log_audit(
        db,
        action="etl.rejected",
        resource_type="etl_job",
        resource_id=job.id,
        actor_id=user.id,
        details={"reason": job.rejection_reason},
    )
    db.commit()
    db.refresh(job)
    return to_job_response(job)
