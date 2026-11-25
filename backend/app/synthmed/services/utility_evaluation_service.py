from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import random
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
from fastapi import HTTPException, Request
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.models.user import User
from app.services.audit_service import log_audit
from app.synthmed.models import SynthMedGeneratedDataset, SynthMedSourceDataset, SynthMedUtilityEvaluation
from app.synthmed.services import versioning_service
from app.synthmed.services.dataset_service import json_safe, read_source_dataframe
from app.synthmed.services.medical_schema_service import profile_medical_schema
from app.synthmed.services.source_service import (
    ensure_generated_access,
    ensure_source_access,
    get_generated,
    get_source,
)
from app.synthmed.services.storage_service import SynthMedStorageService

logger = logging.getLogger(__name__)

TERMINAL = {"Completed", "Failed"}
ACTIVE = {
    "Queued",
    "Validating",
    "Preprocessing",
    "Training",
    "Training TSTR",
    "Training TRTR",
    "Training TSTR/TRTR",
    "Evaluating",
    "Evaluating TSTR",
    "Evaluating TRTR",
    "Evaluating TSTR/TRTR",
    "Saving Results",
}
_executor: ThreadPoolExecutor | None = None
_executor_lock = Lock()

CLASSIFICATION_ALGOS = {
    "LogisticRegression": lambda seed: LogisticRegression(max_iter=1000, random_state=seed),
    "RandomForestClassifier": lambda seed: RandomForestClassifier(n_estimators=200, random_state=seed),
    "DecisionTreeClassifier": lambda seed: DecisionTreeClassifier(random_state=seed),
    "GradientBoostingClassifier": lambda seed: GradientBoostingClassifier(random_state=seed),
}
REGRESSION_ALGOS = {
    "LinearRegression": lambda seed: LinearRegression(),
    "Ridge": lambda seed: Ridge(random_state=seed),
    "RandomForestRegressor": lambda seed: RandomForestRegressor(n_estimators=200, random_state=seed),
    "GradientBoostingRegressor": lambda seed: GradientBoostingRegressor(random_state=seed),
}
ALLOWED_ALGOS = {**CLASSIFICATION_ALGOS, **REGRESSION_ALGOS}
CLASSIFICATION_COMPARISON_KEYS = [
    "accuracy",
    "balancedAccuracy",
    "precisionMacro",
    "recallMacro",
    "f1Macro",
    "f1Weighted",
    "rocAuc",
]
REGRESSION_METRIC_KEYS = ["mae", "mse", "rmse", "r2"]
TARGET_BLOCKLIST = {"age", "gender", "sex", "bloodgroup", "blood_group", "bloodtype"}
IDENTIFIER_HINTS = {
    "id",
    "patientid",
    "patient_id",
    "name",
    "address",
    "phone",
    "email",
    "hospitalid",
    "hospital_id",
    "rowid",
    "anchor",
    "sourceid",
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_phase_status(phase: str, *, do_tstr: bool, do_trtr: bool) -> str:
    if do_tstr and do_trtr:
        return f"{phase} TSTR/TRTR"
    return f"{phase} {'TSTR' if do_tstr else 'TRTR'}"


def _norm(value: Any) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def _session_factory(db: Session | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), expire_on_commit=False) if db is not None else SessionLocal


def _get_executor(settings: Settings) -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, settings.synthmed_generation_worker_count),
                thread_name_prefix="synthmed-utility",
            )
        return _executor


def shutdown_executor(wait: bool = True) -> None:
    global _executor
    with _executor_lock:
        ex = _executor
        _executor = None
    if ex is not None:
        ex.shutdown(wait=wait, cancel_futures=not wait)


def _status(row: SynthMedUtilityEvaluation, value: str, **updates: Any) -> None:
    row.status = value
    row.updated_at = _now()
    for k, v in updates.items():
        setattr(row, k, v)


def _error(error: Exception) -> dict[str, Any]:
    tb = traceback.format_exc()[-2000:]
    msg = str(error)[:1000] or type(error).__name__
    return {"type": type(error).__name__, "message": msg, "traceback": tb}


def _approved_columns(frame: pd.DataFrame) -> set[str]:
    profile = profile_medical_schema(frame)
    return {str(c) for c in profile.get("approvedOutputColumns", [])}


def _is_identifier_like(col: str) -> bool:
    n = _norm(col)
    return any(_norm(h) in n for h in IDENTIFIER_HINTS)


def _target_allowed(target: str, frame: pd.DataFrame) -> tuple[bool, str]:
    n = _norm(target)
    if n in TARGET_BLOCKLIST:
        return False, f"Target '{target}' is blocked by policy."
    if _is_identifier_like(target):
        return False, f"Target '{target}' appears identifier-like."
    approved = _approved_columns(frame)
    if target not in frame.columns:
        return False, f"Target '{target}' not found."
    if approved and target not in approved:
        return False, f"Target '{target}' is not an approved medical output column."
    if frame[target].nunique(dropna=True) < 2:
        return False, f"Target '{target}' has insufficient class/value diversity."
    return True, ""


def _feature_allowed(col: str, target: str, frame: pd.DataFrame) -> tuple[bool, str]:
    if col == target:
        return False, "target column"
    if _is_identifier_like(col):
        return False, "identifier-like"
    approved = _approved_columns(frame)
    if approved and col not in approved:
        return False, "not approved medical output"
    if frame[col].nunique(dropna=True) <= 1:
        return False, "constant/zero-variance"
    n, tn = _norm(col), _norm(target)
    if n == tn or n.endswith(tn) or tn.endswith(n):
        return False, "potential target leakage"
    return True, ""


def _resolve_task_type(target: pd.Series, requested: str | None) -> str:
    numeric = pd.api.types.is_numeric_dtype(target)
    continuous = bool(numeric and target.nunique(dropna=True) > 20)
    requested = str(requested).strip().lower() if requested is not None else ""
    if requested == "regression":
        if continuous:
            return "regression"
        raise HTTPException(
            status_code=422,
            detail="Regression requires a numeric target with more than 20 distinct values.",
        )
    if requested == "classification":
        return "classification"
    if requested:
        raise HTTPException(status_code=422, detail="taskType must be 'regression' or 'classification'.")
    return "regression" if continuous else "classification"


def _build_pipeline(X: pd.DataFrame, algo: str, task_type: str, seed: int) -> Pipeline:
    algos = REGRESSION_ALGOS if task_type == "regression" else CLASSIFICATION_ALGOS
    if algo not in algos:
        raise HTTPException(
            status_code=422,
            detail=f"Model '{algo}' is not supported for {task_type}; allowed: {', '.join(algos)}",
        )
    num_cols = [c for c in X.columns if pd.api.types.is_numeric_dtype(X[c])]
    cat_cols = [c for c in X.columns if c not in num_cols]
    transformers = []
    if num_cols:
        numeric_pipe = Pipeline(
            [("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]
        )
        transformers.append(("num", numeric_pipe, num_cols))
    if cat_cols:
        categorical_pipe = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
            ]
        )
        transformers.append(("cat", categorical_pipe, cat_cols))
    pre = ColumnTransformer(transformers=transformers, remainder="drop", verbose_feature_names_out=False)
    return Pipeline([("preprocess", pre), ("model", algos[algo](seed))])


def _safe_auc(y_true, y_score, labels) -> float | None:
    try:
        unique = np.unique(y_true)
        if len(unique) < 2:
            return None
        if len(labels) == 2:
            if getattr(y_score, "ndim", 1) == 2 and y_score.shape[1] == 2:
                return float(roc_auc_score(y_true, y_score[:, 1]))
            return float(roc_auc_score(y_true, y_score))
        return float(roc_auc_score(y_true, y_score, multi_class="ovr", average="macro", labels=labels))
    except Exception:
        return None


def _labels(*series: Any) -> list[Any]:
    labels: list[Any] = []
    seen: set[str] = set()
    for item in series:
        for value in pd.Series(item).dropna().tolist():
            key = str(value)
            if key not in seen:
                seen.add(key)
                labels.append(value)
    return labels


def _probabilities(pipe: Pipeline, X: pd.DataFrame) -> Any:
    if not hasattr(pipe, "predict_proba"):
        return np.zeros((len(X), 0))
    return pipe.predict_proba(X)


def _classification_metrics(y_true, y_pred, y_score, labels) -> dict[str, Any]:
    report = classification_report(y_true, y_pred, labels=labels, output_dict=True, zero_division=0)
    per_class = {}
    for label in labels:
        key = str(label)
        row = report.get(key, {})
        per_class[key] = {
            "precision": json_safe(row.get("precision")),
            "recall": json_safe(row.get("recall")),
            "f1": json_safe(row.get("f1-score")),
            "support": int(row.get("support", 0)),
        }
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    return {
        "accuracy": json_safe(accuracy_score(y_true, y_pred)),
        "balancedAccuracy": json_safe(balanced_accuracy_score(y_true, y_pred)),
        "precisionMacro": json_safe(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recallMacro": json_safe(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1Macro": json_safe(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1Weighted": json_safe(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "rocAuc": json_safe(_safe_auc(y_true, y_score, labels)),
        "confusionMatrix": {"labels": [str(label) for label in labels], "matrix": cm.tolist()},
        "perClass": per_class,
        "classificationReport": json_safe(report),
    }


def _regression_metrics(y_true, y_pred) -> dict[str, Any]:
    actual = np.asarray(y_true, dtype=float)
    predicted = np.asarray(y_pred, dtype=float)
    mse = float(mean_squared_error(actual, predicted))
    return {
        "mae": json_safe(mean_absolute_error(actual, predicted)),
        "mse": json_safe(mse),
        "rmse": json_safe(float(np.sqrt(mse))),
        "r2": json_safe(r2_score(actual, predicted)),
    }


def _comparison(
    tstr: dict[str, Any] | None,
    trtr: dict[str, Any] | None,
    task_type: str = "classification",
    evaluation_type: str = "BOTH",
) -> dict[str, Any]:
    if not tstr or not trtr:
        missing = [name for name, metrics in (("TSTR", tstr), ("TRTR", trtr)) if not metrics]
        return {
            "taskType": task_type,
            "gap": {},
            "interpretation": (
                "Comparison unavailable because " + " and ".join(missing)
                + " metrics are not present (evaluationType=" + evaluation_type + ")."
            ),
        }
    keys = REGRESSION_METRIC_KEYS if task_type == "regression" else CLASSIFICATION_COMPARISON_KEYS
    gap = {}
    for key in keys:
        a, b = tstr.get(key), trtr.get(key)
        comparable = isinstance(a, (int, float)) and isinstance(b, (int, float))
        gap[key] = json_safe(float(a) - float(b)) if comparable else None
    if task_type == "regression":
        interpretation = (
            "TSTR minus TRTR gaps on the same held-out real test partition. Lower MAE/MSE/RMSE and "
            "higher R2 indicate better TSTR utility. Gaps describe utility difference, not clinical "
            "validity or privacy safety."
        )
    else:
        interpretation = (
            "Compare TSTR against TRTR on the same held-out real test partition. Gaps indicate utility "
            "difference, not clinical validity or privacy safety."
        )
    return {"taskType": task_type, "gap": gap, "interpretation": interpretation}


def _to_csv(report: dict[str, Any]) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["section", "metric", "value"])
    meta = report.get("metadata", {})
    for k, v in meta.items():
        w.writerow(["metadata", k, json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v])
    for section in ["tstr", "trtr"]:
        metrics = (report.get(section) or {}).get("metrics", {})
        for k, v in metrics.items():
            w.writerow([section, k, json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v])
    for wmsg in report.get("warnings", []):
        w.writerow(["warning", "warning", wmsg])
    for lim in report.get("limitations", []):
        w.writerow(["limitation", "limitation", lim])
    return out.getvalue().encode("utf-8")


def _report_payload(row: SynthMedUtilityEvaluation) -> dict[str, Any]:
    metrics = row.metrics_json or {}
    prep = row.preprocessing_config_json or {}
    meta: dict[str, Any] = {
        "evaluationId": row.id,
        "evaluationName": row.evaluation_name,
        "evaluationType": row.evaluation_type,
        "status": row.status,
        "modelName": row.model_name,
        "targetColumn": row.target_column,
        "featureColumns": row.feature_columns_json or [],
        "sourceDatasetId": row.source_dataset_id,
        "generatedDatasetId": row.generated_dataset_id,
        "sourceVersionId": prep.get("sourceVersionId") or prep.get("source_version_id") or "",
        "generatedVersionId": prep.get("generatedVersionId") or prep.get("generated_version_id") or "",
        "trainTestSplit": row.train_test_split or {},
        "preprocessing": prep,
        "createdAt": _iso(row.created_at),
        "completedAt": _iso(row.completed_at),
    }
    methodology: dict[str, Any] = {
        "leakageControls": [
            "Single real-data split reused for TSTR test and TRTR train/test.",
            "Preprocessing fitted only on training data for each run.",
            "Identifier-like and blocked columns excluded.",
            "Duplicate rows dropped before split; no overlap between real train and real test.",
        ]
    }
    if metrics.get("tstr"):
        methodology["tstr"] = (
            "Train exclusively on synthetic records; preprocessing fit on synthetic training only; "
            "evaluate on held-out real test records."
        )
    if metrics.get("trtr"):
        methodology["trtr"] = (
            "Train on real training split; preprocessing fit on real training only; evaluate on same "
            "held-out real test partition."
        )
    payload: dict[str, Any] = {
        "metadata": meta,
        "taskType": metrics.get("taskType") or prep.get("taskType") or "classification",
        "methodology": methodology,
        "comparison": row.comparison_summary_json or {},
        "warnings": row.warnings_json or [],
        "limitations": [
            "TSTR/TRTR utility does not establish clinical validity or patient safety.",
            "TSTR/TRTR utility does not establish privacy/anonymity.",
            "Results depend on target choice, split, preprocessing, and class imbalance.",
        ],
    }
    for section in ["tstr", "trtr"]:
        if metrics.get(section):
            payload[section] = metrics[section]
    return payload


def _pdf_escape(text: str) -> bytes:
    cleaned = str(text).encode("latin-1", errors="replace").decode("latin-1")
    cleaned = "".join(ch if ch == "\t" or ord(ch) >= 32 else "?" for ch in cleaned)
    cleaned = cleaned.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return cleaned.encode("latin-1")


def _format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(json_safe(value), ensure_ascii=True, sort_keys=True)
    return str(json_safe(value))


def _pdf_lines(report: dict[str, Any]) -> list[str]:
    meta = report.get("metadata") or {}
    lines = [
        "SynthMed Utility Evaluation Report",
        f"Evaluation ID: {meta.get('evaluationId', '')}",
        f"Evaluation name: {meta.get('evaluationName', '')}",
        f"Evaluation type: {meta.get('evaluationType', '')}",
        f"Status: {meta.get('status', '')}",
        f"Source dataset ID: {meta.get('sourceDatasetId', '')}",
        f"Generated dataset ID: {meta.get('generatedDatasetId', '')}",
        f"Source version ID: {meta.get('sourceVersionId', '')}",
        f"Generated version ID: {meta.get('generatedVersionId', '')}",
        f"Model: {meta.get('modelName', '')}",
        f"Target: {meta.get('targetColumn', '')}",
        f"Task type: {report.get('taskType', '')}",
        f"Created at: {meta.get('createdAt', '')}",
        f"Completed at: {meta.get('completedAt', '')}",
    ]
    for section in ["tstr", "trtr"]:
        section_data = report.get(section)
        if not section_data:
            continue
        label = section.upper()
        for key in ["trainSource", "trainRecords", "testRecords"]:
            if key in section_data:
                lines.append(f"{label} {key}: {_format_value(section_data[key])}")
        for key, value in (section_data.get("metrics") or {}).items():
            lines.append(f"{label} metric {key}: {_format_value(value)}")
    comparison = report.get("comparison") or {}
    for key, value in (comparison.get("gap") or {}).items():
        lines.append(f"Comparison gap {key}: {_format_value(value)}")
    if comparison.get("interpretation"):
        lines.append(f"Comparison interpretation: {comparison['interpretation']}")
    for warning in report.get("warnings") or []:
        lines.append(f"Warning: {warning}")
    for limitation in report.get("limitations") or []:
        lines.append(f"Limitation: {limitation}")
    return lines


def _build_pdf(lines: list[str]) -> bytes:
    font_number = 3
    first_content_number = 4
    page_numbers = [first_content_number + 2 * index for index in range(len(lines))]
    kids = " ".join(f"{number} 0 R" for number in page_numbers)
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{kids}] /Count {len(lines)} >>".encode("ascii")
        ),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    for index, line in enumerate(lines):
        content_number = first_content_number + 2 * index
        page_number = content_number + 1
        text = b"BT /F1 10 Tf 36 760 Td (" + _pdf_escape(line) + b") Tj ET"
        objects[content_number] = (
            b"<< /Length " + str(len(text)).encode("ascii") + b" >>\nstream\n" + text + b"\nendstream"
        )
        objects[page_number] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_number} 0 R >> >> /Contents {content_number} 0 R >>"
        ).encode("ascii")
    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out.extend(f"{number} 0 obj\n".encode("ascii"))
        out.extend(objects[number])
        out.extend(b"\nendobj\n")
    xref_offset = len(out)
    size = max(objects) + 1
    out.extend(f"xref\n0 {size}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for number in range(1, size):
        out.extend(f"{offsets[number]:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


def _save_reports(storage: SynthMedStorageService, row: SynthMedUtilityEvaluation) -> None:
    payload = _report_payload(row)
    json_content = json.dumps(json_safe(payload), ensure_ascii=False, indent=2).encode("utf-8")
    json_path, json_relative = storage.save_report(row.id, "utility_report.json", json_content)
    csv_path, csv_relative = storage.save_report(row.id, "utility_report.csv", _to_csv(payload))
    pdf_path, pdf_relative = storage.save_report(row.id, "utility_report.pdf", _build_pdf(_pdf_lines(payload)))
    row.report_path = json_relative
    row.report_csv_path = csv_relative
    row.report_pdf_path = pdf_relative
    row.report_sha256 = _sha256_file(json_path)
    row.report_csv_sha256 = _sha256_file(csv_path)
    row.report_pdf_sha256 = _sha256_file(pdf_path)


def _load_frames(db: Session, row: SynthMedUtilityEvaluation, settings: Settings) -> tuple[pd.DataFrame, pd.DataFrame]:
    source = db.get(SynthMedSourceDataset, row.source_dataset_id)
    generated = db.get(SynthMedGeneratedDataset, row.generated_dataset_id)
    if source is None or generated is None:
        raise RuntimeError("Source or generated dataset not found.")
    storage = SynthMedStorageService(settings)
    real = read_source_dataframe(storage.resolve_source(source.stored_path), source.file_format)
    synth = read_source_dataframe(storage.resolve_generated(generated.stored_path), generated.file_format)
    return real, synth


def _validate_and_prepare(
    real: pd.DataFrame,
    synth: pd.DataFrame,
    row: SynthMedUtilityEvaluation,
) -> dict[str, Any]:
    target = row.target_column
    ok, reason = _target_allowed(target, real)
    if not ok:
        raise HTTPException(status_code=422, detail=reason)
    if target not in synth.columns:
        raise HTTPException(status_code=422, detail=f"Target '{target}' missing from synthetic dataset.")
    requested_features = [str(c) for c in (row.feature_columns_json or [])]
    if not requested_features:
        requested_features = [c for c in real.columns if c != target]
    approved_real = _approved_columns(real)
    approved_synth = _approved_columns(synth)
    features: list[str] = []
    excluded: dict[str, str] = {}
    for col in requested_features:
        if col not in real.columns or col not in synth.columns:
            excluded[col] = "missing from real or synthetic dataset"
            continue
        okf, why = _feature_allowed(col, target, real)
        if not okf:
            excluded[col] = why
            continue
        if approved_real and col not in approved_real:
            excluded[col] = "not approved medical output (real)"
            continue
        if approved_synth and col not in approved_synth:
            excluded[col] = "not approved medical output (synthetic)"
            continue
        features.append(col)
    if not features:
        raise HTTPException(status_code=422, detail="No valid features remain after leakage/approval filtering.")
    features = [f for f in features if f != target]
    task_type = _resolve_task_type(real[target], (row.preprocessing_config_json or {}).get("taskType"))
    return {"features": features, "excluded": excluded, "taskType": task_type}


def run_utility_evaluation(
    job_id: str,
    settings: Settings,
    factory: sessionmaker[Session] | None = None,
) -> SynthMedUtilityEvaluation | None:
    session_factory = factory or SessionLocal
    with session_factory() as db:
        row = db.get(SynthMedUtilityEvaluation, job_id)
        if row is None or row.status in TERMINAL:
            return row
        try:
            _status(row, "Validating", started_at=row.started_at or _now(), error_json=None)
            db.commit()
            real, synth = _load_frames(db, row, settings)
            prep = _validate_and_prepare(real, synth, row)
            features = prep["features"]
            task_type = prep["taskType"]
            evaluation_type = str(row.evaluation_type or "BOTH").upper()
            do_tstr = evaluation_type in {"TSTR", "BOTH"}
            do_trtr = evaluation_type in {"TRTR", "BOTH"}
            warnings: list[str] = []
            if prep["excluded"]:
                warnings.append(f"Excluded {len(prep['excluded'])} feature(s) by validation/leakage rules.")
            if not do_tstr:
                warnings.append("TSTR was not requested; no TSTR metrics were computed.")
            if not do_trtr:
                warnings.append("TRTR was not requested; no TRTR metrics were computed.")

            before_r, before_s = len(real), len(synth)
            real = real.drop_duplicates().reset_index(drop=True)
            synth = synth.drop_duplicates().reset_index(drop=True)
            if len(real) != before_r or len(synth) != before_s:
                warnings.append("Duplicate rows were removed before splitting/training to prevent leakage.")

            _status(row, "Preprocessing")
            db.commit()
            split = row.train_test_split or {}
            test_size = float(split.get("testSize", 0.2))
            seed = int(split.get("randomSeed", split.get("seed", 42)))
            random.seed(seed)
            np.random.seed(seed)
            if not (0.1 <= test_size <= 0.5):
                raise HTTPException(status_code=422, detail="testSize must be between 0.1 and 0.5.")

            if task_type == "regression":
                y_real = pd.to_numeric(real[row.target_column], errors="coerce")
                y_synth = pd.to_numeric(synth[row.target_column], errors="coerce")
                real_mask = y_real.notna().to_numpy()
                synth_mask = y_synth.notna().to_numpy()
                if not real_mask.all() or not synth_mask.all():
                    warnings.append("Rows with non-numeric target values were removed before regression.")
                    real = real.loc[real_mask].reset_index(drop=True)
                    synth = synth.loc[synth_mask].reset_index(drop=True)
                    y_real = y_real.loc[real_mask].reset_index(drop=True)
                    y_synth = y_synth.loc[synth_mask].reset_index(drop=True)
            else:
                y_real = real[row.target_column].copy()
                y_synth = synth[row.target_column].copy()

            stratify = None
            stratify_requested = bool(split.get("stratify", True))
            if task_type == "classification" and stratify_requested:
                if y_real.nunique(dropna=True) > 1 and y_real.value_counts().min() >= 2:
                    stratify = y_real
                else:
                    warnings.append("Stratified split unavailable; used random split.")
            elif task_type == "classification":
                warnings.append("Stratified split was not requested; used random split.")

            X_real = real[features].copy()
            X_synth = synth[features].copy()
            for col in features:
                if not pd.api.types.is_numeric_dtype(real[col]):
                    X_real[col] = X_real[col].astype("string")
                if not pd.api.types.is_numeric_dtype(synth[col]):
                    X_synth[col] = X_synth[col].astype("string")
            if task_type == "classification":
                y_real = y_real.astype("string")
                y_synth = y_synth.astype("string")

            Xr_train, Xr_test, yr_train, yr_test = train_test_split(
                X_real,
                y_real,
                test_size=test_size,
                random_state=seed,
                stratify=stratify,
            )
            if len(Xr_test) == 0 or len(Xr_train) == 0 or len(X_synth) == 0:
                raise HTTPException(status_code=422, detail="Insufficient records for train/test evaluation.")

            _status(row, _run_phase_status("Training", do_tstr=do_tstr, do_trtr=do_trtr))
            db.commit()
            tstr_pipe = None
            trtr_pipe = None
            if do_tstr:
                tstr_pipe = _build_pipeline(X_synth, row.model_name, task_type, seed)
                tstr_pipe.fit(X_synth, y_synth)
            if do_trtr:
                trtr_pipe = _build_pipeline(Xr_train, row.model_name, task_type, seed)
                trtr_pipe.fit(Xr_train, yr_train)

            _status(row, _run_phase_status("Evaluating", do_tstr=do_tstr, do_trtr=do_trtr))
            db.commit()
            tstr_metrics: dict[str, Any] | None = None
            trtr_metrics: dict[str, Any] | None = None
            if do_tstr and tstr_pipe is not None:
                pred_tstr = tstr_pipe.predict(Xr_test)
                if task_type == "regression":
                    tstr_metrics = _regression_metrics(yr_test, pred_tstr)
                else:
                    predictions = [pred_tstr]
                    if do_trtr and trtr_pipe is not None:
                        predictions.append(trtr_pipe.predict(Xr_test))
                    labels = _labels(yr_test, *predictions)
                    score_tstr = _probabilities(tstr_pipe, Xr_test)
                    tstr_metrics = _classification_metrics(yr_test, pred_tstr, score_tstr, labels)
                    if score_tstr.size == 0:
                        warnings.append("ROC-AUC unavailable because model does not expose probability scores.")
                    if tstr_metrics.get("rocAuc") is None:
                        warnings.append("ROC-AUC was not computed for some cases.")
            if do_trtr and trtr_pipe is not None:
                pred_trtr = trtr_pipe.predict(Xr_test)
                if task_type == "regression":
                    trtr_metrics = _regression_metrics(yr_test, pred_trtr)
                else:
                    labels = _labels(yr_test, pred_trtr)
                    if tstr_metrics is not None:
                        labels = _labels(yr_test, pred_trtr, tstr_pipe.predict(Xr_test))
                    score_trtr = _probabilities(trtr_pipe, Xr_test)
                    trtr_metrics = _classification_metrics(yr_test, pred_trtr, score_trtr, labels)
                    if score_trtr.size == 0:
                        warnings.append("ROC-AUC unavailable because model does not expose probability scores.")
                    if trtr_metrics.get("rocAuc") is None:
                        warnings.append("ROC-AUC was not computed for some cases.")

            comparison = _comparison(tstr_metrics, trtr_metrics, task_type, evaluation_type)
            _status(row, "Saving Results")
            db.commit()
            row.feature_columns_json = json_safe(features)
            row.preprocessing_config_json = json_safe(
                {
                    **(row.preprocessing_config_json or {}),
                    "taskType": task_type,
                    "excludedFeatures": prep["excluded"],
                    "numericFeatures": [c for c in features if pd.api.types.is_numeric_dtype(real[c])],
                    "categoricalFeatures": [c for c in features if not pd.api.types.is_numeric_dtype(real[c])],
                    "imputation": "median/mode",
                    "scaling": "StandardScaler(numeric)",
                    "encoding": "OneHotEncoder(handle_unknown=ignore,categorical)",
                }
            )
            metrics_payload: dict[str, Any] = {"taskType": task_type}
            if do_tstr and tstr_metrics is not None:
                metrics_payload["tstr"] = {
                    "metrics": tstr_metrics,
                    "trainRecords": int(len(X_synth)),
                    "testRecords": int(len(Xr_test)),
                    "trainSource": "synthetic",
                }
            if do_trtr and trtr_metrics is not None:
                metrics_payload["trtr"] = {
                    "metrics": trtr_metrics,
                    "trainRecords": int(len(Xr_train)),
                    "testRecords": int(len(Xr_test)),
                    "trainSource": "real",
                }
            row.metrics_json = json_safe(metrics_payload)
            row.comparison_summary_json = json_safe(comparison)
            row.warnings_json = json_safe(warnings)
            storage = SynthMedStorageService(settings)
            _save_reports(storage, row)
            _status(row, "Completed", completed_at=_now())
            db.commit()
            return row
        except HTTPException as e:
            row = db.get(SynthMedUtilityEvaluation, job_id)
            if row:
                error_json = {"type": "ValidationError", "message": str(e.detail)}
                _status(row, "Failed", completed_at=_now(), error_json=error_json)
                db.commit()
            return row
        except Exception as error:
            row = db.get(SynthMedUtilityEvaluation, job_id)
            if row:
                _status(row, "Failed", completed_at=_now(), error_json=json_safe(_error(error)))
                db.commit()
            logger.exception("Utility evaluation failed: %s", job_id)
            return row


def create_utility_evaluation(
    db: Session,
    *,
    user: User,
    settings: Settings,
    payload: dict[str, Any],
    request: Request | None = None,
) -> SynthMedUtilityEvaluation:
    source = get_source(db, str(payload.get("sourceDatasetId") or ""))
    generated = get_generated(db, str(payload.get("generatedDatasetId") or ""))
    ensure_source_access(source, user)
    ensure_generated_access(generated, user)
    if generated.source_dataset_id != source.id:
        raise HTTPException(status_code=422, detail="Generated dataset does not belong to selected source dataset.")
    if generated.status != "Completed":
        raise HTTPException(status_code=422, detail="Generated dataset must be completed.")
    eval_type = str(payload.get("evaluationType") or "BOTH").upper()
    if eval_type not in {"TSTR", "TRTR", "BOTH"}:
        raise HTTPException(status_code=422, detail="evaluationType must be TSTR, TRTR, or BOTH.")
    algo = str(payload.get("modelName") or "")
    if algo not in ALLOWED_ALGOS:
        raise HTTPException(status_code=422, detail=f"Unsupported modelName. Allowed: {', '.join(ALLOWED_ALGOS)}")
    target = str(payload.get("targetColumn") or "").strip()
    if not target:
        raise HTTPException(status_code=422, detail="targetColumn is required.")
    storage = SynthMedStorageService(settings)
    real = read_source_dataframe(storage.resolve_source(source.stored_path), source.file_format)
    ok, reason = _target_allowed(target, real)
    if not ok:
        raise HTTPException(status_code=422, detail=reason)
    split = payload.get("trainTestSplit") or {}
    preprocessing = json_safe(payload.get("preprocessing") or {})
    row = SynthMedUtilityEvaluation(
        id=str(uuid4()),
        owner_id=user.id,
        source_dataset_id=source.id,
        generated_dataset_id=generated.id,
        status="Queued",
        evaluation_name=str(payload.get("evaluationName") or f"{generated.dataset_name} {algo} {target} utility"),
        evaluation_type=eval_type,
        model_name=algo,
        target_column=target,
        feature_columns_json=json_safe(payload.get("featureColumns") or []),
        train_test_split=json_safe(
            {
                "testSize": float(split.get("testSize", 0.2)),
                "randomSeed": int(split.get("randomSeed", split.get("seed", 42))),
                "stratify": bool(split.get("stratify", True)),
            }
        ),
        preprocessing_config_json=preprocessing,
        metrics_json={},
        comparison_summary_json={},
        warnings_json=[],
    )
    db.add(row)
    db.flush()
    try:
        src_v = versioning_service.ensure_source_version(db, user=user, settings=settings, source=source)
        gen_v = versioning_service.ensure_generated_version(db, user=user, settings=settings, generated=generated)
        versioning_service.record_lineage(
            db,
            owner_id=user.id,
            event_type="utility_evaluation",
            parent_type="synthmed_dataset_version",
            parent_id=gen_v.id,
            child_type="synthmed_utility_evaluation",
            child_id=row.id,
            source_dataset_id=source.id,
            generated_dataset_id=generated.id,
            metadata={"sourceVersionId": src_v.id, "target": target, "model": algo},
        )
        preprocessing.update({"sourceVersionId": src_v.id, "generatedVersionId": gen_v.id})
        row.preprocessing_config_json = preprocessing
    except Exception:
        pass
    log_audit(
        db,
        action="synthmed.utility_evaluation_created",
        resource_type="synthmed_utility_evaluation",
        resource_id=row.id,
        actor_id=user.id,
        details={"source_dataset_id": source.id, "generated_dataset_id": generated.id, "target": target, "model": algo},
        request=request,
    )
    db.commit()
    db.refresh(row)
    factory = _session_factory(db)
    if settings.synthmed_generation_inline:
        run_utility_evaluation(row.id, settings, factory)
        db.refresh(row)
    else:
        _get_executor(settings).submit(run_utility_evaluation, row.id, settings, factory)
    return row


def list_utility_evaluations(db: Session, user: User) -> list[SynthMedUtilityEvaluation]:
    stmt = select(SynthMedUtilityEvaluation)
    if user.role != UserRole.ADMINISTRATOR:
        stmt = stmt.where(SynthMedUtilityEvaluation.owner_id == user.id)
    return list(db.scalars(stmt.order_by(SynthMedUtilityEvaluation.created_at.desc())))


def get_utility_evaluation(db: Session, eval_id: str, user: User) -> SynthMedUtilityEvaluation:
    row = db.get(SynthMedUtilityEvaluation, eval_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Utility evaluation not found.")
    if row.owner_id != user.id and user.role != UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=403, detail="Not permitted to view this utility evaluation.")
    return row


def to_response(row: SynthMedUtilityEvaluation) -> dict[str, Any]:
    report = _report_payload(row)
    return {
        "id": row.id,
        "sourceDatasetId": row.source_dataset_id,
        "generatedDatasetId": row.generated_dataset_id,
        "status": row.status,
        "evaluationName": row.evaluation_name,
        "evaluationType": row.evaluation_type,
        "modelName": row.model_name,
        "targetColumn": row.target_column,
        "featureColumns": row.feature_columns_json or [],
        "trainTestSplit": row.train_test_split or {},
        "preprocessing": row.preprocessing_config_json or {},
        "metrics": row.metrics_json or {},
        "comparison": row.comparison_summary_json or {},
        "warnings": row.warnings_json or [],
        "reportAvailable": bool(row.report_path),
        "reportCsvAvailable": bool(row.report_csv_path),
        "reportPdfAvailable": bool(row.report_pdf_path),
        "error": (row.error_json or {}).get("message", ""),
        "createdAt": _iso(row.created_at),
        "startedAt": _iso(row.started_at),
        "completedAt": _iso(row.completed_at),
        "report": report if row.status == "Completed" else None,
    }


def _report_matches_format(fmt: str, content: bytes) -> bool:
    if fmt == "json":
        try:
            return isinstance(json.loads(content.decode("utf-8")), dict)
        except (UnicodeDecodeError, ValueError):
            return False
    if fmt == "csv":
        return content.decode("utf-8", errors="ignore").splitlines()[:1] == ["section,metric,value"]
    if fmt == "pdf":
        return content.startswith(b"%PDF-") and b"%%EOF" in content
    return False


def report_download_path(row: SynthMedUtilityEvaluation, settings: Settings, fmt: str) -> tuple[Path, str, str]:
    storage = SynthMedStorageService(settings)
    fmt = str(fmt).lower()
    if fmt == "json":
        stored_path, checksum, media_type, filename = (
            row.report_path,
            row.report_sha256,
            "application/json",
            "utility_report.json",
        )
    elif fmt == "csv":
        stored_path, checksum, media_type, filename = (
            row.report_csv_path,
            row.report_csv_sha256,
            "text/csv",
            "utility_report.csv",
        )
    elif fmt == "pdf":
        stored_path, checksum, media_type, filename = (
            row.report_pdf_path,
            row.report_pdf_sha256,
            "application/pdf",
            "utility_report.pdf",
        )
    else:
        raise HTTPException(status_code=422, detail="Unsupported report format.")
    if not stored_path:
        raise HTTPException(status_code=404, detail=f"Utility {fmt.upper()} report not found.")
    try:
        path = storage.resolve_report(stored_path)
        content = path.read_bytes()
    except (ValueError, FileNotFoundError, OSError) as error:
        raise HTTPException(status_code=404, detail=f"Utility {fmt.upper()} report not found.") from error
    if not checksum:
        raise HTTPException(status_code=409, detail="Report checksum unavailable; download blocked.")
    if hashlib.sha256(content).hexdigest() != checksum:
        raise HTTPException(status_code=409, detail="Report checksum mismatch; download blocked.")
    if not _report_matches_format(fmt, content):
        raise HTTPException(status_code=409, detail="Report content is invalid; download blocked.")
    return path, media_type, filename
