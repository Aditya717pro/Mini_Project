from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.models.enums import FileFormat

MISSING_TOKENS = {"", "na", "n/a", "null", "none", "nan", "<na>"}
DATE_PATTERN = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}|^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$")
BOOLEAN_TOKENS = {"true", "false", "yes", "no", "y", "n"}


@dataclass
class ColumnProfile:
    name: str
    inferred_type: str
    missing: int
    missing_pct: float
    unique_sample: int
    sample_values: list[str]


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


def infer_column_type(series: pd.Series) -> str:
    present = [str(value).strip() for value in series if not is_missing(value)]
    if not present:
        return "Empty"
    numeric = sum(1 for value in present if _is_numeric(value))
    dates = sum(1 for value in present if bool(DATE_PATTERN.match(value)) and not _is_numeric(value))
    booleans = sum(1 for value in present if value.lower() in BOOLEAN_TOKENS)
    def ratio(count: int) -> float:
        return count / len(present)

    if ratio(booleans) >= 0.95:
        return "Boolean"
    if ratio(numeric) >= 0.9:
        return "Numeric"
    if ratio(dates) >= 0.8:
        return "Date"
    if ratio(numeric) >= 0.5 or ratio(dates) >= 0.5:
        return "Mixed"
    return "Text"


def _is_numeric(value: str) -> bool:
    try:
        float(value.replace(",", ""))
    except ValueError:
        return False
    return True


def _read_csv(path: Path) -> tuple[pd.DataFrame, str]:
    frame = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
        skip_blank_lines=True,
    )
    return frame, "CSV data"


def _read_xlsx(path: Path) -> tuple[pd.DataFrame, str]:
    workbook = pd.ExcelFile(path, engine="openpyxl")
    sheet_name = str(workbook.sheet_names[0])
    frame = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object, engine="openpyxl")
    workbook.close()
    return frame, sheet_name


def _read_json(path: Path) -> tuple[pd.DataFrame, str]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = next((value for value in payload.values() if isinstance(value, list)), [payload])
    else:
        raise ValueError("JSON file must contain a record list")
    frame = pd.DataFrame.from_records(records)
    return frame, "JSON records"


def build_profile(frame: pd.DataFrame, sheet_name: str) -> ExtractionProfile:
    frame = frame.dropna(axis=1, how="all")
    if frame.empty or frame.shape[1] == 0:
        raise ValueError("Dataset does not contain any usable columns")
    if frame.shape[0] == 0:
        raise ValueError("Dataset does not contain any data rows")

    columns: list[ColumnProfile] = []
    missing_cells = 0
    for column in frame.columns:
        series = frame[column]
        missing = int(series.map(is_missing).sum())
        present = series[~series.map(is_missing)]
        missing_cells += missing
        samples = []
        for value in present.head(20):
            text = str(json_value(value))
            if text not in samples:
                samples.append(text[:80])
            if len(samples) == 3:
                break
        columns.append(
            ColumnProfile(
                name=str(column),
                inferred_type=infer_column_type(series),
                missing=missing,
                missing_pct=round((missing / len(frame)) * 100, 2),
                unique_sample=int(present.astype(str).nunique()),
                sample_values=samples,
            )
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
        missing_pct=round((missing_cells / total_cells) * 100, 2) if total_cells else 0.0,
        duplicate_rows=duplicate_rows,
        duplicate_pct=round((duplicate_rows / len(frame)) * 100, 2),
        columns=columns,
        preview_rows=preview_rows,
        dtypes={str(column): str(dtype) for column, dtype in frame.dtypes.items()},
    )


def extract_dataset(path: str | Path, file_format: FileFormat) -> ExtractResult:
    source = Path(path)
    if file_format == FileFormat.CSV:
        frame, sheet_name = _read_csv(source)
    elif file_format == FileFormat.XLSX:
        frame, sheet_name = _read_xlsx(source)
    elif file_format == FileFormat.JSON:
        frame, sheet_name = _read_json(source)
    else:
        raise ValueError(f"Unsupported file format: {file_format}")
    return ExtractResult(dataframe=frame, profile=build_profile(frame, sheet_name))
