from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.etl.extract import ExtractResult, extract_dataset
from app.etl.transform import suggest_mappings
from app.models.dataset import Dataset, DatasetMetadata, DatasetVersion
from app.models.enums import DatasetStatus, FileFormat, JobStatus
from app.models.etl import ETLJob, ETLJobLog
from app.models.user import User
from app.schemas.dataset import DatasetMetadataInput
from app.services.audit_service import log_audit
from app.services.storage_service import StorageService
from app.utils.uploads import format_for_extension, validate_upload


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def create_upload(
    db: Session,
    *,
    settings: Settings,
    user: User,
    filename: str,
    content: bytes,
    metadata: DatasetMetadataInput,
    origin: str = "Original",
    provenance_json: dict | None = None,
    source_generated_dataset_id: str | None = None,
    source_repository_dataset_id: str | None = None,
    generation_job_id: str | None = None,
    generation_model: str | None = None,
    metadata_source: str = "upload",
    request: Request | None = None,
) -> tuple[Dataset, ETLJob]:
    file_format: FileFormat = format_for_extension(filename)
    validate_upload(filename, content, settings.max_upload_bytes)
    checksum = _checksum(content)
    dataset_id = str(uuid4())
    version_id = str(uuid4())
    job_id = str(uuid4())
    storage = StorageService(settings)
    raw_path: Path | None = None

    try:
        raw_path = storage.save_raw(dataset_id, "v1.0", filename, content)
        raw_relative_path = storage.relative_path(raw_path, kind="raw")
        extracted: ExtractResult = extract_dataset(raw_path, file_format)
        profile = extracted.profile
        suggestions = suggest_mappings([column.name for column in profile.columns])

        dataset = Dataset(
            id=dataset_id,
            owner_id=user.id,
            title=metadata.title.strip(),
            description=metadata.description.strip(),
            domain=metadata.domain.strip(),
            access_classification=metadata.access,
            status=DatasetStatus.PROCESSING,
            format=file_format,
            original_filename=Path(filename).name,
            original_path=raw_relative_path,
            origin=origin,
            source_generated_dataset_id=source_generated_dataset_id,
            source_repository_dataset_id=source_repository_dataset_id,
            generation_job_id=generation_job_id,
            generation_model=generation_model,
            provenance_json=provenance_json or {},
            checksum_sha256=checksum,
            file_size_bytes=len(content),
            record_count=profile.row_count,
            column_count=profile.column_count,
            current_version_number=1,
            missing_rate=profile.missing_pct,
            duplicate_rate=profile.duplicate_pct,
            research_task=metadata.research_task.strip(),
        )
        version = DatasetVersion(
            id=version_id,
            dataset_id=dataset_id,
            version_number=1,
            version_label="v1.0",
            raw_file_path=raw_relative_path,
            checksum_sha256=checksum,
            file_size_bytes=len(content),
            record_count=profile.row_count,
            column_count=profile.column_count,
            profile_json=profile.as_dict(),
            transformation_log_json={},
            is_current=True,
        )
        record = DatasetMetadata(
            dataset_id=dataset_id,
            keywords=metadata.tags,
            age_range=metadata.age_range.strip(),
            geography=metadata.geography,
            study_design=metadata.study_design.strip(),
            license=metadata.license.strip(),
            ethics_approved=metadata.ethics_approved,
            data_dictionary_available=metadata.data_dictionary_available,
            consent_scope="Declared by contributor" if metadata.ethics_approved else "Not declared",
            intended_tasks=metadata.intended_tasks,
            label_column=metadata.label_column.strip() if metadata.label_column else None,
            additional_json={"source": metadata_source, "checksum_algorithm": "sha256"},
        )
        job = ETLJob(
            id=job_id,
            dataset_id=dataset_id,
            dataset_version_id=version_id,
            initiated_by_id=user.id,
            status=JobStatus.QUEUED,
            current_stage="extract",
            progress=10,
            suggested_mapping_json=suggestions,
            approved_mapping_json={},
            profile_json=profile.as_dict(),
            rows_in=profile.row_count,
            rows_out=0,
            started_at=datetime.now(UTC),
        )
        db.add_all([dataset, version, record, job])
        db.add(
            ETLJobLog(
                job_id=job_id,
                stage="extract",
                level="INFO",
                message=(
                    f"Extracted {profile.row_count} rows and {profile.column_count} columns. "
                    f"SHA-256 {checksum[:16]}... Original file retained at upload time."
                ),
                details_json={"missing_pct": profile.missing_pct, "duplicate_rows": profile.duplicate_rows},
            )
        )
        db.add(
            ETLJobLog(
                job_id=job_id,
                stage="transform",
                level="WARN",
                message=(
                    "Column mapping requires explicit contributor approval. "
                    "Name similarity alone is not equivalence."
                ),
                details_json={"suggestions": len(suggestions)},
            )
        )
        log_audit(
            db,
            action="dataset.uploaded",
            resource_type="dataset",
            resource_id=dataset_id,
            actor_id=user.id,
            details={
                "filename": Path(filename).name,
                "format": file_format.value,
                "checksum": checksum,
                "origin": origin,
                **({"generatedDatasetId": source_generated_dataset_id} if source_generated_dataset_id else {}),
            },
            request=request,
        )
        db.commit()
        db.refresh(dataset)
        db.refresh(job)
        return dataset, job
    except Exception:
        db.rollback()
        if raw_path is not None:
            raw_path.unlink(missing_ok=True)
        raise
