from __future__ import annotations

from pathlib import Path

from app.core.config import Settings


def _safe_component(value: str) -> str:
    if not value or value in {".", ".."} or Path(value).name != value or "/" in value or "\\" in value:
        raise ValueError(f"Unsafe storage path component: {value}")
    return value


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in name).strip("._")
    if not cleaned:
        cleaned = "source_file"
    if len(cleaned) > 180:
        suffix = Path(cleaned).suffix
        cleaned = cleaned[: 180 - len(suffix)] + suffix
    return cleaned


class SynthMedStorageService:
    def __init__(self, settings: Settings):
        base = Path(settings.synthmed_storage_dir).resolve()
        self.base = base
        self.sources_root = base / "sources"
        self.generated_root = base / "generated"
        self.reports_root = base / "reports"
        self.sources_root.mkdir(parents=True, exist_ok=True)
        self.generated_root.mkdir(parents=True, exist_ok=True)
        self.reports_root.mkdir(parents=True, exist_ok=True)

    def save_source(self, dataset_id: str, original_filename: str, content: bytes) -> tuple[Path, str]:
        dataset_id = _safe_component(dataset_id)
        safe_name = _safe_filename(original_filename)
        directory = self.sources_root / dataset_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / safe_name
        target.write_bytes(content)
        relative = f"sources/{dataset_id}/{safe_name}"

        return target, relative

    def resolve_source(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("Stored path must be relative")
        resolved = (self.base / candidate).resolve()
        if not resolved.is_relative_to(self.sources_root):
            raise ValueError("Resolved path is outside the SynthMed sources storage root")
        if not resolved.is_file():
            raise FileNotFoundError("Stored source file does not exist")
        return resolved

    def resolve_generated(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("Stored path must be relative")
        resolved = (self.base / candidate).resolve()
        if not resolved.is_relative_to(self.generated_root):
            raise ValueError("Resolved path is outside the SynthMed generated storage root")
        if not resolved.is_file():
            raise FileNotFoundError("Stored generated file does not exist")
        return resolved

    def remove_source(self, relative_path: str) -> None:
        path = self.resolve_source(relative_path)
        path.unlink(missing_ok=True)
        try:
            path.parent.rmdir()
        except OSError:
            pass

    def save_generated(self, dataset_id: str, filename: str, content: bytes) -> tuple[Path, str]:
        dataset_id = _safe_component(dataset_id)
        safe_name = _safe_filename(filename)
        directory = self.generated_root / dataset_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / safe_name
        target.write_bytes(content)
        return target, f"generated/{dataset_id}/{safe_name}"

    def save_report(self, job_id: str, filename: str, content: bytes) -> tuple[Path, str]:
        job_id = _safe_component(job_id)
        safe_name = _safe_filename(filename)
        directory = self.reports_root / job_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / safe_name
        target.write_bytes(content)
        return target, f"reports/{job_id}/{safe_name}"

    def resolve_report(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("Stored path must be relative")
        resolved = (self.base / candidate).resolve()
        if not resolved.is_relative_to(self.reports_root):
            raise ValueError("Resolved path is outside the SynthMed reports storage root")
        if not resolved.is_file():
            raise FileNotFoundError("Stored report file does not exist")
        return resolved

