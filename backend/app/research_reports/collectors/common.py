from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.research_reports.sanitize import NOT_AVAILABLE, clean_label, clean_text
from app.research_reports.validation import ResolvedSources
from app.services.storage_paths import resolve_within_root
from app.synthmed.services.dataset_service import read_source_dataframe
from app.synthmed.services.storage_service import SynthMedStorageService


def dataset_frame(db: Session, settings: Settings, sources: ResolvedSources, *, processed: bool = False):
    if sources.dataset and sources.dataset_version:
        base = Path(settings.processed_storage_dir if processed else settings.raw_storage_dir)
        stored = sources.dataset_version.processed_file_path if processed else sources.dataset_version.raw_file_path
        if not stored:
            raise HTTPException(status_code=404, detail="Dataset file reference is not available.")
        try:
            path = resolve_within_root(base, stored)
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=404, detail="Dataset file is not available on disk.") from error
        file_format = sources.dataset.format.value
    elif sources.synth_source:
        storage = SynthMedStorageService(settings)
        try:
            path = storage.resolve_source(sources.synth_source.stored_path)
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=404, detail="Source dataset file is not available on disk.") from error
        file_format = sources.synth_source.file_format
    else:
        raise HTTPException(status_code=422, detail="No dataset source was resolved for this report.")
    return read_source_dataframe(path, file_format), file_format


def flatten_values(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            label = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(flatten_values(item, label))
    elif isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            rows.append((prefix or "values", ", ".join(str(item) for item in value)))
        else:
            for index, item in enumerate(value, start=1):
                rows.extend(flatten_values(item, f"{prefix}[{index}]"))
    else:
        rows.append((prefix or "value", value))
    return rows


def metric_rows(value: Any, *, label: str = "Metric") -> list[list[str]]:
    from app.research_reports.sanitize import clean_number

    return [[clean_label(key), clean_number(item)] for key, item in flatten_values(value)]


def numeric_pairs(value: Any) -> tuple[list[str], list[float]]:
    labels: list[str] = []
    numbers: list[float] = []
    for key, item in flatten_values(value):
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        labels.append(clean_label(key))
        numbers.append(number)
    return labels, numbers


def iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else (clean_text(value) if value else NOT_AVAILABLE)
