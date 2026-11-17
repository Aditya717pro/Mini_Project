from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.etl.extract import ExtractionProfile, is_missing
from app.models.dataset import Dataset, DatasetVersion
from app.models.reports import RepresentativenessReport

AGE_COLUMNS = {"age", "age_years", "ageyrs", "age_year"}
SEX_COLUMNS = {"sex", "sex_at_birth", "gender"}
PREGNANCY_COLUMNS = {"pregnancy_stage", "trimester", "pregnancy_trimester"}
PAEDIATRIC_COLUMNS = {"pediatric_age_group", "paediatric_age_group", "age_group", "ageband", "age_band"}
GEOGRAPHY_COLUMNS = {"region", "country", "location", "site", "geography"}


@dataclass
class RepresentativenessAssessment:
    age_bands: list[dict[str, Any]]
    pregnancy_stages: list[dict[str, Any]]
    paediatric_groups: list[dict[str, Any]]
    geography: list[dict[str, Any]]
    missing_attributes: list[dict[str, Any]]
    coverage_notes: list[str]
    summary: str
    score: int
    assessed_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalised(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def _find_column(columns: dict[str, str], candidates: set[str]) -> str | None:
    return next((columns[name] for name in candidates if name in columns), None)


def _series_for(dataframe: pd.DataFrame, column: str | None) -> pd.Series | None:
    if column is None or column not in dataframe.columns:
        return None
    return dataframe[column][~dataframe[column].map(is_missing)]


def _age_band(age: float) -> str:
    if age < 18:
        return "Under 18"
    if age < 25:
        return "18-24"
    if age < 35:
        return "25-34"
    if age < 45:
        return "35-44"
    return "45+"


def _paediatric_group(age: float) -> str:
    if age < 1:
        return "Under 1"
    if age < 5:
        return "1-4"
    if age < 12:
        return "5-11"
    return "12-17"


def _counts(values: pd.Series) -> list[dict[str, Any]]:
    counts = values.astype(str).str.strip().value_counts(dropna=False).head(20)
    return [{"label": str(label), "value": int(count)} for label, count in counts.items()]


def assess_representativeness(dataframe: pd.DataFrame, profile: ExtractionProfile) -> RepresentativenessAssessment:
    columns = {_normalised(column.name): column.name for column in profile.columns}
    age_column = _find_column(columns, AGE_COLUMNS)
    sex_column = _find_column(columns, SEX_COLUMNS)
    pregnancy_column = _find_column(columns, PREGNANCY_COLUMNS)
    paediatric_column = _find_column(columns, PAEDIATRIC_COLUMNS)
    geography_column = _find_column(columns, GEOGRAPHY_COLUMNS)
    missing_attributes: list[dict[str, Any]] = []
    coverage_notes: list[str] = []

    age_values = _series_for(dataframe, age_column)
    age_bands: list[dict[str, Any]] = []
    paediatric_groups: list[dict[str, Any]] = []
    if age_values is not None:
        numeric_ages = pd.to_numeric(age_values, errors="coerce").dropna()
        age_bands = _counts(numeric_ages.map(_age_band)) if not numeric_ages.empty else []
        paediatric_groups = _counts(numeric_ages[numeric_ages < 18].map(_paediatric_group))
        coverage_notes.append(
            f"Age available for {len(numeric_ages)}/{len(dataframe)} records; "
            "age bands are derived from recorded age only."
        )
    else:
        missing_attributes.append(
            {
                "attribute": "Age",
                "detail": "No age column was found in the uploaded dataset.",
                "action": "Do not infer age. Record age at collection or document its absence.",
            }
        )

    pregnancy_values = _series_for(dataframe, pregnancy_column)
    pregnancy_stages = _counts(pregnancy_values) if pregnancy_values is not None else []
    if pregnancy_values is None:
        missing_attributes.append(
            {
                "attribute": "Pregnancy stage",
                "detail": "No pregnancy-stage or trimester column was found.",
                "action": "Report as unavailable; do not derive pregnancy stage from other fields.",
            }
        )

    if not paediatric_groups:
        paediatric_values = _series_for(dataframe, paediatric_column)
        if paediatric_values is not None:
            paediatric_groups = _counts(paediatric_values)
    if not paediatric_groups:
        missing_attributes.append(
            {
                "attribute": "Paediatric age groups",
                "detail": "No paediatric age group or recorded age values are available.",
                "action": "Report as unavailable; do not assign children to age groups without source values.",
            }
        )

    geography_values = _series_for(dataframe, geography_column)
    geography = _counts(geography_values) if geography_values is not None else []
    if geography_values is None:
        missing_attributes.append(
            {
                "attribute": "Geography",
                "detail": "No region, country, location or site column was found.",
                "action": "Report geographical coverage as unavailable; do not infer location.",
            }
        )

    if sex_column is None:
        missing_attributes.append(
            {
                "attribute": "Sex or gender",
                "detail": "No sex or gender column was found.",
                "action": "Report as unavailable; do not infer demographic attributes.",
            }
        )

    coverage_notes = [
        "Only recorded attributes are summarised. Missing demographic characteristics are never inferred.",
        f"Source rows analysed: {len(dataframe)}.",
        f"Demographic attributes available: {5 - len(missing_attributes)}/5.",
    ]
    if age_values is not None and sex_column is None:
        coverage_notes.append("Age is available but sex is unavailable, so sex-specific coverage cannot be assessed.")

    available = 5 - len(missing_attributes)
    score = round(100 * available / 5)
    summary = (
        f"Representativeness is based on {available} of 5 documented demographic attributes. "
        "Unavailable attributes are listed explicitly and no values were inferred."
    )
    return RepresentativenessAssessment(
        age_bands=age_bands,
        pregnancy_stages=pregnancy_stages,
        paediatric_groups=paediatric_groups,
        geography=geography,
        missing_attributes=missing_attributes,
        coverage_notes=coverage_notes,
        summary=summary,
        score=score,
        assessed_at=datetime.now(UTC).isoformat(),
    )


def persist_representativeness_report(
    db: Session,
    *,
    dataset: Dataset,
    version: DatasetVersion,
    assessment: RepresentativenessAssessment,
) -> RepresentativenessReport:
    existing = db.query(RepresentativenessReport).filter_by(dataset_version_id=version.id).one_or_none()
    if existing is not None:
        existing.age_bands_json = assessment.age_bands
        existing.pregnancy_stages_json = assessment.pregnancy_stages
        existing.paediatric_groups_json = assessment.paediatric_groups
        existing.geography_json = assessment.geography
        existing.missing_attributes_json = assessment.missing_attributes
        existing.coverage_notes_json = assessment.coverage_notes
        existing.summary = assessment.summary
        return existing
    report = RepresentativenessReport(
        dataset_id=dataset.id,
        dataset_version_id=version.id,
        age_bands_json=assessment.age_bands,
        pregnancy_stages_json=assessment.pregnancy_stages,
        paediatric_groups_json=assessment.paediatric_groups,
        geography_json=assessment.geography,
        missing_attributes_json=assessment.missing_attributes,
        coverage_notes_json=assessment.coverage_notes,
        summary=assessment.summary,
    )
    db.add(report)
    return report
