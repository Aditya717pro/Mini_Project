from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.etl.pipeline import run_pipeline
from app.models.dataset import DatasetVersion
from app.models.enums import DatasetStatus, JobStatus
from app.models.etl import ETLJob, ETLJobLog
from app.models.user import User
from app.services.audit_service import log_audit
from app.services.quality_service import assess_quality, persist_quality_report
from app.services.readiness_service import assess_readiness, persist_readiness_report
from app.services.representativeness_service import (
    assess_representativeness,
    persist_representativeness_report,
)
from app.services.storage_service import StorageService


def _log(db: Session, job: ETLJob, stage: str, message: str, level: str = "INFO", **details: object) -> None:
    db.add(
        ETLJobLog(
            job_id=job.id,
            stage=stage,
            level=level,
            message=message,
            details_json=details,
        )
    )


def run_etl(
    db: Session,
    *,
    settings: Settings,
    job: ETLJob,
    actor: User,
    approved_mapping: dict[str, str | None],
    research_task: str | None = None,
    request: Request | None = None,
) -> ETLJob:
    if job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ETL job is already running")
    if job.status == JobStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ETL job is already completed")

    dataset = job.dataset
    version = db.get(DatasetVersion, job.dataset_version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset version not found")
    if research_task:
        dataset.research_task = research_task.strip()

    job.status = JobStatus.RUNNING
    job.current_stage = "transform"
    job.progress = 35
    job.approved_mapping_json = approved_mapping
    job.started_at = job.started_at or datetime.now(UTC)
    job.error_message = None
    _log(
        db,
        job,
        "transform",
        "Approved mapping received. Starting extraction, transformation and report generation.",
        mappings=len([value for value in approved_mapping.values() if value]),
    )
    db.commit()

    try:
        storage = StorageService(settings)
        pipeline = run_pipeline(
            raw_path=version.raw_file_path,
            file_format=dataset.format,
            approved_mapping=approved_mapping,
            storage=storage,
            dataset_id=dataset.id,
            version_id=version.id,
        )
        job.progress = 65
        job.current_stage = "quality"
        _log(
            db,
            job,
            "transform",
            "Processed output written. Original upload and preserved original columns remain available.",
            rows_in=len(pipeline.extracted.dataframe),
            rows_out=len(pipeline.transformed.dataframe),
        )

        quality = assess_quality(pipeline.extracted.dataframe, pipeline.extracted.profile)
        quality_report = persist_quality_report(db, dataset=dataset, version=version, job=job, assessment=quality)
        db.flush()
        _log(
            db,
            job,
            "quality",
            f"Quality score {quality.overall}/100 ({quality.grade}); {len(quality.issues)} finding(s).",
        )

        representativeness = assess_representativeness(pipeline.extracted.dataframe, pipeline.extracted.profile)
        persist_representativeness_report(
            db, dataset=dataset, version=version, assessment=representativeness
        )
        _log(
            db,
            job,
            "representativeness",
            representativeness.summary,
            available_attributes=5 - len(representativeness.missing_attributes),
        )

        readiness = assess_readiness(
            dataset=dataset,
            metadata=dataset.metadata_record,
            profile=pipeline.extracted.profile,
            quality=quality,
            research_task=dataset.research_task or "General clinical research",
            representativeness_score=representativeness.score,
        )
        persist_readiness_report(
            db,
            dataset=dataset,
            version=version,
            quality_report_id=quality_report.id,
            assessment=readiness,
        )
        _log(
            db,
            job,
            "readiness",
            f"Readiness verdict: {readiness.verdict} ({readiness.overall}/100) for '{readiness.task}'.",
        )

        version.processed_file_path = str(pipeline.processed_path)
        version.transformation_log_json = pipeline.transformation_log
        version.record_count = len(pipeline.transformed.dataframe)
        version.column_count = len(pipeline.transformed.dataframe.columns)
        dataset.record_count = len(pipeline.extracted.dataframe)
        dataset.column_count = len(pipeline.extracted.dataframe.columns)
        dataset.missing_rate = pipeline.extracted.profile.missing_pct
        dataset.duplicate_rate = pipeline.extracted.profile.duplicate_pct
        dataset.status = DatasetStatus.PENDING_REVIEW
        dataset.approved_at = None
        dataset.approved_by_id = None

        job.status = JobStatus.COMPLETED
        job.current_stage = "complete"
        job.progress = 100
        job.rows_in = len(pipeline.extracted.dataframe)
        job.rows_out = len(pipeline.transformed.dataframe)
        job.completed_at = datetime.now(UTC)
        _log(
            db,
            job,
            "complete",
            "ETL completed. Dataset is pending governance review; quality is not an approval decision.",
        )
        log_audit(
            db,
            action="etl.completed",
            resource_type="etl_job",
            resource_id=job.id,
            actor_id=actor.id,
            details={
                "dataset_id": dataset.id,
                "rows_in": job.rows_in,
                "rows_out": job.rows_out,
                "quality": quality.overall,
                "readiness": readiness.overall,
                "verdict": readiness.verdict,
            },
            request=request,
        )
        db.commit()
        db.refresh(job)
        return job
    except Exception as exc:
        db.rollback()
        failed_job = db.get(ETLJob, job.id)
        if failed_job is not None:
            failed_job.status = JobStatus.FAILED
            failed_job.current_stage = "failed"
            failed_job.progress = 100
            failed_job.error_message = str(exc)[:2000]
            failed_job.completed_at = datetime.now(UTC)
            failed_dataset = failed_job.dataset
            if failed_dataset is not None:
                failed_dataset.status = DatasetStatus.FAILED
            _log(
                db,
                failed_job,
                "failed",
                "ETL failed. Original file remains stored; no processed output is treated as valid.",
                level="ERROR",
                error=str(exc),
            )
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"ETL processing failed: {exc}",
        ) from exc
