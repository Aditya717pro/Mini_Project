from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.dataset import DatasetStatus
from app.models.enums import JobStatus
from app.models.etl import ETLJob, ETLJobLog


def log_job(
    db: Session,
    job: ETLJob,
    stage: str,
    message: str,
    level: str = "INFO",
    **details: object,
) -> None:
    db.add(
        ETLJobLog(
            job_id=job.id,
            stage=stage,
            level=level,
            message=message,
            details_json=details,
        )
    )


def claim_job(
    db: Session,
    job: ETLJob,
    *,
    expected: set[JobStatus],
    next_status: JobStatus,
    stage: str,
    progress: int,
    started: bool = False,
) -> bool:
    values: dict[str, object] = {
        "status": next_status,
        "current_stage": stage,
        "progress": progress,
        "error_message": None,
    }
    if started:
        values["started_at"] = datetime.now(UTC)
    result = db.execute(update(ETLJob).where(ETLJob.id == job.id, ETLJob.status.in_(expected)).values(**values))
    if result.rowcount != 1:
        return False
    db.commit()
    db.refresh(job)
    return True


def fail_job(db: Session, job: ETLJob, error: Exception, *, message: str | None = None) -> None:
    db.rollback()
    failed = db.get(ETLJob, job.id)
    if failed is None:
        return
    failed.status = JobStatus.FAILED
    failed.current_stage = "failed"
    failed.progress = 100
    failed.error_message = str(error)[:2000]
    failed.completed_at = datetime.now(UTC)
    failed_dataset = failed.dataset
    if failed_dataset is not None and failed_dataset.status != DatasetStatus.AVAILABLE:
        failed_dataset.status = DatasetStatus.FAILED
    log_job(
        db,
        failed,
        "failed",
        message or "Job failed. The original file and previous successful outputs remain available.",
        level="ERROR",
        error=str(error),
    )
    db.commit()


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
