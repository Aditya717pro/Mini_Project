from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import CurrentUser, get_app_settings
from app.core.config import Settings
from app.db.session import get_db
from app.etl.transform import COMMON_SCHEMA
from app.models.enums import JobStatus, UserRole
from app.models.etl import ETLJob
from app.models.user import User
from app.schemas.etl import EtlJobResponse, EtlLogResponse, EtlStageResponse, MappingSuggestionResponse, RunJobResponse
from app.schemas.reports import ReadinessRequest
from app.services.dataset_service import iso
from app.services.etl_service import run_etl

router = APIRouter(prefix="/etl", tags=["etl"])


def _accessible_job(db: Session, job_id: str, user: User) -> ETLJob:
    job = db.scalar(
        select(ETLJob)
        .options(
            selectinload(ETLJob.dataset),
            selectinload(ETLJob.logs),
        )
        .where(ETLJob.id == job_id)
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ETL job not found")
    if user.role != UserRole.ADMINISTRATOR and job.dataset.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this ETL job")
    return job


def _stages(job: ETLJob) -> list[EtlStageResponse]:
    status_value = job.status
    if status_value == JobStatus.QUEUED:
        states = ("Completed", "Awaiting review", "Queued")
    elif status_value == JobStatus.RUNNING:
        states = ("Completed", "Running", "Queued")
    elif status_value == JobStatus.AWAITING_REVIEW:
        states = ("Completed", "Completed", "Awaiting review")
    elif status_value == JobStatus.COMPLETED:
        states = ("Completed", "Completed", "Completed")
    elif status_value == JobStatus.FAILED:
        states = ("Completed", "Failed", "Queued")
    else:
        states = ("Queued", "Queued", "Queued")
    details = (
        f"{job.rows_in:,} rows extracted; original file retained.",
        f"{len(job.suggested_mapping_json or [])} suggested mapping(s); explicit approval required.",
        "Processed output is staged for governance review; it is not published automatically.",
    )
    labels = ("Extract", "Transform", "Load")
    keys = ("extract", "transform", "load")
    return [
        EtlStageResponse(key=key, label=label, state=state, detail=detail)
        for key, label, state, detail in zip(keys, labels, states, details, strict=True)
    ]


def _mappings(job: ETLJob) -> list[MappingSuggestionResponse]:
    approved = job.approved_mapping_json or {}
    result: list[MappingSuggestionResponse] = []
    for suggestion in job.suggested_mapping_json or []:
        source = str(suggestion.get("source", ""))
        if source in approved:
            target = approved[source]
            mapping_status = "Approved" if target else "Unmapped"
            note = "Contributor-approved mapping." if target else "Contributor explicitly left this column unmapped."
        else:
            target = suggestion.get("target", "")
            mapping_status = suggestion.get("status", "Suggested")
            note = suggestion.get("note", "")
        result.append(
            MappingSuggestionResponse(
                source=source,
                target=target or "",
                confidence=float(suggestion.get("confidence", 0.0)),
                status=mapping_status,
                note=note,
            )
        )
    return result


def to_job_response(job: ETLJob) -> EtlJobResponse:
    return EtlJobResponse(
        id=job.id,
        datasetId=job.dataset_id,
        datasetTitle=job.dataset.title if job.dataset else "Unknown dataset",
        status=job.status,
        progress=job.progress,
        stages=_stages(job),
        logs=[
            EtlLogResponse(
                time=iso(log.created_at),
                level=log.level,
                stage=log.stage,
                message=log.message,
            )
            for log in sorted(job.logs, key=lambda value: value.created_at)
        ],
        startedAt=iso(job.started_at or job.created_at),
        finishedAt=iso(job.completed_at) if job.completed_at else None,
        rowsIn=job.rows_in,
        rowsOut=job.rows_out,
        mappings=_mappings(job),
    )


@router.get("/jobs", response_model=list[EtlJobResponse])
def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> list[EtlJobResponse]:
    statement = select(ETLJob).options(selectinload(ETLJob.dataset), selectinload(ETLJob.logs))
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
    if user.role == UserRole.RESEARCHER and job.dataset.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the contributor can run ETL")
    mapping = job.approved_mapping_json or {}
    if not mapping:
        mapping = {
            str(item["source"]): item.get("target") or None
            for item in job.suggested_mapping_json or []
            if item.get("status") == "Approved"
        }
    invalid_targets = {target for target in mapping.values() if target and target not in COMMON_SCHEMA}
    if invalid_targets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported common-schema target(s): {', '.join(sorted(invalid_targets))}",
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


@router.post("/jobs/{job_id}/mappings", response_model=EtlJobResponse)
def save_mappings(
    job_id: str,
    mappings: dict[str, str | None],
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> EtlJobResponse:
    job = _accessible_job(db, job_id, user)
    invalid_targets = {target for target in mappings.values() if target and target not in COMMON_SCHEMA}
    if invalid_targets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported common-schema target(s): {', '.join(sorted(invalid_targets))}",
        )
    known_sources = {str(item.get("source")) for item in job.suggested_mapping_json or []}
    unknown = set(mappings) - known_sources
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown source column(s): {', '.join(sorted(unknown))}",
        )
    job.approved_mapping_json = mappings
    job.status = JobStatus.AWAITING_REVIEW
    db.commit()
    db.refresh(job)
    return to_job_response(job)
