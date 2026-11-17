from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.etl.extract import ExtractResult, extract_dataset
from app.etl.load import write_processed_csv, write_transformation_log
from app.etl.transform import TransformResult, transform_dataset
from app.models.enums import FileFormat
from app.services.storage_service import StorageService


@dataclass
class PipelineResult:
    extracted: ExtractResult
    transformed: TransformResult
    processed_path: Path
    log_path: Path
    transformation_log: dict[str, Any]


def run_pipeline(
    *,
    raw_path: str | Path,
    file_format: FileFormat,
    approved_mapping: dict[str, str | None],
    storage: StorageService,
    dataset_id: str,
    version_id: str,
) -> PipelineResult:
    extracted = extract_dataset(raw_path, file_format)
    transformed = transform_dataset(extracted.dataframe, approved_mapping)
    processed_path = write_processed_csv(transformed.dataframe, storage, dataset_id, version_id)
    transformation_log = {
        "dataset_id": dataset_id,
        "version_id": version_id,
        "rows_in": len(extracted.dataframe),
        "rows_out": len(transformed.dataframe),
        "columns_in": len(extracted.dataframe.columns),
        "columns_out": len(transformed.dataframe.columns),
        "approved_mapping": approved_mapping,
        "logs": transformed.logs,
        "missing_counts": transformed.missing_counts,
        "duplicate_count": transformed.duplicate_count,
        "invalid_counts": transformed.invalid_counts,
        "review_count": transformed.review_count,
        "preservation_policy": "Original uploaded file retained; source values preserved in original__ columns.",
    }
    log_path = write_transformation_log(transformation_log, storage, dataset_id, version_id)
    return PipelineResult(
        extracted=extracted,
        transformed=transformed,
        processed_path=processed_path,
        log_path=log_path,
        transformation_log=transformation_log,
    )
