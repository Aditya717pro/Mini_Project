from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.etl.extract import extract_dataset
from app.etl.transform import suggest_mappings
from app.models.dataset import DatasetVersion
from app.models.enums import JobStatus
from app.models.etl import ETLJob
from app.services.job_service import claim_job, fail_job, log_job
from app.services.storage_service import StorageService


def profile_job(db: Session, *, settings: Settings, job: ETLJob) -> ETLJob:
    if job.status == JobStatus.AWAITING_REVIEW:
        return job
    if not claim_job(
        db,
        job,
        expected={JobStatus.QUEUED},
        next_status=JobStatus.PROFILING,
        stage="extract",
        progress=25,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only queued jobs can be profiled (current status: {job.status.value})",
        )

    try:
        version = db.get(DatasetVersion, job.dataset_version_id)
        if version is None:
            raise ValueError("Dataset version not found")
        storage = StorageService(settings)
        raw_path = storage.resolve(version.raw_file_path, kind="raw")
        extracted = extract_dataset(raw_path, job.dataset.format)
        profile = extracted.profile.as_dict()
        job.profile_json = profile
        job.suggested_mapping_json = suggest_mappings([column.name for column in extracted.profile.columns])
        job.rows_in = extracted.profile.row_count
        job.approved_mapping_json = {}
        job.current_stage = "review"
        job.progress = 50
        job.status = JobStatus.AWAITING_REVIEW
        version.profile_json = profile
        log_job(
            db,
            job,
            "extract",
            f"Profiled {profile['row_count']} rows and {profile['column_count']} columns; "
            f"{len(profile['issues'])} profiling finding(s).",
            findings=profile["issues"],
        )
        log_job(
            db,
            job,
            "transform",
            "Mapping suggestions generated. Every decision requires explicit reviewer approval.",
            suggestions=len(job.suggested_mapping_json),
            level="WARN",
        )
        db.commit()
        db.refresh(job)
        return job
    except Exception as error:
        fail_job(db, job, error, message="Profiling failed. The original file was not modified.")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Profiling failed: {error}",
        ) from error
