from __future__ import annotations

import hashlib

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.dataset import Dataset
from app.models.enums import DatasetStatus
from app.models.etl import ETLJob
from app.models.user import User
from app.schemas.dataset import DatasetMetadataInput
from app.services.audit_service import log_audit
from app.services.upload_service import create_upload
from app.synthmed.models import SynthMedGeneratedDataset, SynthMedGenerationJob
from app.synthmed.services.dataset_service import read_source_dataframe
from app.synthmed.services.repository_registration_service import (
    ALLOWED_GENERATED_COLUMNS,
    _generated_format,
    _latest_generation_job,
    _safe_generated_filename,
    _source_repository_dataset_id,
    _validate_generated_columns,
)
from app.synthmed.services.source_service import ensure_generated_access, get_generated
from app.synthmed.services.storage_service import SynthMedStorageService


def ingest_generated_dataset(
    db: Session,
    *,
    settings: Settings,
    user: User,
    generated_dataset_id: str,
    metadata: DatasetMetadataInput,
    request: Request | None = None,
) -> tuple[Dataset, ETLJob]:
    generated: SynthMedGeneratedDataset = get_generated(db, generated_dataset_id)
    ensure_generated_access(generated, user)
    if generated.status != "Completed" or not generated.stored_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Generated dataset is not completed or has no stored file.",
        )

    duplicate = db.scalar(select(Dataset).where(Dataset.source_generated_dataset_id == generated.id))
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Generated dataset is already registered as repository dataset {duplicate.id}.",
        )

    file_format = _generated_format(generated)
    filename = _safe_generated_filename(generated.stored_path, file_format)
    try:
        path = SynthMedStorageService(settings).resolve_generated(generated.stored_path)
    except (ValueError, FileNotFoundError, OSError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Generated file not found on disk."
        ) from error
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated file not found on disk.")
    try:
        content = path.read_bytes()
    except OSError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Generated file could not be read.") from error

    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Generated file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB upload limit.",
        )

    checksum = hashlib.sha256(content).hexdigest()
    if checksum != generated.checksum_sha256 or len(content) != generated.file_size_bytes:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Generated file checksum or size mismatch.")

    frame = read_source_dataframe(path, file_format)
    columns = [str(column) for column in frame.columns]
    if not columns:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Generated dataset has no columns."
        )

    generation_job: SynthMedGenerationJob | None = _latest_generation_job(db, generated)
    job_config = dict(generation_job.config_json or {}) if generation_job is not None else {}
    approved_columns = [str(column) for column in job_config.get("approvedOutputColumns") or []]
    enforce_exact_schema = bool(approved_columns)
    if not approved_columns:
        approved_columns = sorted(ALLOWED_GENERATED_COLUMNS)
    _validate_generated_columns(frame, approved_columns, enforce_exact_schema=enforce_exact_schema)

    repository_dataset_id = _source_repository_dataset_id(db, generated)
    provenance = {
        "ingestionPath": "shared-etl",
        "generatedDatasetId": generated.id,
        "sourceDatasetId": generated.source_dataset_id,
        "sourceDatasetName": generated.source_dataset_name,
        "generationJobId": generation_job.id if generation_job is not None else None,
        "generationModel": generated.selected_model,
        "checksumSha256": generated.checksum_sha256,
        "sourceRepositoryDatasetId": repository_dataset_id,
        "storage": "independent-copy",
        "generatedStoredPath": generated.stored_path,
    }

    dataset, job = create_upload(
        db,
        settings=settings,
        user=user,
        filename=filename,
        content=content,
        metadata=metadata,
        origin="Synthetic",
        provenance_json=provenance,
        source_generated_dataset_id=generated.id,
        source_repository_dataset_id=repository_dataset_id,
        generation_job_id=generation_job.id if generation_job is not None else None,
        generation_model=generated.selected_model,
        metadata_source="synthmed-generated-shared-etl",
        request=request,
    )
    db.refresh(dataset)
    log_audit(
        db,
        action="synthmed.generated_ingestion_queued",
        resource_type="dataset",
        resource_id=dataset.id,
        actor_id=user.id,
        details={
            "generatedDatasetId": generated.id,
            "checksum": checksum,
            "ingestionPath": "shared-etl",
            "etlJobId": job.id,
            "status": DatasetStatus.PROCESSING.value,
        },
        request=request,
    )
    db.commit()
    db.refresh(dataset)
    db.refresh(job)
    return dataset, job
