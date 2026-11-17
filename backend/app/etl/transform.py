from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
from dateutil import parser as date_parser

from app.etl.extract import is_missing

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

DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y")


@dataclass
class TransformResult:
    dataframe: pd.DataFrame
    logs: list[dict[str, Any]] = field(default_factory=list)
    missing_counts: dict[str, int] = field(default_factory=dict)
    duplicate_count: int = 0
    invalid_counts: dict[str, int] = field(default_factory=dict)
    review_count: int = 0
    mapped_columns: list[str] = field(default_factory=list)


def normalize_column_name(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


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
                candidate_reason = "Exact match to an explicit common-schema alias"
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
                    "note": "No reliable match. A contributor must supply an explicit mapping.",
                }
            )
        else:
            suggestions.append(
                {
                    "source": column,
                    "target": best_target,
                    "confidence": best_confidence,
                    "status": "Suggested",
                    "note": f"{best_reason}. Suggestions are never auto-approved.",
                }
            )
    return suggestions


def _parse_date(value: Any) -> str | None:
    text = str(value).strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    try:
        return date_parser.parse(text).date().isoformat()
    except (ValueError, OverflowError, TypeError):
        return None


def _convert_units(series: pd.Series, source: str, target: str) -> tuple[pd.Series, str | None]:
    name = normalize_column_name(source)
    numeric = pd.to_numeric(series, errors="coerce")
    if target == "age_years" and ("month" in name or name.endswith("_mo")):
        return numeric / 12, "Converted age from months to years"
    if target == "weight_kg" and ("lb" in name or "pound" in name):
        return numeric * 0.45359237, "Converted weight from pounds to kilograms"
    if target == "height_cm" and ("meter" in name or name.endswith("_m")) and "cm" not in name:
        return numeric * 100, "Converted height from metres to centimetres"
    if target == "gestational_age_weeks" and "day" in name:
        return numeric / 7, "Converted gestational age from days to weeks"
    return series, None


def _normalise_categories(series: pd.Series, target: str) -> tuple[pd.Series, str | None]:
    rules = CATEGORY_RULES.get(target)
    if not rules:
        return series, None
    converted = series.map(lambda value: rules.get(str(value).strip().lower(), value))
    return converted, f"Normalised category values using {target} rules"


def _validate_target(series: pd.Series, target: str) -> tuple[pd.Series, int]:
    rule = COMMON_SCHEMA.get(target, {"dtype": "string"})
    dtype = rule["dtype"]
    if dtype == "numeric":
        invalid = series.map(
            lambda value: pd.isna(pd.to_numeric([value], errors="coerce")[0]) and not is_missing(value)
        )
        return series, int(invalid.sum())
    if dtype == "date":
        return series, int(series.map(lambda value: _parse_date(value) is None and not is_missing(value)).sum())
    return series, 0


def _review_values(series: pd.Series, target: str) -> int:
    bounds = REVIEW_RANGES.get(target)
    if bounds is None:
        return 0
    numeric = pd.to_numeric(series, errors="coerce")
    lower, upper = bounds
    return int(((numeric < lower) | (numeric > upper)).sum())


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
    result.logs.append(
        {
            "stage": "transform",
            "action": "preserve_originals",
            "field": "",
            "detail": f"Preserved {len(original_columns)} original columns without modification.",
        }
    )

    duplicate_mask = dataframe.duplicated(keep="first")
    result.duplicate_count = int(duplicate_mask.sum())
    result.dataframe["_source_row_number"] = range(1, len(dataframe) + 1)
    result.dataframe["_duplicate_record"] = duplicate_mask.to_numpy()
    result.logs.append(
        {
            "stage": "transform",
            "action": "duplicate_detection",
            "field": "",
            "detail": f"Flagged {result.duplicate_count} duplicate record(s). No rows were removed.",
        }
    )

    validation_flags: list[list[str]] = [[] for _ in range(len(dataframe))]

    for source, target in approved_mapping.items():
        if not target or source not in dataframe.columns:
            result.logs.append(
                {
                    "stage": "transform",
                    "action": "mapping_skipped",
                    "field": str(source),
                    "detail": notes.get(str(source), "Mapping was not approved; source value was preserved only."),
                }
            )
            continue
        schema_target = str(target)
        series = dataframe[source].copy()
        result.missing_counts[schema_target] = int(series.map(is_missing).sum())
        converted, conversion_note = _convert_units(series, str(source), schema_target)
        if conversion_note:
            result.logs.append(
                {
                    "stage": "transform",
                    "action": "unit_conversion",
                    "field": str(source),
                    "detail": conversion_note,
                }
            )
        if COMMON_SCHEMA.get(schema_target, {}).get("dtype") == "date":
            parsed = converted.map(_parse_date)
            converted = pd.Series(
                [
                    parsed_value if parsed_value is not None else original
                    for parsed_value, original in zip(parsed, series, strict=True)
                ],
                index=dataframe.index,
            )
            result.logs.append(
                {
                    "stage": "transform",
                    "action": "date_standardisation",
                    "field": str(source),
                    "detail": "Parsed date values to ISO format where possible; unparseable values retained unchanged.",
                }
            )
        converted, category_note = _normalise_categories(converted, schema_target)
        if category_note:
            result.logs.append(
                {
                    "stage": "transform",
                    "action": "category_normalisation",
                    "field": str(source),
                    "detail": category_note,
                }
            )
        converted, invalid_count = _validate_target(converted, schema_target)
        result.invalid_counts[schema_target] = invalid_count
        for position, value in enumerate(converted):
            if invalid_count and not is_missing(value):
                try:
                    numeric_value = float(str(value).replace(",", ""))
                except ValueError:
                    numeric_value = None
                if numeric_value is None or (
                    schema_target in REVIEW_RANGES
                    and not (REVIEW_RANGES[schema_target][0] <= numeric_value <= REVIEW_RANGES[schema_target][1])
                ):
                    validation_flags[position].append(f"{schema_target}:review")
        mapped_target = f"mapped_{schema_target}" if schema_target in dataframe.columns else schema_target
        result.dataframe[mapped_target] = converted
        result.mapped_columns.append(mapped_target)
        result.logs.append(
            {
                "stage": "transform",
                "action": "common_schema_mapping",
                "field": str(source),
                "detail": f"Mapped to '{mapped_target}' with {result.missing_counts[schema_target]} missing value(s).",
            }
        )
        review_count = _review_values(converted, schema_target)
        result.review_count += review_count
        if review_count:
            result.logs.append(
                {
                    "stage": "transform",
                    "action": "unusual_value_review",
                    "field": str(source),
                    "detail": (
                        f"Flagged {review_count} value(s) for review using documented ranges; "
                        "not treated as errors."
                    ),
                }
            )

    validation_series = pd.Series([";".join(flags) for flags in validation_flags], index=dataframe.index)
    result.dataframe["_validation_flags"] = validation_series
    result.logs.append(
        {
            "stage": "transform",
            "action": "validation_summary",
            "field": "",
            "detail": "No values were imputed, removed or overwritten in the preserved source columns.",
        }
    )
    return result
