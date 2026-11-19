from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import HTTPException, status
from sdv.metadata import Metadata

TABLE_NAME = "synthmed"
IDENTIFIER_PATTERN = re.compile(
    r"(^|_)(patient|patientid|mrn|nhs|ssn|uuid|guid|record|case|subject|member|id)(_|$)"
)
QUASI_IDENTIFIER_PATTERN = re.compile(
    r"(^|_)(age|birth|dob|date|gender|sex|postcode|zip|zipcode|county|district)(_|$)"
)
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S")


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return json_safe(value.to_dict(orient="records"))
    return str(value)


def dump_json(value: Any) -> bytes:
    return json.dumps(json_safe(value), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def read_source_dataframe(path: Path, file_format: str) -> pd.DataFrame:
    try:
        if file_format == "CSV":
            frame = pd.read_csv(path)
        elif file_format == "XLSX":
            frame = pd.read_excel(path)
        elif file_format == "JSON":
            frame = pd.read_json(path)
        else:
            raise ValueError(f"Unsupported format: {file_format}")
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"SynthMed source file could not be read as {file_format}: {error}",
        ) from error

    frame.columns = [str(column) for column in frame.columns]
    if frame.columns.duplicated().any():
        seen: dict[str, int] = {}
        renamed: list[str] = []
        for column in frame.columns:
            count = seen.get(column, 0) + 1
            seen[column] = count
            renamed.append(column if count == 1 else f"{column}_{count}")
        frame.columns = renamed
    if frame.empty:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="SynthMed source dataset must contain at least one record.",
        )
    return frame


def _is_datetime_series(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if not pd.api.types.is_object_dtype(series) and not isinstance(series.dtype, pd.StringDtype):
        return False
    sample = series.dropna().astype(str).head(20)
    if sample.empty:
        return False
    return _infer_datetime_format(sample) is not None


def _infer_datetime_format(sample: pd.Series) -> str | None:
    values = [value.strip() for value in sample.tolist() if value.strip()]
    if not values:
        return None
    for candidate in DATE_FORMATS:
        try:
            parsed = pd.to_datetime(pd.Series(values), format=candidate, errors="raise")
        except (ValueError, TypeError):
            continue
        if parsed.notna().all():
            return candidate
    return None


def _column_kind(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if _is_datetime_series(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        return "numerical"
    return "categorical"


def _is_identifier_name(column: str) -> bool:
    normalized = column.strip().lower().replace(" ", "_").replace("-", "_")
    return bool(IDENTIFIER_PATTERN.search(normalized))


def analyse_dataframe(frame: pd.DataFrame) -> dict[str, Any]:
    total = len(frame)
    columns: list[dict[str, Any]] = []
    for column in frame.columns:
        series = frame[column]
        kind = _column_kind(series)
        unique = int(series.nunique(dropna=True))
        missing = int(series.isna().sum())
        identifier = _is_identifier_name(column) or (
            total > 1 and unique / total > 0.95 and kind == "categorical"
        )
        columns.append(
            {
                "name": column,
                "dtype": str(series.dtype),
                "kind": kind,
                "missingCount": missing,
                "missingPercentage": round(missing / total * 100, 2) if total else 0.0,
                "uniqueCount": unique,
                "constant": series.nunique(dropna=False) <= 1,
                "potentialIdentifier": identifier,
                "quasiIdentifier": bool(QUASI_IDENTIFIER_PATTERN.search(column.strip().lower())),
            }
        )

    return {
        "totalRecords": total,
        "totalColumns": len(frame.columns),
        "columns": json_safe(columns),
        "numericalColumns": [item["name"] for item in columns if item["kind"] == "numerical"],
        "categoricalColumns": [item["name"] for item in columns if item["kind"] == "categorical"],
        "datetimeColumns": [item["name"] for item in columns if item["kind"] == "datetime"],
        "booleanColumns": [item["name"] for item in columns if item["kind"] == "boolean"],
        "potentialIdentifierColumns": [item["name"] for item in columns if item["potentialIdentifier"]],
        "quasiIdentifierColumns": [item["name"] for item in columns if item["quasiIdentifier"]],
        "constantColumns": [item["name"] for item in columns if item["constant"]],
        "duplicateRecords": int(frame.duplicated().sum()),
    }


def _config_list(config: dict[str, Any], key: str) -> list[str]:
    values = config.get(key) or []
    if not isinstance(values, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{key} must be a list of column names.",
        )
    return [str(value) for value in values]


def prepare_dataframe(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    total = len(frame)
    analysis = analyse_dataframe(frame)
    available = list(frame.columns)
    selected = _config_list(config, "selectedColumns") or available
    unknown = [column for column in selected if column not in available]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Selected columns are not present in the source dataset: {', '.join(unknown)}",
        )

    explicit_identifiers = _config_list(config, "identifierColumns")
    primary_key = str(config.get("primaryKey") or "").strip() or None
    identifiers = sorted(set(explicit_identifiers) | set(analysis["potentialIdentifierColumns"]))
    if primary_key:
        identifiers.append(primary_key)
    identifiers = sorted(set(identifiers))
    constants = set(analysis["constantColumns"])
    excluded_identifiers = [column for column in identifiers if column in available]
    excluded_constants = [column for column in selected if column in constants and column not in identifiers]

    included = [column for column in selected if column not in identifiers and column not in excluded_constants]
    if not included:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No modelable columns remain after excluding identifier and constant columns. "
            "Adjust the column configuration and try again.",
        )

    prepared = frame.loc[:, included].copy()
    operations: list[dict[str, Any]] = []
    if excluded_identifiers:
        operations.append(
            {
                "operation": "excluded_identifiers",
                "columns": excluded_identifiers,
                "reason": "Identifier columns are not modelled or reproduced in synthetic records.",
            }
        )
    if excluded_constants:
        operations.append(
            {
                "operation": "excluded_constant_columns",
                "columns": excluded_constants,
                "reason": "Constant columns cannot be learned by CTGAN and are reported instead.",
            }
        )

    numerical = [column for column in _config_list(config, "numericalColumns") if column in included]
    categorical = [column for column in _config_list(config, "categoricalColumns") if column in included]
    sdtype_updates: dict[str, dict[str, Any]] = {}

    for column in numerical:
        converted = pd.to_numeric(prepared[column], errors="coerce")
        coerced = int((prepared[column].notna() & converted.isna()).sum())
        prepared[column] = converted
        sdtype_updates[column] = {"sdtype": "numerical"}
        operations.append(
            {
                "operation": "numerical_coercion",
                "column": column,
                "coercedNonNumericValues": coerced,
                "reason": "User-configured numerical column.",
            }
        )

    for column in categorical:
        prepared[column] = prepared[column].astype("string")
        sdtype_updates[column] = {"sdtype": "categorical"}
        operations.append(
            {
                "operation": "categorical_typing",
                "column": column,
                "reason": "User-configured categorical column.",
            }
        )

    for column in included:
        series = prepared[column]
        if column in numerical or column in categorical:
            continue
        if pd.api.types.is_bool_dtype(series):
            if series.isna().any():
                prepared[column] = series.astype("string")
                sdtype_updates[column] = {"sdtype": "categorical"}
                operations.append(
                    {
                        "operation": "boolean_with_missingness_as_categorical",
                        "column": column,
                        "reason": "Boolean missingness is preserved as a categorical value.",
                    }
                )
            else:
                sdtype_updates[column] = {"sdtype": "boolean"}
            continue
        if _is_datetime_series(series):
            sample = series.dropna().astype(str).head(30)
            inferred = _infer_datetime_format(sample)
            try:
                prepared[column] = (
                    pd.to_datetime(series, format=inferred, errors="coerce")
                    if inferred
                    else pd.to_datetime(series, format="mixed", errors="coerce")
                )
            except Exception:
                prepared[column] = series.astype("string")
                sdtype_updates[column] = {"sdtype": "categorical"}
                operations.append(
                    {
                        "operation": "undetermined_datetime_as_categorical",
                        "column": column,
                        "reason": "Date format could not be determined safely; original values retained as text.",
                    }
                )
                continue
            coerced = int((series.notna() & prepared[column].isna()).sum())
            if inferred:
                sdtype_updates[column] = {"sdtype": "datetime"}
            operations.append(
                {
                    "operation": "datetime_typing",
                    "column": column,
                    "inferredFormat": inferred,
                    "coercedValues": coerced,
                    "reason": "Date columns retain a defined datetime representation; no arbitrary numeric conversion.",
                }
            )

    duplicate_count = int(prepared.duplicated().sum())
    if duplicate_count:
        prepared = prepared.drop_duplicates().reset_index(drop=True)
        operations.append(
            {
                "operation": "duplicate_rows_removed",
                "rows": duplicate_count,
                "reason": "Exact duplicate training rows were removed; original source file was unchanged.",
            }
        )

    preserve_missingness = bool(config.get("preserveMissingness", True))
    if not preserve_missingness:
        before = len(prepared)
        prepared = prepared.dropna().reset_index(drop=True)
        dropped = before - len(prepared)
        operations.append(
            {
                "operation": "rows_with_missing_values_removed",
                "rows": dropped,
                "reason": "Explicitly requested; missing values are never filled with zero.",
            }
        )
    else:
        operations.append(
            {
                "operation": "missingness_preserved",
                "columns": [column for column in included if int(prepared[column].isna().sum()) > 0],
                "reason": "Missing values are retained for SDV/RDT handling; no zero or medical-value imputation.",
            }
        )

    numeric_ranges = config.get("numericRanges") or {}
    for column, bounds in numeric_ranges.items():
        if column not in prepared.columns or not isinstance(bounds, dict):
            continue
        low = bounds.get("min")
        high = bounds.get("max")
        mask = pd.Series(True, index=prepared.index)
        if low is not None:
            mask &= prepared[column] >= float(low)
        if high is not None:
            mask &= prepared[column] <= float(high)
        removed = int((~mask).sum())
        prepared = prepared.loc[mask].reset_index(drop=True)
        operations.append(
            {
                "operation": "numeric_range_constraint",
                "column": column,
                "min": low,
                "max": high,
                "rowsRemoved": removed,
                "reason": "Explicit user-defined valid range.",
            }
        )

    categorical_values = config.get("categoricalValues") or {}
    for column, allowed in categorical_values.items():
        if column not in prepared.columns or not isinstance(allowed, list) or not allowed:
            continue
        mask = prepared[column].isin([str(value) for value in allowed]) | prepared[column].isna()
        removed = int((~mask).sum())
        prepared = prepared.loc[mask].reset_index(drop=True)
        operations.append(
            {
                "operation": "categorical_constraint",
                "column": column,
                "allowedValues": allowed,
                "rowsRemoved": removed,
                "reason": "Explicit user-defined categorical constraint.",
            }
        )

    if prepared.empty:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Preprocessing removed every training row. Review constraints and missing-value settings.",
        )

    metadata = Metadata.detect_from_dataframes({TABLE_NAME: prepared}, infer_keys=None, verbose=False)
    for column, update in sdtype_updates.items():
        metadata.update_column(column_name=column, table_name=TABLE_NAME, **update)
    try:
        metadata.validate()
        metadata.validate_data({TABLE_NAME: prepared})
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"SDV metadata validation failed: {error}",
        ) from error

    report = {
        "sourceRecords": total,
        "sourceColumns": len(available),
        "trainingRecords": len(prepared),
        "trainingColumns": len(prepared.columns),
        "includedColumns": included,
        "excludedIdentifierColumns": excluded_identifiers,
        "excludedConstantColumns": excluded_constants,
        "operations": json_safe(operations),
        "metadata": json_safe(metadata.to_dict()),
        "notes": [
            "The original uploaded source file was read-only and was not modified.",
            "Missing medical values are not filled with zero.",
            "No clinical relationships or medical validity are inferred by preprocessing.",
        ],
    }
    return {
        "frame": prepared,
        "metadata": metadata,
        "metadataDict": json_safe(metadata.to_dict()),
        "report": report,
        "analysis": analysis,
    }
