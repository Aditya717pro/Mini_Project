from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import HTTPException

from app.core.config import Settings
from app.services.storage_paths import relative_path, resolve_within_root


def _safe_component(value: str) -> str:
    if not value or value in {".", ".."} or Path(value).name != value or "/" in value or "\\" in value:
        raise ValueError("Unsafe report path component")
    return value


class ResearchReportStorageService:
    def __init__(self, settings: Settings):
        self.base = Path(settings.synthmed_storage_dir).resolve() / "research_reports"
        self.base.mkdir(parents=True, exist_ok=True)

    def save(self, report_id: str, content: bytes, *, filename: str = "report.pdf") -> tuple[Path, str]:
        safe_id = _safe_component(report_id)
        safe_name = Path(filename).name
        if safe_name != filename or safe_name in {"", ".", ".."} or not safe_name.endswith(".pdf"):
            raise ValueError("Unsafe report filename")
        directory = self.base / safe_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / safe_name
        with target.open("xb") as handle:
            handle.write(content)
        return target, f"research_reports/{relative_path(self.base, target)}"

    def resolve(self, stored_path: str) -> Path:
        candidate = Path(stored_path)
        parts = candidate.parts
        if not parts or parts[0] != "research_reports":
            raise ValueError("Stored path is outside the research reports category")
        return resolve_within_root(
            self.base,
            str(Path(*parts[1:])),
            allow_absolute_legacy=False,
            require_file=True,
        )

    def verify(self, stored_path: str, expected_checksum: str) -> tuple[Path, bytes]:
        try:
            path = self.resolve(stored_path)
            content = path.read_bytes()
        except (ValueError, FileNotFoundError, OSError) as error:
            raise HTTPException(status_code=404, detail="Report file is not available.") from error
        if not content.startswith(b"%PDF-") or b"%%EOF" not in content:
            raise HTTPException(status_code=409, detail="Report file failed format verification.")
        actual = hashlib.sha256(content).hexdigest()
        if expected_checksum and actual != expected_checksum:
            raise HTTPException(status_code=409, detail="Report file failed checksum verification.")
        return path, content
