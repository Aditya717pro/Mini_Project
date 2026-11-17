from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.storage_service import StorageService


def _validate_csv(path: Path, *, expected_rows: int, expected_columns: int) -> None:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if len(frame) != expected_rows or len(frame.columns) != expected_columns:
        raise ValueError(
            f"Processed output validation failed: expected {expected_rows} rows and "
            f"{expected_columns} columns, found {len(frame)} and {len(frame.columns)}"
        )
    if frame.columns.duplicated().any():
        raise ValueError("Processed output validation failed: duplicate column names")


def _validate_log(path: Path) -> None:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or "logs" not in payload or "rows_out" not in payload:
        raise ValueError("Processed transformation log validation failed")


def publish_processed_output(
    *,
    dataframe: pd.DataFrame,
    transformation_log: dict[str, Any],
    storage: StorageService,
    dataset_id: str,
    version_id: str,
) -> tuple[Path, Path]:
    csv_content = dataframe.to_csv(index=False).encode("utf-8")
    log_content = json.dumps(transformation_log, indent=2, default=str).encode("utf-8")
    paths = storage.publish_processed_batch(
        dataset_id,
        version_id,
        [
            (
                "processed.csv",
                csv_content,
                lambda path: _validate_csv(
                    path,
                    expected_rows=len(dataframe),
                    expected_columns=len(dataframe.columns),
                ),
            ),
            ("transform-log.json", log_content, _validate_log),
        ],
    )
    return paths["processed.csv"], paths["transform-log.json"]
