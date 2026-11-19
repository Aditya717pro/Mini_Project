from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.etl.pipeline import run_pipeline
from app.models.dataset import DatasetVersion
from app.models.enums import DatasetStatus, JobStatus
from app.models.etl import ETLJob
from app.models.user import User
from app.services.audit_service import log_audit
from app.services.job_service import claim_job, fail_job, log_job
from app.services.quality_service import assess_quality, persist_quality_report
from app.services.readiness_service import assess_readiness, persist_readiness_report
from app.services.representativeness_service import (
    assess_representativeness,
    persist_representativeness_report,
)
from app.services.storage_service import StorageService


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
    if job.status != JobStatus.APPROVED or not approved_mapping:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ETL can only run for an approved job with reviewed mappings",
        )

    dataset = job.dataset
    version = db.get(DatasetVersion, job.dataset_version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset version not found")
    if research_task:
        dataset.research_task = research_task.strip()

    storage = StorageService(settings)
    try:
        raw_path = storage.resolve(version.raw_file_path, kind="raw")
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset raw file not found on disk",
        ) from error

    job.approved_mapping_json = approved_mapping
    log_job(
        db,
        job,
        "transform",
        "Starting extraction, transformation, validation and report generation.",
        mappings=len([value for value in approved_mapping.values() if value]),
    )
    if not claim_job(
        db,
        job,
        expected={JobStatus.APPROVED},
        next_status=JobStatus.RUNNING,
        stage="extract",
        progress=20,
        started=True,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ETL job is no longer approved; it may already be running or completed",
        )

    try:
        pipeline = run_pipeline(
            raw_path=raw_path,
            file_format=dataset.format,
            approved_mapping=approved_mapping,
            storage=storage,
            dataset_id=dataset.id,
            version_id=version.id,
        )
        job.progress = 65
        job.current_stage = "quality"
        log_job(
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
        log_job(
            db,
            job,
            "quality",
            f"Quality score {quality.overall}/100 ({quality.grade}); {len(quality.issues)} finding(s).",
        )

        representativeness = assess_representativeness(pipeline.extracted.dataframe, pipeline.extracted.profile)
        persist_representativeness_report(
            db, dataset=dataset, version=version, assessment=representativeness
        )
        log_job(
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
        log_job(
            db,
            job,
            "readiness",
            f"Readiness verdict: {readiness.verdict} ({readiness.overall}/100) for '{readiness.task}'.",
        )

        version.processed_file_path = storage.relative_path(pipeline.processed_path, kind="processed")
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
        log_job(
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
        fail_job(
            db,
            job,
            exc,
            message="ETL failed. The original file and previous successful outputs remain available.",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"ETL processing failed: {exc}",
        ) from exc
