from __future__ import annotations

import hashlib
import io
import random
import time
import traceback
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
import torch
from fastapi import HTTPException, Request, status
from sdv.single_table import CTGANSynthesizer
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import SessionLocal
from app.services.audit_service import log_audit
from app.synthmed.models import (
    SynthMedEvaluationReport,
    SynthMedGeneratedDataset,
    SynthMedGenerationConfig,
    SynthMedGenerationJob,
    SynthMedSourceDataset,
)
from app.synthmed.services.dataset_service import (
    TABLE_NAME,
    analyse_dataframe,
    dump_json,
    json_safe,
    prepare_dataframe,
    read_source_dataframe,
)
from app.synthmed.services.evaluation_service import build_privacy_report, build_quality_report
from app.synthmed.services.source_service import to_generated_response
from app.synthmed.services.storage_service import SynthMedStorageService

MODEL_NAME = "SDV CTGANSynthesizer"
TERMINAL_STATUSES = {"Completed", "Failed"}
ACTIVE_STATUSES = {"Queued", "Preprocessing", "Training", "Generating", "Validating"}
_executor: ThreadPoolExecutor | None = None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _session_factory(db: Session | None = None) -> sessionmaker[Session]:
    if db is not None:
        return sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    return SessionLocal


def _executor_for(settings: Settings) -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=settings.synthmed_generation_worker_count, thread_name_prefix="synthmed-ctgan"
        )
    return _executor


def _status(job: SynthMedGenerationJob, value: str, **updates: Any) -> None:
    job.status = value
    for key, item in updates.items():
        setattr(job, key, item)
    job.updated_at = _now()


def _error_details(error: Exception) -> dict[str, Any]:
    return {
        "type": type(error).__name__,
        "message": str(error) or f"{type(error).__name__} raised during generation.",
        "traceback": traceback.format_exc(),
    }


def _validate_config(config: dict[str, Any], settings: Settings) -> None:
    epochs = int(config["epochs"])
    batch_size = int(config["batchSize"])
    record_count = int(config["recordCount"])
    if not (1 <= epochs <= settings.synthmed_ctgan_max_epochs):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Epochs must be between 1 and {settings.synthmed_ctgan_max_epochs}.",
        )
    if not (20 <= batch_size <= 10000) or batch_size % 10 != 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Batch size must be a multiple of 10 between 20 and 10000 for CTGAN.",
        )
    if not (1 <= record_count <= settings.synthmed_ctgan_max_records):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Requested record count must be between 1 and {settings.synthmed_ctgan_max_records}.",
        )


def _set_seed(seed: int | None) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed if seed is not None else int.from_bytes(np.random.bytes(4), "big"))


def _save_report(storage: SynthMedStorageService, job_id: str, filename: str, payload: dict[str, Any]) -> str:
    _, relative = storage.save_report(job_id, filename, dump_json(payload))
    return relative


def _upsert_report(
    db: Session,
    *,
    job: SynthMedGenerationJob,
    generated_id: str,
    report_type: str,
    method: str,
    score: float | None,
    payload: dict[str, Any],
    file_path: str,
) -> SynthMedEvaluationReport:
    report = db.scalar(
        select(SynthMedEvaluationReport).where(
            SynthMedEvaluationReport.job_id == job.id,
            SynthMedEvaluationReport.report_type == report_type,
        )
    )
    if report is None:
        report = SynthMedEvaluationReport(
            id=str(uuid4()),
            job_id=job.id,
            generated_dataset_id=generated_id,
            owner_id=job.owner_id,
            report_type=report_type,
            method=method,
        )
        db.add(report)
    report.method = method
    report.score = json_safe(score)
    report.report_json = json_safe(payload)
    report.file_path = file_path
    return report


def analyse_source(db: Session, source: SynthMedSourceDataset, settings: Settings) -> dict[str, Any]:
    storage = SynthMedStorageService(settings)
    path = storage.resolve_source(source.stored_path)
    frame = read_source_dataframe(path, source.file_format)
    analysis = analyse_dataframe(frame)
    return {
        "sourceDatasetId": source.id,
        "datasetName": source.dataset_name,
        "originalFilename": source.original_filename,
        **json_safe(analysis),
        "generationReady": analysis["totalRecords"] >= 10 and analysis["totalColumns"] >= 2,
        "guidance": (
            "Review identifier and column types before starting CTGAN generation."
            if analysis["totalRecords"] >= 10 and analysis["totalColumns"] >= 2
            else "CTGAN needs at least 10 records and 2 columns for meaningful training."
        ),
    }


def start_generation_job(
    db: Session,
    *,
    source: SynthMedSourceDataset,
    config: dict[str, Any],
    user: Any,
    settings: Settings,
    request: Request | None = None,
) -> SynthMedGenerationJob:
    _validate_config(config, settings)
    job = SynthMedGenerationJob(
        id=str(uuid4()),
        owner_id=user.id,
        source_dataset_id=source.id,
        status="Queued",
        model_name=MODEL_NAME,
        epochs=int(config["epochs"]),
        batch_size=int(config["batchSize"]),
        seed=config.get("seed"),
        requested_record_count=int(config["recordCount"]),
        generated_record_count=0,
        config_json=json_safe(config),
    )
    generation_config = SynthMedGenerationConfig(
        id=str(uuid4()),
        job_id=job.id,
        owner_id=user.id,
        config_json=json_safe(config),
    )
    db.add(job)
    db.add(generation_config)
    log_audit(
        db,
        action="synthmed.generation_started",
        resource_type="synthmed_generation_job",
        resource_id=job.id,
        actor_id=user.id,
        details={
            "source_dataset_id": source.id,
            "model": MODEL_NAME,
            "epochs": job.epochs,
            "batch_size": job.batch_size,
            "record_count": job.requested_record_count,
        },
        request=request,
    )
    db.commit()
    db.refresh(job)

    factory = _session_factory(db)
    if settings.synthmed_generation_inline:
        run_generation_job(job.id, settings, factory)
        db.refresh(job)
    else:
        _executor_for(settings).submit(run_generation_job, job.id, settings, factory)
    return job


def run_generation_job(
    job_id: str, settings: Settings, factory: sessionmaker[Session] | None = None
) -> SynthMedGenerationJob | None:
    session_factory = factory or SessionLocal
    with session_factory() as db:
        job = db.get(SynthMedGenerationJob, job_id)
        if job is None or job.status in TERMINAL_STATUSES:
            return job
        try:
            _status(job, "Preprocessing", started_at=job.started_at or _now())
            db.commit()

            storage = SynthMedStorageService(settings)
            source = db.get(SynthMedSourceDataset, job.source_dataset_id)
            if source is None:
                raise RuntimeError("Source dataset no longer exists.")
            source_path = storage.resolve_source(source.stored_path)
            frame = read_source_dataframe(source_path, source.file_format)
            prepared = prepare_dataframe(frame, job.config_json)

            preprocessing_path = _save_report(storage, job.id, "preprocessing_report.json", prepared["report"])
            metadata_path = _save_report(storage, job.id, "metadata.json", prepared["metadataDict"])

            _status(job, "Training")
            db.commit()
            if settings.environment == "test":
                torch.set_num_threads(1)
            _set_seed(job.seed)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                synthesizer = CTGANSynthesizer(
                    prepared["metadata"],
                    epochs=job.epochs,
                    batch_size=job.batch_size,
                    enable_gpu=False,
                    verbose=False,
                )
            training_started = time.perf_counter()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                synthesizer.fit({TABLE_NAME: prepared["frame"]})
            training_duration = time.perf_counter() - training_started

            model_path, model_relative = storage.save_report(job.id, "ctgan_model.pkl", b"")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                synthesizer.save(str(model_path))

            _status(job, "Generating")
            db.commit()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                sampled = synthesizer.sample(num_rows=job.requested_record_count)
            synthetic = sampled[TABLE_NAME] if isinstance(sampled, dict) else sampled
            if len(synthetic) != job.requested_record_count:
                raise RuntimeError(
                    f"CTGAN generated {len(synthetic)} records but {job.requested_record_count} were requested."
                )

            generated_id = str(uuid4())
            generated_paths: dict[str, str] = {}
            csv_bytes = synthetic.to_csv(index=False).encode("utf-8")
            _, generated_paths["CSV"] = storage.save_generated(
                generated_id, "synthetic_data.csv", csv_bytes
            )
            excel_buffer = io.BytesIO()
            synthetic.to_excel(excel_buffer, index=False, engine="openpyxl")
            _, generated_paths["XLSX"] = storage.save_generated(
                generated_id, "synthetic_data.xlsx", excel_buffer.getvalue()
            )
            json_bytes = synthetic.to_json(orient="records", date_format="iso").encode("utf-8")
            _, generated_paths["JSON"] = storage.save_generated(generated_id, "synthetic_data.json", json_bytes)

            generated = SynthMedGeneratedDataset(
                id=generated_id,
                owner_id=job.owner_id,
                source_dataset_id=source.id,
                dataset_name=str(job.config_json.get("datasetName") or f"{source.dataset_name} synthetic"),
                source_dataset_name=source.dataset_name,
                generation_method=MODEL_NAME,
                record_count=int(len(synthetic)),
                column_count=int(len(synthetic.columns)),
                file_format="CSV",
                file_size_bytes=len(csv_bytes),
                checksum_sha256=hashlib.sha256(csv_bytes).hexdigest()
,
                stored_path=generated_paths["CSV"],
                status="Completed",
            )
            db.add(generated)
            db.flush()
            job.generated_dataset_id = generated_id

            _status(job, "Validating", generated_record_count=int(len(synthetic)))
            db.commit()

            quality = build_quality_report(prepared["frame"], synthetic, prepared["metadataDict"])
            privacy = build_privacy_report(
                prepared["frame"],
                synthetic,
                prepared["metadataDict"],
                prepared["analysis"],
                seed=job.seed,
            )
            quality_path = _save_report(storage, job.id, "quality_report.json", quality)
            privacy_path = _save_report(storage, job.id, "privacy_report.json", privacy)
            _upsert_report(
                db,
                job=job,
                generated_id=generated_id,
                report_type="quality",
                method=quality["method"],
                score=quality.get("overallQualityScore"),
                payload=quality,
                file_path=quality_path,
            )
            _upsert_report(
                db,
                job=job,
                generated_id=generated_id,
                report_type="privacy",
                method=privacy["method"],
                score=privacy.get("newRowSynthesisScore"),
                payload=privacy,
                file_path=privacy_path,
            )
            _upsert_report(
                db,
                job=job,
                generated_id=generated_id,
                report_type="preprocessing",
                method="SynthMed deterministic preprocessing pipeline",
                score=None,
                payload=prepared["report"],
                file_path=preprocessing_path,
            )

            generation_report = {
                "jobId": job.id,
                "generatedDatasetId": generated_id,
                "model": MODEL_NAME,
                "epochs": job.epochs,
                "batchSize": job.batch_size,
                "seed": job.seed,
                "requestedRecordCount": job.requested_record_count,
                "generatedRecordCount": int(len(synthetic)),
                "trainingDurationSeconds": round(training_duration, 3),
                "columns": list(synthetic.columns),
                "generatedPaths": generated_paths,
                "modelPath": model_relative,
                "metadataPath": metadata_path,
                "qualityReportPath": quality_path,
                "privacyReportPath": privacy_path,
                "notes": [
                    "CTGAN training ran on CPU.",
                    "Original source files were not modified.",
                    "Synthetic data is for research and software testing, not clinical decision-making.",
                ],
            }
            generation_path = _save_report(storage, job.id, "generation_report.json", generation_report)
            _upsert_report(
                db,
                job=job,
                generated_id=generated_id,
                report_type="generation",
                method=MODEL_NAME,
                score=None,
                payload=generation_report,
                file_path=generation_path,
            )

            config = dict(job.config_json)
            config["generatedPaths"] = generated_paths
            config["reportPaths"] = {
                "generation": generation_path,
                "preprocessing": preprocessing_path,
                "quality": quality_path,
                "privacy": privacy_path,
                "metadata": metadata_path,
                "model": model_relative,
            }
            job.config_json = json_safe(config)
            _status(
                job,
                "Completed",
                completed_at=_now(),
                training_duration_seconds=round(training_duration, 3),
                generated_record_count=int(len(synthetic)),
                error_json=None,
            )
            log_audit(
                db,
                action="synthmed.generation_completed",
                resource_type="synthmed_generation_job",
                resource_id=job.id,
                actor_id=job.owner_id,
                details={"generated_dataset_id": generated_id, "records": int(len(synthetic))},
            )
            db.commit()
            return job
        except Exception as error:
            db.rollback()
            job = db.get(SynthMedGenerationJob, job_id)
            if job is None:
                return None
            _status(job, "Failed", completed_at=_now(), error_json=json_safe(_error_details(error)))
            log_audit(
                db,
                action="synthmed.generation_failed",
                resource_type="synthmed_generation_job",
                resource_id=job.id,
                actor_id=job.owner_id,
                details=_error_details(error),
            )
            db.commit()
            return job


def job_response(job: SynthMedGenerationJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "sourceDatasetId": job.source_dataset_id,
        "generatedDatasetId": job.generated_dataset_id or "",
        "status": job.status,
        "modelName": job.model_name,
        "epochs": job.epochs,
        "batchSize": job.batch_size,
        "seed": job.seed,
        "requestedRecordCount": job.requested_record_count,
        "generatedRecordCount": job.generated_record_count,
        "trainingDurationSeconds": job.training_duration_seconds,
        "createdAt": _iso(job.created_at),
        "startedAt": _iso(job.started_at),
        "completedAt": _iso(job.completed_at),
        "error": (job.error_json or {}).get("message", ""),
        "config": json_safe(job.config_json),
    }


def get_job(db: Session, job_id: str, user: Any) -> SynthMedGenerationJob:
    job = db.get(SynthMedGenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation job not found.")
    if job.owner_id != user.id and user.role.value != "ADMINISTRATOR":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to view this generation job.")
    return job


def list_jobs(db: Session, user: Any) -> list[SynthMedGenerationJob]:
    return list(
        db.scalars(
            select(SynthMedGenerationJob)
            .where(SynthMedGenerationJob.owner_id == user.id)
            .order_by(SynthMedGenerationJob.created_at.desc())
        )
    )


def job_for_generated(db: Session, generated_id: str) -> SynthMedGenerationJob | None:
    return db.scalar(select(SynthMedGenerationJob).where(SynthMedGenerationJob.generated_dataset_id == generated_id))


def generated_detail(db: Session, generated_id: str, user: Any) -> dict[str, Any]:
    from app.synthmed.services.source_service import ensure_generated_access, get_generated

    generated = get_generated(db, generated_id)
    ensure_generated_access(generated, user)
    job = job_for_generated(db, generated_id)
    reports = list(
        db.scalars(
            select(SynthMedEvaluationReport).where(SynthMedEvaluationReport.generated_dataset_id == generated_id)
        )
    )
    config = dict(job.config_json) if job else {}
    return {
        **to_generated_response(generated).model_dump(),
        "generationJobId": job.id if job else "",
        "modelName": job.model_name if job else generated.generation_method,
        "trainingDurationSeconds": job.training_duration_seconds if job else None,
        "availableFormats": sorted((config.get("generatedPaths") or {}).keys()) or [generated.file_format],
        "reportTypes": sorted({report.report_type for report in reports}),
        "trainingConfig": {
            "epochs": job.epochs if job else None,
            "batchSize": job.batch_size if job else None,
            "seed": job.seed if job else None,
            "preserveMissingness": config.get("preserveMissingness", True),
            "includedColumns": config.get("selectedColumns", []),
        },
    }


def preview_generated(
    db: Session, generated_id: str, user: Any, settings: Settings, page: int, page_size: int
) -> dict[str, Any]:
    from app.synthmed.services.source_service import ensure_generated_access, get_generated

    generated = get_generated(db, generated_id)
    ensure_generated_access(generated, user)
    path = SynthMedStorageService(settings).resolve_generated(generated.stored_path)
    frame = pd.read_csv(path)
    start = (page - 1) * page_size
    rows = json_safe(frame.iloc[start : start + page_size].to_dict(orient="records"))
    return {
        "generatedDatasetId": generated_id,
        "columns": list(frame.columns),
        "rows": rows,
        "totalRecords": int(len(frame)),
        "page": page,
        "pageSize": page_size,
    }


def evaluation_report(db: Session, generated_id: str, report_type: str, user: Any) -> dict[str, Any]:
    from app.synthmed.services.source_service import ensure_generated_access, get_generated

    generated = get_generated(db, generated_id)
    ensure_generated_access(generated, user)
    report = db.scalar(
        select(SynthMedEvaluationReport).where(
            SynthMedEvaluationReport.generated_dataset_id == generated_id,
            SynthMedEvaluationReport.report_type == report_type,
        )
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {report_type} report is available for this generated dataset.",
        )
    return {
        "id": report.id,
        "generatedDatasetId": generated_id,
        "reportType": report.report_type,
        "method": report.method,
        "score": json_safe(report.score),
        "report": json_safe(report.report_json),
        "createdAt": _iso(report.created_at),
    }


def evaluation_report_row(db: Session, generated_id: str, report_type: str) -> SynthMedEvaluationReport:
    report = db.scalar(
        select(SynthMedEvaluationReport).where(
            SynthMedEvaluationReport.generated_dataset_id == generated_id,
            SynthMedEvaluationReport.report_type == report_type,
        )
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {report_type} report file is available.",
        )
    return report


def export_generated(
    db: Session,
    *,
    generated_id: str,
    user: Any,
    file_format: str,
    settings: Settings,
    request: Request | None = None,
) -> dict[str, Any]:
    from app.synthmed.services.source_service import ensure_generated_access, get_generated

    generated = get_generated(db, generated_id)
    ensure_generated_access(generated, user)
    normalized = file_format.strip().upper()
    if normalized not in {"CSV", "XLSX", "JSON"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Export format must be CSV, XLSX or JSON.",
        )

    storage = SynthMedStorageService(settings)
    job = job_for_generated(db, generated_id)
    config = dict(job.config_json) if job else {}
    paths = dict(config.get("generatedPaths") or {})
    if normalized not in paths:
        frame = pd.read_csv(storage.resolve_generated(generated.stored_path))
        if normalized == "CSV":
            content = frame.to_csv(index=False).encode("utf-8")
        elif normalized == "XLSX":
            buffer = io.BytesIO()
            frame.to_excel(buffer, index=False, engine="openpyxl")
            content = buffer.getvalue()
        else:
            content = frame.to_json(orient="records", date_format="iso").encode("utf-8")
        _, paths[normalized] = storage.save_generated(generated_id, f"synthetic_data.{normalized.lower()}", content)
        config["generatedPaths"] = paths
        if job is not None:
            job.config_json = json_safe(config)
    log_audit(
        db,
        action="synthmed.generated_exported",
        resource_type="synthmed_generated_dataset",
        resource_id=generated_id,
        actor_id=user.id,
        details={"format": normalized},
        request=request,
    )
    db.commit()
    return {"generatedDatasetId": generated_id, "format": normalized, "fileName": Path(paths[normalized]).name}


def generated_download_path(db: Session, generated_id: str, file_format: str, settings: Settings) -> tuple[Path, str]:
    generated = db.get(SynthMedGeneratedDataset, generated_id)
    if generated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated dataset not found.")
    normalized = file_format.strip().upper()
    job = job_for_generated(db, generated_id)
    paths = dict((job.config_json if job else {}).get("generatedPaths") or {})
    relative = paths.get(normalized)
    if not relative and normalized == "CSV":
        relative = generated.stored_path
    if not relative:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{normalized} output has not been generated for this dataset.",
        )
    return SynthMedStorageService(settings).resolve_generated(relative), Path(relative).name


def recover_stale_jobs(session_factory: sessionmaker[Session] | None = None) -> int:
    factory = session_factory or SessionLocal
    recovered = 0
    with factory() as db:
        jobs = db.scalars(select(SynthMedGenerationJob).where(SynthMedGenerationJob.status.in_(ACTIVE_STATUSES)))
        for job in jobs:
            _status(
                job,
                "Failed",
                completed_at=_now(),
                error_json={"type": "InterruptedJob", "message": "Generation was interrupted by an API restart."},
            )
            recovered += 1
        db.commit()
    return recovered
