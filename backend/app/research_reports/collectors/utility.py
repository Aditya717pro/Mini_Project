from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.research_reports.collectors.common import flatten_values
from app.research_reports.sanitize import NOT_AVAILABLE, clean_number, clean_text, safe_column_name
from app.research_reports.validation import ResolvedSources
from app.synthmed.services.utility_evaluation_service import _report_payload


def _metric_section(section: dict[str, Any] | None) -> tuple[list[list[Any]], list[str], list[float]]:
    if not section:
        return [[NOT_AVAILABLE, NOT_AVAILABLE]], [], []
    metrics = section.get("metrics") or {}
    rows = [[label, value] for label, value in flatten_values(metrics)]
    labels, values = [], []
    for label, value in flatten_values(metrics):
        try:
            labels.append(label)
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    rows.extend(
        [
            ["Train source", section.get("trainSource", NOT_AVAILABLE)],
            ["Training records", section.get("trainRecords", NOT_AVAILABLE)],
            ["Test records", section.get("testRecords", NOT_AVAILABLE)],
        ]
    )
    return rows, labels, values


def collect(db: Session, settings: Settings, sources: ResolvedSources) -> dict[str, Any]:
    evaluation = sources.utility_evaluation
    if evaluation is None:
        raise HTTPException(status_code=422, detail="A persisted utility evaluation is required for this report.")
    payload = _report_payload(evaluation)
    metrics = evaluation.metrics_json or {}
    comparison = evaluation.comparison_summary_json or {}

    metadata: dict[str, Any] = {
        "Utility evaluation ID": evaluation.id,
        "Source dataset ID": evaluation.source_dataset_id,
        "Generated dataset ID": evaluation.generated_dataset_id,
        "Evaluation name": clean_text(evaluation.evaluation_name),
        "Evaluation type": evaluation.evaluation_type,
        "Status": evaluation.status,
        "Model": evaluation.model_name,
        "Target column": safe_column_name(evaluation.target_column),
        "Task type": payload.get("taskType", NOT_AVAILABLE),
        "Created at": payload["metadata"].get("createdAt", NOT_AVAILABLE),
        "Completed at": payload["metadata"].get("completedAt", NOT_AVAILABLE),
    }

    methodology = [
        ["Leakage control", control]
        for control in (payload.get("methodology") or {}).get("leakageControls") or []
    ]
    if not methodology:
        methodology.append([NOT_AVAILABLE, "No persisted methodology details"])

    tstr_rows, tstr_labels, tstr_values = _metric_section(metrics.get("tstr"))
    trtr_rows, trtr_labels, trtr_values = _metric_section(metrics.get("trtr"))

    comparison_rows: list[list[Any]] = [
        [label, clean_number(value)] for label, value in (comparison.get("gap") or {}).items()
    ]
    if comparison.get("interpretation"):
        comparison_rows.append(["Interpretation", clean_text(comparison["interpretation"])])
    if not comparison_rows:
        comparison_rows.append([NOT_AVAILABLE, "No persisted TSTR/TRTR comparison"])

    return {
        "metadata": metadata,
        "methodology": methodology,
        "tstr_metrics": tstr_rows,
        "tstr_labels": tstr_labels,
        "tstr_values": tstr_values,
        "trtr_metrics": trtr_rows,
        "trtr_labels": trtr_labels,
        "trtr_values": trtr_values,
        "comparison": comparison_rows,
        "warnings": [clean_text(item) for item in payload.get("warnings") or []],
        "limitations": [clean_text(item) for item in payload.get("limitations") or []],
    }
