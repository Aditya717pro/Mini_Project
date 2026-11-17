from pathlib import Path

from app.core.config import Settings


class StorageService:
    def __init__(self, settings: Settings):
        self.raw_root = Path(settings.raw_storage_dir).resolve()
        self.processed_root = Path(settings.processed_storage_dir).resolve()
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.processed_root.mkdir(parents=True, exist_ok=True)

    def save_raw(self, dataset_id: str, version_label: str, filename: str, content: bytes) -> Path:
        suffix = Path(filename).suffix.lower()
        directory = self.raw_root / dataset_id[:2] / dataset_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{version_label}-{dataset_id[:8]}{suffix}"
        target.write_bytes(content)
        return target

    def save_processed(self, dataset_id: str, version_id: str, filename: str, content: bytes) -> Path:
        directory = self.processed_root / dataset_id[:2] / dataset_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{version_id[:8]}-{filename}"
        target.write_bytes(content)
        return target

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
