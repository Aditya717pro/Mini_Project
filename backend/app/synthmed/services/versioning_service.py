from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.enums import UserRole
from app.models.user import User
from app.services.audit_service import log_audit
from app.services.storage_paths import public_reference
from app.synthmed.models import (
    SynthMedComparison,
    SynthMedDatasetLineage,
    SynthMedDatasetVersion,
    SynthMedEvaluationReport,
    SynthMedExperiment,
    SynthMedGeneratedDataset,
    SynthMedGenerationConfigurationSnapshot,
    SynthMedGenerationJob,
    SynthMedSourceDataset,
    SynthMedUtilityEvaluation,
)
from app.synthmed.services import medical_schema_service
from app.synthmed.services.condition_service import SDV_VERSION
from app.synthmed.services.dataset_service import json_safe, read_source_dataframe
from app.synthmed.services.source_service import ensure_generated_access, ensure_source_access
from app.synthmed.services.storage_service import SynthMedStorageService


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(v: datetime | None) -> str:
    return v.isoformat() if v else ""


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _schema(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{"name": str(c), "dtype": str(frame[c].dtype)} for c in frame.columns]


def compute_version_label(
    previous: SynthMedDatasetVersion | None, columns: list[dict[str, Any]], *, restored: bool = False
) -> str:
    if previous is None:
        return "v1.0"
    label = str(previous.version_label or "")
    major, _, minor = label.removeprefix("v").partition(".")
    try:
        major_number, minor_number = int(major), int(minor)
    except ValueError:
        major_number, minor_number = 1, previous.version_number - 1
    if restored:
        return f"v{major_number}.{minor_number + 1}"
    current = {str(item.get("name")): str(item.get("dtype")) for item in columns if isinstance(item, dict)}
    prior = {
        str(item.get("name")): str(item.get("dtype"))
        for item in (previous.schema_json or {}).get("columns", [])
        if isinstance(item, dict)
    }
    if prior and prior != current:
        return f"v{major_number + 1}.0"
    return f"v{major_number}.{minor_number + 1}"


def _missing(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        str(c): {"missing": int(frame[c].isna().sum()), "missingPct": round(float(frame[c].isna().mean() * 100), 4)}
        for c in frame.columns
    }


def _distribution(frame: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for c in frame.columns:
        s = frame[c].dropna()
        if pd.api.types.is_numeric_dtype(s):
            out[str(c)] = {
                "kind": "numeric",
                "mean": json_safe(float(s.mean())) if len(s) else None,
                "std": json_safe(float(s.std(ddof=0))) if len(s) else None,
                "min": json_safe(float(s.min())) if len(s) else None,
                "max": json_safe(float(s.max())) if len(s) else None,
            }
        else:
            vc = s.astype("string").value_counts().head(10)
            out[str(c)] = {
                "kind": "categorical",
                "topValues": [{"value": _pseudonym(k), "count": int(v)} for k, v in vc.items()],
            }
    return out


def _library_versions() -> dict[str, str]:
    import numpy as np
    import pandas as pd
    import sklearn

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikitLearn": sklearn.__version__,
        "sdv": SDV_VERSION,
        "implementation": sys.implementation.name,
    }


_SENSITIVE_CONFIG_KEYS = {
    "anchors",
    "categoricalValues",
    "identifierValues",
    "medicalProfile",
    "previewRows",
    "rawValues",
    "sampleValues",
    "sourcePreservationPlanInternal",
}


def _pseudonym(value: Any) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return f"value_{digest[:10]}"


def _sanitize_snapshot_config(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_snapshot_config(item)
            for key, item in value.items()
            if str(key) not in _SENSITIVE_CONFIG_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_snapshot_config(item) for item in value]
    return value


def _find_column(columns: Any, *names: str) -> str | None:
    normalized = {str(column).strip().lower().replace(" ", "_"): str(column) for column in columns}
    for name in names:
        if name in normalized:
            return normalized[name]
    return None


def _bmi_consistency(frame: pd.DataFrame) -> dict[str, Any]:
    height = _find_column(frame.columns, "height_cm", "height", "height_m")
    weight = _find_column(frame.columns, "weight_kg", "weight")
    bmi = _find_column(frame.columns, "bmi", "body_mass_index")
    if not all((height, weight, bmi)):
        return {"available": False, "reason": "Height, weight and BMI columns are required."}
    height_values = pd.to_numeric(frame[height], errors="coerce")
    weight_values = pd.to_numeric(frame[weight], errors="coerce")
    bmi_values = pd.to_numeric(frame[bmi], errors="coerce")
    height_is_cm = "cm" in str(height).lower()
    height_m = height_values / 100 if height_is_cm else height_values
    with np.errstate(divide="ignore", invalid="ignore"):
        expected = weight_values / (height_m**2)
    valid = expected.notna() & bmi_values.notna() & np.isfinite(expected)
    if not bool(valid.any()):
        return {"available": False, "reason": "No rows contain numeric height, weight and BMI values."}
    difference = (bmi_values[valid] - expected[valid]).abs()
    return {
        "available": True,
        "heightColumn": height,
        "weightColumn": weight,
        "bmiColumn": bmi,
        "comparableRows": int(valid.sum()),
        "meanAbsoluteDifference": json_safe(float(difference.mean())),
        "maxAbsoluteDifference": json_safe(float(difference.max())),
        "rowsOutsideHalfUnit": int((difference > 0.5).sum()),
        "outsideHalfUnitPct": json_safe(float((difference > 0.5).mean() * 100)),
    }


def _dataset_path(settings: Settings, kind: str, stored_path: str) -> Path:
    storage = SynthMedStorageService(settings)
    return storage.resolve_source(stored_path) if kind == "source" else storage.resolve_generated(stored_path)


def _version_path(settings: Settings, version: SynthMedDatasetVersion) -> Path:
    return SynthMedStorageService(settings).resolve_version(version.dataset_kind, version.stored_path)


def _load_frame(settings: Settings, version: SynthMedDatasetVersion) -> pd.DataFrame:
    try:
        path = _version_path(settings, version)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=409, detail=f"Version {version.version_label} file is missing on disk; comparison blocked."
        ) from error
    fmt = version.file_format.upper()
    return read_source_dataframe(path, fmt)


def _validate_generated_frame(
    db: Session, settings: Settings, generated: SynthMedGeneratedDataset, frame: pd.DataFrame
) -> dict[str, Any]:
    source = db.get(SynthMedSourceDataset, generated.source_dataset_id)
    if source is None:
        raise HTTPException(status_code=409, detail="Source dataset is missing; strict medical validation blocked.")
    try:
        profile_frame = read_source_dataframe(
            _dataset_path(settings, "source", source.stored_path), source.file_format.upper()
        )
    except (FileNotFoundError, ValueError, OSError) as error:
        raise HTTPException(
            status_code=409, detail="Source file is missing or unreadable; strict medical validation blocked."
        ) from error
    profile = medical_schema_service.profile_medical_schema(profile_frame)
    validation = medical_schema_service.validate_strict_output_schema(
        frame,
        approved_columns=[str(column) for column in profile["approvedOutputColumns"]],
        identifier_columns=[str(column) for column in profile["excludedIdentifierColumns"]],
    )
    if not validation["passed"]:
        raise HTTPException(
            status_code=422,
            detail="Strict medical output schema validation failed: " + "; ".join(validation["errors"]),
        )
    return validation


def _next_version(db: Session, *, kind: str, logical_id: str) -> SynthMedDatasetVersion | None:
    stmt = (
        select(SynthMedDatasetVersion)
        .where(
            SynthMedDatasetVersion.dataset_kind == kind,
            SynthMedDatasetVersion.logical_dataset_id == logical_id,
        )
        .order_by(SynthMedDatasetVersion.version_number.desc())
    )
    return db.scalars(stmt).first()


def _deactivate_active(db: Session, *, kind: str, logical_id: str) -> None:
    stmt = select(SynthMedDatasetVersion).where(
        SynthMedDatasetVersion.dataset_kind == kind,
        SynthMedDatasetVersion.logical_dataset_id == logical_id,
        SynthMedDatasetVersion.is_active.is_(True),
    )
    for row in db.scalars(stmt):
        row.is_active = False
        row.updated_at = _now()


def record_lineage(
    db: Session,
    *,
    owner_id: str,
    event_type: str,
    parent_type: str,
    parent_id: str,
    child_type: str,
    child_id: str,
    source_dataset_id: str | None = None,
    generated_dataset_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SynthMedDatasetLineage:
    row = SynthMedDatasetLineage(
        id=str(uuid4()),
        owner_id=owner_id,
        event_type=event_type,
        parent_resource_type=parent_type,
        parent_resource_id=parent_id,
        child_resource_type=child_type,
        child_resource_id=child_id,
        source_dataset_id=source_dataset_id,
        generated_dataset_id=generated_dataset_id,
        metadata_json=json_safe(metadata or {}),
    )
    db.add(row)
    return row


def create_dataset_version(
    db: Session,
    *,
    user: User,
    settings: Settings,
    kind: str,
    source: SynthMedSourceDataset | None = None,
    generated: SynthMedGeneratedDataset | None = None,
    parent_version_id: str | None = None,
    transform_history: list[dict[str, Any]] | None = None,
    validation_summary: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    restored_from_version_id: str | None = None,
    snapshot_content: bytes | None = None,
    request: Request | None = None,
) -> SynthMedDatasetVersion:
    if kind == "source":
        if source is None:
            raise ValueError("source required")
        ensure_source_access(source, user)
        logical_id, dataset_id = source.id, source.id
        source_id, generated_id = source.id, None
        dataset_name, file_format, stored_path = source.dataset_name, source.file_format, source.stored_path
        record_count, column_count = source.row_count, source.column_count
    else:
        if generated is None:
            raise ValueError("generated required")
        ensure_generated_access(generated, user)
        logical_id, dataset_id = generated.id, generated.id
        source_id, generated_id = generated.source_dataset_id, generated.id
        dataset_name, file_format, stored_path = (
            generated.dataset_name,
            generated.file_format,
            generated.stored_path,
        )
        record_count, column_count = generated.record_count, generated.column_count

    try:
        live_path = _dataset_path(settings, kind, stored_path)
        content = live_path.read_bytes() if snapshot_content is None else snapshot_content
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=409, detail="Dataset file is missing on disk; version snapshot blocked."
        ) from error
    version_id = str(uuid4())
    storage = SynthMedStorageService(settings)
    snapshot_path, snapshot_relative = storage.save_version_snapshot(
        dataset_id,
        version_id,
        Path(stored_path).name or f"{kind}.csv",
        content,
        kind=kind,
    )
    frame = read_source_dataframe(snapshot_path, file_format.upper())
    validation_payload = dict(validation_summary or {})
    if kind == "generated" and generated is not None:
        validation_payload["medicalSchema"] = _validate_generated_frame(db, settings, generated, frame)
    previous = _next_version(db, kind=kind, logical_id=logical_id)
    number = previous.version_number + 1 if previous else 1
    label = compute_version_label(previous, _schema(frame), restored=bool(restored_from_version_id))
    _deactivate_active(db, kind=kind, logical_id=logical_id)
    metadata_payload = json_safe(dict(metadata or {}))
    metadata_payload["originalStoredPath"] = stored_path
    owner_id = source.owner_id if source is not None and kind == "source" else generated.owner_id
    row = SynthMedDatasetVersion(
        id=version_id,
        owner_id=owner_id,
        dataset_kind=kind,
        logical_dataset_id=logical_id,
        source_dataset_id=source_id,
        generated_dataset_id=generated_id,
        parent_version_id=parent_version_id,
        version_number=number,
        version_label=label,
        is_active=True,
        dataset_name=dataset_name,
        file_format=file_format.upper(),
        stored_path=snapshot_relative,
        checksum_sha256=_sha256_bytes(content),
        file_size_bytes=len(content),
        record_count=int(len(frame)) or record_count,
        column_count=int(len(frame.columns)) or column_count,
        schema_json=json_safe({"columns": _schema(frame)}),
        missing_summary_json=json_safe(_missing(frame)),
        distribution_summary_json=json_safe(_distribution(frame)),
        transform_history_json=json_safe(transform_history or []),
        validation_summary_json=json_safe(validation_payload),
        metadata_json=metadata_payload,
        restored_from_version_id=restored_from_version_id,
    )
    db.add(row)
    log_audit(
        db,
        action="synthmed.version_created",
        resource_type="synthmed_dataset_version",
        resource_id=row.id,
        actor_id=user.id,
        details={
            "kind": kind,
            "sourceDatasetId": source_id,
            "generatedDatasetId": generated_id,
            "versionNumber": number,
            "versionLabel": label,
            "checksum": row.checksum_sha256,
        },
        request=request,
    )
    return row


def ensure_source_version(
    db: Session, *, user: User, settings: Settings, source: SynthMedSourceDataset, request: Request | None = None
) -> SynthMedDatasetVersion:
    existing = _next_version(db, kind="source", logical_id=source.id)
    if existing:
        return existing
    row = create_dataset_version(
        db, user=user, settings=settings, kind="source", source=source, metadata={"origin": "upload"}, request=request
    )
    db.commit()
    db.refresh(row)
    return row


def ensure_generated_version(
    db: Session,
    *,
    user: User,
    settings: Settings,
    generated: SynthMedGeneratedDataset,
    job: SynthMedGenerationJob | None = None,
    request: Request | None = None,
) -> SynthMedDatasetVersion:
    existing = _next_version(db, kind="generated", logical_id=generated.id)
    if existing:
        return existing
    src_ver = _next_version(db, kind="source", logical_id=generated.source_dataset_id)
    if src_ver is not None and not src_ver.is_active:
        src_ver = db.scalar(
            select(SynthMedDatasetVersion)
            .where(
                SynthMedDatasetVersion.dataset_kind == "source",
                SynthMedDatasetVersion.logical_dataset_id == generated.source_dataset_id,
                SynthMedDatasetVersion.is_active.is_(True),
            )
            .order_by(SynthMedDatasetVersion.version_number.desc())
        )
    parent = src_ver.id if src_ver else None
    row = create_dataset_version(
        db,
        user=user,
        settings=settings,
        kind="generated",
        generated=generated,
        parent_version_id=parent,
        transform_history=[
            {
                "step": "synthmed_generation",
                "jobId": job.id if job else None,
                "model": job.selected_model if job else generated.selected_model,
            }
        ],
        validation_summary={"status": generated.status},
        metadata={"generationMethod": generated.generation_method, "generationMode": generated.generation_mode},
        request=request,
    )
    if src_ver:
        record_lineage(
            db,
            owner_id=user.id,
            event_type="source_to_synthetic",
            parent_type="synthmed_dataset_version",
            parent_id=src_ver.id,
            child_type="synthmed_dataset_version",
            child_id=row.id,
            source_dataset_id=generated.source_dataset_id,
            generated_dataset_id=generated.id,
            metadata={"jobId": job.id if job else None},
        )
    db.commit()
    db.refresh(row)
    return row


def list_versions(
    db: Session, *, user: User, settings: Settings, dataset_id: str
) -> list[SynthMedDatasetVersion]:
    source = db.get(SynthMedSourceDataset, dataset_id)
    generated = db.get(SynthMedGeneratedDataset, dataset_id)
    if source:
        ensure_source_access(source, user)
        ensure_source_version(db, user=user, settings=settings, source=source)
        kind = "source"
    elif generated:
        ensure_generated_access(generated, user)
        ensure_generated_version(db, user=user, settings=settings, generated=generated)
        kind = "generated"
    else:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    stmt = select(SynthMedDatasetVersion).where(
        SynthMedDatasetVersion.dataset_kind == kind,
        SynthMedDatasetVersion.logical_dataset_id == dataset_id,
    )
    return list(db.scalars(stmt.order_by(SynthMedDatasetVersion.version_number.desc())))


def get_version(db: Session, *, user: User, version_id: str) -> SynthMedDatasetVersion:
    row = db.get(SynthMedDatasetVersion, version_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Dataset version not found.")
    if row.owner_id != user.id and user.role != UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=403, detail="Not permitted to view this dataset version.")
    return row


def version_belongs_to_dataset(version: SynthMedDatasetVersion, dataset_id: str) -> bool:
    if version.dataset_kind == "source":
        return dataset_id == version.logical_dataset_id and dataset_id == version.source_dataset_id
    if version.dataset_kind == "generated":
        return dataset_id == version.logical_dataset_id and dataset_id == version.generated_dataset_id
    return False


def _generated_linked_summaries(
    db: Session, *, user: User, version: SynthMedDatasetVersion
) -> dict[str, Any]:
    if version.dataset_kind != "generated" or not version.generated_dataset_id:
        return {"available": False, "privacyReports": [], "utilityEvaluations": []}
    linked_child_ids = {
        str(row.child_resource_id)
        for row in db.scalars(
            select(SynthMedDatasetLineage).where(SynthMedDatasetLineage.parent_resource_id == version.id)
        )
    }
    privacy_rows = db.scalars(
        select(SynthMedEvaluationReport).where(
            SynthMedEvaluationReport.generated_dataset_id == version.generated_dataset_id,
            SynthMedEvaluationReport.report_type == "privacy",
        )
    ).all()
    utility_rows = db.scalars(
        select(SynthMedUtilityEvaluation).where(
            SynthMedUtilityEvaluation.generated_dataset_id == version.generated_dataset_id
        )
    ).all()
    privacy = [
        {
            "id": row.id,
            "method": row.method,
            "score": json_safe(row.score),
            "reportAvailable": bool(row.file_path),
            "linkedByLineage": row.id in linked_child_ids,
            "createdAt": _iso(row.created_at),
        }
        for row in privacy_rows
        if (row.owner_id == user.id or user.role == UserRole.ADMINISTRATOR)
        and (row.id in linked_child_ids or row.generated_dataset_id == version.generated_dataset_id)
    ]
    utility = [
        {
            "id": row.id,
            "status": row.status,
            "evaluationType": row.evaluation_type,
            "modelName": row.model_name,
            "targetColumn": row.target_column,
            "taskType": (row.metrics_json or {}).get("taskType")
            or (row.preprocessing_config_json or {}).get("taskType"),
            "metrics": json_safe(row.metrics_json or {}),
            "comparison": json_safe(row.comparison_summary_json or {}),
            "reportAvailable": bool(row.report_path),
            "reportCsvAvailable": bool(row.report_csv_path),
            "reportPdfAvailable": bool(row.report_pdf_path),
            "linkedByLineage": row.id in linked_child_ids,
            "createdAt": _iso(row.created_at),
        }
        for row in utility_rows
        if (row.owner_id == user.id or user.role == UserRole.ADMINISTRATOR)
        and (row.id in linked_child_ids or row.generated_dataset_id == version.generated_dataset_id)
    ]
    return {"available": bool(privacy or utility), "privacyReports": privacy, "utilityEvaluations": utility}


def _distribution_deltas(frame_a: pd.DataFrame, frame_b: pd.DataFrame, column: str) -> dict[str, Any]:
    a = frame_a[column].dropna()
    b = frame_b[column].dropna()
    if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
        stats_a = {
            "mean": json_safe(float(a.mean())) if len(a) else None,
            "std": json_safe(float(a.std(ddof=0))) if len(a) else None,
            "min": json_safe(float(a.min())) if len(a) else None,
            "max": json_safe(float(a.max())) if len(a) else None,
        }
        stats_b = {
            "mean": json_safe(float(b.mean())) if len(b) else None,
            "std": json_safe(float(b.std(ddof=0))) if len(b) else None,
            "min": json_safe(float(b.min())) if len(b) else None,
            "max": json_safe(float(b.max())) if len(b) else None,
        }
        delta = {
            key: json_safe(stats_b[key] - stats_a[key])
            if stats_a[key] is not None and stats_b[key] is not None
            else None
            for key in stats_a
        }
        return {"kind": "numeric", "a": stats_a, "b": stats_b, "delta": delta}
    counts_a = a.astype("string").value_counts(normalize=True)
    counts_b = b.astype("string").value_counts(normalize=True)
    top_a = _pseudonym(counts_a.index[0]) if len(counts_a) else None
    top_b = _pseudonym(counts_b.index[0]) if len(counts_b) else None
    return {
        "kind": "categorical",
        "topA": json_safe({_pseudonym(key): value for key, value in counts_a.head(5).to_dict().items()}),
        "topB": json_safe({_pseudonym(key): value for key, value in counts_b.head(5).to_dict().items()}),
        "topValueA": top_a,
        "topValueB": top_b,
        "shareA": json_safe(float(counts_a.iloc[0])) if len(counts_a) else None,
        "shareB": json_safe(float(counts_b.iloc[0])) if len(counts_b) else None,
        "shareDelta": json_safe(float(counts_b.iloc[0] - counts_a.iloc[0]))
        if len(counts_a) and len(counts_b)
        else None,
        "topValueChanged": top_a != top_b,
    }


def compare_versions(
    db: Session, *, user: User, settings: Settings, dataset_id: str, version_a_id: str, version_b_id: str
) -> dict[str, Any]:
    a = get_version(db, user=user, version_id=version_a_id)
    b = get_version(db, user=user, version_id=version_b_id)
    if not version_belongs_to_dataset(a, dataset_id) or not version_belongs_to_dataset(b, dataset_id):
        raise HTTPException(status_code=422, detail="Versions do not belong to the requested dataset.")
    fa, fb = _load_frame(settings, a), _load_frame(settings, b)
    actual_checksum_a = _sha256_bytes(_version_path(settings, a).read_bytes())
    actual_checksum_b = _sha256_bytes(_version_path(settings, b).read_bytes())
    cols_a, cols_b = set(fa.columns), set(fb.columns)
    common = sorted(cols_a & cols_b)
    dtypes_a = {str(column): str(fa[column].dtype) for column in fa.columns}
    dtypes_b = {str(column): str(fb[column].dtype) for column in fb.columns}
    schema_changes = {
        "added": sorted(cols_b - cols_a),
        "removed": sorted(cols_a - cols_b),
        "common": common,
        "dtypeChanges": [
            {"column": column, "dtypeA": dtypes_a[column], "dtypeB": dtypes_b[column]}
            for column in common
            if dtypes_a[column] != dtypes_b[column]
        ],
    }
    missing_a, missing_b = a.missing_summary_json or {}, b.missing_summary_json or {}
    missing_deltas = {
        column: {
            "missingA": (missing_a.get(column) or {}).get("missing"),
            "missingB": (missing_b.get(column) or {}).get("missing"),
            "delta": (missing_b.get(column) or {}).get("missing", 0) - (missing_a.get(column) or {}).get("missing", 0),
            "missingPctA": (missing_a.get(column) or {}).get("missingPct"),
            "missingPctB": (missing_b.get(column) or {}).get("missingPct"),
        }
        for column in common
    }
    distributions = {column: _distribution_deltas(fa, fb, column) for column in common[:30]}
    return json_safe(
        {
            "datasetId": dataset_id,
            "versionA": to_version_response(a),
            "versionB": to_version_response(b),
            "metadata": {
                "recordCountDelta": b.record_count - a.record_count,
                "columnCountDelta": b.column_count - a.column_count,
                "checksumChanged": actual_checksum_a != actual_checksum_b,
                "checksumA": a.checksum_sha256,
                "checksumB": b.checksum_sha256,
                "actualChecksumA": actual_checksum_a,
                "actualChecksumB": actual_checksum_b,
                "checksumMatchesRecorded": {
                    "a": actual_checksum_a == a.checksum_sha256,
                    "b": actual_checksum_b == b.checksum_sha256,
                },
            },
            "schema": schema_changes,
            "missing": {"a": missing_a, "b": missing_b, "deltas": missing_deltas},
            "distributions": distributions,
            "transformHistory": {"a": a.transform_history_json, "b": b.transform_history_json},
            "validation": {"a": a.validation_summary_json, "b": b.validation_summary_json},
            "generatedResources": {
                "a": _generated_linked_summaries(db, user=user, version=a),
                "b": _generated_linked_summaries(db, user=user, version=b),
            },
            "medicalConsistency": {"a": _bmi_consistency(fa), "b": _bmi_consistency(fb)},
        }
    )


def restore_version(
    db: Session,
    *,
    user: User,
    settings: Settings,
    dataset_id: str,
    version_id: str,
    request: Request | None = None,
) -> SynthMedDatasetVersion:
    version = get_version(db, user=user, version_id=version_id)
    src = db.get(SynthMedSourceDataset, dataset_id)
    gen = db.get(SynthMedGeneratedDataset, dataset_id)
    if src and version.logical_dataset_id not in {src.id, dataset_id}:
        raise HTTPException(status_code=422, detail="Version does not belong to source dataset.")
    if gen and version.logical_dataset_id not in {gen.id, dataset_id}:
        raise HTTPException(status_code=422, detail="Version does not belong to generated dataset.")
    dataset = src or gen
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if src is not None:
        ensure_source_access(src, user)
    else:
        ensure_generated_access(gen, user)
    kind = "source" if src else "generated"
    try:
        live_path = _dataset_path(settings, kind, dataset.stored_path)
        historical_path = _version_path(settings, version)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=409, detail="Dataset or historical version file is missing; restore blocked."
        ) from error
    content = historical_path.read_bytes()
    checksum = _sha256_bytes(content)
    if version.checksum_sha256 and checksum != version.checksum_sha256:
        raise HTTPException(status_code=409, detail="Checksum mismatch; restore blocked.")
    metadata = dict(version.metadata_json or {})
    metadata["restoredFromVersionId"] = version.id
    transform_history = list(version.transform_history_json or [])
    transform_history.append({"step": "restore", "restoredFromVersionId": version.id, "restoredAt": _iso(_now())})
    active = create_dataset_version(
        db,
        user=user,
        settings=settings,
        kind=kind,
        source=src,
        generated=gen,
        parent_version_id=version.id,
        transform_history=transform_history,
        validation_summary=dict(version.validation_summary_json or {}),
        metadata=metadata,
        restored_from_version_id=version.id,
        snapshot_content=content,
        request=request,
    )
    if gen is not None:
        temporary = live_path.with_name(f"{live_path.name}.restore-{uuid4().hex}")
        temporary.write_bytes(content)
        temporary.replace(live_path)
        gen.checksum_sha256 = checksum
        gen.file_size_bytes = len(content)
        gen.record_count = active.record_count
        gen.column_count = active.column_count
    record_lineage(
        db,
        owner_id=user.id,
        event_type="restore",
        parent_type="synthmed_dataset_version",
        parent_id=version.id,
        child_type="synthmed_dataset_version",
        child_id=active.id,
        source_dataset_id=active.source_dataset_id,
        generated_dataset_id=active.generated_dataset_id,
        metadata={"datasetId": dataset_id, "checksum": checksum},
    )
    log_audit(
        db,
        action="synthmed.version_restored",
        resource_type="synthmed_dataset_version",
        resource_id=active.id,
        actor_id=user.id,
        details={"datasetId": dataset_id, "restoredFrom": version.id, "newVersionId": active.id},
        request=request,
    )
    db.commit()
    db.refresh(active)
    return active


def version_download_path(
    db: Session, *, user: User, settings: Settings, dataset_id: str, version_id: str
) -> tuple[SynthMedDatasetVersion, Path]:
    version = get_version(db, user=user, version_id=version_id)
    if not version_belongs_to_dataset(version, dataset_id):
        raise HTTPException(status_code=404, detail="Version not found for dataset.")
    try:
        path = _version_path(settings, version)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Version path is outside the expected storage category.") from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=409, detail="Version file is missing on disk; download blocked.") from error
    if not path.exists():
        raise HTTPException(status_code=409, detail="Version file is missing on disk; download blocked.")
    if version.checksum_sha256 and _sha256_bytes(path.read_bytes()) != version.checksum_sha256:
        raise HTTPException(status_code=409, detail="Version checksum mismatch; download blocked.")
    return version, path


def lineage_for_dataset(db: Session, *, user: User, settings: Settings, dataset_id: str) -> dict[str, Any]:
    versions = list_versions(db, user=user, settings=settings, dataset_id=dataset_id)
    ids = [v.id for v in versions]
    dataset_ids = [dataset_id]
    stmt = select(SynthMedDatasetLineage).where(
        (SynthMedDatasetLineage.source_dataset_id == dataset_id)
        | (SynthMedDatasetLineage.generated_dataset_id == dataset_id)
        | (SynthMedDatasetLineage.parent_resource_id.in_(dataset_ids + ids))
        | (SynthMedDatasetLineage.child_resource_id.in_(dataset_ids + ids))
    ).order_by(SynthMedDatasetLineage.created_at.asc())
    rows = [r for r in db.scalars(stmt) if r.owner_id == user.id or user.role == UserRole.ADMINISTRATOR]
    return {
        "datasetId": dataset_id,
        "versions": [to_version_response(v) for v in versions],
        "lineage": [to_lineage_response(r) for r in rows],
    }


def snapshot_config(db: Session, *, user: User, job: SynthMedGenerationJob) -> SynthMedGenerationConfigurationSnapshot:
    cfg = json_safe(_sanitize_snapshot_config(job.config_json or {}))
    cfg.setdefault("sdvVersion", SDV_VERSION)
    cfg.setdefault("libraryVersions", _library_versions())
    payload = json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode("utf-8")
    row = SynthMedGenerationConfigurationSnapshot(
        id=str(uuid4()),
        owner_id=user.id,
        source_dataset_id=job.source_dataset_id,
        job_id=job.id,
        model_name=job.selected_model or job.model_name,
        config_json=cfg,
        config_hash=hashlib.sha256(payload).hexdigest(),
        is_immutable=True,
    )
    db.add(row)
    return row


def to_version_response(row: SynthMedDatasetVersion) -> dict[str, Any]:
    return {
        "id": row.id,
        "ownerId": row.owner_id,
        "datasetKind": row.dataset_kind,
        "logicalDatasetId": row.logical_dataset_id,
        "sourceDatasetId": row.source_dataset_id,
        "generatedDatasetId": row.generated_dataset_id,
        "parentVersionId": row.parent_version_id,
        "versionNumber": row.version_number,
        "versionLabel": row.version_label,
        "isActive": bool(row.is_active),
        "datasetName": row.dataset_name,
        "fileFormat": row.file_format,
        "storedPath": public_reference(row.stored_path),
        "checksumSha256": row.checksum_sha256,
        "fileSizeBytes": row.file_size_bytes,
        "recordCount": row.record_count,
        "columnCount": row.column_count,
        "datasetSchema": row.schema_json or {},
        "missingSummary": row.missing_summary_json or {},
        "distributionSummary": row.distribution_summary_json or {},
        "transformHistory": row.transform_history_json or [],
        "validationSummary": row.validation_summary_json or {},
        "metadata": row.metadata_json or {},
        "restoredFromVersionId": row.restored_from_version_id,
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
    }


def to_lineage_response(row: SynthMedDatasetLineage) -> dict[str, Any]:
    return {
        "id": row.id,
        "eventType": row.event_type,
        "parentResourceType": row.parent_resource_type,
        "parentResourceId": row.parent_resource_id,
        "childResourceType": row.child_resource_type,
        "childResourceId": row.child_resource_id,
        "sourceDatasetId": row.source_dataset_id,
        "generatedDatasetId": row.generated_dataset_id,
        "metadata": row.metadata_json or {},
        "createdAt": _iso(row.created_at),
    }


def to_snapshot_response(row: SynthMedGenerationConfigurationSnapshot) -> dict[str, Any]:
    return {
        "id": row.id,
        "ownerId": row.owner_id,
        "sourceDatasetId": row.source_dataset_id,
        "jobId": row.job_id,
        "modelName": row.model_name,
        "config": row.config_json or {},
        "configHash": row.config_hash,
        "isImmutable": bool(row.is_immutable),
        "createdAt": _iso(row.created_at),
    }


def _experiment_lineage(db: Session, row: SynthMedExperiment) -> list[SynthMedDatasetLineage]:
    related = {
        row.id,
        row.source_dataset_id,
        row.generated_dataset_id,
        row.source_version_id,
        row.generated_version_id,
        row.generation_job_id,
        row.comparison_id,
        row.utility_evaluation_id,
    }
    related.discard(None)
    stmt = (
        select(SynthMedDatasetLineage)
        .where(SynthMedDatasetLineage.owner_id == row.owner_id)
        .order_by(SynthMedDatasetLineage.created_at.asc())
    )
    return [event for event in db.scalars(stmt) if {event.parent_resource_id, event.child_resource_id} & related]


def to_experiment_response(db: Session, row: SynthMedExperiment) -> dict[str, Any]:
    snapshot = (
        db.get(SynthMedGenerationConfigurationSnapshot, row.configuration_snapshot_id)
        if row.configuration_snapshot_id
        else None
    )
    privacy = None
    if row.generated_dataset_id:
        privacy = db.scalar(
            select(SynthMedEvaluationReport).where(
                SynthMedEvaluationReport.generated_dataset_id == row.generated_dataset_id,
                SynthMedEvaluationReport.report_type == "privacy",
            )
        )
    comparison = db.get(SynthMedComparison, row.comparison_id) if row.comparison_id else None
    utility = db.get(SynthMedUtilityEvaluation, row.utility_evaluation_id) if row.utility_evaluation_id else None
    lineage = _experiment_lineage(db, row)
    return {
        "id": row.id,
        "ownerId": row.owner_id,
        "name": row.name,
        "description": row.description,
        "status": row.status,
        "sourceDatasetId": row.source_dataset_id,
        "sourceVersionId": row.source_version_id,
        "generatedDatasetId": row.generated_dataset_id,
        "generatedVersionId": row.generated_version_id,
        "generationJobId": row.generation_job_id,
        "configurationSnapshotId": row.configuration_snapshot_id,
        "comparisonId": row.comparison_id,
        "utilityEvaluationId": row.utility_evaluation_id,
        "notes": row.notes,
        "metadata": row.metadata_json or {},
        "configurationSnapshot": to_snapshot_response(snapshot) if snapshot else None,
        "lineage": [to_lineage_response(event) for event in lineage],
        "privacyReport": {
            "available": privacy is not None,
            "id": privacy.id if privacy else None,
            "method": privacy.method if privacy else "",
            "score": json_safe(privacy.score) if privacy else None,
            "reportAvailable": bool(privacy.file_path) if privacy else False,
            "createdAt": _iso(privacy.created_at) if privacy else "",
        },
        "utilityEvaluation": {
            "available": utility is not None,
            "id": utility.id if utility else None,
            "status": utility.status if utility else "",
            "evaluationType": utility.evaluation_type if utility else "",
            "modelName": utility.model_name if utility else "",
            "targetColumn": utility.target_column if utility else "",
            "taskType": (utility.metrics_json or {}).get("taskType")
            or (utility.preprocessing_config_json or {}).get("taskType")
            if utility
            else None,
            "metrics": json_safe(utility.metrics_json or {}) if utility else {},
            "comparison": json_safe(utility.comparison_summary_json or {}) if utility else {},
            "reportAvailable": bool(utility.report_path) if utility else False,
            "reportCsvAvailable": bool(utility.report_csv_path) if utility else False,
            "reportPdfAvailable": bool(utility.report_pdf_path) if utility else False,
        },
        "comparisonSummary": {
            "available": comparison is not None,
            "id": comparison.id if comparison else None,
            "name": comparison.name if comparison else "",
            "score": json_safe(comparison.summary_score) if comparison else None,
            "reportAvailable": bool(comparison.file_path) if comparison else False,
        },
        "reportAvailability": {
            "privacyReport": bool(privacy and privacy.file_path),
            "utilityReport": bool(utility and utility.report_path),
            "utilityCsvReport": bool(utility and utility.report_csv_path),
            "utilityPdfReport": bool(utility and utility.report_pdf_path),
            "comparisonReport": bool(comparison and comparison.file_path),
        },
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
    }
