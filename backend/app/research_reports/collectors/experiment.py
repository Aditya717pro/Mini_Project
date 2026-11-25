from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.research_reports.collectors.common import flatten_values
from app.research_reports.sanitize import NOT_AVAILABLE, clean_label, clean_number, clean_text
from app.research_reports.validation import ResolvedSources
from app.synthmed.models import SynthMedDatasetVersion
from app.synthmed.services.versioning_service import to_experiment_response


def collect(db: Session, settings: Settings, sources: ResolvedSources) -> dict[str, Any]:
    experiment = sources.experiment
    if experiment is None:
        raise HTTPException(status_code=422, detail="A persisted experiment is required for this report.")
    response = to_experiment_response(db, experiment)

    metadata: dict[str, Any] = {
        "Experiment ID": experiment.id,
        "Status": experiment.status,
        "Source dataset ID": experiment.source_dataset_id or NOT_AVAILABLE,
        "Source version ID": experiment.source_version_id or NOT_AVAILABLE,
        "Generated dataset ID": experiment.generated_dataset_id or NOT_AVAILABLE,
        "Generated version ID": experiment.generated_version_id or NOT_AVAILABLE,
        "Generation job ID": experiment.generation_job_id or NOT_AVAILABLE,
        "Configuration snapshot ID": experiment.configuration_snapshot_id or NOT_AVAILABLE,
        "Comparison ID": experiment.comparison_id or NOT_AVAILABLE,
        "Utility evaluation ID": experiment.utility_evaluation_id or NOT_AVAILABLE,
        "Created at": response.get("createdAt", NOT_AVAILABLE),
        "Updated at": response.get("updatedAt", NOT_AVAILABLE),
    }

    configuration: list[list[Any]] = [
        [clean_label(label), clean_number(value)]
        for label, value in flatten_values(response.get("configurationSnapshot") or {})
    ]
    if not configuration:
        configuration.append([NOT_AVAILABLE, "No persisted configuration snapshot"])

    lineage: list[list[Any]] = []
    for event in response.get("lineage") or []:
        lineage.append(
            [
                clean_text(event.get("eventType")),
                clean_text(event.get("parentResourceId")),
                clean_text(event.get("childResourceId")),
                clean_text(event.get("createdAt")),
            ]
        )
    if not lineage:
        lineage.append([NOT_AVAILABLE, NOT_AVAILABLE, NOT_AVAILABLE, "No lineage events recorded"])

    version_rows: list[list[Any]] = []
    logical_ids = [
        value
        for value in (experiment.source_dataset_id, experiment.generated_dataset_id)
        if value
    ]
    if logical_ids:
        versions = db.scalars(
            select(SynthMedDatasetVersion)
            .where(SynthMedDatasetVersion.logical_dataset_id.in_(logical_ids))
            .order_by(SynthMedDatasetVersion.created_at.desc())
        )
        for version in versions:
            version_rows.append(
                [
                    version.dataset_kind,
                    version.version_label or version.version_number,
                    version.record_count,
                    version.checksum_sha256 or NOT_AVAILABLE,
                ]
            )
    if not version_rows:
        version_rows.append([NOT_AVAILABLE, NOT_AVAILABLE, NOT_AVAILABLE, NOT_AVAILABLE])

    privacy = response.get("privacyReport") or {}
    utility = response.get("utilityEvaluation") or {}
    comparison = response.get("comparisonSummary") or {}
    outputs = [
        [
            "Configuration snapshot",
            bool(response.get("configurationSnapshot")),
            experiment.configuration_snapshot_id or NOT_AVAILABLE,
            "PERSISTED" if response.get("configurationSnapshot") else "NOT AVAILABLE",
        ],
        [
            "Privacy evaluation",
            privacy.get("available", False),
            privacy.get("id") or NOT_AVAILABLE,
            privacy.get("method") or NOT_AVAILABLE,
        ],
        [
            "Utility evaluation",
            utility.get("available", False),
            utility.get("id") or NOT_AVAILABLE,
            clean_text(utility.get("status")),
        ],
        [
            "Comparison",
            comparison.get("available", False),
            comparison.get("id") or NOT_AVAILABLE,
            clean_text(comparison.get("name")),
        ],
    ]

    utility_metrics: list[list[Any]] = [
        [clean_label(label), clean_number(value)]
        for label, value in flatten_values(utility.get("comparison") or {})
    ]
    if not utility_metrics:
        utility_metrics.append([NOT_AVAILABLE, "No persisted utility comparison"])

    return {
        "metadata": metadata,
        "configuration": configuration,
        "lineage": lineage,
        "versions": version_rows,
        "outputs": outputs,
        "utility_metrics": utility_metrics,
        "limitations": [
            "Experiment evidence is consolidated from persisted records only.",
            "Absent evaluations are listed as NOT AVAILABLE and are not inferred from related records.",
            "This report does not replace governed access, privacy, or clinical review.",
        ],
    }
