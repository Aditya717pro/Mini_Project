import subprocess
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.storage_paths import relative_path, resolve_within_root
from app.services.storage_service import StorageService
from app.synthmed.services.storage_service import SynthMedStorageService


def test_resolve_within_root_accepts_relative_and_contained_absolute(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    target = root / "source.csv"
    target.write_text("id\n1\n", encoding="utf-8")

    assert resolve_within_root(root, "source.csv") == target.resolve()
    assert resolve_within_root(root, str(target)) == target.resolve()


def test_resolve_within_root_rejects_traversal_and_outside_absolute(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("secret\n", encoding="utf-8")

    with pytest.raises(ValueError):
        resolve_within_root(root, "../outside.csv")
    with pytest.raises(ValueError):
        resolve_within_root(root, str(outside))


def test_resolve_within_root_rejects_directory(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    directory = root / "nested"
    directory.mkdir()

    with pytest.raises(FileNotFoundError):
        resolve_within_root(root, "nested")


def test_resolve_within_root_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("secret\n", encoding="utf-8")
    link = root / "link.csv"
    try:
        link.symlink_to(outside)
    except OSError:
        link = None
    if link is not None and not link.is_symlink():
        link = None

    if link is not None:
        stored_path = "link.csv"
    else:
        outside_dir = tmp_path / "outside_dir"
        outside_dir.mkdir()
        (outside_dir / "secret.csv").write_text("secret\n", encoding="utf-8")
        junction = root / "link_dir"
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(outside_dir)],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip("Neither symlinks nor directory junctions are available in this environment")
        stored_path = "link_dir/secret.csv"

    with pytest.raises(ValueError):
        resolve_within_root(root, stored_path)


def test_relative_path_is_normalised_and_posix(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    target = root / "nested" / "source.csv"
    target.parent.mkdir(parents=True)
    target.write_text("id\n1\n", encoding="utf-8")

    assert relative_path(root, target) == "nested/source.csv"


def test_storage_service_keeps_raw_and_processed_roots_separate(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        raw_storage_dir=tmp_path / "raw",
        processed_storage_dir=tmp_path / "processed",
    )
    storage = StorageService(settings)
    raw = storage.save_raw("dataset-1", "v1.0", "source.csv", b"id\n1\n")
    processed = storage.publish_processed_batch(
        "dataset-1", "version-1", [("processed.csv", b"id\n1\n", lambda path: None)]
    )["processed.csv"]

    raw_relative = storage.relative_path(raw, kind="raw")
    processed_relative = storage.relative_path(processed, kind="processed")
    assert not Path(raw_relative).is_absolute()
    assert not Path(processed_relative).is_absolute()
    assert storage.resolve(raw_relative, kind="raw") == raw.resolve()
    assert storage.resolve(processed_relative, kind="processed") == processed.resolve()
    with pytest.raises((ValueError, FileNotFoundError)):
        storage.resolve(raw_relative, kind="processed")


def test_synthmed_storage_rejects_cross_root_paths(tmp_path: Path) -> None:
    settings = Settings(environment="test", synthmed_storage_dir=tmp_path / "synthmed")
    storage = SynthMedStorageService(settings)
    source, relative = storage.save_source("dataset-1", "source.csv", b"id\n1\n")

    assert storage.resolve_source(relative) == source.resolve()
    with pytest.raises(ValueError):
        storage.resolve_generated(relative)
    with pytest.raises(ValueError):
        storage.resolve_report(relative)


def test_meddatahub_and_synthmed_roots_are_isolated(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        raw_storage_dir=tmp_path / "raw",
        processed_storage_dir=tmp_path / "processed",
        synthmed_storage_dir=tmp_path / "synthmed",
    )
    meddatahub = StorageService(settings)
    synthmed = SynthMedStorageService(settings)

    raw = meddatahub.save_raw("dataset-1", "v1.0", "source.csv", b"id\n1\n")
    source, _ = synthmed.save_source("dataset-1", "source.csv", b"id\n1\n")

    with pytest.raises((ValueError, FileNotFoundError)):
        synthmed.resolve_source(str(raw))
    with pytest.raises((ValueError, FileNotFoundError)):
        synthmed.resolve_generated(str(raw))
    with pytest.raises((ValueError, FileNotFoundError)):
        meddatahub.resolve(str(source), kind="raw")
    with pytest.raises((ValueError, FileNotFoundError)):
        meddatahub.resolve(str(source), kind="processed")
