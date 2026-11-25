from __future__ import annotations

from pathlib import Path


def resolve_within_root(
    root: Path,
    stored_path: str,
    *,
    allow_absolute_legacy: bool = True,
    require_file: bool = True,
) -> Path:
    if not isinstance(stored_path, str) or not stored_path.strip() or "\x00" in stored_path:
        raise ValueError("Stored path is invalid")
    base = Path(root).resolve()
    candidate = Path(stored_path)
    if candidate.is_absolute():
        if not allow_absolute_legacy:
            raise ValueError("Absolute stored paths are not allowed")
        resolved = candidate.resolve()
    else:
        if candidate.drive:
            raise ValueError("Stored path contains a drive component")
        resolved = (base / candidate).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError("Resolved file path is outside the storage root")
    if require_file and not resolved.is_file():
        raise FileNotFoundError("Stored file does not exist")
    return resolved


def relative_path(root: Path, path: Path) -> str:
    base = Path(root).resolve()
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError("Path is outside the storage root")
    return resolved.relative_to(base).as_posix()


def public_reference(value: str | None) -> str | None:
    if not value:
        return None
    candidate = Path(value)
    if candidate.is_absolute() or candidate.drive:
        return candidate.name
    return value
