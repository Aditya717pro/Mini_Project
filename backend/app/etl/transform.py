from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from app.etl.extract import AMBIGUOUS_DATE_PATTERN, is_missing

COMMON_SCHEMA: dict[str, dict[str, Any]] = {
    "participant_id": {
        "aliases": ["participant_id", "patient_id", "subject_id", "participant", "patient", "subject"],
        "dtype": "string",
    },
    "age_years": {"aliases": ["age_years", "age", "ageyrs", "age_year"], "dtype": "numeric"},
    "weight_kg": {"aliases": ["weight_kg", "weight", "wt_kg", "wt"], "dtype": "numeric"},
    "height_cm": {"aliases": ["height_cm", "height", "ht_cm", "ht"], "dtype": "numeric"},
    "sex_at_birth": {
        "aliases": ["sex_at_birth", "sex", "gender", "sex_at_delivery"],
        "dtype": "category",
    },
    "gestational_age_weeks": {
        "aliases": ["gestational_age_weeks", "gestational_age", "ga_weeks", "gestation_weeks"],
        "dtype": "numeric",
    },
    "pregnancy_stage": {
        "aliases": ["pregnancy_stage", "trimester", "pregnancy_trimester"],
        "dtype": "category",
    },
    "pediatric_age_group": {
        "aliases": ["pediatric_age_group", "age_group", "ageband", "age_band"],
        "dtype": "category",
    },
    "region": {"aliases": ["region", "geography", "location", "country", "site"], "dtype": "string"},
    "visit_date": {
        "aliases": ["visit_date", "date", "assessment_date", "collection_date"],
        "dtype": "date",
    },
    "label": {"aliases": ["label", "outcome", "target", "diagnosis", "condition"], "dtype": "string"},
}

CATEGORY_RULES: dict[str, dict[str, str]] = {
    "sex_at_birth": {"f": "Female", "female": "Female", "m": "Male", "male": "Male"},
    "pregnancy_stage": {
        "t1": "First trimester",
        "trimester_1": "First trimester",
        "first": "First trimester",
        "t2": "Second trimester",
        "trimester_2": "Second trimester",
        "second": "Second trimester",
        "t3": "Third trimester",
        "trimester_3": "Third trimester",
        "third": "Third trimester",
    },
}

REVIEW_RANGES: dict[str, tuple[float, float]] = {
    "age_years": (0, 120),
    "weight_kg": (1, 300),
    "height_cm": (30, 250),
    "gestational_age_weeks": (0, 45),
}

INVALID_RANGES: dict[str, tuple[float, float]] = {
    "age_years": (0, 130),
    "weight_kg": (0, 500),
    "height_cm": (0, 300),
    "gestational_age_weeks": (0, 50),
}

DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d")


@dataclass
class TransformResult:
    dataframe: pd.DataFrame
    logs: list[dict[str, Any]] = field(default_factory=list)
    missing_counts: dict[str, int] = field(default_factory=dict)
    duplicate_count: int = 0
    invalid_counts: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)
    warning_counts: dict[str, int] = field(default_factory=dict)
    review_count: int = 0
    mapped_columns: list[str] = field(default_factory=list)
    row_issues: list[dict[str, Any]] = field(default_factory=list)


def normalize_column_name(name: str) -> str:
    normalized = str(name).strip().lower()
    normalized = "".join(character if character.isalnum() else "_" for character in normalized)
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_")


def _tokens(name: str) -> set[str]:
    return {token for token in normalize_column_name(name).split("_") if len(token) > 2}


def suggest_mappings(columns: list[str]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for column in columns:
        normalized = normalize_column_name(column)
        best_target: str | None = None
        best_confidence = 0.0
        best_reason = "No reliable name-based match"
        for target, rule in COMMON_SCHEMA.items():
            aliases = {normalize_column_name(alias) for alias in rule["aliases"]}
            if normalized in aliases or normalized == target:
                confidence = 0.92
                candidate_reason = "Exact match to a published common-schema alias"
            else:
                overlap = _tokens(normalized) & _tokens(target)
                confidence = 0.55 if overlap else 0.0
                candidate_reason = "Token overlap only; verify against the data dictionary"
            if confidence > best_confidence:
                best_target = target
                best_confidence = confidence
                best_reason = candidate_reason
        if best_target is None:
            suggestions.append(
                {
                    "source": column,
                    "target": "",
                    "confidence": 0.0,
                    "status": "Unmapped",
                    "note": "No reliable match. A reviewer must supply an explicit mapping.",
                }
            )
        else:
            suggestions.append(
                {
                    "source": column,
                    "target": best_target,
                    "confidence": best_confidence,
                    "status": "Suggested",
                    "note": f"{best_reason}. This is a suggestion, not an approval.",
                }
            )
    return suggestions


def parse_unambiguous_date(value: Any) -> str | None:
    text = str(value).strip()
    if AMBIGUOUS_DATE_PATTERN.fullmatch(text):
        return None
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def _convert_units(series: pd.Series, source: str, target: str) -> tuple[pd.Series, str | None, str | None]:
    tokens = _tokens(source)
    numeric = pd.to_numeric(series.map(lambda value: str(value).replace(",", "")), errors="coerce")
    if target == "age_years" and tokens & {"month", "months", "mo"}:
        return numeric / 12, "Converted age from months to years (unit stated in the source column name)", None
    if target == "weight_kg" and tokens & {"lb", "lbs", "pound", "pounds"}:
        return numeric * 0.45359237, "Converted weight from pounds to kilograms (unit stated in the source name)", None
    if target == "height_cm" and tokens & {"meter", "meters", "metre", "metres"}:
        return numeric * 100, "Converted height from metres to centimetres (unit stated in the source name)", None
    if target == "gestational_age_weeks" and tokens & {"day", "days"}:
        return numeric / 7, "Converted gestational age from days to weeks (unit stated in the source name)", None
    if COMMON_SCHEMA.get(target, {}).get("dtype") == "numeric" and target in REVIEW_RANGES:
        return series, None, "No unit was stated in the source column name; no unit conversion was applied"
    return series, None, None


def _normalise_categories(series: pd.Series, target: str) -> tuple[pd.Series, str | None]:
    rules = CATEGORY_RULES.get(target)
    if not rules:
        return series, None
    converted = series.map(lambda value: rules.get(str(value).strip().lower(), value))
    return converted, f"Normalised known {target} category values; unknown values were left unchanged"


def _validate_target(series: pd.Series, target: str) -> tuple[pd.Series, pd.Series, pd.Series]:
    dtype = COMMON_SCHEMA.get(target, {}).get("dtype", "string")
    missing = series.map(is_missing)
    errors = pd.Series(False, index=series.index)
    warnings = pd.Series(False, index=series.index)
    converted = series.copy()

    if dtype == "numeric":
        numeric = pd.to_numeric(series.map(lambda value: str(value).replace(",", "")), errors="coerce")
        errors = numeric.isna() & ~missing
        converted = pd.Series([None if is_missing(value) else value for value in numeric], index=series.index)
        if target in REVIEW_RANGES:
            lower, upper = REVIEW_RANGES[target]
            hard_lower, hard_upper = INVALID_RANGES.get(target, (lower, upper))
            warnings = ((numeric < lower) | (numeric > upper)) & ~errors & ~missing
            errors = errors | (((numeric <= hard_lower) | (numeric >= hard_upper)) & ~missing)
            warnings = warnings & ~errors
    elif dtype == "date":
        parsed = series.map(lambda value: None if is_missing(value) else parse_unambiguous_date(value))
        ambiguous = series.map(lambda value: bool(AMBIGUOUS_DATE_PATTERN.fullmatch(str(value).strip())))
        errors = parsed.isna() & ~missing & ~ambiguous
        warnings = ambiguous & ~missing
        converted = pd.Series(parsed, index=series.index)
    elif dtype == "category" and target in CATEGORY_RULES:
        allowed = set(CATEGORY_RULES[target].values())
        warnings = ~series.map(lambda value: str(value) in allowed) & ~missing

    return converted, errors.fillna(False), warnings.fillna(False)


def _log(result: TransformResult, action: str, field: str, detail: str, level: str = "INFO") -> None:
    result.logs.append(
        {"stage": "transform", "action": action, "field": field, "detail": detail, "level": level}
    )


def transform_dataset(
    dataframe: pd.DataFrame,
    approved_mapping: dict[str, str | None],
    *,
    mapping_notes: dict[str, str] | None = None,
) -> TransformResult:
    result = TransformResult(dataframe=dataframe.copy())
    notes = mapping_notes or {}
    original_columns: list[str] = []

    for index, column in enumerate(dataframe.columns):
        original_name = f"original__{index}__{normalize_column_name(str(column))}"
        result.dataframe[original_name] = dataframe[column]
        original_columns.append(original_name)
    result.dataframe = result.dataframe.drop(columns=list(dataframe.columns))
    _log(
        result,
        "preserve_originals",
        "",
        f"Preserved {len(original_columns)} original columns without modification.",
    )

    duplicate_mask = dataframe.duplicated(keep="first")
    result.duplicate_count = int(duplicate_mask.sum())
    result.dataframe["_source_row_number"] = range(1, len(dataframe) + 1)
    result.dataframe["_duplicate_record"] = duplicate_mask.to_numpy()
    _log(
        result,
        "duplicate_detection",
        "",
        f"Flagged {result.duplicate_count} duplicate record(s). No rows were removed.",
    )

    validation_flags: list[list[str]] = [[] for _ in range(len(dataframe))]
    used_targets: set[str] = set()

    for source, target in approved_mapping.items():
        source_name = str(source)
        if not target or source_name not in dataframe.columns:
            _log(
                result,
                "mapping_skipped",
                source_name,
                notes.get(source_name, "No approved mapping; the source value was preserved only."),
                level="WARN",
            )
            continue
        schema_target = str(target)
        if schema_target in used_targets:
            _log(
                result,
                "duplicate_target",
                source_name,
                f"Target '{schema_target}' is already mapped from another source; this mapping was skipped.",
                level="WARN",
            )
            continue
        used_targets.add(schema_target)

        series = dataframe[source_name].copy()
        result.missing_counts[schema_target] = int(series.map(is_missing).sum())
        converted, conversion_note, unit_warning = _convert_units(series, source_name, schema_target)
        if conversion_note:
            _log(result, "unit_conversion", source_name, conversion_note)
        if unit_warning:
            _log(result, "unit_not_stated", source_name, unit_warning, level="WARN")

        if COMMON_SCHEMA.get(schema_target, {}).get("dtype") == "date":
            _log(
                result,
                "date_standardisation",
                source_name,
                "Only ISO and year-first dates are standardised; ambiguous values are left unchanged and flagged.",
            )
        converted, category_note = _normalise_categories(converted, schema_target)
        if category_note:
            _log(result, "category_normalisation", source_name, category_note)

        converted, errors, warnings = _validate_target(converted, schema_target)
        result.error_counts[schema_target] = int(errors.sum())
        result.invalid_counts[schema_target] = int(errors.sum())
        result.warning_counts[schema_target] = int(warnings.sum())

        for position, (is_error, is_warning) in enumerate(zip(errors, warnings, strict=True)):
            if is_error:
                validation_flags[position].append(f"{schema_target}:error")
            if is_warning:
                validation_flags[position].append(f"{schema_target}:review")

        for position, (is_error, is_warning) in enumerate(zip(errors, warnings, strict=True)):
            severity = "error" if is_error else "warning" if is_warning else None
            if severity is None:
                continue
            original = dataframe[source_name].iloc[position]
            result.row_issues.append(
                {
                    "row": position + 1,
                    "source": source_name,
                    "target": schema_target,
                    "severity": severity,
                    "code": "invalid_value" if is_error else "review_value",
                    "original": str(original),
                    "converted": str(converted.iloc[position]),
                    "message": (
                        f"Invalid value for {schema_target}; original value preserved and flagged."
                        if is_error
                        else f"Value for {schema_target} requires manual review; no automatic correction was made."
                    ),
                }
            )

        mapped_target = f"mapped_{schema_target}" if schema_target in dataframe.columns else schema_target
        result.dataframe[mapped_target] = converted
        result.mapped_columns.append(mapped_target)
        _log(
            result,
            "common_schema_mapping",
            source_name,
            f"Mapped to '{mapped_target}' with {result.missing_counts[schema_target]} missing value(s); "
            f"{result.error_counts[schema_target]} error(s) and {result.warning_counts[schema_target]} warning(s).",
        )

    result.review_count = len(result.row_issues)
    result.dataframe["_validation_flags"] = pd.Series(
        [";".join(flags) for flags in validation_flags], index=dataframe.index
    )
    _log(
        result,
        "validation_summary",
        "",
        f"Recorded {result.review_count} row-level finding(s). No values were imputed or rows removed; "
        "source values remain in original__ columns.",
    )
    return result
