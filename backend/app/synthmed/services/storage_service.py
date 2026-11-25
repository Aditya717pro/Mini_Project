from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.services.storage_paths import resolve_within_root


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


def _within_category(stored_path: str, category: str) -> str:
    candidate = Path(stored_path)
    if candidate.is_absolute():
        return stored_path
    parts = candidate.parts
    if not parts or parts[0] != category:
        raise ValueError("Stored path is outside the expected storage category")
    return str(Path(*parts[1:]))



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

    def save_version_snapshot(
        self, dataset_id: str, version_id: str, filename: str, content: bytes, *, kind: str
    ) -> tuple[Path, str]:
        if kind not in {"source", "generated"}:
            raise ValueError("Unsupported version snapshot category")
        category = "sources" if kind == "source" else "generated"
        dataset_id = _safe_component(dataset_id)
        version_id = _safe_component(version_id)
        safe_name = _safe_filename(filename)
        root = self.sources_root if category == "sources" else self.generated_root
        directory = root / dataset_id / "versions" / version_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / safe_name
        with target.open("xb") as handle:
            handle.write(content)
        return target, f"{category}/{dataset_id}/versions/{version_id}/{safe_name}"

    def resolve_source(self, relative_path: str) -> Path:
        return resolve_within_root(self.sources_root, _within_category(relative_path, "sources"))

    def resolve_generated(self, relative_path: str) -> Path:
        return resolve_within_root(self.generated_root, _within_category(relative_path, "generated"))

    def resolve_version(self, kind: str, relative_path: str) -> Path:
        return self.resolve_source(relative_path) if kind == "source" else self.resolve_generated(relative_path)



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
        with target.open("xb") as handle:
            handle.write(content)
        return target, f"reports/{job_id}/{safe_name}"

    def resolve_report(self, relative_path: str) -> Path:
        return resolve_within_root(self.reports_root, _within_category(relative_path, "reports"))

