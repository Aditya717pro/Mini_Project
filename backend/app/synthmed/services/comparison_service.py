from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.models.enums import UserRole
from app.models.user import User
from app.services.audit_service import log_audit
from app.synthmed.models import SynthMedComparison
from app.synthmed.schemas import (
    SynthMedComparisonChart,
    SynthMedComparisonColumnMetric,
    SynthMedComparisonListItem,
    SynthMedComparisonResponse,
    SynthMedComparisonSummary,
)
from app.synthmed.services.dataset_service import (
    analyse_dataframe,
    dump_json,
    json_safe,
    read_source_dataframe,
)
from app.synthmed.services.source_service import (
    ensure_generated_access,
    ensure_source_access,
    get_generated,
    get_source,
)
from app.synthmed.services.storage_service import SynthMedStorageService

METHOD = "Source vs generated distribution comparison"
CATEGORICAL_KINDS = {"categorical", "boolean", "datetime"}
LIMITATIONS = [
    "Distribution similarity is descriptive only and does not establish clinical validity.",
    "Identifier-style columns are excluded during generation and may legitimately be absent from synthetic output.",
    "Only columns shared by both files are compared numerically; inspect column coverage before interpreting scores.",
    "No differential privacy mechanism or re-identification guarantee is implied by this comparison.",
]


def _iso(value: Any) -> str:
    if not value:
        return ""
    if getattr(value, "tzinfo", None) is not None:
        value = value.replace(tzinfo=None)
    return value.isoformat()


def _validate_id(value: str, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found.") from error


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not np.isfinite(number):
        return None
    return round(number, digits)


def _kind_map(frame: pd.DataFrame) -> dict[str, str]:
    return {item["name"]: str(item["kind"]) for item in analyse_dataframe(frame)["columns"]}


def _missing_map(frame: pd.DataFrame) -> dict[str, float]:
    return {
        item["name"]: float(item["missingPercentage"])
        for item in analyse_dataframe(frame)["columns"]
    }


def _unique_map(frame: pd.DataFrame) -> dict[str, int]:
    return {
        item["name"]: int(item["uniqueCount"])
        for item in analyse_dataframe(frame)["columns"]
    }


def _numeric_values(series: pd.Series) -> np.ndarray:
    converted = pd.to_numeric(series, errors="coerce")
    return converted.dropna().astype(float).to_numpy()


def _categorical_values(series: pd.Series) -> pd.Series:
    values = series.dropna().astype("string").str.strip()
    return values[values != ""]


def _numeric_stats(series: pd.Series) -> dict[str, Any]:
    values = _numeric_values(series)
    if values.size == 0:
        return {"count": 0, "mean": None, "stdDev": None, "min": None, "median": None, "max": None}
    return json_safe(
        {
            "count": int(values.size),
            "mean": float(np.mean(values)),
            "stdDev": float(np.std(values, ddof=0)),
            "min": float(np.min(values)),
            "median": float(np.median(values)),
            "max": float(np.max(values)),
        }
    )


def _categorical_stats(series: pd.Series) -> dict[str, Any]:
    values = _categorical_values(series)
    total = int(values.size)
    counts = values.value_counts().head(10)
    return json_safe(
        {
            "count": total,
            "uniqueCount": int(values.nunique()),
            "topValues": [
                {
                    "value": str(value),
                    "count": int(count),
                    "percentage": _round(count / total * 100, 2) if total else 0.0,
                }
                for value, count in counts.items()
            ],
        }
    )


def _ks_distance(original: pd.Series, synthetic: pd.Series) -> float | None:
    real = np.sort(_numeric_values(original))
    generated = np.sort(_numeric_values(synthetic))
    if real.size == 0 or generated.size == 0:
        return None
    combined = np.concatenate([real, generated])
    real_cdf = np.searchsorted(real, combined, side="right") / real.size
    synthetic_cdf = np.searchsorted(generated, combined, side="right") / generated.size
    return _round(float(np.max(np.abs(real_cdf - synthetic_cdf))))


def _total_variation_distance(original: pd.Series, synthetic: pd.Series) -> float | None:
    real = _categorical_values(original)
    generated = _categorical_values(synthetic)
    if real.empty and generated.empty:
        return None
    real_counts = real.value_counts(normalize=True).to_dict()
    synthetic_counts = generated.value_counts(normalize=True).to_dict()
    categories = set(real_counts) | set(synthetic_counts)
    distance = 0.5 * sum(
        abs(float(real_counts.get(category, 0.0)) - float(synthetic_counts.get(category, 0.0)))
        for category in categories
    )
    return _round(distance)


def _numeric_chart(column: str, original: pd.Series, synthetic: pd.Series) -> dict[str, Any] | None:
    real = _numeric_values(original)
    generated = _numeric_values(synthetic)
    if real.size == 0 and generated.size == 0:
        return None
    combined = np.concatenate([real, generated]) if real.size and generated.size else (real if real.size else generated)
    if combined.size == 0 or not np.isfinite(combined).all():
        return None

    low = float(np.min(combined))
    high = float(np.max(combined))
    if low == high:
        points = [
            {
                "bucket": f"{low:.4g}",
                "original": int(real.size),
                "synthetic": int(generated.size),
            }
        ]
        return json_safe({"column": column, "kind": "numerical", "title": f"{column} distribution", "points": points})

    bins = int(min(12, max(4, np.sqrt(combined.size))))
    edges = np.histogram_bin_edges(combined, bins=bins)
    real_counts, _ = np.histogram(real, bins=edges)
    synthetic_counts, _ = np.histogram(generated, bins=edges)
    points = [
        {
            "bucket": f"{edges[index]:.4g}–{edges[index + 1]:.4g}",
            "original": int(real_counts[index]),
            "synthetic": int(synthetic_counts[index]),
        }
        for index in range(len(edges) - 1)
    ]
    return json_safe({"column": column, "kind": "numerical", "title": f"{column} distribution", "points": points})


def _categorical_chart(column: str, original: pd.Series, synthetic: pd.Series) -> dict[str, Any] | None:
    real = _categorical_values(original)
    generated = _categorical_values(synthetic)
    real_counts = real.value_counts().to_dict()
    synthetic_counts = generated.value_counts().to_dict()
    categories = sorted(
        set(real_counts) | set(synthetic_counts),
        key=lambda value: int(real_counts.get(value, 0)) + int(synthetic_counts.get(value, 0)),
        reverse=True,
    )[:10]
    if not categories:
        return None
    points = [
        {
            "category": str(category),
            "original": _round(int(real_counts.get(category, 0)) / real.size * 100, 2) if real.size else 0.0,
            "synthetic": (
                _round(int(synthetic_counts.get(category, 0)) / generated.size * 100, 2) if generated.size else 0.0
            ),
        }
        for category in categories
    ]
    return json_safe({"column": column, "kind": "categorical", "title": f"{column} categories", "points": points})


def build_comparison_report(
    source_frame: pd.DataFrame,
    synthetic_frame: pd.DataFrame,
    source_name: str,
    generated_name: str,
) -> dict[str, Any]:
    source_kinds = _kind_map(source_frame)
    synthetic_kinds = _kind_map(synthetic_frame)
    source_missing = _missing_map(source_frame)
    synthetic_missing = _missing_map(synthetic_frame)
    source_unique = _unique_map(source_frame)
    synthetic_unique = _unique_map(synthetic_frame)

    shared = [column for column in source_frame.columns if column in synthetic_frame.columns]
    if not shared:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The original and synthetic datasets have no columns in common.",
        )

    columns: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []
    numeric_similarities: list[float] = []
    categorical_similarities: list[float] = []
    all_similarities: list[float] = []
    missingness_values: list[float] = []

    for column in shared:
        source_kind = source_kinds.get(column, "unknown")
        synthetic_kind = synthetic_kinds.get(column, "unknown")
        source_series = source_frame[column]
        synthetic_series = synthetic_frame[column]
        item: dict[str, Any] = {
            "name": column,
            "sourceKind": source_kind,
            "syntheticKind": synthetic_kind,
            "shared": True,
            "similarity": None,
            "metric": "",
            "sourceMissingPercentage": _round(source_missing.get(column, 0.0), 2),
            "syntheticMissingPercentage": _round(synthetic_missing.get(column, 0.0), 2),
            "sourceUniqueCount": source_unique.get(column, 0),
            "syntheticUniqueCount": synthetic_unique.get(column, 0),
            "sourceStats": {},
            "syntheticStats": {},
        }
        missingness_values.append(
            abs(float(source_missing.get(column, 0.0)) - float(synthetic_missing.get(column, 0.0)))
        )

        if source_kind == "numerical" and synthetic_kind == "numerical":
            distance = _ks_distance(source_series, synthetic_series)
            similarity = None if distance is None else _round(1.0 - distance)
            item.update(
                {
                    "similarity": similarity,
                    "metric": "1 − Kolmogorov-Smirnov distance",
                    "sourceStats": _numeric_stats(source_series),
                    "syntheticStats": _numeric_stats(synthetic_series),
                }
            )
            if similarity is not None:
                numeric_similarities.append(float(similarity))
                all_similarities.append(float(similarity))
            chart = _numeric_chart(column, source_series, synthetic_series)
            if chart:
                charts.append(chart)
        elif source_kind in CATEGORICAL_KINDS and synthetic_kind in CATEGORICAL_KINDS:
            distance = _total_variation_distance(source_series, synthetic_series)
            similarity = None if distance is None else _round(1.0 - distance)
            item.update(
                {
                    "similarity": similarity,
                    "metric": "1 − categorical total variation distance",
                    "sourceStats": _categorical_stats(source_series),
                    "syntheticStats": _categorical_stats(synthetic_series),
                }
            )
            if similarity is not None:
                categorical_similarities.append(float(similarity))
                all_similarities.append(float(similarity))
            chart = _categorical_chart(column, source_series, synthetic_series)
            if chart:
                charts.append(chart)
        else:
            item["metric"] = "Column kinds differ; no distribution distance computed."
            item["sourceStats"] = (
                _numeric_stats(source_series) if source_kind == "numerical" else _categorical_stats(source_series)
            )
            item["syntheticStats"] = (
                _numeric_stats(synthetic_series)
                if synthetic_kind == "numerical"
                else _categorical_stats(synthetic_series)
            )
        columns.append(item)

    summary: dict[str, Any] = {
        "sourceRows": int(len(source_frame)),
        "syntheticRows": int(len(synthetic_frame)),
        "rowDifference": int(len(synthetic_frame) - len(source_frame)),
        "sourceColumns": int(len(source_frame.columns)),
        "syntheticColumns": int(len(synthetic_frame.columns)),
        "sharedColumns": int(len(shared)),
        "onlySourceColumns": json_safe(
            [column for column in source_frame.columns if column not in synthetic_frame.columns]
        ),
        "onlySyntheticColumns": json_safe(
            [column for column in synthetic_frame.columns if column not in source_frame.columns]
        ),
        "overallSimilarity": _round(float(np.mean(all_similarities)) if all_similarities else None),
        "numericSimilarity": _round(float(np.mean(numeric_similarities)) if numeric_similarities else None),
        "categoricalSimilarity": _round(float(np.mean(categorical_similarities)) if categorical_similarities else None),
        "missingnessDeltaPercentage": _round(float(np.mean(missingness_values)) if missingness_values else None),
    }

    return json_safe(
        {
            "method": METHOD,
            "sourceName": source_name,
            "generatedName": generated_name,
            "summary": summary,
            "columns": columns,
            "charts": charts,
            "limitations": LIMITATIONS,
        }
    )


def _base_item(row: SynthMedComparison) -> SynthMedComparisonListItem:
    report = row.report_json or {}
    summary_payload = report.get("summary") or {}
    return SynthMedComparisonListItem(
        id=row.id,
        name=row.name or "Comparison",
        sourceDatasetId=row.source_dataset_id,
        sourceDatasetName=row.source_dataset.dataset_name if row.source_dataset else "Unknown source",
        generatedDatasetId=row.generated_dataset_id,
        generatedDatasetName=row.generated_dataset.dataset_name if row.generated_dataset else "Unknown synthetic",
        summary=SynthMedComparisonSummary.model_validate(summary_payload),
        createdAt=_iso(row.created_at),
        createdBy=row.owner.full_name if row.owner else "Unknown",
        reportAvailable=bool(row.file_path),
    )


def _comparison_query():
    return select(SynthMedComparison).options(
        joinedload(SynthMedComparison.source_dataset),
        joinedload(SynthMedComparison.generated_dataset),
        joinedload(SynthMedComparison.owner),
    )


def list_comparisons(db: Session, user: User) -> list[SynthMedComparison]:
    statement = _comparison_query()
    if user.role != UserRole.ADMINISTRATOR:
        statement = statement.where(SynthMedComparison.owner_id == user.id)
    return list(db.scalars(statement.order_by(SynthMedComparison.created_at.desc())))


def get_comparison(db: Session, comparison_id: str, user: User) -> SynthMedComparison:
    row = db.scalar(_comparison_query().where(SynthMedComparison.id == _validate_id(comparison_id, "Comparison")))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found.")
    if row.owner_id != user.id and user.role != UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this comparison.")
    return row


def to_list_response(row: SynthMedComparison) -> SynthMedComparisonListItem:
    return _base_item(row)


def to_response(row: SynthMedComparison) -> SynthMedComparisonResponse:
    report = row.report_json or {}
    return SynthMedComparisonResponse(
        **_base_item(row).model_dump(),
        method=report.get("method") or row.method or METHOD,
        columns=[SynthMedComparisonColumnMetric.model_validate(item) for item in report.get("columns", [])],
        charts=[SynthMedComparisonChart.model_validate(item) for item in report.get("charts", [])],
        limitations=[str(item) for item in report.get("limitations", [])],
    )


def create_comparison(
    db: Session,
    *,
    source_id: str,
    generated_id: str,
    name: str,
    settings: Settings,
    user: User,
    request: Request | None = None,
) -> SynthMedComparison:
    source = get_source(db, source_id)
    generated = get_generated(db, generated_id)
    ensure_source_access(source, user)
    ensure_generated_access(generated, user)

    if generated.source_dataset_id != source.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The selected synthetic dataset was not generated from the selected original dataset.",
        )
    if generated.status != "Completed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only completed synthetic datasets can be compared.",
        )

    storage = SynthMedStorageService(settings)
    try:
        source_path = storage.resolve_source(source.stored_path)
        generated_path = storage.resolve_generated(generated.stored_path)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found on disk.") from error

    source_frame = read_source_dataframe(source_path, source.file_format)
    synthetic_frame = read_source_dataframe(generated_path, generated.file_format)
    report = build_comparison_report(source_frame, synthetic_frame, source.dataset_name, generated.dataset_name)

    comparison_id = str(uuid4())
    _, relative_path = storage.save_report(comparison_id, "comparison_report.json", dump_json(report))
    summary = report["summary"]
    row = SynthMedComparison(
        id=comparison_id,
        owner_id=user.id,
        source_dataset_id=source.id,
        generated_dataset_id=generated.id,
        name=(name or "").strip() or f"{source.dataset_name} vs {generated.dataset_name}",
        method=METHOD,
        summary_score=summary.get("overallSimilarity"),
        report_json=report,
        file_path=relative_path,
    )
    db.add(row)
    log_audit(
        db,
        action="synthmed.comparison_created",
        resource_type="synthmed_comparison",
        resource_id=row.id,
        actor_id=user.id,
        details={
            "source_dataset_id": source.id,
            "generated_dataset_id": generated.id,
            "shared_columns": summary.get("sharedColumns"),
            "overall_similarity": summary.get("overallSimilarity"),
        },
        request=request,
    )
    db.commit()
    row = db.scalar(_comparison_query().where(SynthMedComparison.id == comparison_id)) or row
    return row


def comparison_report_path(row: SynthMedComparison, settings: Settings):
    if not row.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison report is not available.")
    try:
        return SynthMedStorageService(settings).resolve_report(row.file_path)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comparison report not found on disk."
        ) from error
