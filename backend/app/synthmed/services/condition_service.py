from __future__ import annotations

import inspect
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from fastapi import HTTPException
from sdv.sampling import Condition
from sdv.single_table import CTGANSynthesizer, GaussianCopulaSynthesizer, TVAESynthesizer
from sdv.version import community as SDV_VERSION

from app.core.config import Settings
from app.synthmed.models import SynthMedSourceDataset
from app.synthmed.services.dataset_service import (
    TABLE_NAME,
    analyse_dataframe,
    prepare_dataframe,
    read_source_dataframe,
)
from app.synthmed.services.medical_schema_service import profile_medical_schema
from app.synthmed.services.storage_service import SynthMedStorageService

SUPPORTED_OPERATOR = "eq"
RANGE_OPERATORS = {"between", "range", "gt", "gte", "lt", "lte"}
MODEL_ALIASES = {
    "ctgan": "CTGAN",
    "sdv ctgansynthesizer": "CTGAN",
    "sdv ctgan synthesizer": "CTGAN",
    "tvae": "TVAE",
    "sdv tvaesynthesizer": "TVAE",
    "sdv tvae synthesizer": "TVAE",
    "gaussiancopula": "GaussianCopula",
    "gaussian copula": "GaussianCopula",
    "sdv gaussiancopulasynthesizer": "GaussianCopula",
    "sdv gaussian copula synthesizer": "GaussianCopula",
}
MODEL_LABELS = {
    "CTGAN": "SDV CTGANSynthesizer",
    "TVAE": "SDV TVAESynthesizer",
    "GaussianCopula": "SDV GaussianCopulaSynthesizer",
}


@dataclass(frozen=True)
class ModelCapabilities:
    model: str
    sdv_class: str
    sampling_api: str
    sampling_strategy: str
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "sdvClass": self.sdv_class,
            "samplingApi": self.sampling_api,
            "conditionalSampling": True,
            "multipleConditions": True,
            "exactEquality": True,
            "rangeOperators": False,
            "primaryKeyConditions": False,
            "missingValueConditions": False,
            "unconditionalSampling": True,
            "implemented": True,
            "sdvVersion": SDV_VERSION,
            "samplingStrategy": self.sampling_strategy,
            "notes": list(self.notes),
        }


CAPABILITIES: dict[str, ModelCapabilities] = {
    "CTGAN": ModelCapabilities(
        model="CTGAN",
        sdv_class="CTGANSynthesizer",
        sampling_api="sample_from_conditions",
        sampling_strategy="reject_sampling",
        notes=(
            f"SDV {SDV_VERSION} exposes conditional sampling through sample_from_conditions with "
            "sdv.sampling.Condition objects that specify exact column values only.",
            "CTGAN conditioning uses reject sampling; rare exact values may return fewer rows or fail.",
            "The fitted synthesizer object is retained for the complete generate-and-sample operation.",
        ),
    ),
    "TVAE": ModelCapabilities(
        model="TVAE",
        sdv_class="TVAESynthesizer",
        sampling_api="sample_from_conditions",
        sampling_strategy="reject_sampling",
        notes=(
            f"SDV {SDV_VERSION} exposes conditional sampling through sample_from_conditions with "
            "sdv.sampling.Condition objects that specify exact column values only.",
            "TVAE conditioning uses reject sampling; rare exact values may return fewer rows or fail.",
            "The fitted synthesizer object is retained for the complete generate-and-sample operation.",
        ),
    ),
    "GaussianCopula": ModelCapabilities(
        model="GaussianCopula",
        sdv_class="GaussianCopulaSynthesizer",
        sampling_api="sample_from_conditions",
        sampling_strategy="gaussian_multivariate",
        notes=(
            f"SDV {SDV_VERSION} exposes conditional sampling through sample_from_conditions with "
            "sdv.sampling.Condition objects that specify exact column values only.",
            "GaussianCopula samples conditioned rows from the fitted Gaussian multivariate model.",
            "Out-of-bounds numeric values can fail because GaussianCopula does not use reject sampling.",
        ),
    ),
}

MODEL_CLASSES = {
    "CTGAN": CTGANSynthesizer,
    "TVAE": TVAESynthesizer,
    "GaussianCopula": GaussianCopulaSynthesizer,
}


def verify_sdv_api() -> dict[str, bool]:
    condition_signature = inspect.signature(Condition)
    condition_object = "column_values" in condition_signature.parameters
    result: dict[str, bool] = {}
    for model, capability in CAPABILITIES.items():
        synthesizer = MODEL_CLASSES[model]
        method = getattr(synthesizer, capability.sampling_api, None)
        has_parameter = False
        if method is not None:
            parameters = inspect.signature(method).parameters
            has_parameter = "conditions" in parameters
        result[model] = callable(method) and has_parameter and condition_object
    return result


def normalize_model(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return "CTGAN"
    raw = str(value).strip()
    if raw in CAPABILITIES:
        return raw
    return MODEL_ALIASES.get(raw.lower())


def get_capabilities(value: Any) -> ModelCapabilities:
    model = normalize_model(value)
    if model is None:
        raise ValueError(f"Unknown synthesis model: {value!r}")
    return CAPABILITIES[model]


def model_capabilities() -> list[dict[str, Any]]:
    return [CAPABILITIES[model].as_dict() for model in CAPABILITIES]


def _as_condition_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return dict(item.model_dump())
    if isinstance(item, dict):
        return dict(item)
    return {}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and not math.isfinite(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _condition_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [_as_condition_dict(item) for item in (config.get("conditions") or [])]


def _record_count(config: dict[str, Any]) -> int | None:
    value = config.get("recordCount")
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _combined_mode(normalized: list[dict[str, Any]], record_count: int | None) -> bool:
    if len(normalized) < 2 or record_count is None:
        return False
    columns = [str(item["column"]) for item in normalized]
    if len(set(columns)) != len(columns):
        return False
    return all(int(item["numRows"]) == record_count for item in normalized)


def build_sampling_plan(normalized: list[dict[str, Any]], record_count: int | None) -> list[dict[str, Any]]:
    if not normalized:
        return []
    if _combined_mode(normalized, record_count):
        return [
            {
                "mode": "all_conditions",
                "numRows": record_count,
                "conditions": [dict(item) for item in normalized],
            }
        ]
    return [
        {
            "mode": "condition_cohort",
            "numRows": int(item["numRows"]),
            "conditions": [dict(item)],
        }
        for item in normalized
    ]


def build_sdv_conditions(plan: list[dict[str, Any]]) -> list[Condition]:
    built: list[Condition] = []
    for cohort in plan:
        column_values: dict[str, Any] = {}
        for item in cohort["conditions"]:
            column_values[str(item["column"])] = item["value"]
        built.append(Condition(column_values=column_values, num_rows=int(cohort["numRows"])))
    return built


def _sdtype_from_prepared(prepared: dict[str, Any], column: str, config: dict[str, Any]) -> str:
    categorical = set(config.get("categoricalColumns") or [])
    numerical = set(config.get("numericalColumns") or [])
    if column in categorical:
        return "categorical"
    if column in numerical:
        return "numerical"
    tables = (prepared.get("metadataDict") or {}).get("tables") or {}
    metadata_column = ((tables.get(TABLE_NAME) or {}).get("columns") or {}).get(column) or {}
    return str(metadata_column.get("sdtype") or "categorical")


def validate_conditions(
    *,
    source: SynthMedSourceDataset,
    config: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    normalized: list[dict[str, Any]] = []
    plan: list[dict[str, Any]] = []

    try:
        capabilities = get_capabilities(config.get("model"))
    except ValueError as error:
        return {
            "valid": False,
            "model": str(config.get("model") or ""),
            "capabilities": CAPABILITIES["CTGAN"].as_dict(),
            "eligibleColumns": [],
            "ineligibleColumns": [],
            "normalizedConditions": [],
            "samplingPlan": [],
            "errors": [str(error)],
            "warnings": [],
        }
    model = capabilities.model

    try:
        storage = SynthMedStorageService(settings)
        frame = read_source_dataframe(storage.resolve_source(source.stored_path), source.file_format)
        prepared = prepare_dataframe(frame, dict(config))
    except (HTTPException, ValueError, FileNotFoundError, OSError) as error:
        detail = error.detail if isinstance(error, HTTPException) else str(error)
        return {
            "valid": False,
            "model": model,
            "capabilities": capabilities.as_dict(),
            "eligibleColumns": [],
            "ineligibleColumns": [],
            "normalizedConditions": [],
            "samplingPlan": [],
            "errors": [f"Source dataset could not be prepared for condition validation: {detail}"],
            "warnings": [],
        }

    prepared_frame = prepared["frame"]
    analysis = analyse_dataframe(frame)
    analysis_by_name = {item["name"]: item for item in analysis["columns"]}
    medical_approved = set(profile_medical_schema(frame)["approvedOutputColumns"])
    selected = config.get("selectedColumns") or list(frame.columns)
    identifiers = set(config.get("identifierColumns") or []) | set(analysis["potentialIdentifierColumns"])
    primary_key = config.get("primaryKey")
    if primary_key:
        identifiers.add(str(primary_key))
    constants = set(analysis["constantColumns"])
    categorical_values = config.get("categoricalValues") or {}
    numeric_ranges = config.get("numericRanges") or {}

    eligible: list[dict[str, Any]] = []
    ineligible: list[dict[str, Any]] = []
    for column in frame.columns:
        info = analysis_by_name.get(column, {})
        missing_count = int(info.get("missingCount", 0))
        unique_count = int(info.get("uniqueCount", 0))
        if column in identifiers:
            ineligible.append({"name": column, "reason": "Patient identifier or primary key"})
            continue
        if column in constants:
            ineligible.append({"name": column, "reason": "Constant column"})
            continue
        if column not in selected:
            ineligible.append({"name": column, "reason": "Not selected for modelling"})
            continue
        if column not in medical_approved:
            ineligible.append({"name": column, "reason": "Not an approved medical output column"})
            continue
        if column not in prepared_frame.columns:
            ineligible.append({"name": column, "reason": "Not included after preprocessing"})
            continue
        eligible.append(
            {
                "name": column,
                "sdtype": _sdtype_from_prepared(prepared, column, config),
                "missingCount": missing_count,
                "uniqueCount": unique_count,
            }
        )

    eligible_by_name = {item["name"]: item for item in eligible}
    total_rows = 0
    grouped: dict[str, list[tuple[str, Any]]] = defaultdict(list)

    for raw_condition in _condition_rows(config):
        column = str(raw_condition.get("column") or "").strip()
        operator = str(raw_condition.get("operator") or SUPPORTED_OPERATOR).strip().lower()
        raw_num_rows = raw_condition.get("numRows", 1)
        if isinstance(raw_num_rows, bool):
            num_rows = 1
            errors.append(f"Condition numRows for column '{column or '<unknown>'}' must be a positive integer.")
        else:
            try:
                num_rows = int(raw_num_rows)
            except (TypeError, ValueError):
                num_rows = 0
                errors.append(f"Condition numRows for column '{column or '<unknown>'}' must be a positive integer.")

        if num_rows < 1:
            errors.append(f"Condition numRows for column '{column or '<unknown>'}' must be at least 1.")
        total_rows += max(num_rows, 0)

        if not column:
            errors.append("Every condition must specify a column.")
            continue
        if column not in frame.columns:
            errors.append(f"Condition column '{column}' does not exist in the source dataset.")
            continue
        if column in identifiers:
            errors.append(
                f"Condition column '{column}' is a patient identifier or primary key and cannot be conditioned on."
            )
            continue
        if column not in eligible_by_name:
            if column not in medical_approved:
                errors.append(f"Condition column '{column}' is not an approved medical output column.")
            else:
                errors.append(f"Condition column '{column}' is not eligible for modelling.")
            continue

        if raw_condition.get("values") is not None:
            errors.append(
                f"Condition for column '{column}' supplies 'values'. SDV {SDV_VERSION} conditions accept one "
                "exact value per condition; add separate condition rows for additional cohorts."
            )
            continue

        if operator in RANGE_OPERATORS:
            low = _numeric(raw_condition.get("min"))
            high = _numeric(raw_condition.get("max"))
            if low is None or high is None:
                errors.append(f"Range condition for column '{column}' requires numeric 'min' and 'max'.")
            elif low > high:
                errors.append(f"Range condition for column '{column}' has min {low} greater than max {high}.")
            errors.append(
                f"Operator '{operator}' is not supported by SDV {SDV_VERSION} "
                f"{capabilities.sampling_api} for model {model}; only exact equality is available."
            )
            continue

        if operator != SUPPORTED_OPERATOR:
            errors.append(
                f"Operator '{operator}' is not supported for model {model}. "
                f"Supported operator: '{SUPPORTED_OPERATOR}'."
            )
            continue

        value = raw_condition.get("value")
        if _is_missing(value):
            errors.append(f"Condition for column '{column}' cannot use a missing or empty value.")
            continue

        sdtype = eligible_by_name[column]["sdtype"]
        if sdtype == "numerical":
            number = _numeric(value)
            if number is None:
                errors.append(f"Numerical condition for column '{column}' requires a numeric value.")
                continue
            bounds = numeric_ranges.get(column) or {}
            low = _numeric(bounds.get("min")) if bounds.get("min") is not None else None
            high = _numeric(bounds.get("max")) if bounds.get("max") is not None else None
            if (low is not None and number < low) or (high is not None and number > high):
                errors.append(
                    f"Numerical condition value {number} for column '{column}' is outside the configured "
                    f"range [{low}, {high}]."
                )
            observed = pd.to_numeric(prepared_frame[column], errors="coerce").dropna()
            if not observed.empty:
                observed_low = float(observed.min())
                observed_high = float(observed.max())
                if number < observed_low or number > observed_high:
                    warnings.append(
                        f"Numerical condition value {number} for column '{column}' is outside the prepared "
                        f"training range [{observed_low}, {observed_high}]."
                    )
            normalized.append(
                {
                    "column": column,
                    "operator": SUPPORTED_OPERATOR,
                    "value": number,
                    "numRows": num_rows,
                    "sdtype": sdtype,
                }
            )
            grouped[column].append((SUPPORTED_OPERATOR, number))
        else:
            allowed_raw = categorical_values.get(column)
            if allowed_raw:
                allowed = {str(item) for item in allowed_raw}
            else:
                values = prepared_frame[column].dropna().unique().tolist()
                allowed = {str(item) for item in values}
            string_value = str(value).strip()
            if sdtype == "boolean" and string_value.lower() in {"true", "false", "1", "0"}:
                canonical = "True" if string_value.lower() in {"true", "1"} else "False"
                if canonical in allowed or canonical.lower() in {item.lower() for item in allowed}:
                    string_value = canonical
            if string_value not in allowed and string_value.lower() not in {item.lower() for item in allowed}:
                preview = ", ".join(sorted(allowed)[:5])
                errors.append(
                    f"Categorical condition value '{value}' for column '{column}' is not present in the source "
                    f"dataset after preparation or configured allowed values. Examples: {preview or '<none>'}."
                )
                continue
            normalized.append(
                {
                    "column": column,
                    "operator": SUPPORTED_OPERATOR,
                    "value": string_value,
                    "numRows": num_rows,
                    "sdtype": sdtype,
                }
            )
            grouped[column].append((SUPPORTED_OPERATOR, string_value))

        if prepared_frame[column].isna().any():
            warnings.append(
                f"Column '{column}' contains missing values; SDV conditions match exact non-null values only."
            )

    record_count = _record_count(config)
    combined = _combined_mode(normalized, record_count)
    if record_count is not None and not combined and total_rows != record_count:
        errors.append(
            f"Sum of condition numRows ({total_rows}) must equal the requested recordCount ({record_count})."
        )
    if combined:
        for column, items in grouped.items():
            values = {str(item[1]) for item in items}
            if len(values) > 1:
                errors.append(
                    f"Conflicting exact condition values for column '{column}': {sorted(values)}. "
                    "Use separate cohorts with different numRows or remove the conflicting value."
                )
    else:
        for column, items in grouped.items():
            operators = {item[0] for item in items}
            if len(operators) > 1:
                errors.append(f"Conflicting condition operators for column '{column}': {sorted(operators)}.")
            values = {str(item[1]) for item in items}
            if len(values) > 1:
                warnings.append(
                    f"Column '{column}' has multiple distinct exact condition values; SDV will sample them as "
                    "separate cohorts."
                )

    if not errors:
        plan = build_sampling_plan(normalized, record_count)
        try:
            build_sdv_conditions(plan)
        except (TypeError, ValueError) as error:
            errors.append(f"SDV condition objects could not be created: {error}")
            plan = []

    return {
        "valid": not errors,
        "model": model,
        "capabilities": capabilities.as_dict(),
        "eligibleColumns": eligible,
        "ineligibleColumns": ineligible,
        "normalizedConditions": normalized,
        "samplingPlan": plan,
        "errors": errors,
        "warnings": warnings,
    }


def _matches_condition(series: pd.Series, condition: dict[str, Any]) -> pd.Series:
    value = condition.get("value")
    if str(condition.get("sdtype") or "") == "numerical":
        target = _numeric(value)
        if target is None:
            return pd.Series(False, index=series.index)
        numeric = pd.to_numeric(series, errors="coerce")
        return numeric.notna() & np.isclose(numeric.to_numpy(dtype=float), target, rtol=0.01, atol=0)
    actual = series.astype("string").str.strip()
    target_text = str(value).strip()
    if str(condition.get("sdtype") or "") == "boolean":
        return actual.str.lower().eq(target_text.lower()).fillna(False)
    return actual.eq(target_text).fillna(False)


def _mask_for(frame: pd.DataFrame, conditions: list[dict[str, Any]]) -> pd.Series:
    mask = pd.Series(True, index=frame.index)
    for condition in conditions:
        column = str(condition.get("column") or "")
        if column not in frame.columns:
            return pd.Series(False, index=frame.index)
        mask &= _matches_condition(frame[column], condition)
    return mask


def _percentage(count: int, total: int) -> float:
    return round(count / total * 100, 2) if total else 0.0


def evaluate_condition_satisfaction(
    synthetic_frame: pd.DataFrame,
    normalized: list[dict[str, Any]],
    plan: list[dict[str, Any]],
    record_count: int | None = None,
) -> dict[str, Any]:
    total = int(len(synthetic_frame))
    expected_total = int(record_count) if record_count is not None else sum(
        int(cohort.get("numRows", 0)) for cohort in plan
    )

    condition_results: list[dict[str, Any]] = []
    for index, condition in enumerate(normalized):
        mask = _mask_for(synthetic_frame, [condition])
        satisfied = int(mask.sum())
        condition_results.append(
            {
                "index": index,
                "column": str(condition.get("column") or ""),
                "operator": str(condition.get("operator") or SUPPORTED_OPERATOR),
                "requestedValue": condition.get("value"),
                "requestedRows": int(condition.get("numRows", 0)),
                "totalGeneratedRecords": total,
                "satisfyingRecords": satisfied,
                "nonSatisfyingRecords": total - satisfied,
                "satisfactionPercentage": _percentage(satisfied, total),
            }
        )

    cohort_results: list[dict[str, Any]] = []
    all_cohorts_satisfied = True
    for index, cohort in enumerate(plan):
        conditions = cohort.get("conditions") or []
        expected = int(cohort.get("numRows", 0))
        mask = _mask_for(synthetic_frame, conditions)
        satisfied = int(mask.sum())
        cohort_passed = satisfied == expected
        all_cohorts_satisfied = all_cohorts_satisfied and cohort_passed
        cohort_results.append(
            {
                "index": index,
                "mode": str(cohort.get("mode") or "condition_cohort"),
                "conditions": [
                    {
                        "column": str(item.get("column") or ""),
                        "operator": str(item.get("operator") or SUPPORTED_OPERATOR),
                        "value": item.get("value"),
                    }
                    for item in conditions
                ],
                "requestedRows": expected,
                "totalGeneratedRecords": total,
                "satisfyingRecords": satisfied,
                "nonSatisfyingRecords": total - satisfied,
                "satisfactionPercentage": _percentage(satisfied, total),
                "passed": cohort_passed,
            }
        )

    combined_mask = (
        _mask_for(synthetic_frame, normalized)
        if normalized
        else pd.Series(True, index=synthetic_frame.index)
    )
    combined_satisfied = int(combined_mask.sum()) if normalized else total
    exact_count = total == expected_total if expected_total else True
    passed = bool(normalized) and all_cohorts_satisfied and exact_count

    return {
        "method": "Direct evaluation of generated records against requested exact conditions",
        "conditional": bool(normalized),
        "requestedConditions": [
            {
                "column": str(item.get("column") or ""),
                "operator": str(item.get("operator") or SUPPORTED_OPERATOR),
                "value": item.get("value"),
                "numRows": int(item.get("numRows", 0)),
            }
            for item in normalized
        ],
        "conditions": condition_results,
        "cohorts": cohort_results,
        "combined": {
            "requestedConditions": len(normalized),
            "totalGeneratedRecords": total,
            "satisfyingRecords": combined_satisfied,
            "nonSatisfyingRecords": total - combined_satisfied,
            "satisfactionPercentage": _percentage(combined_satisfied, total),
        },
        "generatedRecordCount": total,
        "expectedRecordCount": expected_total,
        "recordCountMatches": exact_count,
        "allConditionsSatisfied": passed,
        "passed": passed,
        "limitations": [
            "Satisfaction is measured from the exported generated records after SDV reverse transformation.",
            "Numerical equality uses the same 1 percent relative tolerance as SDV 2.2 condition filtering.",
            "Condition satisfaction does not establish statistical similarity, clinical validity or privacy.",
        ],
    }
