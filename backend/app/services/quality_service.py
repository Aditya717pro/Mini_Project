from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from dateutil import parser as date_parser
from sqlalchemy.orm import Session

from app.etl.extract import ExtractionProfile, is_missing
from app.models.dataset import Dataset, DatasetVersion
from app.models.etl import ETLJob
from app.models.reports import QualityReport

RULES_VERSION = "quality-rules-v1"
WEIGHTS = {
    "completeness": 0.25,
    "validity": 0.20,
    "consistency": 0.15,
    "uniqueness": 0.15,
    "typeCorrectness": 0.25,
}
PHYSICAL_RANGES = {
    "age_years": (0, 130),
    "weight_kg": (0, 500),
    "height_cm": (10, 300),
    "gestational_age_weeks": (0, 50),
}
CATEGORY_VALUES = {
    "sex": {"female", "male", "f", "m", "intersex", "unknown"},
    "sex_at_birth": {"female", "male", "f", "m", "intersex", "unknown"},
    "pregnancy_stage": {"first trimester", "second trimester", "third trimester", "postpartum", "not applicable"},
    "trimester": {"first", "second", "third", "1", "2", "3"},
}


@dataclass
class QualityAssessment:
    overall: int
    grade: str
    dimensions: dict[str, float]
    issues: list[dict[str, Any]]
    assessed_at: str
    rules_version: str
    sample_size: int
    method: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_date(value: Any) -> bool:
    try:
        date_parser.parse(str(value))
        return True
    except (ValueError, OverflowError, TypeError):
        return False


def _is_numeric(value: Any) -> bool:
    try:
        float(str(value).replace(",", ""))
        return True
    except ValueError:
        return False


def _canonical_name(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def _grade(score: float) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 60:
        return "Fair"
    return "Poor"


def assess_quality(dataframe: pd.DataFrame, profile: ExtractionProfile) -> QualityAssessment:
    row_count = max(len(dataframe), 1)
    total_cells = max(row_count * max(len(dataframe.columns), 1), 1)
    missing_cells = sum(int(dataframe[column].map(is_missing).sum()) for column in dataframe.columns)
    completeness = 100 * (1 - missing_cells / total_cells)
    uniqueness = 100 * (1 - profile.duplicate_rows / row_count)

    type_checked = 0
    type_correct = 0
    validity_checked = 0
    valid_values = 0
    consistency_checked = 0
    consistent_values = 0
    issues: list[dict[str, Any]] = []

    for column_profile in profile.columns:
        column = column_profile.name
        if column not in dataframe.columns:
            continue
        series = dataframe[column]
        present = series[~series.map(is_missing)]
        present_count = len(present)
        normalized = _canonical_name(column)
        if present_count == 0:
            continue

        if column_profile.inferred_type == "Numeric":
            valid = present.map(_is_numeric)
            type_checked += present_count
            type_correct += int(valid.sum())
            validity_checked += present_count
            valid_values += int(valid.sum())
            if int((~valid).sum()):
                issues.append(
                    _issue(
                        "validity",
                        "High",
                        column,
                        f"{int((~valid).sum())} value(s) do not match the inferred numeric type.",
                        int((~valid).sum()),
                        "Verify the column against the data dictionary and correct at source.",
                    )
                )
            for target, (lower, upper) in PHYSICAL_RANGES.items():
                if target in normalized:
                    numeric = pd.to_numeric(present, errors="coerce")
                    outside = int(((numeric < lower) | (numeric > upper)).sum())
                    if outside:
                        issues.append(
                            _issue(
                                "validity",
                                "Medium",
                                column,
                                f"{outside} value(s) fall outside the documented physical range {lower}-{upper}.",
                                outside,
                                "Review these values against the source collection form before use.",
                            )
                        )
        elif column_profile.inferred_type == "Date":
            parsed = present.map(_parse_date)
            type_checked += present_count
            type_correct += int(parsed.sum())
            validity_checked += present_count
            valid_values += int(parsed.sum())
            if int((~parsed).sum()):
                issues.append(
                    _issue(
                        "consistency",
                        "Medium",
                        column,
                        f"{int((~parsed).sum())} date value(s) use formats that could not be parsed.",
                        int((~parsed).sum()),
                        "Standardise dates to ISO 8601 at source and document the collection format.",
                    )
                )
        elif column_profile.inferred_type == "Boolean":
            type_checked += present_count
            type_correct += present_count
            validity_checked += present_count
            valid_values += present_count
        elif column_profile.inferred_type == "Text":
            rule = CATEGORY_VALUES.get(normalized)
            if rule:
                normalized_values = present.astype(str).str.strip().str.lower()
                matched = int(normalized_values.isin(rule).sum())
                consistency_checked += present_count
                consistent_values += matched
                if matched < present_count:
                    issues.append(
                        _issue(
                            "consistency",
                            "Medium",
                            column,
                            f"{present_count - matched} categor(y/ies) outside the documented vocabulary.",
                            present_count - matched,
                            "Apply the agreed category vocabulary and record unmapped values.",
                        )
                    )

        missing = int(series.map(is_missing).sum())
        if missing:
            severity = "High" if missing / max(len(series), 1) >= 0.2 else "Medium"
            issues.append(
                _issue(
                    "completeness",
                    severity,
                    column,
                    f"{missing} missing value(s) ({missing / max(len(series), 1) * 100:.1f}%).",
                    missing,
                    "Document missingness; do not impute without a research-specific protocol.",
                )
            )

    if profile.duplicate_rows:
        issues.append(
            _issue(
                "uniqueness",
                "High" if profile.duplicate_rows / row_count >= 0.05 else "Medium",
                "all columns",
                f"{profile.duplicate_rows} exact duplicate record(s) detected.",
                profile.duplicate_rows,
                "Confirm whether duplicates are legitimate repeat visits or data-entry errors.",
            )
        )

    type_correctness = 100 * (type_correct / type_checked) if type_checked else 100.0
    validity = 100 * (valid_values / validity_checked) if validity_checked else 100.0
    consistency = 100 * (consistent_values / consistency_checked) if consistency_checked else 100.0

    dimensions = {
        "completeness": round(completeness, 2),
        "validity": round(validity, 2),
        "consistency": round(consistency, 2),
        "uniqueness": round(uniqueness, 2),
        "typeCorrectness": round(type_correctness, 2),
    }
    overall = round(sum(dimensions[key] * weight for key, weight in WEIGHTS.items()), 0)
    return QualityAssessment(
        overall=int(overall),
        grade=_grade(overall),
        dimensions=dimensions,
        issues=issues,
        assessed_at=datetime.now(UTC).isoformat(),
        rules_version=RULES_VERSION,
        sample_size=len(dataframe),
        method=(
            "Rule-based assessment. Overall = completeness 25% + validity 20% + "
            "type correctness 25% + consistency 15% + uniqueness 15%. "
            "Missingness is reported separately and is never imputed."
        ),
    )


def _issue(
    dimension: str,
    severity: str,
    field_name: str,
    description: str,
    affected_records: int,
    recommendation: str,
) -> dict[str, Any]:
    key = f"{dimension}-{field_name}-{description}".lower().replace(" ", "-")
    return {
        "id": key,
        "dimension": dimension,
        "severity": severity,
        "field": field_name,
        "description": description,
        "affectedRecords": affected_records,
        "recommendation": recommendation,
    }


def persist_quality_report(
    db: Session,
    *,
    dataset: Dataset,
    version: DatasetVersion,
    job: ETLJob | None,
    assessment: QualityAssessment,
) -> QualityReport:
    existing = db.query(QualityReport).filter_by(
        dataset_version_id=version.id, formula_version=assessment.rules_version
    ).one_or_none()
    if existing is not None:
        db.delete(existing)
        db.flush()
    report = QualityReport(
        dataset_id=dataset.id,
        dataset_version_id=version.id,
        etl_job_id=job.id if job else None,
        overall_score=assessment.overall,
        formula_version=assessment.rules_version,
        dimensions_json=assessment.dimensions,
        findings_json=assessment.issues,
        sample_size=assessment.sample_size,
        method=assessment.method,
    )
    db.add(report)
    return report
