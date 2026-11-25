from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.research_reports.sanitize import NOT_AVAILABLE, clean_number, clean_text
from app.research_reports.validation import ResolvedSources


def collect(db: Session, settings: Settings, sources: ResolvedSources) -> dict[str, Any]:
    evaluation = sources.privacy_evaluation
    if evaluation is None:
        raise HTTPException(status_code=422, detail="A persisted privacy evaluation is required for this report.")
    report = evaluation.report_json or {}
    nearest = report.get("nearestNeighbourDistance") or {}

    metadata: dict[str, Any] = {
        "Privacy evaluation ID": evaluation.id,
        "Generation job ID": evaluation.job_id,
        "Generated dataset ID": evaluation.generated_dataset_id,
        "Method": evaluation.method or report.get("method") or NOT_AVAILABLE,
        "Recorded score": clean_number(evaluation.score),
        "Created at": evaluation.created_at.isoformat() if evaluation.created_at else NOT_AVAILABLE,
    }

    metrics: list[list[Any]] = [
        [
            "Exact overlap records",
            report.get("exactOverlapRecords", NOT_AVAILABLE),
            "Exact record matches under modelled columns",
        ],
        [
            "Exact overlap percentage",
            report.get("exactOverlapPercentage", NOT_AVAILABLE),
            "Percentage of synthetic records exactly matched",
        ],
        [
            "Synthetic duplicate records",
            report.get("syntheticDuplicateRecords", NOT_AVAILABLE),
            "Duplicate generated records",
        ],
        [
            "Real duplicate records",
            report.get("realDuplicateRecords", NOT_AVAILABLE),
            "Duplicates recorded in source analysis",
        ],
        ["New row synthesis score", report.get("newRowSynthesisScore", NOT_AVAILABLE), "Persisted SDMetrics score"],
    ]
    overlap: list[list[Any]] = [
        ["Nearest neighbour minimum", nearest.get("minimum", NOT_AVAILABLE), "Minimum recorded encoded distance"],
        ["Nearest neighbour median", nearest.get("median", NOT_AVAILABLE), "Median recorded encoded distance"],
        ["Nearest neighbour p90", nearest.get("p90", NOT_AVAILABLE), "90th percentile recorded encoded distance"],
        ["Threshold", nearest.get("threshold", NOT_AVAILABLE), "Persisted screening threshold"],
        [
            "Suspicious records",
            nearest.get("suspiciousRecords", NOT_AVAILABLE),
            "Records below the persisted threshold",
        ],
    ]

    not_evaluated = [
        ["Membership inference attack", "NOT EVALUATED", "No persisted membership inference result exists."],
        ["Attribute disclosure attack", "NOT EVALUATED", "No persisted attribute disclosure result exists."],
        ["Differential privacy guarantee", "NOT EVALUATED", "No differential privacy mechanism is implemented."],
        ["Formal anonymity guarantee", "NOT EVALUATED", "Heuristic screening cannot establish anonymity."],
    ]

    limitations = [clean_text(item) for item in report.get("limitations") or []]
    warnings = [clean_text(item) for item in report.get("warnings") or []]
    if report.get("newRowSynthesisError"):
        limitations.append(f"New row synthesis error: {clean_text(report['newRowSynthesisError'])}")
    limitations.extend(warnings)

    return {
        "metadata": metadata,
        "metrics": metrics,
        "overlap": overlap,
        "not_evaluated": not_evaluated,
        "limitations": limitations,
    }
