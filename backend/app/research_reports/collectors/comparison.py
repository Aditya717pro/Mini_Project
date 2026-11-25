from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.research_reports.collectors.common import flatten_values
from app.research_reports.sanitize import NOT_AVAILABLE, clean_number, clean_text, safe_column_name
from app.research_reports.validation import ResolvedSources


def collect(db: Session, settings: Settings, sources: ResolvedSources) -> dict[str, Any]:
    comparison = sources.comparison
    if comparison is None:
        raise HTTPException(status_code=422, detail="A persisted comparison is required for this report.")
    report = comparison.report_json or {}
    summary = report.get("summary") or {}

    metadata: dict[str, Any] = {
        "Comparison ID": comparison.id,
        "Source dataset ID": comparison.source_dataset_id,
        "Generated dataset ID": comparison.generated_dataset_id,
        "Method": report.get("method") or comparison.method or NOT_AVAILABLE,
        "Compared columns": summary.get("comparedColumns", NOT_AVAILABLE),
        "Source rows": summary.get("sourceRows", NOT_AVAILABLE),
        "Synthetic rows": summary.get("syntheticRows", NOT_AVAILABLE),
        "Record difference": summary.get("rowDifference", NOT_AVAILABLE),
        "Created at": comparison.created_at.isoformat() if comparison.created_at else NOT_AVAILABLE,
    }

    column_metrics: list[list[Any]] = []
    for item in report.get("columns") or []:
        column_metrics.append(
            [
                safe_column_name(item.get("name")),
                clean_text(item.get("metric"), default="No metric recorded"),
                clean_number(item.get("similarity")),
                clean_number(item.get("sourceMissingPercentage")),
                clean_number(item.get("syntheticMissingPercentage")),
                clean_number(item.get("sourceUniqueCount")),
                clean_number(item.get("syntheticUniqueCount")),
            ]
        )
    if not column_metrics:
        column_metrics.append([NOT_AVAILABLE] * 7)

    chart_labels: list[str] = []
    chart_values: list[float] = []
    for chart in report.get("charts") or []:
        column = safe_column_name(chart.get("column"))
        for index, point in enumerate(chart.get("points") or [], start=1):
            bucket = point.get("bucket")
            label = f"{column} - bucket {index}" if bucket else f"{column} - category {index}"
            chart_labels.append(label)
            chart_values.append(float(point.get("original") or 0))
            chart_labels.append(f"{label} (synthetic)")
            chart_values.append(float(point.get("synthetic") or 0))

    clinical_rows: list[list[Any]] = []
    for label, value in flatten_values(report.get("clinical") or {}):
        clinical_rows.append([label, NOT_AVAILABLE, value])
    if not clinical_rows:
        clinical_rows.append([NOT_AVAILABLE, "No persisted clinical comparison", NOT_AVAILABLE])

    return {
        "metadata": metadata,
        "column_metrics": column_metrics,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "clinical": clinical_rows,
        "limitations": [clean_text(item) for item in (report.get("limitations") or [])]
        or ["Comparison limitations were not recorded with this report."],
    }
