from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.etl.extract import ExtractionProfile
from app.models.dataset import Dataset, DatasetMetadata, DatasetVersion
from app.models.reports import ReadinessReport
from app.services.quality_service import QualityAssessment

METHOD = (
    "Rule-based task-specific readiness assessment. This is not a measure of data quality alone "
    "and does not validate scientific fitness for any research use."
)

CATEGORY_WEIGHTS = {
    "dataQuality": 0.18,
    "featureAvailability": 0.16,
    "labelAvailability": 0.17,
    "missingValues": 0.09,
    "metadataCompleteness": 0.10,
    "documentation": 0.10,
    "representativeness": 0.10,
    "taskSuitability": 0.10,
}

CATEGORY_LABELS = {
    "dataQuality": "Data quality",
    "featureAvailability": "Feature availability",
    "labelAvailability": "Label availability",
    "missingValues": "Missing values",
    "metadataCompleteness": "Metadata completeness",
    "documentation": "Documentation",
    "representativeness": "Representativeness",
    "taskSuitability": "Task suitability",
}

TASK_FEATURES = {
    "paediatric": {"age_years", "sex_at_birth", "region", "pediatric_age_group"},
    "pregnancy": {"age_years", "sex_at_birth", "pregnancy_stage", "gestational_age_weeks", "region"},
    "maternal": {"age_years", "sex_at_birth", "pregnancy_stage", "gestational_age_weeks", "region"},
    "women": {"age_years", "sex_at_birth", "pregnancy_stage", "region"},
    "default": {"age_years", "sex_at_birth", "region"},
}


@dataclass
class ReadinessAssessment:
    task: str
    overall: int
    verdict: str
    categories: list[dict[str, Any]]
    limitations: list[str]
    recommendations: list[str]
    assessed_at: str
    method: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalised(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def _task_features(task: str) -> set[str]:
    lowered = task.lower()
    for keyword, features in TASK_FEATURES.items():
        if keyword in lowered:
            return features
    return TASK_FEATURES["default"]


def _metadata_completeness(metadata: DatasetMetadata | None, dataset: Dataset) -> tuple[int, list[str]]:
    if metadata is None:
        return 0, ["Dataset metadata record is missing."]
    fields = {
        "description": bool(dataset.description.strip()),
        "age range": bool(metadata.age_range.strip()),
        "geography": bool(metadata.geography),
        "study design": bool(metadata.study_design.strip()),
        "licence": bool(metadata.license.strip()),
        "ethics approval": metadata.ethics_approved,
        "data dictionary": metadata.data_dictionary_available,
        "consent scope": bool(metadata.consent_scope.strip()),
        "intended tasks": bool(metadata.intended_tasks),
        "research task": bool(dataset.research_task.strip()),
    }
    missing = [label for label, present in fields.items() if not present]
    return round(100 * (len(fields) - len(missing)) / len(fields)), missing


def assess_readiness(
    *,
    dataset: Dataset,
    metadata: DatasetMetadata | None,
    profile: ExtractionProfile,
    quality: QualityAssessment,
    research_task: str,
    representativeness_score: int,
) -> ReadinessAssessment:
    columns = {_normalised(column.name): column for column in profile.columns}
    expected_features = _task_features(research_task)
    available_features = sorted(expected_features & set(columns))
    feature_score = round(100 * len(available_features) / len(expected_features)) if expected_features else 50

    label_column = (metadata.label_column if metadata else None) or ""
    label_profile = columns.get(_normalised(label_column)) if label_column else None
    if label_profile is not None:
        label_score = round(max(0, 100 - label_profile.missing_pct * 2))
        label_note = f"Label column '{label_profile.name}' is present with {label_profile.missing_pct}% missing."
    else:
        label_score = 15
        label_note = "No validated label column is declared in dataset metadata."

    missing_score = round(max(0, 100 - profile.missing_pct))
    metadata_score, missing_metadata = _metadata_completeness(metadata, dataset)
    documentation_items = [
        bool(metadata and metadata.data_dictionary_available),
        bool(metadata and metadata.license.strip()),
        bool(metadata and metadata.ethics_approved),
        len(dataset.description.strip()) >= 80,
        bool(dataset.research_task.strip()),
    ]
    documentation_score = round(100 * sum(documentation_items) / len(documentation_items))

    task_hits = len(available_features) / len(expected_features) if expected_features else 0.5
    task_score = round(100 * (0.65 * task_hits + 0.35 * (label_score / 100)))

    feature_note = f"{len(available_features)}/{len(expected_features)} expected features found."
    categories = [
        _category("dataQuality", quality.overall, "Derived from the separate quality report."),
        _category("featureAvailability", feature_score, feature_note),
        _category("labelAvailability", label_score, label_note),
        _category("missingValues", missing_score, f"{profile.missing_pct}% of source cells are missing."),
        _category("metadataCompleteness", metadata_score, "Metadata fields required for research reuse."),
        _category(
            "documentation",
            documentation_score,
            "Data dictionary, licence, ethics, description and task declaration.",
        ),
        _category(
            "representativeness",
            representativeness_score,
            "Derived from available demographic and clinical characteristics.",
        ),
        _category("taskSuitability", task_score, f"Assessed against the declared task: {research_task}."),
    ]
    overall = round(sum(category["score"] * CATEGORY_WEIGHTS[category["key"]] for category in categories))
    verdict = "Ready" if overall >= 80 else "Ready with caveats" if overall >= 60 else "Not ready"

    limitations: list[str] = []
    recommendations: list[str] = []
    if quality.overall < 75:
        limitations.append("The source data quality score is below the recommended threshold.")
        recommendations.append("Resolve high-severity quality findings before model development.")
    if feature_score < 75:
        missing_features = sorted(expected_features - set(columns))
        limitations.append(f"Missing expected task features: {', '.join(missing_features) or 'none identified'}.")
        recommendations.append("Add or map the missing task features and document any proxies.")
    if label_score < 50:
        limitations.append(label_note)
        recommendations.append("Declare and validate a label column before supervised modelling.")
    if profile.missing_pct > 10:
        limitations.append(f"Missingness is {profile.missing_pct}%, which may bias downstream models.")
        recommendations.append("Document the missingness mechanism; do not impute without a protocol.")
    if missing_metadata:
        limitations.append(f"Metadata is incomplete: {', '.join(missing_metadata)}.")
        recommendations.append("Complete the metadata record and publish a data dictionary.")
    if representativeness_score < 60:
        limitations.append("Available demographic coverage is limited or incomplete.")
        recommendations.append(
            "Report unavailable demographic attributes explicitly and avoid unsupported population claims."
        )

    return ReadinessAssessment(
        task=research_task,
        overall=overall,
        verdict=verdict,
        categories=categories,
        limitations=limitations,
        recommendations=recommendations or ["Maintain the documented metadata and re-assess after each version."],
        assessed_at=datetime.now(UTC).isoformat(),
        method=METHOD,
    )


def _category(key: str, score: int, note: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": CATEGORY_LABELS[key],
        "score": max(0, min(100, int(score))),
        "weight": CATEGORY_WEIGHTS[key],
        "note": note,
    }


def persist_readiness_report(
    db: Session,
    *,
    dataset: Dataset,
    version: DatasetVersion,
    quality_report_id: str | None,
    assessment: ReadinessAssessment,
) -> ReadinessReport:
    existing = db.query(ReadinessReport).filter_by(
        dataset_version_id=version.id, research_task=assessment.task
    ).one_or_none()
    if existing is not None:
        existing.overall_score = assessment.overall
        existing.verdict = assessment.verdict
        existing.categories_json = assessment.categories
        existing.limitations_json = assessment.limitations
        existing.recommendations_json = assessment.recommendations
        existing.quality_report_id = quality_report_id
        return existing
    report = ReadinessReport(
        dataset_id=dataset.id,
        dataset_version_id=version.id,
        quality_report_id=quality_report_id,
        research_task=assessment.task,
        overall_score=assessment.overall,
        verdict=assessment.verdict,
        categories_json=assessment.categories,
        limitations_json=assessment.limitations,
        recommendations_json=assessment.recommendations,
        method=assessment.method,
    )
    db.add(report)
    return report
