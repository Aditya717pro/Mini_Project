from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.storage_service import StorageService


def write_processed_csv(dataframe: pd.DataFrame, storage: StorageService, dataset_id: str, version_id: str) -> Path:
    content = dataframe.to_csv(index=False).encode("utf-8")
    return storage.save_processed(dataset_id, version_id, "processed.csv", content)


def write_transformation_log(log: dict[str, Any], storage: StorageService, dataset_id: str, version_id: str) -> Path:
    content = json.dumps(log, indent=2, default=str).encode("utf-8")
    return storage.save_processed(dataset_id, version_id, "transform-log.json", content)
