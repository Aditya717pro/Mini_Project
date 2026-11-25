from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.enums import UserRole
from app.models.user import User
from app.services.audit_service import log_audit
from app.synthmed.models import (
    SynthMedComparison,
    SynthMedDatasetVersion,
    SynthMedExperiment,
    SynthMedGeneratedDataset,
    SynthMedGenerationConfigurationSnapshot,
    SynthMedGenerationJob,
    SynthMedSourceDataset,
    SynthMedUtilityEvaluation,
)
from app.synthmed.schemas import SynthMedGenerationStartRequest
from app.synthmed.services import condition_service, generation_service, versioning_service
from app.synthmed.services.source_service import (
    ensure_generated_access,
    ensure_source_access,
    get_generated,
    get_source,
)

ALLOWED_STATUSES = {"Draft", "Queued", "Running", "Completed", "Failed", "Cancelled", "Incomplete"}
ACTIVE_JOB_STATUSES = {"Preprocessing", "Training", "Generating", "Validating", "Evaluating", "Running"}
ACTIVE_UTILITY_STATUSES = {
    "Validating",
    "Preprocessing",
    "Training",
    "Training TSTR",
    "Training TRTR",
    "Training TSTR/TRTR",
    "Evaluating",
    "Evaluating TSTR",
    "Evaluating TRTR",
    "Evaluating TSTR/TRTR",
    "Saving Results",
}
INTERNAL_CONFIG_KEYS = {
    "sourceDatasetId",
    "clinicalSetup",
    "sourcePreservationPlan",
    "sourcePreservationPlanInternal",
    "normalizedConditions",
    "samplingPlan",
    "conditionValidation",
    "reusedFromExperimentId",
    "reusedFromSnapshotId",
    "reuseWarnings",
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _ensure_owner(row: Any, user: User) -> None:
    if row.owner_id != user.id and user.role != UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=403, detail="Not permitted to access this experiment.")


def _ensure_version(
    db: Session,
    *,
    user: User,
    version_id: str,
    dataset_id: str | None,
    kind: str,
) -> SynthMedDatasetVersion:
    version = db.get(SynthMedDatasetVersion, str(version_id))
    if version is None:
        raise HTTPException(status_code=404, detail=f"{kind.title()} dataset version not found.")
    _ensure_owner(version, user)
    if version.dataset_kind != kind:
        raise HTTPException(status_code=422, detail=f"Version is not a {kind} dataset version.")
    if dataset_id and version.logical_dataset_id != dataset_id:
        raise HTTPException(status_code=422, detail=f"{kind.title()} version does not belong to the selected dataset.")
    return version


def _ensure_snapshot(
    db: Session, *, user: User, snapshot_id: str, source_id: str | None
) -> SynthMedGenerationConfigurationSnapshot:
    snapshot = db.get(SynthMedGenerationConfigurationSnapshot, str(snapshot_id))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Configuration snapshot not found.")
    _ensure_owner(snapshot, user)
    if source_id and snapshot.source_dataset_id and snapshot.source_dataset_id != source_id:
        raise HTTPException(
            status_code=422, detail="Configuration snapshot belongs to a different source dataset."
        )
    return snapshot


def _derive_status(db: Session, *, requested: str | None, job_id: str | None, utility_id: str | None) -> str:
    if requested and requested != "Draft":
        if requested not in ALLOWED_STATUSES:
            raise HTTPException(status_code=422, detail=f"Unsupported experiment status: {requested}.")
        return requested
    statuses: list[str] = []
    if job_id:
        job = db.get(SynthMedGenerationJob, job_id)
        if job is not None:
            statuses.append(job.status)
    if utility_id:
        utility = db.get(SynthMedUtilityEvaluation, utility_id)
        if utility is not None:
            statuses.append(utility.status)
    if any(status in {"Failed", "Cancelled", "Incomplete"} for status in statuses):
        return next(status for status in statuses if status in {"Failed", "Cancelled", "Incomplete"})
    if any(status in ACTIVE_JOB_STATUSES or status in ACTIVE_UTILITY_STATUSES for status in statuses):
        return "Running"
    if "Completed" in statuses:
        return "Completed"
    if statuses:
        return "Queued"
    return "Draft"


def create_experiment(
    db: Session,
    *,
    user: User,
    settings: Settings,
    payload: dict[str, Any],
    request: Request | None = None,
) -> SynthMedExperiment:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Experiment name is required.")
    source_id = payload.get("sourceDatasetId")
    generated_id = payload.get("generatedDatasetId")
    job_id = payload.get("generationJobId")
    comparison_id = payload.get("comparisonId")
    utility_id = payload.get("utilityEvaluationId")
    source_version_id = payload.get("sourceVersionId")
    generated_version_id = payload.get("generatedVersionId")
    snapshot_id = payload.get("configurationSnapshotId")

    if source_id:
        source = get_source(db, str(source_id))
        ensure_source_access(source, user)
    if generated_id:
        generated = get_generated(db, str(generated_id))
        ensure_generated_access(generated, user)
        if not source_id:
            source_id = generated.source_dataset_id
    if source_version_id:
        version = _ensure_version(
            db,
            user=user,
            version_id=str(source_version_id),
            dataset_id=str(source_id) if source_id else None,
            kind="source",
        )
        source_id = source_id or version.logical_dataset_id
    if generated_version_id:
        version = _ensure_version(
            db,
            user=user,
            version_id=str(generated_version_id),
            dataset_id=str(generated_id) if generated_id else None,
            kind="generated",
        )
        generated_id = generated_id or version.logical_dataset_id
        source_id = source_id or version.source_dataset_id
    if job_id:
        job = db.get(SynthMedGenerationJob, str(job_id))
        if job is None or (job.owner_id != user.id and user.role != UserRole.ADMINISTRATOR):
            raise HTTPException(status_code=404, detail="Generation job not found.")
        if source_id and job.source_dataset_id != source_id:
            raise HTTPException(status_code=422, detail="Generation job belongs to a different source dataset.")
        if generated_id and job.generated_dataset_id and job.generated_dataset_id != generated_id:
            raise HTTPException(status_code=422, detail="Generation job belongs to a different generated dataset.")
        source_id = source_id or job.source_dataset_id
        if not snapshot_id:
            snapshot = versioning_service.snapshot_config(db, user=user, job=job)
            db.add(snapshot)
            db.flush()
            snapshot_id = snapshot.id
    if snapshot_id:
        _ensure_snapshot(db, user=user, snapshot_id=str(snapshot_id), source_id=str(source_id) if source_id else None)
    if comparison_id:
        comparison = db.get(SynthMedComparison, str(comparison_id))
        if comparison is None or (comparison.owner_id != user.id and user.role != UserRole.ADMINISTRATOR):
            raise HTTPException(status_code=404, detail="Comparison not found.")
        if source_id and comparison.source_dataset_id != source_id:
            raise HTTPException(status_code=422, detail="Comparison belongs to a different source dataset.")
        if generated_id and comparison.generated_dataset_id != generated_id:
            raise HTTPException(status_code=422, detail="Comparison belongs to a different generated dataset.")
        source_id = source_id or comparison.source_dataset_id
        generated_id = generated_id or comparison.generated_dataset_id
    if utility_id:
        utility = db.get(SynthMedUtilityEvaluation, str(utility_id))
        if utility is None or (utility.owner_id != user.id and user.role != UserRole.ADMINISTRATOR):
            raise HTTPException(status_code=404, detail="Utility evaluation not found.")
        if source_id and utility.source_dataset_id != source_id:
            raise HTTPException(status_code=422, detail="Utility evaluation belongs to a different source dataset.")
        if generated_id and utility.generated_dataset_id != generated_id:
            raise HTTPException(status_code=422, detail="Utility evaluation belongs to a different generated dataset.")
        source_id = source_id or utility.source_dataset_id
        generated_id = generated_id or utility.generated_dataset_id

    if source_id and not source_version_id:
        source = db.get(SynthMedSourceDataset, str(source_id))
        if source is not None:
            source_version_id = versioning_service.ensure_source_version(
                db, user=user, settings=settings, source=source, request=request
            ).id
    if generated_id and not generated_version_id:
        generated = db.get(SynthMedGeneratedDataset, str(generated_id))
        if generated is not None:
            generated_version_id = versioning_service.ensure_generated_version(
                db, user=user, settings=settings, generated=generated, request=request
            ).id

    status = _derive_status(
        db,
        requested=str(payload.get("status") or "Draft"),
        job_id=str(job_id) if job_id else None,
        utility_id=str(utility_id) if utility_id else None,
    )
    row = SynthMedExperiment(
        id=str(uuid4()),
        owner_id=user.id,
        name=name,
        description=str(payload.get("description") or ""),
        status=status,
        source_dataset_id=str(source_id) if source_id else None,
        source_version_id=str(source_version_id) if source_version_id else None,
        generated_dataset_id=str(generated_id) if generated_id else None,
        generated_version_id=str(generated_version_id) if generated_version_id else None,
        generation_job_id=str(job_id) if job_id else None,
        configuration_snapshot_id=str(snapshot_id) if snapshot_id else None,
        comparison_id=str(comparison_id) if comparison_id else None,
        utility_evaluation_id=str(utility_id) if utility_id else None,
        notes=str(payload.get("notes") or ""),
        metadata_json=payload.get("metadata") or {},
    )
    db.add(row)
    log_audit(
        db,
        action="synthmed.experiment_created",
        resource_type="synthmed_experiment",
        resource_id=row.id,
        actor_id=user.id,
        details={
            "name": name,
            "sourceDatasetId": row.source_dataset_id,
            "generatedDatasetId": row.generated_dataset_id,
            "status": status,
        },
        request=request,
    )
    db.commit()
    db.refresh(row)
    return row


def list_experiments(db: Session, *, user: User) -> list[SynthMedExperiment]:
    stmt = select(SynthMedExperiment)
    if user.role != UserRole.ADMINISTRATOR:
        stmt = stmt.where(SynthMedExperiment.owner_id == user.id)
    return list(db.scalars(stmt.order_by(SynthMedExperiment.created_at.desc())))


def get_experiment(db: Session, *, user: User, experiment_id: str) -> SynthMedExperiment:
    row = db.get(SynthMedExperiment, experiment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Experiment not found.")
    _ensure_owner(row, user)
    return row


def _reuse_warnings(
    *,
    row: SynthMedExperiment,
    snapshot: SynthMedGenerationConfigurationSnapshot,
    config: dict[str, Any],
    source_id: str,
) -> list[str]:
    warnings: list[str] = []
    raw_model = config.get("model") or config.get("selectedModel") or snapshot.model_name
    model = condition_service.normalize_model(raw_model)
    if model is None:
        warnings.append(f"Snapshot model {raw_model!r} is unsupported; using CTGAN.")
        model = "CTGAN"
    elif model not in condition_service.MODEL_LABELS:
        warnings.append(f"Snapshot model {model!r} is no longer supported; using CTGAN.")
        model = "CTGAN"
    config["model"] = model
    config["selectedModel"] = model
    saved_version = config.get("sdvVersion") or (row.metadata_json or {}).get("sdvVersion")
    if saved_version and saved_version != condition_service.SDV_VERSION:
        warnings.append(f"SDV version changed from {saved_version} to {condition_service.SDV_VERSION}.")
    supported = set(SynthMedGenerationStartRequest.model_fields)
    for key in sorted(config):
        if key not in supported and key not in INTERNAL_CONFIG_KEYS:
            warnings.append(f"Snapshot parameter '{key}' is not supported by the current generation schema.")
    for key, field in SynthMedGenerationStartRequest.model_fields.items():
        if key in {"epochs", "batchSize", "recordCount"} and key not in config:
            config[key] = field.default
            warnings.append(f"Snapshot is missing '{key}'; using current default {field.default}.")
    configured_source = config.get("sourceDatasetId")
    if configured_source and configured_source != source_id:
        warnings.append(f"Source dataset changed from {configured_source} to {source_id}.")
    if snapshot.source_dataset_id and snapshot.source_dataset_id != source_id:
        warnings.append(f"Snapshot source dataset changed from {snapshot.source_dataset_id} to {source_id}.")
    if row.source_dataset_id and row.source_dataset_id != source_id:
        warnings.append(f"Experiment source dataset changed from {row.source_dataset_id} to {source_id}.")
    return warnings


def reuse_configuration(
    db: Session,
    *,
    user: User,
    settings: Settings,
    experiment_id: str,
    payload: dict[str, Any] | None = None,
    request: Request | None = None,
) -> SynthMedGenerationJob:
    row = get_experiment(db, user=user, experiment_id=experiment_id)
    if not row.configuration_snapshot_id:
        raise HTTPException(status_code=422, detail="Experiment has no configuration snapshot to reuse.")
    snapshot = _ensure_snapshot(db, user=user, snapshot_id=row.configuration_snapshot_id, source_id=None)
    config = dict(snapshot.config_json or {})
    source_id = str(config.get("sourceDatasetId") or row.source_dataset_id or "")
    if not source_id:
        raise HTTPException(status_code=422, detail="Snapshot is missing source dataset; cannot reuse safely.")
    source = get_source(db, source_id)
    ensure_source_access(source, user)
    warnings = _reuse_warnings(row=row, snapshot=snapshot, config=config, source_id=source.id)
    config["sourceDatasetId"] = source.id
    config["reusedFromExperimentId"] = row.id
    config["reusedFromSnapshotId"] = snapshot.id
    config["reuseWarnings"] = warnings
    job = generation_service.start_generation_job(
        db, user=user, source=source, config=config, settings=settings, request=request
    )
    attempts = list((row.metadata_json or {}).get("attempts") or [])
    attempt = {
        "jobId": job.id,
        "snapshotId": snapshot.id,
        "warnings": warnings,
        "createdAt": _iso(_now()),
        "status": job.status,
        "reusedFromExperimentId": row.id,
    }
    attempts.append(attempt)
    if (payload or {}).get("reuseAsNewExperiment"):
        metadata = dict(row.metadata_json or {})
        metadata["attempts"] = attempts
        metadata["reusedFromExperimentId"] = row.id
        create_experiment(
            db,
            user=user,
            settings=settings,
            payload={
                "name": f"{row.name} (reuse)",
                "description": row.description,
                "status": "Queued",
                "sourceDatasetId": source.id,
                "generatedDatasetId": row.generated_dataset_id,
                "generationJobId": job.id,
                "configurationSnapshotId": snapshot.id,
                "comparisonId": row.comparison_id,
                "utilityEvaluationId": row.utility_evaluation_id,
                "notes": row.notes,
                "metadata": metadata,
            },
            request=request,
        )
    else:
        metadata = dict(row.metadata_json or {})
        metadata["attempts"] = attempts
        row.metadata_json = metadata
        row.updated_at = _now()
        if not row.generation_job_id:
            row.generation_job_id = job.id
    log_audit(
        db,
        action="synthmed.experiment_reused",
        resource_type="synthmed_experiment",
        resource_id=row.id,
        actor_id=user.id,
        details={"jobId": job.id, "snapshotId": snapshot.id, "warnings": warnings, "attemptCount": len(attempts)},
        request=request,
    )
    db.commit()
    db.refresh(job)
    return job


def experiment_history(db: Session, *, user: User, experiment_id: str) -> dict[str, Any]:
    row = get_experiment(db, user=user, experiment_id=experiment_id)
    enriched = versioning_service.to_experiment_response(db, row)
    return {
        "experimentId": row.id,
        "attempts": list((row.metadata_json or {}).get("attempts") or []),
        "lineage": enriched["lineage"],
        "status": row.status,
        "createdAt": enriched["createdAt"],
        "updatedAt": enriched["updatedAt"],
    }


def experiment_configurations(db: Session, *, user: User, experiment_id: str) -> list[dict[str, Any]]:
    row = get_experiment(db, user=user, experiment_id=experiment_id)
    snapshot_ids = [row.configuration_snapshot_id] if row.configuration_snapshot_id else []
    snapshot_ids.extend(
        str(attempt["snapshotId"])
        for attempt in (row.metadata_json or {}).get("attempts", [])
        if isinstance(attempt, dict) and attempt.get("snapshotId")
    )
    snapshots = []
    for snapshot_id in dict.fromkeys(snapshot_ids):
        snapshot = _ensure_snapshot(
            db, user=user, snapshot_id=str(snapshot_id), source_id=row.source_dataset_id
        )
        snapshots.append(versioning_service.to_snapshot_response(snapshot))
    return snapshots
