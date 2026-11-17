from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings

Validator = Callable[[Path], None]


def _safe_component(value: str) -> str:
    if not value or value in {".", ".."} or Path(value).name != value or "/" in value or "\\" in value:
        raise ValueError(f"Unsafe storage path component: {value}")
    return value


class StorageService:
    def __init__(self, settings: Settings):
        self.raw_root = Path(settings.raw_storage_dir).resolve()
        self.processed_root = Path(settings.processed_storage_dir).resolve()
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.processed_root.mkdir(parents=True, exist_ok=True)

    def save_raw(self, dataset_id: str, version_label: str, filename: str, content: bytes) -> Path:
        dataset_id = _safe_component(dataset_id)
        filename = _safe_component(Path(filename).name)
        directory = self.raw_root / dataset_id[:2] / dataset_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{version_label}-{dataset_id[:8]}-{filename}"
        target.write_bytes(content)
        return target

    def processed_target(self, dataset_id: str, version_id: str, filename: str) -> Path:
        dataset_id = _safe_component(dataset_id)
        version_id = _safe_component(version_id)
        filename = _safe_component(filename)
        return self.processed_root / dataset_id[:2] / dataset_id / f"{version_id[:8]}-{filename}"

    def publish_processed_batch(
        self,
        dataset_id: str,
        version_id: str,
        files: list[tuple[str, bytes, Validator]],
    ) -> dict[str, Path]:
        targets = {filename: self.processed_target(dataset_id, version_id, filename) for filename, _, _ in files}
        for target in targets.values():
            target.parent.mkdir(parents=True, exist_ok=True)

        staged: list[tuple[Path, Path, bytes | None]] = []
        temp_paths: list[Path] = []
        try:
            for filename, content, validate in files:
                target = targets[filename]
                temp = target.parent / f".{target.name}.{uuid4().hex}.tmp"
                temp_paths.append(temp)
                temp.write_bytes(content)
                validate(temp)
                staged.append((temp, target, target.read_bytes() if target.exists() else None))

            for temp, target, _ in staged:
                os.replace(temp, target)
            return targets
        except Exception:
            for temp in temp_paths:
                temp.unlink(missing_ok=True)
            for _temp, target, previous in staged:
                if previous is None:
                    target.unlink(missing_ok=True)
                else:
                    restore = target.parent / f".{target.name}.{uuid4().hex}.restore"
                    try:
                        restore.write_bytes(previous)
                        os.replace(restore, target)
                    finally:
                        restore.unlink(missing_ok=True)
            raise

    def resolve(self, relative_or_absolute_path: str, *, kind: str) -> Path:
        base = self.raw_root if kind == "raw" else self.processed_root
        candidate = Path(relative_or_absolute_path)
        if not candidate.is_absolute():
            candidate = base / candidate
        resolved = candidate.resolve()
        if not resolved.is_relative_to(base):
            raise ValueError("Resolved file path is outside the storage root")
        if not resolved.is_file():
            raise FileNotFoundError("Stored file does not exist")
        return resolved
