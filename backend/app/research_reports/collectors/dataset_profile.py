from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.reports import QualityReport, ReadinessReport
from app.research_reports.collectors.common import dataset_frame, flatten_values
from app.research_reports.sanitize import NOT_AVAILABLE, clean_number, clean_text, safe_column_name
from app.research_reports.validation import ResolvedSources
from app.synthmed.services.dataset_service import analyse_dataframe


def _number(value: Any) -> Any:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return NOT_AVAILABLE


def collect(db: Session, settings: Settings, sources: ResolvedSources) -> dict[str, Any]:
    frame, file_format = dataset_frame(db, settings, sources)
    analysis = analyse_dataframe(frame)
    version = sources.dataset_version or sources.synth_version
    version_label = getattr(version, "version_label", "") or ""
    version_number = getattr(version, "version_number", "") or ""

    metadata: dict[str, Any] = {
        "Dataset ID": sources.dataset.id if sources.dataset else sources.synth_source.id,
        "Source kind": "Core dataset" if sources.dataset else "SynthMed source",
        "Version ID": version.id if version else NOT_AVAILABLE,
        "Version label": version_label or NOT_AVAILABLE,
        "Version number": version_number or NOT_AVAILABLE,
        "File format": file_format,
        "Records": len(frame),
        "Columns": len(frame.columns),
        "Duplicate records": analysis["duplicateRecords"],
        "Missing rate": clean_number(getattr(sources.dataset, "missing_rate", None)),
        "Record checksum": getattr(version, "checksum_sha256", "") or NOT_AVAILABLE,
    }

    schema_rows: list[list[Any]] = []
    for column in analysis["columns"]:
        name = safe_column_name(column["name"])
        if name == "[REDACTED]" or column.get("potentialIdentifier"):
            continue
        flag = "quasi-identifier" if column.get("quasiIdentifier") else "standard"
        schema_rows.append(
            [
                name,
                clean_text(column.get("dtype")),
                clean_text(column.get("kind")),
                column.get("missingCount", 0),
                column.get("missingPercentage", 0),
                column.get("uniqueCount", 0),
                flag,
            ]
        )

    numeric_rows: list[list[Any]] = []
    categorical_rows: list[list[Any]] = []
    for column in analysis["columns"]:
        original = column["name"]
        name = safe_column_name(original)
        if name == "[REDACTED]" or column.get("potentialIdentifier"):
            continue
        if column.get("kind") == "numerical":
            series = frame[original]
            numeric_rows.append(
                [
                    name,
                    _number(series.min()),
                    _number(series.max()),
                    _number(series.mean()),
                    _number(series.median()),
                    _number(series.std()),
                    int(series.isna().sum()),
                ]
            )
        elif column.get("kind") in {"categorical", "boolean", "datetime"}:
            series = frame[original]
            counts = series.value_counts(dropna=True)
            categorical_rows.append(
                [
                    name,
                    "[NOT DISCLOSED]",
                    int(counts.iloc[0]) if not counts.empty else 0,
                    int(series.nunique(dropna=True)),
                    int(series.isna().sum()),
                ]
            )

    quality_rows: list[list[Any]] = []
    dataset_id = sources.dataset.id if sources.dataset else None
    version_id = sources.dataset_version.id if sources.dataset_version else None
    if dataset_id and version_id:
        quality = db.scalar(
            select(QualityReport)
            .where(QualityReport.dataset_id == dataset_id, QualityReport.dataset_version_id == version_id)
            .order_by(QualityReport.created_at.desc())
        )
        if quality:
            for label, value in flatten_values(quality.dimensions_json or {}):
                quality_rows.append([label, value, quality.method])
            quality_rows.append(["Overall quality score", quality.overall_score, quality.formula_version])
        readiness = db.scalar(
            select(ReadinessReport)
            .where(ReadinessReport.dataset_id == dataset_id, ReadinessReport.dataset_version_id == version_id)
            .order_by(ReadinessReport.created_at.desc())
        )
        if readiness:
            quality_rows.append(["Readiness verdict", readiness.verdict, readiness.method])
    if not quality_rows:
        quality_rows.append([NOT_AVAILABLE, NOT_AVAILABLE, "No persisted assessment for this version"])

    return {
        "metadata": metadata,
        "schema_columns": schema_rows,
        "numerical": numeric_rows,
        "categorical": categorical_rows,
        "quality": quality_rows,
        "limitations": [
            "Identifier-like columns are omitted from the schema and distribution tables.",
            "Categorical values are not disclosed to avoid exposing rare or patient-level entries.",
            "Quality context is reproduced only where a persisted assessment exists for this version.",
        ],
    }


def assert_supported(sources: ResolvedSources) -> None:
    if sources.dataset is None and sources.synth_source is None:
        raise HTTPException(status_code=422, detail="A persisted dataset source is required for this report.")
