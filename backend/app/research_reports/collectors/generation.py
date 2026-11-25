from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.research_reports.collectors.common import flatten_values
from app.research_reports.sanitize import NOT_AVAILABLE, clean_number
from app.research_reports.validation import ResolvedSources
from app.synthmed.models import SynthMedDatasetVersion, SynthMedEvaluationReport
from app.synthmed.services.generation_service import generation_metadata

_CONFIG_KEYS = {
    "epochs",
    "batchSize",
    "seed",
    "generationMode",
    "selectedModel",
    "model",
    "recordCount",
    "requestedRecordCount",
    "generationProfile",
    "validationStatus",
    "sourcePreservingMode",
    "ageToleranceYears",
}


def collect(db: Session, settings: Settings, sources: ResolvedSources) -> dict[str, Any]:
    job = sources.generation_job
    if job is None:
        raise HTTPException(status_code=422, detail="A persisted generation job is required for this report.")
    generated = sources.generated_dataset

    metadata: dict[str, Any] = {
        "Generation job ID": job.id,
        "Source dataset ID": job.source_dataset_id,
        "Generated dataset ID": generated.id if generated else NOT_AVAILABLE,
        "Status": job.status,
        "Model": job.selected_model,
        "Generation mode": job.generation_mode,
        "Requested records": job.requested_record_count,
        "Generated records": job.generated_record_count,
        "Epochs": job.epochs,
        "Batch size": job.batch_size,
        "Seed": job.seed,
        "Duration seconds": job.training_duration_seconds,
        "Started at": job.started_at.isoformat() if job.started_at else NOT_AVAILABLE,
        "Completed at": job.completed_at.isoformat() if job.completed_at else NOT_AVAILABLE,
        "Generated checksum": generated.checksum_sha256 if generated and generated.checksum_sha256 else NOT_AVAILABLE,
    }

    config_rows = [
        [label, value]
        for label, value in flatten_values(job.config_json or {})
        if label.split(".")[-1] in _CONFIG_KEYS
    ]
    if not config_rows:
        config_rows.append([NOT_AVAILABLE, "No persisted generation settings"])

    environment_rows: list[list[Any]] = []
    meta = generation_metadata(db, generated.id) if generated else {}
    for label, value in flatten_values(meta):
        lowered = label.lower()
        if any(token in lowered for token in ("version", "library", "python", "model", "profile")):
            environment_rows.append([label, value])
    if not environment_rows:
        environment_rows.append([NOT_AVAILABLE, "No model or library versions recorded"])

    job_metrics = [
        ["Requested records", job.requested_record_count],
        ["Generated records", job.generated_record_count],
        ["Training duration (seconds)", job.training_duration_seconds],
        ["Epochs", job.epochs],
        ["Batch size", job.batch_size],
    ]

    evaluation_rows: list[list[Any]] = []
    reports = db.scalars(
        select(SynthMedEvaluationReport)
        .where(SynthMedEvaluationReport.generated_dataset_id == generated.id)
        .order_by(SynthMedEvaluationReport.created_at.desc())
    ) if generated else []
    for report in reports:
        evaluation_rows.append(
            [
                report.report_type,
                report.method or NOT_AVAILABLE,
                clean_number(report.score),
                report.created_at.isoformat(),
            ]
        )
    if not evaluation_rows:
        evaluation_rows.append([NOT_AVAILABLE, NOT_AVAILABLE, NOT_AVAILABLE, "No evaluation reports recorded"])

    clinical_rows: list[list[Any]] = []
    for label, value in flatten_values(meta.get("clinicalValidation") or {}):
        clinical_rows.append([label, NOT_AVAILABLE, value])
    for label, value in flatten_values(meta.get("schemaValidation") or {}):
        clinical_rows.append([label, NOT_AVAILABLE, value])
    if not clinical_rows:
        clinical_rows.append([NOT_AVAILABLE, "No persisted clinical validation", NOT_AVAILABLE])

    version_rows: list[list[Any]] = []
    logical_ids = [job.source_dataset_id]
    if generated:
        logical_ids.append(generated.id)
    versions = db.scalars(
        select(SynthMedDatasetVersion)
        .where(SynthMedDatasetVersion.logical_dataset_id.in_(logical_ids))
        .order_by(SynthMedDatasetVersion.created_at.desc())
    )
    for version in versions:
        version_rows.append(
            [
                version.dataset_kind,
                version.version_label or version.version_number,
                version.record_count,
                version.checksum_sha256 or NOT_AVAILABLE,
            ]
        )
    if not version_rows:
        version_rows.append([NOT_AVAILABLE, NOT_AVAILABLE, NOT_AVAILABLE, NOT_AVAILABLE])

    return {
        "metadata": metadata,
        "configuration": config_rows,
        "environment": environment_rows,
        "job_metrics": job_metrics,
        "evaluation_reports": evaluation_rows,
        "clinical": clinical_rows,
        "versions": version_rows,
        "limitations": [
            "Model provenance is limited to values persisted with the generation job and configuration snapshot.",
            "Synthetic data must not be treated as real patient observations or as clinically validated records.",
            "Evaluation reports are reproduced with their recorded methods and scores only.",
        ],
    }
