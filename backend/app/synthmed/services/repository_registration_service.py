from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.dataset import Dataset
from app.models.user import User
from app.schemas.dataset import DatasetMetadataInput
from app.synthmed.models import SynthMedDatasetVersion, SynthMedGeneratedDataset, SynthMedGenerationJob
from app.synthmed.services.medical_schema_service import (
    MEASUREMENTS,
    detect_identifier_name,
    validate_strict_output_schema,
)

ALLOWED_GENERATED_COLUMNS = frozenset(
    {"Age", "Gender", "Disease", "Disease_Level", *(definition.canonical for definition in MEASUREMENTS)}
)
EXTENSIONS_BY_FORMAT = {"CSV": "csv", "XLSX": "xlsx", "JSON": "json"}


def _metadata_input(payload: DatasetMetadataInput | BaseModel | dict[str, Any]) -> DatasetMetadataInput:
    if isinstance(payload, DatasetMetadataInput):
        return payload
    if isinstance(payload, BaseModel):
        return DatasetMetadataInput.model_validate(payload.model_dump())
    return DatasetMetadataInput.model_validate(payload)


def _generated_format(generated: SynthMedGeneratedDataset) -> str:
    file_format = getattr(generated.file_format, "value", str(generated.file_format)).upper()
    if file_format not in EXTENSIONS_BY_FORMAT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Generated dataset has an unsupported file format.",
        )
    return file_format


def _safe_generated_filename(stored_path: str, file_format: str) -> str:
    original_name = Path(stored_path).name or "generated"
    stem = Path(original_name).stem or "generated"
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "generated"
    return f"{cleaned[:120]}.{EXTENSIONS_BY_FORMAT[file_format]}"


def _source_repository_dataset_id(db: Session, generated: SynthMedGeneratedDataset) -> str | None:
    statement = (
        select(SynthMedDatasetVersion)
        .where(
            SynthMedDatasetVersion.dataset_kind == "source",
            SynthMedDatasetVersion.logical_dataset_id == generated.source_dataset_id,
        )
        .order_by(SynthMedDatasetVersion.version_number.desc())
    )
    for version in db.scalars(statement):
        metadata = version.metadata_json or {}
        repository_id = metadata.get("repositoryDatasetId")
        if metadata.get("origin") == "repository" and repository_id and db.get(Dataset, repository_id) is not None:
            return str(repository_id)
    return None


def _latest_generation_job(db: Session, generated: SynthMedGeneratedDataset) -> SynthMedGenerationJob | None:
    return db.scalar(
        select(SynthMedGenerationJob)
        .where(SynthMedGenerationJob.generated_dataset_id == generated.id)
        .order_by(SynthMedGenerationJob.created_at.desc())
    )


def _validate_generated_columns(
    frame: Any,
    approved_columns: list[str],
    *,
    enforce_exact_schema: bool,
) -> None:
    columns = [str(column) for column in frame.columns]
    allowed = set(approved_columns)
    offending = [column for column in columns if column not in allowed or detect_identifier_name(column)]
    report = (
        validate_strict_output_schema(frame, approved_columns=approved_columns)
        if enforce_exact_schema
        else None
    )
    if report is not None:
        for hit in report.get("contentHits", []):
            column = str(hit.get("column") or "")
            if column in columns and column not in offending:
                offending.append(column)
    if offending or (report is not None and not report.get("passed")):
        detail: dict[str, Any] = {
            "offendingColumns": offending,
            "allowedColumns": sorted(approved_columns),
        }
        if report is not None:
            detail["errors"] = report.get("errors", [])
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def register_generated_dataset_in_repository(
    db: Session,
    *,
    settings: Settings,
    user: User,
    generated_dataset_id: str,
    payload: DatasetMetadataInput | BaseModel | dict[str, Any],
    request: Request | None = None,
) -> tuple[Dataset, str]:
    from app.services.generated_ingestion_service import ingest_generated_dataset

    metadata = _metadata_input(payload)
    dataset, job = ingest_generated_dataset(
        db,
        settings=settings,
        user=user,
        generated_dataset_id=generated_dataset_id,
        metadata=metadata,
        request=request,
    )
    return (
        dataset,
        "Generated dataset queued for the shared repository ETL pipeline. "
        f"Complete ETL job {job.id} before governance review.",
    )
