from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from fastapi import HTTPException, Request, status
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core.config import Settings
from app.etl.extract import extract_dataset, is_missing
from app.models.audit import AuditLog
from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import FileFormat, UserRole
from app.models.etl import ETLJob
from app.models.user import User
from app.services.audit_service import log_audit
from app.services.storage_paths import public_reference
from app.services.storage_service import StorageService


@event.listens_for(Session, "do_orm_execute")
def _current_version_first(execute_state: Any) -> None:
    statement = execute_state.statement
    if not execute_state.is_select or not isinstance(statement, Select):
        return
    if DatasetVersion not in {description.get("entity") for description in statement.column_descriptions}:
        return
    if statement._order_by_clauses:
        return
    execute_state.statement = statement.order_by(
        DatasetVersion.is_current.desc(), DatasetVersion.version_number.desc()
    )


_raw_reference_sync = threading.local()


@event.listens_for(DatasetVersion.raw_file_path, "set")
def _keep_raw_reference_consistent(target: DatasetVersion, value: Any, oldvalue: Any, _initiator: Any) -> None:
    def unsafe(candidate: Any) -> bool:
        if not isinstance(candidate, str) or not candidate:
            return False
        path = Path(candidate)
        return path.is_absolute() or ".." in path.parts

    if getattr(_raw_reference_sync, "active", False) or not (unsafe(value) or unsafe(oldvalue)):
        return
    dataset = target.dataset
    if dataset is None:
        return
    _raw_reference_sync.active = True
    try:
        for sibling in dataset.versions:
            if sibling is not target and sibling.raw_file_path != value:
                sibling.raw_file_path = value
    finally:
        _raw_reference_sync.active = False


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _naive(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=None) if value is not None and value.tzinfo is not None else value


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return str(value)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _lineage(version: DatasetVersion) -> dict[str, Any]:
    log = version.transformation_log_json or {}
    payload = log.get("lineage") if isinstance(log.get("lineage"), dict) else {}
    return dict(payload)


def parent_version_id(version: DatasetVersion) -> str | None:
    log = version.transformation_log_json or {}
    return _lineage(version).get("parentVersionId") or log.get("parent_version_id")


def version_kind(version: DatasetVersion) -> str:
    kind = _lineage(version).get("kind") or (version.transformation_log_json or {}).get("kind")
    if kind in {"Original", "Processed"}:
        return kind
    return "Processed" if version.processed_file_path else "Original"


def restored_from_version_id(version: DatasetVersion) -> str | None:
    return _lineage(version).get("restoredFromVersionId")


def version_note(version: DatasetVersion) -> str:
    return str(_lineage(version).get("note") or "")


def _transformation_history(version: DatasetVersion) -> list[dict[str, Any]]:
    lineage = _lineage(version)
    history = lineage.get("history")
    if isinstance(history, list):
        return [_json_safe(item) for item in history if isinstance(item, dict)]
    log = version.transformation_log_json or {}
    if not log:
        return []
    return [
        {
            "step": version_kind(version).lower(),
            "versionId": version.id,
            "rowsIn": log.get("rows_in"),
            "rowsOut": log.get("rows_out"),
            "approvedMapping": log.get("approved_mapping") or lineage.get("approvedMapping") or {},
            "unitConversions": lineage.get("unitConversions") or log.get("unit_conversions") or [],
        }
    ]


def _validation_summary(version: DatasetVersion) -> dict[str, Any]:
    lineage = _lineage(version)
    summary = lineage.get("validationSummary")
    if isinstance(summary, dict) and summary:
        return _json_safe(summary)
    log = version.transformation_log_json or {}
    return _json_safe(
        {
            "errors": log.get("error_counts") or {},
            "warnings": log.get("warning_counts") or {},
            "invalid": log.get("invalid_counts") or {},
            "reviewCount": log.get("review_count", 0),
            "duplicateCount": log.get("duplicate_count", 0),
        }
    )


def _summaries(frame: pd.DataFrame) -> dict[str, Any]:
    schema: list[dict[str, str]] = []
    missing: dict[str, Any] = {}
    distribution: dict[str, Any] = {}
    for column in frame.columns:
        name = str(column)
        series = frame[column]
        missing_flags = series.map(is_missing)
        present = series[~missing_flags]
        schema.append({"name": name, "dtype": str(series.dtype)})
        missing[name] = {
            "missing": int(missing_flags.sum()),
            "missingPct": round(float(missing_flags.mean() * 100), 4) if len(series) else 0.0,
        }
        if pd.api.types.is_numeric_dtype(present):
            numeric = pd.to_numeric(present, errors="coerce").dropna()
            distribution[name] = {
                "kind": "numeric",
                "distinct": int(numeric.nunique()),
                "mean": _json_safe(numeric.mean()) if len(numeric) else None,
                "std": _json_safe(numeric.std(ddof=0)) if len(numeric) else None,
                "min": _json_safe(numeric.min()) if len(numeric) else None,
                "max": _json_safe(numeric.max()) if len(numeric) else None,
            }
        else:
            counts = present.astype("string").value_counts()
            distribution[name] = {
                "kind": "categorical",
                "distinct": int(counts.size),
                "topCounts": [int(value) for value in counts.head(10)],
            }
    return {"schema": schema, "missing": missing, "distribution": distribution}


def _sanitised_profile(profile: dict[str, Any]) -> dict[str, Any]:
    result = _json_safe(profile)
    if isinstance(result, dict):
        result["preview_rows"] = []
        for column in result.get("columns") or []:
            if isinstance(column, dict):
                column["sample_values"] = []
    return result


def _resolve_version_file(settings: Settings, version: DatasetVersion) -> tuple[Path, str]:
    storage = StorageService(settings)
    try:
        if version.processed_file_path:
            return storage.resolve(version.processed_file_path, kind="processed"), "processed"
        return storage.resolve(version.raw_file_path, kind="raw"), "raw"
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Version file is missing or outside the expected storage root",
        ) from error


def _load_frame(settings: Settings, dataset: Dataset, version: DatasetVersion) -> tuple[pd.DataFrame, Path, str]:
    path, kind = _resolve_version_file(settings, version)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version file is missing on disk")
    file_format = FileFormat.CSV if kind == "processed" else dataset.format
    try:
        return extract_dataset(path, file_format).dataframe, path, kind
    except (ValueError, OSError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version file could not be read: {error}",
        ) from error


def _versions(dataset: Dataset) -> list[DatasetVersion]:
    return sorted(
        dataset.versions,
        key=lambda item: (item.is_current, item.version_number),
        reverse=True,
    )


def _current(dataset: Dataset) -> DatasetVersion | None:
    return next((version for version in dataset.versions if version.is_current), None)


def _next_number(dataset: Dataset) -> int:
    return max((version.version_number for version in dataset.versions), default=0) + 1


def _next_label(previous: DatasetVersion | None, *, restored: bool = False, schema_changed: bool = False) -> str:
    label = str(previous.version_label) if previous else "v1.0"
    major_text, _, minor_text = label.removeprefix("v").partition(".")
    try:
        major, minor = int(major_text), int(minor_text)
    except ValueError:
        major, minor = 1, max((previous.version_number if previous else 1) - 1, 0)
    if restored:
        return f"v{major}.{minor + 1}"
    if schema_changed and previous is not None and version_kind(previous) == "Processed":
        return f"v{major + 1}.0"
    return f"v{major}.{minor + 1}"


def _deactivate_current(dataset: Dataset) -> None:
    for version in dataset.versions:
        version.is_current = False


def _copy_to_version(
    storage: StorageService,
    dataset: Dataset,
    *,
    version_id: str,
    label: str,
    filename: str,
    content: bytes,
    kind: str,
) -> tuple[Path, str]:
    safe_name = Path(filename).name or ("processed.csv" if kind == "processed" else "source.csv")
    if kind == "processed":
        targets = storage.publish_processed_batch(
            dataset.id,
            version_id,
            [(safe_name, content, lambda _path: None)],
        )
        target = targets[safe_name]
        return target, storage.relative_path(target, kind="processed")
    target = storage.save_raw(dataset.id, label, safe_name, content)
    return target, storage.relative_path(target, kind="raw")


def _audit_lineage(
    db: Session,
    *,
    action: str,
    dataset: Dataset,
    version: DatasetVersion,
    user: User,
    details: dict[str, Any],
    request: Request | None,
) -> None:
    payload = _json_safe(
        {
            "datasetId": dataset.id,
            "versionId": version.id,
            "versionLabel": version.version_label,
            "parentVersionId": parent_version_id(version),
            **details,
        }
    )
    log_audit(
        db,
        action=action,
        resource_type="dataset",
        resource_id=dataset.id,
        actor_id=user.id,
        details=payload,
        request=request,
    )
    log_audit(
        db,
        action="dataset.lineage",
        resource_type="dataset_version",
        resource_id=version.id,
        actor_id=user.id,
        details=payload,
        request=request,
    )


def version_item(settings: Settings, dataset: Dataset, version: DatasetVersion | None) -> dict[str, Any]:
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset version not found")
    try:
        path, _ = _resolve_version_file(settings, version)
        available = path.exists()
    except HTTPException:
        available = False
    if available:
        try:
            summary = _summaries(_load_frame(settings, dataset, version)[0])
        except HTTPException:
            summary = {"schema": [], "missing": {}, "distribution": {}}
    else:
        summary = {"schema": [], "missing": {}, "distribution": {}}
    return _json_safe(
        {
            "id": version.id,
            "versionNumber": version.version_number,
            "versionLabel": version.version_label,
            "kind": version_kind(version),
            "recordCount": version.record_count,
            "columnCount": version.column_count,
            "createdAt": _iso(version.created_at),
            "creator": dataset.owner_id,
            "checksumSha256": version.checksum_sha256,
            "isCurrent": bool(version.is_current),
            "rawFilePath": public_reference(version.raw_file_path),
            "processedFilePath": public_reference(version.processed_file_path),
            "parentVersionId": parent_version_id(version),
            "transformationHistory": _transformation_history(version),
            "validationSummary": _validation_summary(version),
            "fileAvailable": available,
            "datasetSchema": summary["schema"],
            "missingSummary": summary["missing"],
            "distributionSummary": summary["distribution"],
            "restoredFromVersionId": restored_from_version_id(version),
            "note": version_note(version),
        }
    )


def get_history(db: Session, settings: Settings, dataset: Dataset) -> dict[str, Any]:
    versions = _versions(dataset)
    current = next((version for version in versions if version.is_current), versions[0] if versions else None)
    updated = max(
        [value for value in (_naive(dataset.updated_at), *(_naive(v.updated_at) for v in versions)) if value],
        default=None,
    )
    return {
        "datasetId": dataset.id,
        "datasetName": dataset.title,
        "datasetType": dataset.format.value,
        "ownerId": dataset.owner_id,
        "currentVersion": current.version_label if current else "",
        "totalVersions": len(versions),
        "lastUpdatedAt": _iso(updated),
        "versions": [version_item(settings, dataset, version) for version in versions],
    }


def get_version(db: Session, settings: Settings, dataset: Dataset, version_id: str) -> dict[str, Any]:
    version = next((item for item in dataset.versions if item.id == version_id), None)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset version not found")
    return version_item(settings, dataset, version)


def create_processed_version(
    db: Session,
    *,
    settings: Settings,
    dataset: Dataset,
    job: ETLJob,
    actor: User,
    pipeline: Any,
    version_id: str | None = None,
    request: Request | None = None,
) -> DatasetVersion:
    previous = _current(dataset)
    if previous is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dataset has no original version")
    previous_kind = version_kind(previous)
    schema_changed = False
    if previous_kind == "Processed":
        previous_columns = {str(column["name"]) for column in _summaries(pipeline.transformed.dataframe)["schema"]}
        logged = (previous.profile_json or {}).get("processedSchema") or []
        logged_columns = {str(column.get("name")) for column in logged if isinstance(column, dict)}
        schema_changed = bool(logged_columns) and previous_columns != logged_columns
    label = _next_label(previous, schema_changed=schema_changed)
    number = _next_number(dataset)
    version_id = version_id or str(uuid4())
    path = Path(pipeline.processed_path)
    content = path.read_bytes()
    storage = StorageService(settings)
    processed_relative = storage.relative_path(path, kind="processed")
    summaries = _summaries(pipeline.transformed.dataframe)
    profile = _sanitised_profile(pipeline.extracted.profile.as_dict())
    profile.update(
        {
            "processedSchema": summaries["schema"],
            "processedMissingSummary": summaries["missing"],
            "processedDistributionSummary": summaries["distribution"],
        }
    )
    log = dict(pipeline.transformation_log or {})
    lineage = {
        "event": "etl_processed",
        "kind": "Processed",
        "parentVersionId": previous.id,
        "sourceDatasetId": dataset.id,
        "sourceVersionId": previous.id,
        "etlJobId": job.id,
        "approvedMapping": dict(job.approved_mapping_json or {}),
        "approvedById": job.approved_by_id,
        "approvedByName": job.approver.email if job.approver else None,
        "approvedAt": _iso(job.approved_at),
        "humanApproverId": job.approved_by_id,
        "unitConversions": _json_safe(log.get("unit_conversions") or log.get("unitConversions") or []),
        "createdAt": _iso(datetime.now(UTC)),
        "history": [
            {
                "step": "etl_processed",
                "versionId": version_id,
                "parentVersionId": previous.id,
                "etlJobId": job.id,
                "approvedById": job.approved_by_id,
                "approvedAt": _iso(job.approved_at),
                "approvedMapping": dict(job.approved_mapping_json or {}),
                "unitConversions": _json_safe(log.get("unit_conversions") or log.get("unitConversions") or []),
                "rowsIn": log.get("rows_in"),
                "rowsOut": log.get("rows_out"),
            }
        ],
    }
    log.update(
        {
            "kind": "Processed",
            "parent_version_id": previous.id,
            "lineage": lineage,
            "processed_file_path": processed_relative,
        }
    )
    _deactivate_current(dataset)
    version = DatasetVersion(
        id=version_id,
        dataset_id=dataset.id,
        version_number=number,
        version_label=label,
        raw_file_path=previous.raw_file_path,
        processed_file_path=processed_relative,
        checksum_sha256=sha256_bytes(content),
        file_size_bytes=len(content),
        record_count=len(pipeline.transformed.dataframe),
        column_count=len(pipeline.transformed.dataframe.columns),
        profile_json=_json_safe(profile),
        transformation_log_json=_json_safe(log),
        is_current=True,
    )
    db.add(version)
    dataset.versions.append(version)
    dataset.current_version_number = number
    _audit_lineage(
        db,
        action="dataset.version_created",
        dataset=dataset,
        version=version,
        user=actor,
        details={
            "kind": "Processed",
            "etlJobId": job.id,
            "checksumSha256": version.checksum_sha256,
            "approvedById": job.approved_by_id,
            "approvedAt": _iso(job.approved_at),
        },
        request=request,
    )
    return version


def create_snapshot_version(
    db: Session,
    *,
    settings: Settings,
    dataset: Dataset,
    user: User,
    note: str = "",
    request: Request | None = None,
) -> DatasetVersion:
    if dataset.owner_id != user.id and user.role != UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the dataset owner may create versions.")
    previous = _current(dataset)
    if previous is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dataset has no version to snapshot")
    path, kind = _resolve_version_file(settings, previous)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version file is missing on disk")
    content = path.read_bytes()
    digest = sha256_bytes(content)
    if previous.checksum_sha256 and digest != previous.checksum_sha256:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Checksum mismatch; snapshot blocked.")
    message = note.strip()
    if not message and digest == previous.checksum_sha256:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No file change or checkpoint note was supplied; snapshot skipped",
        )
    number = _next_number(dataset)
    label = _next_label(previous)
    version_id = str(uuid4())
    storage = StorageService(settings)
    filename = Path(previous.processed_file_path or previous.raw_file_path).name
    _, relative = _copy_to_version(
        storage,
        dataset,
        version_id=version_id,
        label=label,
        filename=filename,
        content=content,
        kind=kind,
    )
    frame = _load_frame(settings, dataset, previous)[0]
    summaries = _summaries(frame)
    profile = _sanitised_profile(previous.profile_json or {})
    profile.update(
        {
            "schema": summaries["schema"],
            "missingSummary": summaries["missing"],
            "distributionSummary": summaries["distribution"],
        }
    )
    log = dict(previous.transformation_log_json or {})
    lineage = dict(_lineage(previous))
    history = _transformation_history(previous)
    history.append(
        {
            "step": "snapshot",
            "versionId": version_id,
            "parentVersionId": previous.id,
            "note": message,
            "checksumSha256": digest,
            "createdAt": _iso(datetime.now(UTC)),
        }
    )
    lineage.update(
        {
            "event": "snapshot",
            "kind": "Processed" if kind == "processed" else "Original",
            "parentVersionId": previous.id,
            "note": message,
            "history": history,
            "createdAt": _iso(datetime.now(UTC)),
        }
    )
    log.update({"kind": lineage["kind"], "parent_version_id": previous.id, "lineage": lineage})
    _deactivate_current(dataset)
    version = DatasetVersion(
        id=version_id,
        dataset_id=dataset.id,
        version_number=number,
        version_label=label,
        raw_file_path=relative if kind == "raw" else previous.raw_file_path,
        processed_file_path=relative if kind == "processed" else None,
        checksum_sha256=digest,
        file_size_bytes=len(content),
        record_count=len(frame),
        column_count=len(frame.columns),
        profile_json=_json_safe(profile),
        transformation_log_json=_json_safe(log),
        is_current=True,
    )
    db.add(version)
    dataset.versions.append(version)
    dataset.current_version_number = number
    _audit_lineage(
        db,
        action="dataset.version_created",
        dataset=dataset,
        version=version,
        user=user,
        details={"kind": lineage["kind"], "event": "snapshot", "note": message, "checksumSha256": digest},
        request=request,
    )
    return version


def _column_map(columns: list[dict[str, Any]]) -> dict[str, str]:
    return {str(item.get("name")): str(item.get("dtype", "")) for item in columns if isinstance(item, dict)}


def compare_versions(
    db: Session,
    settings: Settings,
    dataset: Dataset,
    version_a_id: str,
    version_b_id: str,
) -> dict[str, Any]:
    by_id = {version.id: version for version in dataset.versions}
    if version_a_id not in by_id or version_b_id not in by_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Both versions must belong to this dataset",
        )
    first, second = by_id[version_a_id], by_id[version_b_id]
    frame_a, path_a, kind_a = _load_frame(settings, dataset, first)
    frame_b, path_b, kind_b = _load_frame(settings, dataset, second)
    summary_a, summary_b = _summaries(frame_a), _summaries(frame_b)
    schema_a, schema_b = _column_map(summary_a["schema"]), _column_map(summary_b["schema"])
    added = [{"name": name, "dtype": dtype} for name, dtype in schema_b.items() if name not in schema_a]
    removed = [{"name": name, "dtype": dtype} for name, dtype in schema_a.items() if name not in schema_b]
    dtype_changes = [
        {"name": name, "from": dtype, "to": schema_b[name]}
        for name, dtype in schema_a.items()
        if name in schema_b and schema_b[name] != dtype
    ]
    missing_changes = []
    for name in schema_a.keys() & schema_b.keys():
        before = summary_a["missing"].get(name, {}).get("missingPct", 0.0)
        after = summary_b["missing"].get(name, {}).get("missingPct", 0.0)
        if before != after:
            missing_changes.append({"column": name, "from": before, "to": after, "delta": round(after - before, 4)})
    numeric_changes = []
    categorical_changes = []
    for name in schema_a.keys() & schema_b.keys():
        dist_a = summary_a["distribution"].get(name, {})
        dist_b = summary_b["distribution"].get(name, {})
        if dist_a.get("kind") == "numeric" and dist_b.get("kind") == "numeric":
            for metric in ("mean", "std", "min", "max"):
                before, after = dist_a.get(metric), dist_b.get(metric)
                if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                    numeric_changes.append(
                        {
                            "column": name,
                            "metric": metric,
                            "from": before,
                            "to": after,
                            "delta": round(after - before, 4),
                        }
                    )
        if dist_a.get("kind") == "categorical" and dist_b.get("kind") == "categorical":
            for metric in ("distinct",):
                before, after = dist_a.get(metric), dist_b.get(metric)
                if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                    categorical_changes.append(
                        {"column": name, "metric": metric, "from": before, "to": after, "delta": after - before}
                    )
    checksum_a = sha256_file(path_a)
    checksum_b = sha256_file(path_b)
    payload = {
        "datasetId": dataset.id,
        "datasetName": dataset.title,
        "a": {
            "id": first.id,
            "versionLabel": first.version_label,
            "versionNumber": first.version_number,
            "kind": version_kind(first),
            "fileKind": kind_a,
            "checksumSha256": first.checksum_sha256,
            "actualChecksumSha256": checksum_a,
            "checksumMatchesRecorded": checksum_a == first.checksum_sha256,
            "recordCount": first.record_count,
            "columnCount": first.column_count,
            "schema": summary_a["schema"],
            "missingSummary": summary_a["missing"],
            "distributionSummary": summary_a["distribution"],
            "transformationHistory": _transformation_history(first),
            "validationSummary": _validation_summary(first),
        },
        "b": {
            "id": second.id,
            "versionLabel": second.version_label,
            "versionNumber": second.version_number,
            "kind": version_kind(second),
            "fileKind": kind_b,
            "checksumSha256": second.checksum_sha256,
            "actualChecksumSha256": checksum_b,
            "checksumMatchesRecorded": checksum_b == second.checksum_sha256,
            "recordCount": second.record_count,
            "columnCount": second.column_count,
            "schema": summary_b["schema"],
            "missingSummary": summary_b["missing"],
            "distributionSummary": summary_b["distribution"],
            "transformationHistory": _transformation_history(second),
            "validationSummary": _validation_summary(second),
        },
        "comparison": {
            "schema": {
                "added": added,
                "removed": removed,
                "dtypeChanges": dtype_changes,
                "unchanged": sorted(schema_a.keys() & schema_b.keys()),
            },
            "schemaAdded": added,
            "schemaRemoved": removed,
            "dtypeChanges": dtype_changes,
            "missing": {
                "added": sorted(set(summary_b["missing"]) - set(summary_a["missing"])),
                "removed": sorted(set(summary_a["missing"]) - set(summary_b["missing"])),
                "changed": missing_changes,
            },
            "numericDistribution": numeric_changes,
            "categoricalDistribution": categorical_changes,
            "recordCountDelta": len(frame_b) - len(frame_a),
            "columnCountDelta": len(frame_b.columns) - len(frame_a.columns),
            "checksumChanged": checksum_a != checksum_b,
            "transformationHistory": {
                "a": _transformation_history(first),
                "b": _transformation_history(second),
            },
            "validationSummary": {
                "a": _validation_summary(first),
                "b": _validation_summary(second),
            },
        },
    }
    return _json_safe(payload)


def restore_version(
    db: Session,
    *,
    settings: Settings,
    dataset: Dataset,
    version_id: str,
    user: User,
    request: Request | None = None,
) -> DatasetVersion:
    if user.role != UserRole.ADMINISTRATOR and dataset.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner or an administrator can restore a version",
        )
    source = next((item for item in dataset.versions if item.id == version_id), None)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset version not found")
    path, kind = _resolve_version_file(settings, source)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Historical version file is missing on disk")
    content = path.read_bytes()
    checksum = sha256_bytes(content)
    if checksum != source.checksum_sha256:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version checksum mismatch; restore blocked")
    number = _next_number(dataset)
    label = _next_label(_current(dataset) or source, restored=True)
    version_id = str(uuid4())
    storage = StorageService(settings)
    filename = Path(source.processed_file_path or source.raw_file_path).name
    target, relative = _copy_to_version(
        storage,
        dataset,
        version_id=version_id,
        label=label,
        filename=filename,
        content=content,
        kind=kind,
    )
    frame = extract_dataset(target, FileFormat.CSV if kind == "processed" else dataset.format).dataframe
    summaries = _summaries(frame)
    profile = _sanitised_profile(source.profile_json or {})
    profile.update(
        {
            "schema": summaries["schema"],
            "missingSummary": summaries["missing"],
            "distributionSummary": summaries["distribution"],
        }
    )
    history = _transformation_history(source)
    history.append(
        {
            "step": "restore",
            "restoredFromVersionId": source.id,
            "restoredById": user.id,
            "checksumSha256": checksum,
            "createdAt": _iso(datetime.now(UTC)),
        }
    )
    lineage = dict(_lineage(source))
    lineage.update(
        {
            "event": "restore",
            "kind": "Processed" if kind == "processed" else "Original",
            "parentVersionId": source.id,
            "restoredFromVersionId": source.id,
            "note": "Restored from historical version.",
            "history": history,
            "createdAt": _iso(datetime.now(UTC)),
        }
    )
    log = dict(source.transformation_log_json or {})
    log.update({"kind": lineage["kind"], "parent_version_id": source.id, "lineage": lineage})
    _deactivate_current(dataset)
    version = DatasetVersion(
        id=version_id,
        dataset_id=dataset.id,
        version_number=number,
        version_label=label,
        raw_file_path=relative if kind == "raw" else source.raw_file_path,
        processed_file_path=relative if kind == "processed" else None,
        checksum_sha256=checksum,
        file_size_bytes=len(content),
        record_count=len(frame),
        column_count=len(frame.columns),
        profile_json=_json_safe(profile),
        transformation_log_json=_json_safe(log),
        is_current=True,
    )
    db.add(version)
    dataset.versions.append(version)
    dataset.current_version_number = number
    _audit_lineage(
        db,
        action="dataset.version_restored",
        dataset=dataset,
        version=version,
        user=user,
        details={
            "restoredFromVersionId": source.id,
            "kind": lineage["kind"],
            "checksumSha256": checksum,
        },
        request=request,
    )
    return version


def lineage_events(db: Session, dataset: Dataset) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    versions = list(dataset.versions)
    version_ids = {version.id for version in versions}
    for version in versions:
        parent = parent_version_id(version)
        if parent:
            events.append(
                {
                    "type": "version_branch" if restored_from_version_id(version) else "version_created",
                    "parentVersionId": parent,
                    "childVersionId": version.id,
                    "timestamp": _iso(version.created_at),
                    "metadata": {
                        "parentLabel": next(
                            (item.version_label for item in versions if item.id == parent), ""
                        ),
                        "childLabel": version.version_label,
                        "kind": version_kind(version),
                        "restoredFromVersionId": restored_from_version_id(version),
                    },
                }
            )
    jobs = list(dataset.etl_jobs)
    job_ids = {job.id for job in jobs}
    for job in jobs:
        events.append(
            {
                "type": "etl_job",
                "parentVersionId": job.dataset_version_id,
                "childVersionId": None,
                "timestamp": _iso(job.approved_at or job.started_at or job.created_at),
                "metadata": {
                    "jobId": job.id,
                    "status": job.status.value,
                    "approvedById": job.approved_by_id,
                    "approvedMapping": _json_safe(job.approved_mapping_json or {}),
                },
            }
        )
    statement = select(AuditLog).where(
        (AuditLog.resource_type == "dataset") & AuditLog.resource_id.in_({dataset.id, *version_ids, *job_ids})
        | (AuditLog.resource_type == "etl_job") & AuditLog.resource_id.in_(job_ids)
        | (AuditLog.resource_type == "dataset_version") & AuditLog.resource_id.in_(version_ids)
    )
    for entry in db.scalars(statement):
        events.append(
            {
                "type": entry.action,
                "parentVersionId": None,
                "childVersionId": entry.resource_id if entry.resource_type == "dataset_version" else None,
                "timestamp": _iso(entry.created_at),
                "metadata": _json_safe(entry.details_json or {}),
            }
        )
    return _json_safe(sorted(events, key=lambda item: item["timestamp"]))


def get_lineage(db: Session, settings: Settings, dataset: Dataset) -> dict[str, Any]:
    versions = _versions(dataset)
    events = lineage_events(db, dataset)
    return {
        "datasetId": dataset.id,
        "versions": [version_item(settings, dataset, version) for version in versions],
        "lineage": events,
        "events": events,
    }


def version_for_lineage(db: Session, settings: Settings, dataset: Dataset, version_id: str) -> dict[str, Any]:
    item = get_version(db, settings, dataset, version_id)
    events = [
        event
        for event in lineage_events(db, dataset)
        if version_id in {event.get("parentVersionId"), event.get("childVersionId")}
        or event.get("metadata", {}).get("versionId") == version_id
    ]
    return {
        "datasetId": dataset.id,
        "versions": [item],
        "lineage": events,
        "events": events,
    }


def version_download_path(
    db: Session,
    settings: Settings,
    dataset: Dataset,
    version_id: str,
) -> tuple[DatasetVersion, Path, str, str]:
    version = next((item for item in dataset.versions if item.id == version_id), None)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset version not found")
    path, _ = _resolve_version_file(settings, version)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version file is missing on disk")
    if version.checksum_sha256 and sha256_file(path) != version.checksum_sha256:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version checksum mismatch; download blocked")
    suffix = path.suffix or f".{dataset.format.value.lower()}"
    filename = f"{dataset.title.replace(' ', '_')}_{version.version_label}{suffix}"
    media_type = {
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".json": "application/json",
    }.get(suffix.lower(), "application/octet-stream")
    return version, path, filename, media_type
