from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from app.models.enums import FileFormat

MISSING_TOKENS = {"", "na", "n/a", "null", "none", "nan", "<na>"}
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
YEAR_FIRST_DATE_PATTERN = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$")
AMBIGUOUS_DATE_PATTERN = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$")
BOOLEAN_TOKENS = {"true", "false", "yes", "no", "y", "n"}


@dataclass
class ColumnProfile:
    name: str
    inferred_type: str
    missing: int
    missing_pct: float
    unique_sample: int
    sample_values: list[str]
    ambiguous_dates: int = 0


@dataclass
class ExtractionProfile:
    sheet_name: str
    row_count: int
    column_count: int
    missing_cells: int
    missing_pct: float
    duplicate_rows: int
    duplicate_pct: float
    columns: list[ColumnProfile]
    preview_rows: list[dict[str, Any]]
    dtypes: dict[str, str]
    issues: list[dict[str, Any]] = field(default_factory=list)
    duplicate_columns: list[str] = field(default_factory=list)
    empty_columns: list[str] = field(default_factory=list)
    ambiguous_date_columns: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractResult:
    dataframe: pd.DataFrame
    profile: ExtractionProfile


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        return False
    return isinstance(value, str) and value.strip().lower() in MISSING_TOKENS


def json_value(value: Any) -> Any:
    if is_missing(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def date_value_counts(series: pd.Series) -> tuple[int, int]:
    values = [str(value).strip() for value in series if not is_missing(value)]
    unambiguous = sum(
        1 for value in values if ISO_DATE_PATTERN.fullmatch(value) or YEAR_FIRST_DATE_PATTERN.fullmatch(value)
    )
    ambiguous = sum(
        1
        for value in values
        if AMBIGUOUS_DATE_PATTERN.fullmatch(value)
        and not (ISO_DATE_PATTERN.fullmatch(value) or YEAR_FIRST_DATE_PATTERN.fullmatch(value))
    )
    return unambiguous, ambiguous


def infer_column_type(series: pd.Series) -> str:
    present = [str(value).strip() for value in series if not is_missing(value)]
    if not present:
        return "Empty"
    numeric = sum(1 for value in present if _is_numeric(value))
    booleans = sum(1 for value in present if value.lower() in BOOLEAN_TOKENS)
    unambiguous_dates, ambiguous_dates = date_value_counts(series)

    def ratio(count: int) -> float:
        return count / len(present)

    if ratio(booleans) >= 0.95:
        return "Boolean"
    if ratio(numeric) >= 0.9 and unambiguous_dates == 0:
        return "Numeric"
    if unambiguous_dates / len(present) >= 0.8:
        return "Date"
    if ambiguous_dates / len(present) >= 0.8:
        return "Mixed"
    if ratio(numeric) >= 0.5 or unambiguous_dates / len(present) >= 0.5:
        return "Mixed"
    return "Text"


def _is_numeric(value: str) -> bool:
    try:
        float(value.replace(",", ""))
    except ValueError:
        return False
    return True


def _read_csv(path: Path) -> tuple[pd.DataFrame, str, list[str]]:
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CSV file must be UTF-8 encoded; the file could not be decoded") from error
    try:
        header = next(csv.reader(io.StringIO(text)))
    except StopIteration as error:
        raise ValueError("CSV file is empty") from error
    counts = Counter(name.strip() for name in header)
    duplicates = sorted(name for name, count in counts.items() if count > 1 and name)
    if duplicates:
        raise ValueError(f"Duplicate CSV column names are not supported: {', '.join(duplicates)}")
    try:
        frame = pd.read_csv(
            io.StringIO(text),
            dtype=str,
            keep_default_na=False,
            skip_blank_lines=True,
            on_bad_lines="error",
        )
    except pd.errors.ParserError as error:
        raise ValueError(f"Malformed CSV file: {error}") from error
    return frame, "CSV data", duplicates


def _read_xlsx(path: Path) -> tuple[pd.DataFrame, str, list[str]]:
    workbook = pd.ExcelFile(path, engine="openpyxl")
    sheet_name = str(workbook.sheet_names[0])
    frame = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object, engine="openpyxl")
    workbook.close()
    return frame, sheet_name, []


def _read_json(path: Path) -> tuple[pd.DataFrame, str, list[str]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = next((value for value in payload.values() if isinstance(value, list)), [payload])
    else:
        raise ValueError("JSON file must contain a record list")
    frame = pd.DataFrame.from_records(records)
    return frame, "JSON records", []


def build_profile(
    frame: pd.DataFrame,
    sheet_name: str,
    *,
    duplicate_columns: list[str] | None = None,
) -> ExtractionProfile:
    if len(frame) == 0:
        raise ValueError("Dataset does not contain any data rows")
    if frame.shape[1] == 0:
        raise ValueError("Dataset does not contain any usable columns")

    duplicate_columns = duplicate_columns or []
    issues: list[dict[str, Any]] = []
    empty_columns: list[str] = []
    ambiguous_date_columns: list[str] = []
    columns: list[ColumnProfile] = []
    missing_cells = 0

    for column in frame.columns:
        series = frame[column]
        missing = int(series.map(is_missing).sum())
        present = series[~series.map(is_missing)]
        missing_cells += missing
        name = str(column)
        if missing == len(frame):
            empty_columns.append(name)
            continue
        unambiguous_dates, ambiguous_dates = date_value_counts(series)
        inferred_type = infer_column_type(series)
        if ambiguous_dates:
            ambiguous_date_columns.append(name)
            issues.append(
                {
                    "code": "ambiguous_date",
                    "severity": "warning",
                    "field": name,
                    "message": (
                        f"{ambiguous_dates} value(s) use an ambiguous day/month order and were not parsed. "
                        "Supply an explicit date convention during mapping review."
                    ),
                }
            )
        if inferred_type == "Mixed":
            issues.append(
                {
                    "code": "inconsistent_type",
                    "severity": "warning",
                    "field": name,
                    "message": "Values are not consistently typed; the column requires manual review.",
                }
            )
        samples: list[str] = []
        for value in present.head(20):
            text = str(json_value(value))
            if text not in samples:
                samples.append(text[:80])
            if len(samples) == 3:
                break
        columns.append(
            ColumnProfile(
                name=name,
                inferred_type=inferred_type,
                missing=missing,
                missing_pct=round((missing / len(frame)) * 100, 2),
                unique_sample=int(present.astype(str).nunique()),
                sample_values=samples,
                ambiguous_dates=ambiguous_dates,
            )
        )

    for name in empty_columns:
        issues.append(
            {
                "code": "empty_column",
                "severity": "warning",
                "field": name,
                "message": "The column contains no usable values and was excluded from mapping suggestions.",
            }
        )

    total_cells = len(frame) * len(frame.columns)
    duplicate_rows = int(frame.duplicated().sum())
    preview_rows = [
        {str(column): json_value(value) for column, value in row.items()}
        for row in frame.head(5).to_dict(orient="records")
    ]
    return ExtractionProfile(
        sheet_name=sheet_name,
        row_count=len(frame),
        column_count=len(frame.columns),
        missing_cells=missing_cells,
        missing_pct=round((missing_cells / total_cells) * 100, 2),
        duplicate_rows=duplicate_rows,
        duplicate_pct=round((duplicate_rows / len(frame)) * 100, 2),
        columns=columns,
        preview_rows=preview_rows,
        dtypes={str(column): str(dtype) for column, dtype in frame.dtypes.items()},
        issues=issues,
        duplicate_columns=duplicate_columns,
        empty_columns=empty_columns,
        ambiguous_date_columns=ambiguous_date_columns,
    )


def extract_dataset(path: str | Path, file_format: FileFormat) -> ExtractResult:
    source = Path(path)
    if file_format == FileFormat.CSV:
        frame, sheet_name, duplicates = _read_csv(source)
    elif file_format == FileFormat.XLSX:
        frame, sheet_name, duplicates = _read_xlsx(source)
    elif file_format == FileFormat.JSON:
        frame, sheet_name, duplicates = _read_json(source)
    else:
        raise ValueError(f"Unsupported file format: {file_format}")
    return ExtractResult(
        dataframe=frame,
        profile=build_profile(frame, sheet_name, duplicate_columns=duplicates),
    )
