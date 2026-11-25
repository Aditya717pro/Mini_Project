from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import random
import time
import traceback
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
import torch
from fastapi import HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.models.user import User
from app.services.audit_service import log_audit
from app.synthmed.models import (
    SynthMedEvaluationReport,
    SynthMedGeneratedDataset,
    SynthMedGenerationConfig,
    SynthMedGenerationJob,
    SynthMedSourceDataset,
)
from app.synthmed.services import (
    clinical_reference_service,
    condition_service,
    medical_schema_service,
    versioning_service,
)
from app.synthmed.services.dataset_service import (
    TABLE_NAME,
    analyse_dataframe,
    dump_json,
    json_safe,
    prepare_dataframe,
    read_source_dataframe,
)
from app.synthmed.services.evaluation_service import build_privacy_report, build_quality_report
from app.synthmed.services.source_service import to_generated_response
from app.synthmed.services.storage_service import SynthMedStorageService

logger = logging.getLogger(__name__)

MODEL_NAME = condition_service.MODEL_LABELS["CTGAN"]
CLINICAL_PROFILES = {"Standard", "NormalRange", "ClinicalDistribution"}
TERMINAL_STATUSES = {"Completed", "Failed"}
ACTIVE_STATUSES = {"Queued", "Preprocessing", "Training", "Generating", "Validating", "Evaluating"}
INTERRUPTED_ERROR_TYPE = "InterruptedJob"
INTERRUPTED_ERROR_MESSAGE = "Generation was interrupted by an API restart."
_executor: ThreadPoolExecutor | None = None
_executor_lock = Lock()
_executor_stopping = False


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _session_factory(db: Session | None = None) -> sessionmaker[Session]:
    if db is not None:
        return sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    return SessionLocal


def _executor_for(settings: Settings) -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor_stopping:
            raise RuntimeError("SynthMed generation executor is shutting down")
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.synthmed_generation_worker_count, thread_name_prefix="synthmed-ctgan"
            )
        return _executor


def shutdown_executor(wait: bool = True) -> None:
    global _executor, _executor_stopping
    with _executor_lock:
        _executor_stopping = True
        executor = _executor
        _executor = None
    if executor is not None:
        try:
            executor.shutdown(wait=wait, cancel_futures=not wait)
        except Exception:
            logger.exception("SynthMed generation executor shutdown failed")


def _status(job: SynthMedGenerationJob, value: str, **updates: Any) -> None:
    job.status = value
    for key, item in updates.items():
        setattr(job, key, item)
    job.updated_at = _now()


def _error_details(error: Exception) -> dict[str, Any]:
    tb = traceback.format_exc()[-2000:]
    msg = str(error)[:1200] or f"{type(error).__name__} raised during generation."
    return {
        "type": type(error).__name__,
        "message": f"{msg}\n{tb}"[:3000],
        "traceback": tb,
    }


def _validate_config(config: dict[str, Any], settings: Settings, model: str) -> None:
    record_count = int(config["recordCount"])
    if not (1 <= record_count <= settings.synthmed_ctgan_max_records):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Requested record count must be between 1 and {settings.synthmed_ctgan_max_records}.",
        )
    if model == "GaussianCopula":
        return
    epochs = int(config["epochs"])
    batch_size = int(config["batchSize"])
    if not (1 <= epochs <= settings.synthmed_ctgan_max_epochs):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Epochs must be between 1 and {settings.synthmed_ctgan_max_epochs}.",
        )
    if not (20 <= batch_size <= 10000) or batch_size % 10 != 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Batch size must be a multiple of 10 between 20 and 10000 for CTGAN and TVAE.",
        )


def _set_seed(seed: int | None) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed if seed is not None else int.from_bytes(np.random.bytes(4), "big"))


def _save_report(storage: SynthMedStorageService, job_id: str, filename: str, payload: dict[str, Any]) -> str:
    _, relative = storage.save_report(job_id, filename, dump_json(payload))
    return relative


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in (value or []) if isinstance(item, dict)]


def _normalise_column_name(value: Any) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def _resolve_column(columns: list[str], *candidates: str) -> str | None:
    normalised = {_normalise_column_name(column): column for column in columns}
    for candidate in candidates:
        resolved = normalised.get(_normalise_column_name(candidate))
        if resolved:
            return resolved
    return None


def _column_mapping(config: dict[str, Any], columns: list[str]) -> dict[str, str | None]:
    """Resolve key medical columns using schema profile mapping first, then safe aliases."""
    profile = ((config.get("clinicalSetup") or {}).get("medicalProfile") or config.get("medicalProfile") or {})
    by_standard: dict[str, str] = {}
    for item in profile.get("columns", []) if isinstance(profile, dict) else []:
        if not isinstance(item, dict):
            continue
        original = str(item.get("originalName") or "")
        standard = str(item.get("standardisedName") or "")
        role = str(item.get("role") or "")
        approved = bool(item.get("approvedForOutput"))
        confidence = str(item.get("mappingConfidence") or "")
        if original in columns and approved and confidence not in {"Rejected", "Low"}:
            if standard and standard not in by_standard:
                by_standard[standard] = original
            if role in {"Disease", "Disease_Level"} and role not in by_standard:
                by_standard[role] = original

    def pick(standard: str, *aliases: str) -> str | None:
        mapped = by_standard.get(standard)
        if mapped in columns:
            return mapped
        return _resolve_column(columns, *aliases)

    return {
        "age": pick("Age", "Age", "Age_Years", "Patient_Age"),
        "gender": pick("Gender", "Gender", "Sex", "Sex_at_birth"),
        "disease": pick("Disease", "Disease", "Diagnosis"),
        "disease_level": pick("Disease_Level", "Disease_Level", "Severity", "Severity_Level"),
        "height_cm": pick("Height", "Height_cm", "Height", "height_cm"),
        "weight_kg": pick("Weight", "Weight_kg", "Weight", "weight_kg"),
        "bmi": pick("BMI", "BMI", "Body_Mass_Index", "bmi"),
        "systolic_bp": pick("Systolic_BP", "Systolic_BP_mmHg", "Systolic_BP", "SBP", "systolic_bp"),
        "diastolic_bp": pick("Diastolic_BP", "Diastolic_BP_mmHg", "Diastolic_BP", "DBP", "diastolic_bp"),
    }


def _source_preserving_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("sourcePreservingMode"))


def _age_tolerance(config: dict[str, Any]) -> int:
    try:
        value = int(config.get("ageToleranceYears", 5))
    except (TypeError, ValueError):
        value = 5
    return max(0, min(120, value))


def _finite_number(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        is_percent = text.endswith("%")
        if is_percent:
            text = text[:-1].strip()
        try:
            number = float(text)
        except ValueError:
            return default
        if is_percent:
            number /= 100.0
        return number if math.isfinite(number) and number >= 0 else default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) and number >= 0 else default


def _numeric_tolerances(
    config: dict[str, Any], source: pd.DataFrame, columns: list[str], age_column: str | None
) -> dict[str, float]:
    configured: dict[str, Any] = {}
    for key in ("numericTolerances", "sourceValueTolerances"):
        values = config.get(key) or {}
        if isinstance(values, dict):
            configured.update({str(name): value for name, value in values.items()})
    global_tolerance = _finite_number(
        config.get("numericTolerance", config.get("sourceValueTolerance"))
    )
    global_percent = _finite_number(config.get("numericTolerancePercent"))
    if global_percent is not None:
        global_percent /= 100.0
    tolerances: dict[str, float] = {}
    for column in columns:
        if column == age_column or not pd.api.types.is_numeric_dtype(source.get(column, pd.Series(dtype="float64"))):
            continue
        explicit = _finite_number(configured.get(column))
        if explicit is None and global_tolerance is not None:
            explicit = global_tolerance
        if explicit is None and global_percent is not None:
            numeric = pd.to_numeric(source[column], errors="coerce").abs().dropna()
            baseline = float(numeric.median()) if not numeric.empty else 1.0
            explicit = global_percent * max(baseline, 1.0)
        if explicit is None:
            numeric = pd.to_numeric(source[column], errors="coerce").abs().dropna()
            baseline = float(numeric.median()) if not numeric.empty else 1.0
            explicit = 0.05 * max(baseline, 1.0)
        tolerances[column] = float(explicit)
    return tolerances


def _coerce_source_values(values: list[Any], reference: pd.Series) -> pd.Series:
    series = pd.Series(values, dtype="object")
    if pd.api.types.is_bool_dtype(reference):
        return series.map({True: True, False: False, "True": True, "False": False}).astype("boolean")
    if pd.api.types.is_datetime64_any_dtype(reference):
        return pd.to_datetime(series, errors="coerce")
    if pd.api.types.is_numeric_dtype(reference):
        converted = pd.to_numeric(series, errors="coerce")
        if converted.isna().any():
            return converted.astype("Float64" if pd.api.types.is_float_dtype(reference) else "Int64")
        if pd.api.types.is_integer_dtype(reference) and (converted % 1 == 0).all():
            return converted.astype("int64")
        return converted.astype("float64")
    if isinstance(reference.dtype, pd.StringDtype):
        return series.astype("string")
    return series


def _condition_items(normalized_conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for condition in normalized_conditions or []:
        nested = condition.get("conditions") or []
        if isinstance(nested, list) and nested:
            items.extend([item for item in nested if isinstance(item, dict)])
        elif isinstance(condition, dict):
            items.append(condition)
    return items


def _source_row_matches_conditions(
    row: pd.Series, conditions: list[dict[str, Any]], tolerance_map: dict[str, float]
) -> bool:
    for condition in _condition_items(conditions):
        if str(condition.get("operator") or "eq") != "eq":
            return False
        column = str(condition.get("column") or "")
        if column not in row.index:
            return False
        actual = row.get(column)
        expected = condition.get("value")
        if actual is None or pd.isna(actual) or expected is None:
            return False
        try:
            if pd.api.types.is_numeric_dtype(pd.Series([actual])) and not isinstance(expected, str):
                if abs(float(actual) - float(expected)) > max(tolerance_map.get(column, 0.0), 1e-9):
                    return False
            elif str(actual).strip() != str(expected).strip():
                return False
        except (TypeError, ValueError):
            return False
    return True


def _resolve_age_column(columns: list[str], config: dict[str, Any] | None = None) -> str | None:
    if config:
        mapped = _column_mapping(config, columns).get("age")
        if mapped:
            return mapped
    return _resolve_column(columns, "Age", "Age_Years", "Patient_Age")


def _resolve_gender_column(columns: list[str], config: dict[str, Any] | None = None) -> str | None:
    if config:
        mapped = _column_mapping(config, columns).get("gender")
        if mapped:
            return mapped
    return _resolve_column(columns, "Gender", "Sex")


def _resolve_disease_column(columns: list[str], config: dict[str, Any] | None = None) -> str | None:
    if config:
        mapped = _column_mapping(config, columns).get("disease")
        if mapped:
            return mapped
    return _resolve_column(columns, "Disease")


def _resolve_disease_level_column(columns: list[str], config: dict[str, Any] | None = None) -> str | None:
    if config:
        mapped = _column_mapping(config, columns).get("disease_level")
        if mapped:
            return mapped
    return _resolve_column(columns, "Disease_Level", "DiseaseLevel", "Severity", "Severity_Level")


def _numeric_scalar(value: Any) -> float | None:
    if isinstance(value, bool) or value is None or pd.isna(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _age_int(value: Any) -> int | None:
    number = _numeric_scalar(value)
    if number is None:
        return None
    if abs(number - round(number)) > 1e-6:
        return None
    return int(round(number))


def _age_bounds(config: dict[str, Any], prepared: pd.DataFrame, age_column: str | None) -> tuple[int, int]:
    bounds = (config.get("numericRanges") or {}).get(age_column or "", {}) if age_column else {}
    lower = _age_int(bounds.get("min"))
    upper = _age_int(bounds.get("max"))
    if lower is None or upper is None:
        if age_column and age_column in prepared.columns:
            numeric = pd.to_numeric(prepared[age_column], errors="coerce").dropna()
            if not numeric.empty:
                lower = lower if lower is not None else int(math.floor(float(numeric.min())))
                upper = upper if upper is not None else int(math.ceil(float(numeric.max())))
    lower = 0 if lower is None else max(0, lower)
    upper = lower if upper is None else max(lower, upper)
    return lower, upper


def _categorical_reference_values(prepared: pd.DataFrame, config: dict[str, Any], column: str) -> list[str]:
    configured = config.get("categoricalValues") or {}
    if isinstance(configured.get(column), list) and configured[column]:
        return [str(value) for value in configured[column]]
    if column not in prepared.columns:
        return []
    return [str(value) for value in prepared[column].dropna().astype("string").unique().tolist()]


def _distribution(values: list[Any]) -> dict[str, Any]:
    counts = Counter(str(value) for value in values)
    total = sum(counts.values())
    ordered = dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
    return {
        "total": total,
        "counts": ordered,
        "proportions": {
            key: round(count / total * 100, 2) if total else 0.0 for key, count in ordered.items()
        },
    }


def _numeric_distribution(series: pd.Series) -> dict[str, Any]:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return {"count": 0}
    return {
        "count": int(numeric.count()),
        "min": json_safe(float(numeric.min())),
        "max": json_safe(float(numeric.max())),
        "mean": json_safe(float(numeric.mean())),
        "median": json_safe(float(numeric.median())),
        "std": json_safe(float(numeric.std(ddof=0))),
    }


def _source_preservation_plan(
    source: pd.DataFrame,
    prepared: dict[str, Any],
    config: dict[str, Any],
    requested_record_count: int,
    normalized_conditions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    frame = prepared["frame"]
    columns = [str(column) for column in frame.columns]
    mapping = _column_mapping(config, columns)
    config["columnMapping"] = json_safe(mapping)
    age_column = mapping.get("age") or _resolve_age_column(columns, config)
    gender_column = mapping.get("gender") or _resolve_gender_column(columns, config)
    disease_column = mapping.get("disease") or _resolve_disease_column(columns, config)
    disease_level_column = mapping.get("disease_level") or _resolve_disease_level_column(columns, config)
    age_lower, age_upper = _age_bounds(config, frame, age_column)
    categorical_columns = {
        column
        for column in {
            gender_column: "gender",
            disease_column: "disease",
            disease_level_column: "disease_level",
        }
        if column
    }
    source_rows = source.loc[:, columns].copy() if all(column in source.columns for column in columns) else frame.copy()
    tolerance_map = _numeric_tolerances(config, source_rows, columns, age_column)
    base_plan: dict[str, Any] = {
        "ageColumn": age_column,
        "genderColumn": gender_column,
        "diseaseColumn": disease_column,
        "diseaseLevelColumn": disease_level_column,
        "ageToleranceYears": _age_tolerance(config),
        "ageBounds": {"min": age_lower, "max": age_upper},
        "numericTolerances": tolerance_map,
        "categoricalColumns": sorted(categorical_columns),
        "sourceRecordCount": int(len(source_rows)),
        "requestedRecordCount": int(requested_record_count),
    }
    if not _source_preserving_enabled(config):
        return {
            **base_plan,
            "enabled": False,
            "strict": False,
            "rows": [],
            "sourceRowIndices": [],
            "selectedSourceRowCount": 0,
            "eligibleSourceRowCount": int(len(source_rows)),
            "anchorCount": 0,
        }

    conditions = list(normalized_conditions or [])
    if conditions:
        eligible_positions = [
            index
            for index in range(len(source_rows))
            if _source_row_matches_conditions(source_rows.iloc[index], conditions, tolerance_map)
        ]
        if not eligible_positions:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Strict source-preserving mode found no source rows matching the requested conditions.",
            )
    else:
        eligible_positions = list(range(len(source_rows)))
    if not eligible_positions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Strict source-preserving mode requires at least one source row.",
        )

    row_indices = [eligible_positions[index % len(eligible_positions)] for index in range(requested_record_count)]
    rows: list[dict[str, Any]] = []
    for position in row_indices:
        record = source_rows.iloc[position].to_dict()
        row: dict[str, Any] = {"sourceRowIndex": int(position)}
        for column in columns:
            value = record.get(column)
            row[column] = None if value is None or pd.isna(value) else json_safe(value)
        if age_column:
            anchor_age = _age_int(record.get(age_column))
            if anchor_age is not None:
                row["age"] = anchor_age
        for kind, column in (
            ("gender", gender_column),
            ("disease", disease_column),
            ("disease_level", disease_level_column),
        ):
            if not column:
                continue
            value = record.get(column)
            if value is None or pd.isna(value):
                continue
            row[kind] = str(value).strip()
        rows.append(row)

    anchor_ages = [item["age"] for item in rows if "age" in item]
    if age_column and not anchor_ages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Strict source-preserving mode requires a usable age column in the approved source data. "
                "No integer source ages could be derived."
            ),
        )

    categorical_values = {
        column: _categorical_reference_values(source_rows, config, column) for column in categorical_columns
    }
    return {
        **base_plan,
        "enabled": True,
        "strict": True,
        "rows": rows,
        "sourceRowIndices": row_indices,
        "anchorCount": len(rows),
        "anchorAgeCount": len(anchor_ages),
        "selectedSourceRowCount": len(rows),
        "eligibleSourceRowCount": len(eligible_positions),
        "categoricalValues": categorical_values,
        "notes": [
            "Each generated row is aligned to one source row in source order.",
            "Source row indices are internal only and are never exported.",
        ],
    }


def _source_alignment_metrics(
    plan: dict[str, Any], synthetic: pd.DataFrame, config: dict[str, Any]
) -> dict[str, Any]:
    rows = list(plan.get("rows") or [])[: len(synthetic)]
    age_column = plan.get("ageColumn")
    tolerance = int(plan.get("ageToleranceYears", _age_tolerance(config)))
    numeric_tolerances = dict(
        plan.get("numericTolerances")
        or _numeric_tolerances(config, synthetic, list(synthetic.columns), age_column)
    )
    category_columns = {
        "gender": ("genderMismatchCount", plan.get("genderColumn")),
        "disease": ("diseaseMismatchCount", plan.get("diseaseColumn")),
        "disease_level": ("diseaseLevelMismatchCount", plan.get("diseaseLevelColumn")),
    }
    category_mismatches: dict[str, int] = defaultdict(int)
    for kind, (key, column) in category_columns.items():
        if not column or column not in synthetic.columns:
            continue
        for index, value in enumerate(synthetic[column].tolist()):
            expected = rows[index].get(kind, rows[index].get(column)) if index < len(rows) else None
            if expected is None or pd.isna(expected):
                if not pd.isna(value):
                    category_mismatches[key] += 1
                continue
            if pd.isna(value) or str(value).strip() != str(expected).strip():
                category_mismatches[key] += 1

    age_violations = 0
    age_deviations: list[int] = []
    if age_column and age_column in synthetic.columns:
        generated_ages = pd.to_numeric(synthetic[age_column], errors="coerce")
        for index, value in enumerate(generated_ages.tolist()):
            expected = _age_int(rows[index].get("age", rows[index].get(age_column))) if index < len(rows) else None
            generated_age = _age_int(value)
            if expected is None or generated_age is None or abs(generated_age - expected) > tolerance:
                age_violations += 1
            if expected is not None and generated_age is not None:
                age_deviations.append(abs(generated_age - expected))

    numeric_violations: dict[str, int] = defaultdict(int)
    protected = {age_column, plan.get("genderColumn"), plan.get("diseaseColumn"), plan.get("diseaseLevelColumn")}
    for column in synthetic.columns:
        if column in protected or column not in numeric_tolerances:
            continue
        generated = pd.to_numeric(synthetic[column], errors="coerce")
        allowed = numeric_tolerances[column]
        for index, value in enumerate(generated.tolist()):
            expected = _numeric_scalar(rows[index].get(column)) if index < len(rows) else None
            actual = _numeric_scalar(value)
            if expected is None or actual is None or abs(actual - expected) > allowed:
                numeric_violations[column] += 1

    missing_records = max(0, len(plan.get("rows") or []) - len(synthetic))
    extra_records = max(0, len(synthetic) - len(plan.get("rows") or []))
    row_order_mismatches = (
        int(category_mismatches.get("genderMismatchCount", 0))
        + int(category_mismatches.get("diseaseMismatchCount", 0))
        + int(category_mismatches.get("diseaseLevelMismatchCount", 0))
        + age_violations
        + sum(numeric_violations.values())
        + missing_records
        + extra_records
    )
    failures: list[str] = []
    if category_mismatches.get("genderMismatchCount"):
        failures.append(f"{category_mismatches['genderMismatchCount']} gender value(s) do not match their source row.")
    if age_violations:
        failures.append(f"{age_violations} generated age(s) exceed the +/-{tolerance} year source tolerance.")
    if category_mismatches.get("diseaseMismatchCount"):
        failures.append(
            f"{category_mismatches['diseaseMismatchCount']} disease value(s) do not match their source row."
        )
    if category_mismatches.get("diseaseLevelMismatchCount"):
        failures.append(
            f"{category_mismatches['diseaseLevelMismatchCount']} disease level value(s) do not match their source row."
        )
    if numeric_violations:
        failures.append(
            "Source-preserving numeric tolerance violations: "
            + ", ".join(f"{column}={count}" for column, count in sorted(numeric_violations.items()))
        )
    if missing_records or extra_records:
        failures.append(
            f"Source row count mismatch: {missing_records} missing record(s), {extra_records} extra record(s)."
        )
    return {
        "sourceRowCount": len(plan.get("rows") or []),
        "generatedRecordCount": int(len(synthetic)),
        "genderMismatchCount": int(category_mismatches.get("genderMismatchCount", 0)),
        "ageViolationCount": age_violations,
        "diseaseMismatchCount": int(category_mismatches.get("diseaseMismatchCount", 0)),
        "diseaseLevelMismatchCount": int(category_mismatches.get("diseaseLevelMismatchCount", 0)),
        "numericViolations": dict(numeric_violations),
        "numericViolationCount": int(sum(numeric_violations.values())),
        "missingRecordCount": missing_records,
        "extraRecordCount": extra_records,
        "rowOrderMismatchCount": row_order_mismatches,
        "ageDeviations": age_deviations,
        "ageWithinTolerance": sum(1 for value in age_deviations if value <= tolerance),
        "categoryMismatches": dict(category_mismatches),
        "failures": failures,
        "passed": not row_order_mismatches,
        "status": "Passed" if not row_order_mismatches else "Failed",
    }


def _preservation_source_frame(plan: dict[str, Any], columns: list[str]) -> pd.DataFrame:
    rows = list(plan.get("rows") or [])
    return pd.DataFrame({column: [row.get(column) for row in rows] for column in columns})


def _public_clinical_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "_mandatoryFailures"}


def _apply_source_preservation(
    synthetic: pd.DataFrame,
    *,
    plan: dict[str, Any],
    config: dict[str, Any],
    rng: np.random.Generator | None = None,
    normalized_conditions: list[dict[str, Any]] | None = None,
    row_start: int = 0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not plan.get("enabled"):
        return synthetic, {"enabled": False}

    frame = synthetic.copy().reset_index(drop=True)
    source_rows = list(plan.get("rows") or [])[row_start : row_start + len(frame)]
    if len(source_rows) != len(frame):
        raise RuntimeError("Strict source-preserving mode could not align a source row to every generated record.")

    protected = {
        plan.get("ageColumn"),
        plan.get("genderColumn"),
        plan.get("diseaseColumn"),
        plan.get("diseaseLevelColumn"),
    }
    numeric_tolerances = dict(plan.get("numericTolerances") or {})
    restored: dict[str, int] = defaultdict(int)
    for column in frame.columns:
        source_values = [row.get(column) for row in source_rows]
        source_series = _coerce_source_values(source_values, frame[column])
        if column in protected or not pd.api.types.is_numeric_dtype(frame[column]):
            frame[column] = source_series
            continue
        generated_numeric = pd.to_numeric(frame[column], errors="coerce")
        source_numeric = pd.to_numeric(source_series, errors="coerce")
        tolerance = float(numeric_tolerances.get(column, 0.0))
        invalid = source_numeric.notna() & (
            generated_numeric.isna() | ((generated_numeric - source_numeric).abs() > tolerance)
        )
        invalid |= source_numeric.isna() & generated_numeric.notna()
        if bool(invalid.any()):
            restored[column] += int(invalid.sum())
        frame[column] = source_series

    alignment = _source_alignment_metrics(plan, frame, config)
    meta = {
        "enabled": True,
        "strict": True,
        "selectedSourceRowCount": int(len(source_rows)),
        "selectedAnchorCount": int(len(source_rows)),
        "ageDeviations": alignment["ageDeviations"],
        "ageWithinTolerance": int(alignment["ageWithinTolerance"]),
        "categoryMismatches": alignment["categoryMismatches"],
        "failures": list(alignment["failures"]),
        "sourceValueRestorations": dict(restored),
        "rejectedCandidateRecords": int(sum(1 for count in restored.values() if count > 0)),
        "regenerationAttempts": int(sum(restored.values())),
        "alignment": alignment,
    }
    return frame, meta


def _enforce_bmi_consistency(
    frame: pd.DataFrame, config: dict[str, Any] | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = frame.copy()
    mapping = _column_mapping(config or {}, list(out.columns))
    height_col = mapping.get("height_cm") or _resolve_column(list(out.columns), "Height_cm", "Height", "height_cm")
    weight_col = mapping.get("weight_kg") or _resolve_column(list(out.columns), "Weight_kg", "Weight", "weight_kg")
    bmi_col = mapping.get("bmi") or _resolve_column(list(out.columns), "BMI", "Body_Mass_Index", "bmi")
    report: dict[str, Any] = {"checked": False, "correctedRecords": 0, "inconsistentRecords": 0}
    if not (height_col and weight_col and bmi_col):
        return out, report
    h = pd.to_numeric(out[height_col], errors="coerce")
    w = pd.to_numeric(out[weight_col], errors="coerce")
    b = pd.to_numeric(out[bmi_col], errors="coerce")
    valid = h.notna() & w.notna() & (h > 0) & (w > 0)
    expected = w / ((h / 100.0) ** 2)
    tolerance = 0.1
    inconsistent = valid & b.notna() & ((b - expected).abs() > tolerance)
    missing_bmi = valid & b.isna()
    to_fix = inconsistent | missing_bmi
    if to_fix.any():
        out.loc[to_fix, bmi_col] = expected.loc[to_fix].round(1)
    report = {
        "checked": True,
        "heightColumn": height_col,
        "weightColumn": weight_col,
        "bmiColumn": bmi_col,
        "tolerance": tolerance,
        "formula": "BMI = weight_kg / (height_m^2), height_m = height_cm / 100",
        "inconsistentRecords": int(inconsistent.sum()),
        "missingBmiFilled": int(missing_bmi.sum()),
        "correctedRecords": int(to_fix.sum()),
        "correction": "Derived BMI recalculated from final validated height and weight when inconsistent or missing.",
    }
    return out, report


def _normalise_clinical_config(config: dict[str, Any]) -> str:
    profile = str(config.get("generationProfile") or "Standard")
    if profile not in CLINICAL_PROFILES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown generation profile: {profile!r}.",
        )
    config["generationProfile"] = profile
    for key in ("clinicalVariables", "referenceOverrides", "diseaseRules"):
        config[key] = _dict_list(config.get(key))
    config["enforceStrictSchema"] = bool(config.get("enforceStrictSchema", False))
    config["maxSamplingAttempts"] = int(config.get("maxSamplingAttempts") or 4)
    config["sourcePreservingMode"] = bool(config.get("sourcePreservingMode"))
    config["ageToleranceYears"] = _age_tolerance(config)
    for key in ("numericTolerance", "numericTolerancePercent"):
        if config.get(key) is not None:
            config[key] = _finite_number(config[key])
    for key in ("numericTolerances", "sourceValueTolerances"):
        values = config.get(key) or {}
        if isinstance(values, dict):
            config[key] = {
                str(name): _finite_number(value) for name, value in values.items() if _finite_number(value) is not None
            }
    return profile


def _prepare_clinical_config(
    source: SynthMedSourceDataset, config: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    profile = _normalise_clinical_config(config)

    storage = SynthMedStorageService(settings)
    frame = read_source_dataframe(storage.resolve_source(source.stored_path), source.file_format)
    medical = medical_schema_service.profile_medical_schema(frame)
    allowed = [str(column) for column in medical["approvedOutputColumns"]]
    requested = [str(column) for column in (config.get("approvedOutputColumns") or allowed)]
    approved = [column for column in allowed if column in requested]
    if not approved:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "No medical output columns remain. Synthetic output requires at least one age, gender, disease "
                "or clinical measurement column."
            ),
        )

    variables = config["clinicalVariables"]
    variable_columns = [str(item.get("column") or "") for item in variables if item.get("enabled", True)]
    missing_variables = [column for column in variable_columns if column and column not in approved]
    if missing_variables:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Clinical variables must use approved output columns: " + ", ".join(missing_variables),
        )

    subset = frame.loc[:, approved]
    schema_validation = medical_schema_service.validate_strict_output_schema(
        subset,
        approved_columns=approved,
        identifier_columns=medical["excludedIdentifierColumns"],
    )
    if not schema_validation["passed"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Strict output schema validation failed: " + "; ".join(schema_validation["errors"]),
        )

    configured_identifiers = [str(item) for item in (config.get("identifierColumns") or [])]
    identifiers = sorted(set(configured_identifiers) | set(medical["excludedIdentifierColumns"]))
    config["approvedOutputColumns"] = approved
    config["selectedColumns"] = approved
    config["identifierColumns"] = identifiers
    config["clinicalSchemaValidation"] = schema_validation
    config["excludedOutputColumns"] = [column for column in requested if column not in approved]
    return {
        "generationProfile": profile,
        "strictSchema": True,
        "schemaValidation": schema_validation,
        "medicalProfile": medical,
        "approvedOutputColumns": approved,
        "excludedOutputColumns": config["excludedOutputColumns"],
    }


def _upsert_report(
    db: Session,
    *,
    job: SynthMedGenerationJob,
    generated_id: str,
    report_type: str,
    method: str,
    score: float | None,
    payload: dict[str, Any],
    file_path: str,
) -> SynthMedEvaluationReport:
    report = db.scalar(
        select(SynthMedEvaluationReport).where(
            SynthMedEvaluationReport.job_id == job.id,
            SynthMedEvaluationReport.report_type == report_type,
        )
    )
    if report is None:
        report = SynthMedEvaluationReport(
            id=str(uuid4()),
            job_id=job.id,
            generated_dataset_id=generated_id,
            owner_id=job.owner_id,
            report_type=report_type,
            method=method,
        )
        db.add(report)
    report.method = method
    report.score = json_safe(score)
    report.report_json = json_safe(payload)
    report.file_path = file_path
    return report


def analyse_source(db: Session, source: SynthMedSourceDataset, settings: Settings) -> dict[str, Any]:
    storage = SynthMedStorageService(settings)
    path = storage.resolve_source(source.stored_path)
    frame = read_source_dataframe(path, source.file_format)
    analysis = analyse_dataframe(frame)
    return {
        "sourceDatasetId": source.id,
        "datasetName": source.dataset_name,
        "originalFilename": source.original_filename,
        **json_safe(analysis),
        "generationReady": analysis["totalRecords"] >= 10 and analysis["totalColumns"] >= 2,
        "guidance": (
            "Review identifier and column types before starting CTGAN generation."
            if analysis["totalRecords"] >= 10 and analysis["totalColumns"] >= 2
            else "CTGAN needs at least 10 records and 2 columns for meaningful training."
        ),
    }


def start_generation_job(
    db: Session,
    *,
    source: SynthMedSourceDataset,
    config: dict[str, Any],
    user: User,
    settings: Settings,
    request: Request | None = None,
) -> SynthMedGenerationJob:
    model = condition_service.normalize_model(config.get("model"))
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown synthesis model: {config.get('model')!r}.",
        )
    _validate_config(config, settings, model)

    requested_conditions = config.get("conditions") or []
    requested_mode = str(config.get("generationMode") or "Unconditional")
    if requested_mode == "Conditional" and not requested_conditions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Conditional generation requires at least one condition.",
        )
    mode = "Conditional" if requested_conditions else "Unconditional"
    config = dict(config)
    clinical_setup = _prepare_clinical_config(source, config, settings)
    config["clinicalSetup"] = clinical_setup

    storage = SynthMedStorageService(settings)
    frame = read_source_dataframe(storage.resolve_source(source.stored_path), source.file_format)
    prepared_for_plan = prepare_dataframe(frame, config)

    validation: dict[str, Any] = {
        "valid": True,
        "model": model,
        "capabilities": condition_service.CAPABILITIES[model].as_dict(),
        "normalizedConditions": [],
        "samplingPlan": [],
        "errors": [],
        "warnings": [],
    }
    normalized_conditions: list[dict[str, Any]] = []
    sampling_plan: list[dict[str, Any]] = []
    if requested_conditions:
        validation = condition_service.validate_conditions(source=source, config=config, settings=settings)
        if not validation["valid"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Condition validation failed: " + "; ".join(validation["errors"]),
            )
        normalized_conditions = list(validation["normalizedConditions"])
        sampling_plan = list(validation["samplingPlan"])

    preservation_plan = _source_preservation_plan(
        frame,
        prepared_for_plan,
        config,
        int(config["recordCount"]),
        normalized_conditions,
    )
    public_plan = {
        key: value
        for key, value in preservation_plan.items()
        if key not in {"anchors", "rows", "sourceRowIndices"}
    }
    config["sourcePreservationPlan"] = json_safe(public_plan)
    config["sourcePreservationPlanInternal"] = preservation_plan

    config["model"] = model
    config["generationMode"] = mode
    config["selectedModel"] = model
    config["normalizedConditions"] = json_safe(normalized_conditions)
    config["samplingPlan"] = json_safe(sampling_plan)
    config["conditionValidation"] = json_safe(validation)
    config["sourcePreservingMode"] = bool(config.get("sourcePreservingMode"))
    config["ageToleranceYears"] = _age_tolerance(config)

    job = SynthMedGenerationJob(
        id=str(uuid4()),
        owner_id=user.id,
        source_dataset_id=source.id,
        status="Queued",
        model_name=condition_service.MODEL_LABELS[model],
        generation_mode=mode,
        selected_model=model,
        epochs=int(config["epochs"]),
        batch_size=int(config["batchSize"]),
        seed=config.get("seed"),
        requested_record_count=int(config["recordCount"]),
        generated_record_count=0,
        normalized_conditions_json=json_safe(normalized_conditions),
        condition_validation_json=json_safe(validation),
        config_json=json_safe(config),
    )
    generation_config = SynthMedGenerationConfig(
        id=str(uuid4()),
        job_id=job.id,
        owner_id=user.id,
        config_json=json_safe(config),
    )
    db.add(job)
    db.add(generation_config)
    db.flush()
    snapshot = versioning_service.snapshot_config(db, user=user, job=job)
    db.add(snapshot)
    log_audit(
        db,
        action="synthmed.generation_started",
        resource_type="synthmed_generation_job",
        resource_id=job.id,
        actor_id=user.id,
        details={
            "source_dataset_id": source.id,
            "model": model,
            "generation_mode": mode,
            "generation_profile": config.get("generationProfile", "Standard"),
            "condition_count": len(normalized_conditions),
            "epochs": job.epochs,
            "batch_size": job.batch_size,
            "record_count": job.requested_record_count,
            "configuration_snapshot_id": snapshot.id,
        },
        request=request,
    )
    db.commit()
    db.refresh(job)

    factory = _session_factory(db)
    if settings.synthmed_generation_inline:
        run_generation_job(job.id, settings, factory)
        db.refresh(job)
    else:
        _executor_for(settings).submit(run_generation_job, job.id, settings, factory)
    return job


def _scale_sampling_plan(plan: list[dict[str, Any]], rows: int) -> list[dict[str, Any]]:
    if not plan:
        return []
    total = sum(int(cohort.get("numRows") or 0) for cohort in plan) or 1
    remaining = rows
    scaled: list[dict[str, Any]] = []
    for index, cohort in enumerate(plan):
        if index == len(plan) - 1:
            cohort_rows = remaining
        else:
            proportional = max(1, round(int(cohort.get("numRows") or 0) * rows / total))
            reserve = len(plan) - index - 1
            cohort_rows = min(proportional, max(1, remaining - reserve))
        cohort_rows = max(1, cohort_rows)
        remaining -= cohort_rows
        scaled.append({**cohort, "numRows": cohort_rows})
    return scaled


def _sample_batch(
    synthesizer: Any,
    *,
    model: str,
    mode: str,
    sampling_plan: list[dict[str, Any]],
    rows: int,
) -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if mode == "Conditional":
            conditions = condition_service.build_sdv_conditions(_scale_sampling_plan(sampling_plan, rows))
            sampled = synthesizer.sample_from_conditions(conditions=conditions)
        else:
            sampled = synthesizer.sample(num_rows=rows)
    return sampled[TABLE_NAME] if isinstance(sampled, dict) else sampled


def _rejection_sample(
    synthesizer: Any,
    *,
    model: str,
    mode: str,
    sampling_plan: list[dict[str, Any]],
    requested_rows: int,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    profile = str(config.get("generationProfile") or "Standard")
    if profile == "Standard":
        synthetic = _sample_batch(
            synthesizer,
            model=model,
            mode=mode,
            sampling_plan=sampling_plan,
            rows=requested_rows,
        )
        return synthetic, {
            "method": "No clinical rejection sampling for the Standard profile",
            "attempts": 1,
            "sampledRecords": int(len(synthetic)),
            "acceptedRecords": int(len(synthetic)),
            "rejectedRecords": 0,
            "rejectionCounts": {},
        }

    max_attempts = int(config.get("maxSamplingAttempts") or 4)
    variables = config.get("clinicalVariables") or []
    overrides = config.get("referenceOverrides") or []
    disease_rules = config.get("diseaseRules") or []
    accepted_parts: list[pd.DataFrame] = []
    accepted_rows = 0
    sampled_rows = 0
    rejected_rows = 0
    attempts = 0
    rejection_counts: dict[str, int] = {}

    while accepted_rows < requested_rows and attempts < max_attempts:
        attempts += 1
        needed = requested_rows - accepted_rows
        batch = _sample_batch(
            synthesizer,
            model=model,
            mode=mode,
            sampling_plan=sampling_plan,
            rows=needed,
        )
        sampled_rows += int(len(batch))
        report = clinical_reference_service.validate_clinical_records(
            batch,
            generation_profile=profile,
            clinical_variables=variables,
            overrides=overrides,
            disease_rules=disease_rules,
        )
        failures = report.get("_mandatoryFailures") or []
        mask = pd.Series([bool(value) for value in failures], index=batch.index)
        rejected_rows += int(mask.sum())
        for key, value in (report.get("classificationCounts") or {}).items():
            if key in {"implausible", "invalid", "unverified"} or (
                profile == "NormalRange" and key == "abnormal_plausible"
            ):
                rejection_counts[key] = rejection_counts.get(key, 0) + int(value or 0)
        accepted = batch.loc[~mask]
        if not accepted.empty:
            accepted_parts.append(accepted)
            accepted_rows += int(len(accepted))

    rejection_report = {
        "method": "Bounded rejection sampling against documented clinical references",
        "generationProfile": profile,
        "attempts": attempts,
        "maxAttempts": max_attempts,
        "sampledRecords": sampled_rows,
        "acceptedRecords": accepted_rows,
        "rejectedRecords": rejected_rows,
        "rejectionCounts": rejection_counts,
        "limitations": clinical_reference_service.CLINICAL_LIMITATIONS,
    }
    if accepted_rows < requested_rows:
        raise RuntimeError(
            "Clinical validation could not produce the requested record count "
            f"({accepted_rows}/{requested_rows}) within {max_attempts} sampling attempts: "
            f"{json.dumps(json_safe(rejection_report), ensure_ascii=False)}"
        )
    synthetic = pd.concat(accepted_parts, ignore_index=True).iloc[:requested_rows].reset_index(drop=True)
    return synthetic, rejection_report


def _validate_synthetic_frame(
    *,
    synthetic: pd.DataFrame,
    prepared: dict[str, Any],
    config: dict[str, Any],
    plan: dict[str, Any],
    normalized_conditions: list[dict[str, Any]],
    sampling_plan: list[dict[str, Any]],
    requested_record_count: int,
    anchor_meta: dict[str, Any] | None = None,
    source_alignment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings_list: list[str] = []
    expected_columns = [str(column) for column in config.get("approvedOutputColumns") or prepared["frame"].columns]

    if list(synthetic.columns) != expected_columns:
        failures.append(
            f"Output schema differs from approved schema: expected {expected_columns}, "
            f"received {list(synthetic.columns)}."
        )
    if len(synthetic) != requested_record_count:
        failures.append(
            f"Generated record count {len(synthetic)} does not match requested {requested_record_count}."
        )

    duplicate_rows = int(synthetic.duplicated().sum())
    conditional = bool(normalized_conditions)
    if duplicate_rows and not bool(plan.get("enabled")) and not conditional:
        failures.append(f"Generated dataset contains {duplicate_rows} duplicate record(s).")
    elif duplicate_rows:
        warnings_list.append(
            f"Generated dataset contains {duplicate_rows} duplicate record(s); "
            "accepted because generation used constrained sampling/validation."
        )

    missing_counts = {
        str(column): int(count) for column, count in synthetic.isna().sum().items() if int(count) > 0
    }
    if missing_counts and not bool(config.get("preserveMissingness", True)):
        failures.append("Missing values were introduced while preserveMissingness is disabled.")
    elif missing_counts:
        warnings_list.append(
            "Missing values were preserved from source/model behavior; "
            "no medical-value imputation was applied."
        )

    identifier_check = medical_schema_service.validate_strict_output_schema(
        synthetic,
        approved_columns=expected_columns,
        identifier_columns=list(config.get("identifierColumns") or []),
    )
    if not identifier_check["passed"]:
        failures.extend([str(item) for item in identifier_check.get("errors", [])])
    # Strict schema: final frame must be only approved columns in approved order.
    if identifier_check["passed"] and list(synthetic.columns) != expected_columns:
        synthetic_cols = [c for c in expected_columns if c in synthetic.columns]
        extra = [c for c in synthetic.columns if c not in expected_columns]
        if extra:
            failures.append("Unexpected non-approved columns present in synthetic output: " + ", ".join(extra))
        elif synthetic_cols == expected_columns:
            pass

    mapping = _column_mapping(config, list(synthetic.columns))
    for key, label in (("gender", "Gender"), ("disease", "Disease"), ("disease_level", "Disease_Level")):
        resolved = mapping.get(key) or _resolve_column(list(synthetic.columns), label)
        if not resolved or resolved not in synthetic.columns:
            continue
        allowed = _categorical_reference_values(prepared["frame"], config, resolved)
        if not allowed:
            continue
        actual = synthetic[resolved].dropna().astype("string").unique().tolist()
        unexpected = sorted(set(actual) - set(allowed))
        if unexpected:
            failures.append(f"Unexpected categories for {resolved}: {unexpected}")

    age_column = _resolve_age_column(list(synthetic.columns), config)
    age_bounds = _age_bounds(config, prepared["frame"], age_column)
    if age_column and age_column in synthetic.columns:
        numeric_age = pd.to_numeric(synthetic[age_column], errors="coerce")
        invalid_age = synthetic.loc[numeric_age.isna() | (numeric_age % 1 != 0)]
        if not invalid_age.empty:
            failures.append(f"Age column '{age_column}' contains non-integer or missing values.")
        below = int((numeric_age < age_bounds[0]).sum())
        above = int((numeric_age > age_bounds[1]).sum())
        if below or above:
            failures.append(
                f"Age column '{age_column}' contains values outside source bounds [{age_bounds[0]}, {age_bounds[1]}]."
            )

    alignment = source_alignment or dict((anchor_meta or {}).get("alignment") or {})
    if plan.get("enabled"):
        if alignment:
            failures.extend([str(item) for item in alignment.get("failures") or []])
        else:
            tolerance = int(plan.get("ageToleranceYears", _age_tolerance(config)))
            deviations = list((anchor_meta or {}).get("ageDeviations") or [])
            if age_column and anchor_meta is not None and len(deviations) != len(synthetic):
                failures.append("Source-preserving age deviations could not be evaluated for every generated record.")
            if deviations and any(int(value) > tolerance for value in deviations):
                failures.append(f"Generated ages exceeded the configured tolerance of +/-{tolerance} years.")
            mismatch_total = sum(
                int(value) for value in dict((anchor_meta or {}).get("categoryMismatches") or {}).values()
            )
            if mismatch_total:
                failures.append(f"Source-preserving categorical mismatches detected: {mismatch_total}.")
            failures.extend([str(item) for item in ((anchor_meta or {}).get("failures") or [])])

    measurement_issues: list[str] = []
    mapping = _column_mapping(config, list(synthetic.columns))
    gender_col = mapping.get("gender")
    disease_col = mapping.get("disease")
    disease_level_col = mapping.get("disease_level")
    for column in synthetic.columns:
        if column in {age_column, gender_col, disease_col, disease_level_col}:
            continue
        if pd.api.types.is_numeric_dtype(
            prepared["frame"].get(column, pd.Series(dtype="float64"))
        ) or pd.api.types.is_numeric_dtype(synthetic[column]):
            numeric = pd.to_numeric(synthetic[column], errors="coerce")
            if numeric.notna().any() and (numeric.dropna() < 0).any():
                measurement_issues.append(f"{column}: negative values are not allowed.")

    sbp = mapping.get("systolic_bp")
    dbp = mapping.get("diastolic_bp")
    if sbp and dbp:
        s = pd.to_numeric(synthetic[sbp], errors="coerce")
        d = pd.to_numeric(synthetic[dbp], errors="coerce")
        invalid_bp = int(((s.notna()) & (d.notna()) & (s <= d)).sum())
        if invalid_bp:
            measurement_issues.append(f"{sbp}/{dbp}: systolic must be greater than diastolic ({invalid_bp} rows).")

    # Documented measurement constraints (no invented clinical rules; preserve abnormal-but-plausible).
    measurement_constraints: dict[str, tuple[float, float]] = {
        "Systolic_BP": (40, 300),
        "Diastolic_BP": (20, 200),
        "Heart_Rate": (20, 300),
        "Respiratory_Rate": (4, 80),
        "SpO2": (50, 100),
        "BMI": (8, 90),
    }
    profile_columns = (
        (config.get("clinicalSetup") or {}).get("medicalProfile")
        or config.get("medicalProfile")
        or {}
    ).get("columns", [])
    for item in profile_columns if isinstance(profile_columns, list) else []:
        if not isinstance(item, dict):
            continue
        col = str(item.get("originalName") or "")
        measurement = str(item.get("measurement") or item.get("standardisedName") or "")
        if not col or col not in synthetic.columns or measurement not in measurement_constraints:
            continue
        low, high = measurement_constraints[measurement]
        vals = pd.to_numeric(synthetic[col], errors="coerce")
        bad = int((vals.notna() & ((vals < low) | (vals > high))).sum())
        if bad:
            measurement_issues.append(
                f"{col}: {bad} value(s) outside documented plausibility envelope {low}-{high} for {measurement}."
            )

    height_col = _resolve_column(list(synthetic.columns), "Height_cm", "Height", "height_cm")
    weight_col = _resolve_column(list(synthetic.columns), "Weight_kg", "Weight", "weight_kg")
    bmi_col = _resolve_column(list(synthetic.columns), "BMI", "Body_Mass_Index", "bmi")
    bmi_report: dict[str, Any] = {"checked": False}
    if height_col and weight_col and bmi_col:
        h = pd.to_numeric(synthetic[height_col], errors="coerce")
        w = pd.to_numeric(synthetic[weight_col], errors="coerce")
        b = pd.to_numeric(synthetic[bmi_col], errors="coerce")
        height_m = h / 100.0
        expected = w / (height_m * height_m)
        valid_mask = h.notna() & w.notna() & b.notna() & (h > 0) & (w > 0)
        delta = (b - expected).abs()
        tolerance = 0.1  # documented rounding tolerance for BMI consistency checks
        inconsistent_mask = valid_mask & (delta > tolerance)
        inconsistent = int(inconsistent_mask.sum())
        bmi_report = {
            "checked": True,
            "heightColumn": height_col,
            "weightColumn": weight_col,
            "bmiColumn": bmi_col,
            "tolerance": tolerance,
            "inconsistentRecords": inconsistent,
            "formula": "BMI = weight_kg / (height_m^2), height_m = height_cm / 100",
            "correction": "none",
        }
        if inconsistent:
            measurement_issues.append(
                f"{bmi_col}: {inconsistent} record(s) inconsistent with height/weight beyond tolerance {tolerance}."
            )
    failures.extend(measurement_issues)

    satisfaction = {
        "method": "Not applicable to unconditional generation",
        "conditional": False,
        "passed": True,
        "combined": {"satisfactionPercentage": 100.0, "totalGeneratedRecords": int(len(synthetic))},
        "limitations": ["No conditions were requested for this generation job."],
    }
    if normalized_conditions and len(synthetic) == requested_record_count:
        satisfaction = condition_service.evaluate_condition_satisfaction(
            synthetic, normalized_conditions, sampling_plan, requested_record_count
        )
        if not satisfaction["passed"]:
            failures.append("Requested conditional constraints were not satisfied by the final synthetic dataset.")

    return {
        "passed": not failures,
        "failures": failures,
        "warnings": warnings_list,
        "duplicateRecords": duplicate_rows,
        "missingCounts": missing_counts,
        "schemaValidation": identifier_check,
        "ageBounds": {"min": age_bounds[0], "max": age_bounds[1]},
        "bmiConsistency": bmi_report,
        "conditionSatisfaction": satisfaction,
        "sourceAlignment": alignment or None,
    }


def _build_source_preservation_report(
    *,
    source: pd.DataFrame,
    synthetic: pd.DataFrame,
    config: dict[str, Any],
    plan: dict[str, Any],
    anchor_meta: dict[str, Any] | None,
    validation: dict[str, Any],
    rejection_report: dict[str, Any] | None = None,
    source_alignment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enabled = bool(plan.get("enabled"))
    strict = enabled and bool(plan.get("strict"))
    age_column = plan.get("ageColumn")
    tolerance = int(plan.get("ageToleranceYears", _age_tolerance(config)))
    report: dict[str, Any] = {
        "method": (
            "Strict one-to-one source row preservation"
            if strict
            else "Source anchor preservation and population distribution comparison"
        ),
        "enabled": enabled,
        "strict": strict,
        "mode": "Strict Source-Preserving Mode" if strict else ("Source-Preserving Mode" if enabled else "Disabled"),
        "ageToleranceYears": tolerance,
        "ageColumn": age_column,
        "ageBounds": plan.get("ageBounds") or {},
        "notes": [
            "Record-level constraint satisfaction and population-level distribution similarity "
            "are reported separately.",
            "Clinical plausibility is assessed by clinical/schema validation, not by distribution similarity alone.",
            "Source anchors and source row identifiers are internal only and are never exported.",
        ],
    }
    if not enabled:
        report["limitations"] = ["Source-Preserving Mode was disabled for this generation job."]
        report["validationFailures"] = validation.get("failures", [])
        report["validationWarnings"] = validation.get("warnings", [])
        return report

    alignment = dict(source_alignment or (anchor_meta or {}).get("alignment") or {})
    if strict:
        restoration_counts = dict((anchor_meta or {}).get("sourceValueRestorations") or {})
        record_validation = {
            "status": str(alignment.get("status") or ("Passed" if alignment.get("passed") else "Failed")),
            "sourceRecordCount": int(alignment.get("sourceRowCount", 0) or 0),
            "generatedRecordCount": int(alignment.get("generatedRecordCount", 0) or 0),
            "genderMismatchCount": int(alignment.get("genderMismatchCount", 0) or 0),
            "ageViolationCount": int(alignment.get("ageViolationCount", 0) or 0),
            "diseaseMismatchCount": int(alignment.get("diseaseMismatchCount", 0) or 0),
            "diseaseLevelMismatchCount": int(alignment.get("diseaseLevelMismatchCount", 0) or 0),
            "numericViolations": dict(alignment.get("numericViolations") or {}),
            "missingRecordCount": int(alignment.get("missingRecordCount", 0) or 0),
            "extraRecordCount": int(alignment.get("extraRecordCount", 0) or 0),
            "rowOrderMismatchCount": int(alignment.get("rowOrderMismatchCount", 0) or 0),
            "failures": list(alignment.get("failures") or []),
        }
        report.update(
            {
                "sourceRecordCount": int(plan.get("sourceRecordCount", 0) or 0),
                "generatedRecordCount": int(alignment.get("generatedRecordCount", len(synthetic)) or len(synthetic)),
                "selectedSourceRecordCount": int(plan.get("selectedSourceRowCount", len(synthetic)) or len(synthetic)),
                "genderMismatchCount": record_validation["genderMismatchCount"],
                "ageViolationCount": record_validation["ageViolationCount"],
                "diseaseMismatchCount": record_validation["diseaseMismatchCount"],
                "diseaseLevelMismatchCount": record_validation["diseaseLevelMismatchCount"],
                "numericViolations": record_validation["numericViolations"],
                "numericViolationCount": int(alignment.get("numericViolationCount", 0) or 0),
                "missingRecordCount": record_validation["missingRecordCount"],
                "extraRecordCount": record_validation["extraRecordCount"],
                "rowOrderMismatchCount": record_validation["rowOrderMismatchCount"],
                "duplicateRecords": int(validation.get("duplicateRecords", 0) or 0),
                "sourceValueRestorations": restoration_counts,
                "restoredValueCount": int(sum(restoration_counts.values())),
                "recordLevelValidation": record_validation,
                "status": record_validation["status"],
                "numericTolerances": dict(plan.get("numericTolerances") or {}),
            }
        )

    deviations = [
        int(value)
        for value in (alignment.get("ageDeviations") or (anchor_meta or {}).get("ageDeviations") or [])
    ]
    age_source = (
        pd.to_numeric(source.get(age_column), errors="coerce").dropna()
        if age_column
        else pd.Series(dtype=float)
    )
    age_synth = (
        pd.to_numeric(synthetic.get(age_column), errors="coerce").dropna()
        if age_column
        else pd.Series(dtype=float)
    )
    report["originalAgeDistribution"] = _numeric_distribution(age_source)
    report["generatedAgeDistribution"] = _numeric_distribution(age_synth)
    report["ageDeviation"] = {
        "count": len(deviations),
        "min": min(deviations) if deviations else None,
        "max": max(deviations) if deviations else None,
        "mean": round(sum(deviations) / len(deviations), 3) if deviations else None,
        "median": float(np.median(deviations)) if deviations else None,
    }
    within = sum(1 for value in deviations if value <= tolerance)
    report["ageWithinTolerance"] = {
        "count": within,
        "total": len(deviations),
        "percentage": round(within / len(deviations) * 100, 2) if deviations else 0.0,
        "toleranceYears": tolerance,
    }

    def _category_report(column: str | None, label: str) -> dict[str, Any]:
        if not column or column not in source.columns or column not in synthetic.columns:
            return {"available": False, "column": column}
        src_dist = _distribution(source[column].dropna().astype("string").tolist())
        syn_dist = _distribution(synthetic[column].dropna().astype("string").tolist())
        src_keys = set(src_dist["counts"])
        syn_keys = set(syn_dist["counts"])
        return {
            "available": True,
            "column": column,
            "label": label,
            "original": src_dist,
            "generated": syn_dist,
            "unexpectedCategories": sorted(syn_keys - src_keys),
            "missingCategories": sorted(src_keys - syn_keys),
            "mismatchCount": int(
                alignment.get(
                    {
                        "Gender": "genderMismatchCount",
                        "Disease": "diseaseMismatchCount",
                        "Disease_Level": "diseaseLevelMismatchCount",
                    }.get(label, ""),
                    0,
                )
                or ((anchor_meta or {}).get("categoryMismatches") or {}).get(column, 0)
                or 0
            ),
        }

    report["genderPreservation"] = _category_report(plan.get("genderColumn"), "Gender")
    report["diseasePreservation"] = _category_report(plan.get("diseaseColumn"), "Disease")
    report["diseaseLevelPreservation"] = _category_report(plan.get("diseaseLevelColumn"), "Disease_Level")

    measurement_diffs: list[dict[str, Any]] = []
    for column in synthetic.columns:
        if column in {age_column, plan.get("genderColumn"), plan.get("diseaseColumn"), plan.get("diseaseLevelColumn")}:
            continue
        if not pd.api.types.is_numeric_dtype(source.get(column, pd.Series(dtype="float64"))):
            continue
        if not pd.api.types.is_numeric_dtype(synthetic.get(column, pd.Series(dtype="float64"))):
            continue
        src = pd.to_numeric(source[column], errors="coerce").dropna()
        syn = pd.to_numeric(synthetic[column], errors="coerce").dropna()
        if src.empty or syn.empty:
            continue
        measurement_diffs.append(
            {
                "column": column,
                "sourceMean": json_safe(float(src.mean())),
                "generatedMean": json_safe(float(syn.mean())),
                "meanDelta": json_safe(float(syn.mean() - src.mean())),
                "sourceStd": json_safe(float(src.std(ddof=0))),
                "generatedStd": json_safe(float(syn.std(ddof=0))),
            }
        )
    report["medicalMeasurementDistributionDifferences"] = measurement_diffs[:25]
    bmi_report = validation.get("bmiConsistency") or {}
    report["heightWeightBmiConsistency"] = {
        "checked": bool(bmi_report.get("checked")),
        "formula": bmi_report.get("formula"),
        "tolerance": bmi_report.get("tolerance"),
        "inconsistentRecords": int(bmi_report.get("inconsistentRecords", 0) or 0),
        "correctedRecords": int(bmi_report.get("correctedRecords", 0) or 0),
        "missingBmiFilled": int(bmi_report.get("missingBmiFilled", 0) or 0),
    }
    report["missingValues"] = {
        "source": {str(c): int(v) for c, v in source.isna().sum().items() if int(v) > 0},
        "generated": dict(validation.get("missingCounts") or {}),
    }
    rejection = dict(rejection_report or {})
    strict_rejections = int((anchor_meta or {}).get("rejectedCandidateRecords", 0) or 0) if strict else 0
    strict_attempts = int((anchor_meta or {}).get("regenerationAttempts", 0) or 0) if strict else 0
    report["rejectedRecordCount"] = int(rejection.get("rejectedRecords", 0) or 0) + strict_rejections
    report["regenerationAttempts"] = int(rejection.get("attempts", 0) or 0) + strict_attempts
    report["acceptedBatchCount"] = int(rejection.get("acceptedRecords", 0) or 0)
    report["validationFailures"] = validation.get("failures", [])
    report["validationWarnings"] = validation.get("warnings", [])
    report["privacyEvaluationWarning"] = (
        "Source anchoring can increase record-level similarity and privacy risk; "
        "review P3/privacy screening before release. "
        "This report does not claim anonymity."
    )
    return report


def run_generation_job(
    job_id: str, settings: Settings, factory: sessionmaker[Session] | None = None
) -> SynthMedGenerationJob | None:
    session_factory = factory or SessionLocal
    with session_factory() as db:
        job = db.get(SynthMedGenerationJob, job_id)
        if job is None or job.status in TERMINAL_STATUSES:
            return job
        try:
            model = condition_service.normalize_model(job.selected_model or job.config_json.get("model")) or "CTGAN"
            model_label = condition_service.MODEL_LABELS[model]
            mode = job.generation_mode or str(job.config_json.get("generationMode") or "Unconditional")
            normalized_conditions = list(
                job.normalized_conditions_json or job.config_json.get("normalizedConditions") or []
            )
            sampling_plan = list(job.config_json.get("samplingPlan") or [])
            if mode == "Conditional":
                sampling_plan = condition_service.build_sampling_plan(normalized_conditions, job.requested_record_count)
            _status(job, "Preprocessing", started_at=job.started_at or _now())
            db.commit()

            storage = SynthMedStorageService(settings)
            source = db.get(SynthMedSourceDataset, job.source_dataset_id)
            if source is None:
                raise RuntimeError("Source dataset no longer exists.")
            source_path = storage.resolve_source(source.stored_path)
            frame = read_source_dataframe(source_path, source.file_format)
            prepared = prepare_dataframe(frame, job.config_json)
            preservation_plan = dict(
                job.config_json.get("sourcePreservationPlanInternal")
                or _source_preservation_plan(
                    frame,
                    prepared,
                    job.config_json,
                    int(job.requested_record_count),
                    normalized_conditions,
                )
            )

            preprocessing_path = _save_report(storage, job.id, "preprocessing_report.json", prepared["report"])
            metadata_path = _save_report(storage, job.id, "metadata.json", prepared["metadataDict"])

            _status(job, "Training")
            db.commit()
            if settings.environment == "test":
                torch.set_num_threads(1)
            _set_seed(job.seed)
            synthesizer_class = condition_service.MODEL_CLASSES[model]
            synthesizer_kwargs: dict[str, Any] = {}
            if model in {"CTGAN", "TVAE"}:
                synthesizer_kwargs.update(
                    {"epochs": job.epochs, "batch_size": job.batch_size, "enable_gpu": False, "verbose": False}
                )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                synthesizer = synthesizer_class(prepared["metadata"], **synthesizer_kwargs)
            training_started = time.perf_counter()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                synthesizer.fit({TABLE_NAME: prepared["frame"]})
            training_duration = time.perf_counter() - training_started

            model_path, model_relative = storage.save_report(job.id, f"{model.lower()}_model.pkl", b"")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                synthesizer.save(str(model_path))

            _status(job, "Generating")
            db.commit()
            profile = str(job.config_json.get("generationProfile") or "Standard")
            rng = np.random.default_rng(job.seed if job.seed is not None else None)
            source_preserving = bool(job.config_json.get("sourcePreservingMode"))
            generated_parts: list[pd.DataFrame] = []
            anchor_meta_accum: dict[str, Any] = {
                "ageDeviations": [],
                "ageWithinTolerance": 0,
                "categoryMismatches": defaultdict(int),
                "failures": [],
                "selectedAnchorCount": 0,
                "sourceValueRestorations": defaultdict(int),
                "rejectedCandidateRecords": 0,
                "regenerationAttempts": 0,
            }
            source_row_cursor = 0
            rejection_report: dict[str, Any] = {
                "method": "Not applied",
                "generationProfile": profile,
                "attempts": 0,
                "sampledRecords": 0,
                "acceptedRecords": 0,
                "rejectedRecords": 0,
                "rejectionCounts": {},
            }
            max_attempts = max(1, int(job.config_json.get("maxSamplingAttempts") or 4))
            remaining = int(job.requested_record_count)
            attempts = 0
            while remaining > 0 and attempts < max_attempts:
                attempts += 1
                synthetic_batch, batch_rejection = _rejection_sample(
                    synthesizer,
                    model=model,
                    mode=mode,
                    sampling_plan=sampling_plan,
                    requested_rows=remaining,
                    config=job.config_json,
                )
                rejection_report["attempts"] = (
                    int(rejection_report.get("attempts", 0)) + int(batch_rejection.get("attempts", 0))
                )
                rejection_report["sampledRecords"] = (
                    int(rejection_report.get("sampledRecords", 0)) + int(batch_rejection.get("sampledRecords", 0))
                )
                rejection_report["rejectedRecords"] = (
                    int(rejection_report.get("rejectedRecords", 0))
                    + int(batch_rejection.get("rejectedRecords", 0))
                )
                for key, value in (batch_rejection.get("rejectionCounts") or {}).items():
                    rejection_report["rejectionCounts"][key] = (
                        int(rejection_report["rejectionCounts"].get(key, 0)) + int(value or 0)
                    )

                expected_columns = list(prepared["frame"].columns)
                if list(synthetic_batch.columns) != expected_columns:
                    raise RuntimeError(
                        f"{model_label} output schema differs from the prepared training schema: "
                        f"expected {expected_columns}, received {list(synthetic_batch.columns)}."
                    )

                batch_anchor_meta = None
                if source_preserving:
                    synthetic_batch, batch_anchor_meta = _apply_source_preservation(
                        synthetic_batch,
                        plan=preservation_plan,
                        config=job.config_json,
                        rng=rng,
                        normalized_conditions=normalized_conditions,
                        row_start=source_row_cursor,
                    )
                synthetic_batch, bmi_correction = _enforce_bmi_consistency(synthetic_batch, job.config_json)

                batch_plan = (
                    _scale_sampling_plan(sampling_plan, len(synthetic_batch))
                    if mode == "Conditional"
                    else sampling_plan
                )
                batch_validation = _validate_synthetic_frame(
                    synthetic=synthetic_batch,
                    prepared=prepared,
                    config=job.config_json,
                    plan=preservation_plan,
                    normalized_conditions=normalized_conditions,
                    sampling_plan=batch_plan,
                    requested_record_count=len(synthetic_batch),
                    anchor_meta=batch_anchor_meta if source_preserving else None,
                )
                batch_validation["bmiConsistency"] = bmi_correction
                if batch_validation["passed"]:
                    candidate = synthetic_batch.reset_index(drop=True)
                    if source_preserving:
                        new_rows = candidate
                    elif generated_parts:
                        existing = pd.concat(generated_parts, ignore_index=True)
                        combined = pd.concat([existing, candidate], ignore_index=True)
                        deduped = combined.drop_duplicates().reset_index(drop=True)
                        new_rows = deduped.iloc[len(existing):].reset_index(drop=True)
                    else:
                        new_rows = candidate.drop_duplicates().reset_index(drop=True)
                    if new_rows.empty:
                        rejection_report["rejectedRecords"] = (
                            int(rejection_report.get("rejectedRecords", 0)) + len(candidate)
                        )
                        rejection_report["rejectionCounts"]["duplicate_records"] = (
                            int(rejection_report["rejectionCounts"].get("duplicate_records", 0))
                            + len(candidate)
                        )
                        continue
                    if batch_anchor_meta:
                        accepted_n = len(new_rows)
                        anchor_meta_accum["ageDeviations"].extend(
                            list(batch_anchor_meta.get("ageDeviations", []))[:accepted_n]
                        )
                        anchor_meta_accum["ageWithinTolerance"] += int(batch_anchor_meta.get("ageWithinTolerance", 0))
                        for key, value in (batch_anchor_meta.get("categoryMismatches") or {}).items():
                            anchor_meta_accum["categoryMismatches"][key] += int(value)
                        anchor_meta_accum["failures"].extend(batch_anchor_meta.get("failures", []))
                        anchor_meta_accum["selectedAnchorCount"] += min(
                            int(batch_anchor_meta.get("selectedAnchorCount", 0)), accepted_n
                        )
                        for key, value in (batch_anchor_meta.get("sourceValueRestorations") or {}).items():
                            anchor_meta_accum["sourceValueRestorations"][key] += int(value)
                        anchor_meta_accum["rejectedCandidateRecords"] += int(
                            batch_anchor_meta.get("rejectedCandidateRecords", 0)
                        )
                        anchor_meta_accum["regenerationAttempts"] += int(
                            batch_anchor_meta.get("regenerationAttempts", 0)
                        )
                        if source_preserving:
                            source_row_cursor += accepted_n
                    generated_parts.append(new_rows)
                    remaining -= len(new_rows)
                else:
                    rejection_report["rejectedRecords"] = (
                        int(rejection_report.get("rejectedRecords", 0)) + len(synthetic_batch)
                    )
                    rejection_report["rejectionCounts"]["source_preservation_or_validation"] = int(
                        rejection_report["rejectionCounts"].get("source_preservation_or_validation", 0)
                    ) + len(synthetic_batch)
                    if attempts >= max_attempts:
                        raise RuntimeError(
                            "Generated records failed strict validation: "
                            + "; ".join(batch_validation["failures"][:8])
                        )

            if remaining > 0:
                raise RuntimeError(
                    f"Could not generate {job.requested_record_count} validated records within {max_attempts} attempts."
                )

            synthetic = pd.concat(generated_parts, ignore_index=True).reset_index(drop=True)
            if not source_preserving:
                synthetic = synthetic.iloc[: job.requested_record_count].reset_index(drop=True)
            synthetic, final_bmi_correction = _enforce_bmi_consistency(synthetic, job.config_json)
            rejection_report["acceptedRecords"] = int(len(synthetic))
            rejection_report["method"] = str(rejection_report.get("method") or "Bounded validation-aware generation")
            rejection_report["generationProfile"] = profile
            rejection_report["bmiConsistency"] = final_bmi_correction
            if source_preserving:
                rejection_report["sourcePreservingMode"] = True
                rejection_report["ageToleranceYears"] = _age_tolerance(job.config_json)

            final_alignment = (
                _source_alignment_metrics(preservation_plan, synthetic, job.config_json)
                if source_preserving
                else None
            )

            _status(job, "Validating", generated_record_count=int(len(synthetic)))
            db.commit()
            final_validation = _validate_synthetic_frame(
                synthetic=synthetic,
                prepared=prepared,
                config=job.config_json,
                plan=preservation_plan,
                normalized_conditions=normalized_conditions,
                sampling_plan=sampling_plan,
                requested_record_count=job.requested_record_count,
                anchor_meta=anchor_meta_accum if source_preserving else None,
                source_alignment=final_alignment,
            )
            final_validation["bmiConsistency"] = final_bmi_correction
            if not final_validation["passed"]:
                raise RuntimeError(
                    "Generated dataset failed final validation: "
                    + "; ".join(final_validation["failures"][:12])
                )

            if profile != "Standard" or job.config_json.get("clinicalVariables"):
                clinical_report = clinical_reference_service.validate_clinical_records(
                    synthetic,
                    generation_profile=profile,
                    clinical_variables=job.config_json.get("clinicalVariables") or [],
                    overrides=job.config_json.get("referenceOverrides") or [],
                    disease_rules=job.config_json.get("diseaseRules") or [],
                )
                failures = clinical_report.get("_mandatoryFailures") or []
                if profile != "Standard" and any(bool(value) for value in failures):
                    raise RuntimeError(
                        "Generated records failed final clinical validation: "
                        f"{json.dumps(json_safe(_public_clinical_report(clinical_report)), ensure_ascii=False)}"
                    )
            else:
                clinical_report = {
                    "method": "Not applied to the Standard generation profile",
                    "generationProfile": profile,
                    "totalRecords": int(len(synthetic)),
                    "classificationCounts": {},
                    "warnings": [],
                    "limitations": clinical_reference_service.CLINICAL_LIMITATIONS,
                }
            clinical_report_public = _public_clinical_report(clinical_report)

            schema_validation = final_validation["schemaValidation"]
            satisfaction = final_validation["conditionSatisfaction"]
            job.satisfaction_json = json_safe(satisfaction)

            report_source = (
                _preservation_source_frame(preservation_plan, list(synthetic.columns))
                if source_preserving
                else prepared["frame"]
            )
            preservation_report = _build_source_preservation_report(
                source=report_source,
                synthetic=synthetic,
                config=job.config_json,
                plan=preservation_plan,
                anchor_meta=anchor_meta_accum if source_preserving else None,
                validation=final_validation,
                rejection_report=rejection_report,
                source_alignment=final_alignment,
            )

            generated_id = str(uuid4())
            generated_paths: dict[str, str] = {}
            csv_bytes = synthetic.to_csv(index=False).encode("utf-8")
            _, generated_paths["CSV"] = storage.save_generated(generated_id, "synthetic_data.csv", csv_bytes)
            excel_buffer = io.BytesIO()
            synthetic.to_excel(excel_buffer, index=False, engine="openpyxl")
            _, generated_paths["XLSX"] = storage.save_generated(
                generated_id, "synthetic_data.xlsx", excel_buffer.getvalue()
            )
            json_bytes = synthetic.to_json(orient="records", date_format="iso").encode("utf-8")
            _, generated_paths["JSON"] = storage.save_generated(generated_id, "synthetic_data.json", json_bytes)

            generated = SynthMedGeneratedDataset(
                id=generated_id,
                owner_id=job.owner_id,
                source_dataset_id=source.id,
                dataset_name=str(job.config_json.get("datasetName") or f"{source.dataset_name} synthetic"),
                source_dataset_name=source.dataset_name,
                generation_method=model_label,
                generation_mode=mode,
                selected_model=model,
                record_count=int(len(synthetic)),
                column_count=int(len(synthetic.columns)),
                file_format="CSV",
                file_size_bytes=len(csv_bytes),
                checksum_sha256=hashlib.sha256(csv_bytes).hexdigest(),
                stored_path=generated_paths["CSV"],
                status="Completed",
            )
            db.add(generated)
            db.flush()
            job.generated_dataset_id = generated_id

            _status(job, "Evaluating")
            quality = build_quality_report(prepared["frame"], synthetic, prepared["metadataDict"])
            privacy = build_privacy_report(
                prepared["frame"],
                synthetic,
                prepared["metadataDict"],
                prepared["analysis"],
                seed=job.seed,
                conditional=mode == "Conditional",
            )
            quality_path = _save_report(storage, job.id, "quality_report.json", quality)
            privacy_path = _save_report(storage, job.id, "privacy_report.json", privacy)
            conditions_path = ""
            if mode == "Conditional":
                conditions_path = _save_report(storage, job.id, "condition_satisfaction.json", satisfaction)
                _upsert_report(
                    db,
                    job=job,
                    generated_id=generated_id,
                    report_type="conditions",
                    method=satisfaction["method"],
                    score=satisfaction["combined"]["satisfactionPercentage"],
                    payload=satisfaction,
                    file_path=conditions_path,
                )
            _upsert_report(
                db,
                job=job,
                generated_id=generated_id,
                report_type="quality",
                method=quality["method"],
                score=quality.get("overallQualityScore"),
                payload=quality,
                file_path=quality_path,
            )
            _upsert_report(
                db,
                job=job,
                generated_id=generated_id,
                report_type="privacy",
                method=privacy["method"],
                score=privacy.get("newRowSynthesisScore"),
                payload=privacy,
                file_path=privacy_path,
            )
            _upsert_report(
                db,
                job=job,
                generated_id=generated_id,
                report_type="preprocessing",
                method="SynthMed deterministic preprocessing pipeline",
                score=None,
                payload=prepared["report"],
                file_path=preprocessing_path,
            )
            clinical_payload = {
                "clinicalValidation": clinical_report_public,
                "schemaValidation": schema_validation,
                "rejectionSampling": rejection_report,
            }
            clinical_path = _save_report(storage, job.id, "clinical_validation.json", clinical_payload)
            _upsert_report(
                db,
                job=job,
                generated_id=generated_id,
                report_type="clinical",
                method=str(clinical_report_public.get("method") or clinical_reference_service.CLINICAL_METHOD),
                score=None,
                payload=clinical_payload,
                file_path=clinical_path,
            )
            preservation_path = _save_report(storage, job.id, "source_preservation_report.json", preservation_report)
            _upsert_report(
                db,
                job=job,
                generated_id=generated_id,
                report_type="preservation",
                method=str(preservation_report.get("method") or "Source-preserving validation"),
                score=preservation_report.get("ageWithinTolerance", {}).get("percentage"),
                payload=preservation_report,
                file_path=preservation_path,
            )

            generation_report = {
                "jobId": job.id,
                "generatedDatasetId": generated_id,
                "model": model_label,
                "selectedModel": model,
                "generationMode": mode,
                "sdvVersion": condition_service.SDV_VERSION,
                "samplingApi": condition_service.CAPABILITIES[model].sampling_api,
                "samplingStrategy": condition_service.CAPABILITIES[model].sampling_strategy,
                "epochs": job.epochs if model in {"CTGAN", "TVAE"} else None,
                "batchSize": job.batch_size if model in {"CTGAN", "TVAE"} else None,
                "seed": job.seed,
                "requestedRecordCount": job.requested_record_count,
                "generatedRecordCount": int(len(synthetic)),
                "trainingDurationSeconds": round(training_duration, 3),
                "conditions": json_safe(normalized_conditions),
                "samplingPlan": json_safe(sampling_plan),
                "conditionSatisfaction": satisfaction,
                "generationProfile": profile,
                "clinicalValidation": clinical_report_public,
                "schemaValidation": schema_validation,
                "rejectionSampling": rejection_report,
                "sourcePreservation": preservation_report,
                "columns": list(synthetic.columns),
                "generatedPaths": generated_paths,
                "modelPath": model_relative,
                "metadataPath": metadata_path,
                "qualityReportPath": quality_path,
                "privacyReportPath": privacy_path,
                "conditionsReportPath": conditions_path,
                "clinicalReportPath": clinical_path,
                "sourcePreservationReportPath": preservation_path,
                "notes": [
                    f"{model_label} training ran on CPU.",
                    "Original source files were not modified.",
                    "The same fitted synthesizer instance produced all requested records.",
                    "Synthetic data is for research and software testing, not clinical decision-making.",
                ],
            }
            generation_path = _save_report(storage, job.id, "generation_report.json", generation_report)
            _upsert_report(
                db,
                job=job,
                generated_id=generated_id,
                report_type="generation",
                method=model_label,
                score=None,
                payload=generation_report,
                file_path=generation_path,
            )

            config = dict(job.config_json)
            config.pop("sourcePreservationPlanInternal", None)
            config["generatedPaths"] = generated_paths
            config["reportPaths"] = {
                "generation": generation_path,
                "preprocessing": preprocessing_path,
                "quality": quality_path,
                "privacy": privacy_path,
                "conditions": conditions_path,
                "clinical": clinical_path,
                "preservation": preservation_path,
                "metadata": metadata_path,
                "model": model_relative,
            }
            config["clinicalValidation"] = clinical_report_public
            config["schemaValidation"] = schema_validation
            config["rejectionSampling"] = rejection_report
            config["sourcePreservation"] = preservation_report
            config["validationStatus"] = "Passed" if final_validation["passed"] else "Failed"
            job.config_json = json_safe(config)
            job.satisfaction_json = json_safe(satisfaction)
            _status(
                job,
                "Completed",
                completed_at=_now(),
                training_duration_seconds=round(training_duration, 3),
                generated_record_count=int(len(synthetic)),
                error_json=None,
            )
            log_audit(
                db,
                action="synthmed.generation_completed",
                resource_type="synthmed_generation_job",
                resource_id=job.id,
                actor_id=job.owner_id,
                details={
                    "generated_dataset_id": generated_id,
                    "model": model,
                    "generation_mode": mode,
                    "generation_profile": profile,
                    "records": int(len(synthetic)),
                    "conditions_satisfied": bool(satisfaction["passed"]),
                    "clinical_validation_applied": profile != "Standard",
                    "source_preserving_mode": bool(source_preserving),
                    "age_tolerance_years": _age_tolerance(job.config_json),
                },
            )
            try:
                owner = db.get(User, job.owner_id)
                if owner is not None:
                    source_version = versioning_service.ensure_source_version(
                        db, user=owner, settings=settings, source=source
                    )
                    generated_version = versioning_service.ensure_generated_version(
                        db, user=owner, settings=settings, generated=generated, job=job
                    )
                    versioning_service.record_lineage(
                        db,
                        owner_id=owner.id,
                        event_type="generation_job",
                        parent_type="synthmed_generation_job",
                        parent_id=job.id,
                        child_type="synthmed_generated_dataset",
                        child_id=generated.id,
                        source_dataset_id=source.id,
                        generated_dataset_id=generated.id,
                        metadata={
                            "sourceVersionId": source_version.id,
                            "generatedVersionId": generated_version.id,
                        },
                    )
            except Exception:
                logger.exception("Failed to record P5 versioning for job %s", job.id)
            db.commit()
            return job
        except Exception as error:
            db.rollback()
            job = db.get(SynthMedGenerationJob, job_id)
            if job is None:
                return None
            _status(job, "Failed", completed_at=_now(), error_json=json_safe(_error_details(error)))
            log_audit(
                db,
                action="synthmed.generation_failed",
                resource_type="synthmed_generation_job",
                resource_id=job.id,
                actor_id=job.owner_id,
                details=_error_details(error),
            )
            db.commit()
            return job


def job_response(job: SynthMedGenerationJob) -> dict[str, Any]:
    config = dict(job.config_json or {})
    source_preservation = dict(config.get("sourcePreservation") or {})
    validation_status = str(config.get("validationStatus") or ("Failed" if job.status == "Failed" else ""))
    return {
        "id": job.id,
        "sourceDatasetId": job.source_dataset_id,
        "generatedDatasetId": job.generated_dataset_id or "",
        "status": job.status,
        "modelName": job.model_name,
        "generationMode": job.generation_mode,
        "selectedModel": job.selected_model,
        "epochs": job.epochs,
        "batchSize": job.batch_size,
        "seed": job.seed,
        "requestedRecordCount": job.requested_record_count,
        "generatedRecordCount": job.generated_record_count,
        "trainingDurationSeconds": job.training_duration_seconds,
        "createdAt": _iso(job.created_at),
        "startedAt": _iso(job.started_at),
        "completedAt": _iso(job.completed_at),
        "conditions": json_safe(job.normalized_conditions_json or config.get("normalizedConditions") or []),
        "conditionValidation": json_safe(job.condition_validation_json or {}),
        "conditionSatisfaction": json_safe(job.satisfaction_json or {}),
        "error": (job.error_json or {}).get("message", ""),
        "config": json_safe(config),
        "generationProfile": str(config.get("generationProfile") or "Standard"),
        "clinicalValidation": json_safe(config.get("clinicalValidation") or {}),
        "schemaValidation": json_safe(config.get("schemaValidation") or {}),
        "sourcePreservingMode": bool(config.get("sourcePreservingMode")),
        "ageToleranceYears": int(config.get("ageToleranceYears", 5)),
        "validationStatus": validation_status,
        "sourcePreservation": json_safe(source_preservation),
    }


def get_job(db: Session, job_id: str, user: User) -> SynthMedGenerationJob:
    job = db.get(SynthMedGenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation job not found.")
    if job.owner_id != user.id and user.role != UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to view this generation job.")
    return job


def list_jobs(db: Session, user: User) -> list[SynthMedGenerationJob]:
    statement = select(SynthMedGenerationJob)
    if user.role != UserRole.ADMINISTRATOR:
        statement = statement.where(SynthMedGenerationJob.owner_id == user.id)
    return list(db.scalars(statement.order_by(SynthMedGenerationJob.created_at.desc())))


def job_for_generated(db: Session, generated_id: str) -> SynthMedGenerationJob | None:
    return db.scalar(select(SynthMedGenerationJob).where(SynthMedGenerationJob.generated_dataset_id == generated_id))


def generated_detail(db: Session, generated_id: str, user: User) -> dict[str, Any]:
    from app.synthmed.services.source_service import (
        ensure_generated_access,
        generated_registration_map,
        get_generated,
    )

    generated = get_generated(db, generated_id)
    ensure_generated_access(generated, user)
    job = job_for_generated(db, generated_id)
    registration = generated_registration_map(db, [generated.id]).get(generated.id)
    reports = list(
        db.scalars(
            select(SynthMedEvaluationReport).where(SynthMedEvaluationReport.generated_dataset_id == generated_id)
        )
    )
    config = dict(job.config_json) if job else {}
    return {
        **to_generated_response(generated, registration).model_dump(),
        "generationJobId": job.id if job else "",
        "modelName": job.model_name if job else generated.generation_method,
        "generationMode": job.generation_mode if job else generated.generation_mode,
        "selectedModel": job.selected_model if job else generated.selected_model,
        "trainingDurationSeconds": job.training_duration_seconds if job else None,
        "availableFormats": sorted((config.get("generatedPaths") or {}).keys()) or [generated.file_format],
        "reportTypes": sorted({report.report_type for report in reports}),
        "trainingConfig": {
            "model": job.selected_model if job else generated.selected_model,
            "samplingStrategy": condition_service.CAPABILITIES[
                condition_service.normalize_model(job.selected_model if job else generated.selected_model) or "CTGAN"
            ].sampling_strategy,
            "epochs": job.epochs if job and job.selected_model in {"CTGAN", "TVAE"} else None,
            "batchSize": job.batch_size if job and job.selected_model in {"CTGAN", "TVAE"} else None,
            "seed": job.seed if job else None,
            "preserveMissingness": config.get("preserveMissingness", True),
            "includedColumns": config.get("selectedColumns", []),
            "sourcePreservingMode": bool(config.get("sourcePreservingMode")),
            "ageToleranceYears": int(config.get("ageToleranceYears", 5)),
        },
        "conditions": json_safe(
            (job.normalized_conditions_json if job else None) or config.get("normalizedConditions") or []
        ),
        "conditionSatisfaction": json_safe((job.satisfaction_json if job else None) or {}),
        "generationProfile": str(config.get("generationProfile") or "Standard"),
        "clinicalValidation": json_safe(config.get("clinicalValidation") or {}),
        "schemaValidation": json_safe(config.get("schemaValidation") or {}),
        "sourcePreservingMode": bool(config.get("sourcePreservingMode")),
        "ageToleranceYears": int(config.get("ageToleranceYears", 5)),
        "validationStatus": str(config.get("validationStatus") or ""),
        "sourcePreservation": json_safe(config.get("sourcePreservation") or {}),
    }


def preview_generated(
    db: Session, generated_id: str, user: User, settings: Settings, page: int, page_size: int
) -> dict[str, Any]:
    from app.synthmed.services.source_service import ensure_generated_access, get_generated

    generated = get_generated(db, generated_id)
    ensure_generated_access(generated, user)
    path = SynthMedStorageService(settings).resolve_generated(generated.stored_path)
    frame = pd.read_csv(path)
    start = (page - 1) * page_size
    rows = json_safe(frame.iloc[start : start + page_size].to_dict(orient="records"))
    return {
        "generatedDatasetId": generated_id,
        "columns": list(frame.columns),
        "rows": rows,
        "totalRecords": int(len(frame)),
        "page": page,
        "pageSize": page_size,
    }


def evaluation_report(db: Session, generated_id: str, report_type: str, user: User) -> dict[str, Any]:
    from app.synthmed.services.source_service import ensure_generated_access, get_generated

    generated = get_generated(db, generated_id)
    ensure_generated_access(generated, user)
    report = db.scalar(
        select(SynthMedEvaluationReport).where(
            SynthMedEvaluationReport.generated_dataset_id == generated_id,
            SynthMedEvaluationReport.report_type == report_type,
        )
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {report_type} report is available for this generated dataset.",
        )
    return {
        "id": report.id,
        "generatedDatasetId": generated_id,
        "reportType": report.report_type,
        "method": report.method,
        "score": json_safe(report.score),
        "report": json_safe(report.report_json),
        "createdAt": _iso(report.created_at),
    }


def evaluation_report_row(db: Session, generated_id: str, report_type: str) -> SynthMedEvaluationReport:
    report = db.scalar(
        select(SynthMedEvaluationReport).where(
            SynthMedEvaluationReport.generated_dataset_id == generated_id,
            SynthMedEvaluationReport.report_type == report_type,
        )
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {report_type} report file is available.",
        )
    return report


def models_payload() -> dict[str, Any]:
    return {
        "models": condition_service.model_capabilities(),
        "sdvVersion": condition_service.SDV_VERSION,
        "message": (
            "Conditional sampling uses SDV sample_from_conditions with exact equality conditions. "
            "Range, missing-value and identifier conditions are rejected."
        ),
    }


def dataset_columns_payload(
    db: Session, source: SynthMedSourceDataset, user: User, settings: Settings, model: str = "CTGAN"
) -> dict[str, Any]:
    validation = condition_service.validate_conditions(
        source=source,
        config={"model": model, "conditions": [], "selectedColumns": None},
        settings=settings,
    )
    storage = SynthMedStorageService(settings)
    frame = read_source_dataframe(storage.resolve_source(source.stored_path), source.file_format)
    analysis = analyse_dataframe(frame)
    return {
        "sourceDatasetId": source.id,
        "totalColumns": int(len(frame.columns)),
        "eligibleColumns": validation["eligibleColumns"],
        "ineligibleColumns": validation["ineligibleColumns"],
        "numericalColumns": analysis["numericalColumns"],
        "categoricalColumns": analysis["categoricalColumns"],
        "booleanColumns": analysis["booleanColumns"],
        "datetimeColumns": analysis["datetimeColumns"],
        "potentialIdentifierColumns": analysis["potentialIdentifierColumns"],
        "generationReady": analysis["totalRecords"] >= 10 and analysis["totalColumns"] >= 2,
        "guidance": (
            "Only eligible columns can be used as exact equality conditions. "
            "Patient identifiers are excluded from generation and condition validation."
        ),
    }


def validate_conditions_payload(
    source: SynthMedSourceDataset, config: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    return condition_service.validate_conditions(source=source, config=config, settings=settings)


def condition_satisfaction_report(db: Session, generated_id: str, user: User) -> dict[str, Any]:
    from app.synthmed.services.source_service import ensure_generated_access

    generated = db.get(SynthMedGeneratedDataset, generated_id)
    if generated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated dataset not found.")
    ensure_generated_access(generated, user)
    job = job_for_generated(db, generated_id)
    report = evaluation_report(db, generated_id, "conditions", user)
    if job is not None:
        report["conditions"] = json_safe(
            job.normalized_conditions_json or job.config_json.get("normalizedConditions") or []
        )
        report["generationMode"] = job.generation_mode
        report["selectedModel"] = job.selected_model
    return report


def generated_evaluation_summary(db: Session, generated_id: str, user: User) -> dict[str, Any]:
    from app.synthmed.services.source_service import ensure_generated_access

    generated = db.get(SynthMedGeneratedDataset, generated_id)
    if generated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated dataset not found.")
    ensure_generated_access(generated, user)
    reports = list(
        db.scalars(
            select(SynthMedEvaluationReport).where(SynthMedEvaluationReport.generated_dataset_id == generated_id)
        )
    )
    by_type = {report.report_type: json_safe(report.report_json) for report in reports}
    job = job_for_generated(db, generated_id)
    generation_profile = str((job.config_json if job else {}).get("generationProfile") or "Standard")
    config = dict(job.config_json if job else {})
    return {
        "generatedDatasetId": generated_id,
        "generationMode": generated.generation_mode,
        "selectedModel": generated.selected_model,
        "availableReports": sorted(by_type),
        "quality": by_type.get("quality"),
        "privacy": by_type.get("privacy"),
        "conditions": by_type.get("conditions"),
        "clinical": by_type.get("clinical"),
        "generationProfile": generation_profile,
        "sourcePreservation": by_type.get("preservation") or json_safe(config.get("sourcePreservation") or {}),
        "validationStatus": str(config.get("validationStatus") or ""),
        "limitations": [
            "Condition satisfaction, statistical similarity, data quality, clinical validation, "
            "source preservation and privacy risk are separate concepts.",
            "Passing clinical reference checks does not establish clinical validity or fitness for patient care.",
            "Source anchoring can increase record-level similarity and privacy risk; "
            "review P3/privacy screening before release.",
            "No differential privacy mechanism is implemented.",
        ],
    }


def generation_metadata(db: Session, generated_id: str) -> dict[str, Any]:
    job = job_for_generated(db, generated_id)
    if job is None:
        return {}
    config = dict(job.config_json or {})
    return {
        "model": job.selected_model,
        "modelName": job.model_name,
        "generationMode": job.generation_mode,
        "requestedConditions": json_safe(
            job.normalized_conditions_json or config.get("normalizedConditions") or []
        ),
        "conditionSatisfaction": json_safe(job.satisfaction_json or {}),
        "generationDurationSeconds": job.training_duration_seconds,
        "recordCount": job.generated_record_count,
        "generationProfile": str(config.get("generationProfile") or "Standard"),
        "clinicalValidation": json_safe(config.get("clinicalValidation") or {}),
        "schemaValidation": json_safe(config.get("schemaValidation") or {}),
        "rejectionSampling": json_safe(config.get("rejectionSampling") or {}),
        "clinicalVariables": json_safe(config.get("clinicalVariables") or []),
        "referenceOverrides": json_safe(config.get("referenceOverrides") or []),
        "diseaseRules": json_safe(config.get("diseaseRules") or []),
        "approvedOutputColumns": json_safe(config.get("approvedOutputColumns") or []),
        "excludedOutputColumns": json_safe(config.get("excludedOutputColumns") or []),
        "sourcePreservingMode": bool(config.get("sourcePreservingMode")),
        "ageToleranceYears": int(config.get("ageToleranceYears", 5)),
        "sourcePreservation": json_safe(config.get("sourcePreservation") or {}),
        "validationStatus": str(config.get("validationStatus") or ""),
        "status": job.status,
    }


def export_generated(
    db: Session,
    *,
    generated_id: str,
    user: User,
    file_format: str,
    settings: Settings,
    request: Request | None = None,
) -> dict[str, Any]:
    from app.synthmed.services.source_service import ensure_generated_access, get_generated

    generated = get_generated(db, generated_id)
    ensure_generated_access(generated, user)
    normalized = file_format.strip().upper()
    if normalized not in {"CSV", "XLSX", "JSON"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Export format must be CSV, XLSX or JSON.",
        )

    storage = SynthMedStorageService(settings)
    job = job_for_generated(db, generated_id)
    config = dict(job.config_json) if job else {}
    paths = dict(config.get("generatedPaths") or {})
    if normalized not in paths:
        frame = pd.read_csv(storage.resolve_generated(generated.stored_path))
        if normalized == "CSV":
            content = frame.to_csv(index=False).encode("utf-8")
        elif normalized == "XLSX":
            buffer = io.BytesIO()
            frame.to_excel(buffer, index=False, engine="openpyxl")
            content = buffer.getvalue()
        else:
            content = frame.to_json(orient="records", date_format="iso").encode("utf-8")
        _, paths[normalized] = storage.save_generated(generated_id, f"synthetic_data.{normalized.lower()}", content)
        config["generatedPaths"] = paths
        if job is not None:
            job.config_json = json_safe(config)
    log_audit(
        db,
        action="synthmed.generated_exported",
        resource_type="synthmed_generated_dataset",
        resource_id=generated_id,
        actor_id=user.id,
        details={"format": normalized},
        request=request,
    )
    db.commit()
    return {"generatedDatasetId": generated_id, "format": normalized, "fileName": Path(paths[normalized]).name}


def generated_download_path(db: Session, generated_id: str, file_format: str, settings: Settings) -> tuple[Path, str]:
    generated = db.get(SynthMedGeneratedDataset, generated_id)
    if generated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated dataset not found.")
    normalized = file_format.strip().upper()
    job = job_for_generated(db, generated_id)
    paths = dict((job.config_json if job else {}).get("generatedPaths") or {})
    relative = paths.get(normalized)
    if not relative and normalized == "CSV":
        relative = generated.stored_path
    if not relative:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{normalized} output has not been generated for this dataset.",
        )
    return SynthMedStorageService(settings).resolve_generated(relative), Path(relative).name


def recover_stale_jobs(session_factory: sessionmaker[Session] | None = None, *, stale_after_seconds: int = 0) -> int:
    factory = session_factory or SessionLocal
    cutoff = _now() - timedelta(seconds=stale_after_seconds) if stale_after_seconds > 0 else None
    recovered = 0
    with factory() as db:
        statement = select(SynthMedGenerationJob.id, SynthMedGenerationJob.owner_id).where(
            SynthMedGenerationJob.status.in_(ACTIVE_STATUSES)
        )
        if cutoff is not None:
            statement = statement.where(SynthMedGenerationJob.updated_at <= cutoff)
        candidates = db.execute(statement).all()
        for job_id, owner_id in candidates:
            conditions = [
                SynthMedGenerationJob.id == job_id,
                SynthMedGenerationJob.status.in_(ACTIVE_STATUSES),
            ]
            if cutoff is not None:
                conditions.append(SynthMedGenerationJob.updated_at <= cutoff)
            result = db.execute(
                update(SynthMedGenerationJob)
                .where(*conditions)
                .values(
                    status="Failed",
                    completed_at=_now(),
                    updated_at=_now(),
                    error_json={"type": INTERRUPTED_ERROR_TYPE, "message": INTERRUPTED_ERROR_MESSAGE},
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                continue
            log_audit(
                db,
                action="synthmed.generation_interrupted",
                resource_type="synthmed_generation_job",
                resource_id=job_id,
                actor_id=owner_id,
                details={"reason": "api_restart", "stale_after_seconds": stale_after_seconds},
            )
            recovered += 1
        db.commit()
    return recovered
