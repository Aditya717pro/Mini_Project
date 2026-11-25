import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.enums import UserRole
from app.models.user import User
from app.synthmed.models import SynthMedGeneratedDataset, SynthMedSourceDataset, SynthMedUtilityEvaluation
from app.synthmed.services import utility_evaluation_service
from app.synthmed.services.storage_service import SynthMedStorageService


def _user(db: Session, email: str, role=UserRole.RESEARCHER) -> User:
    u = User(email=email, full_name="U", hashed_password="x", role=role, is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _save_df(storage: SynthMedStorageService, dataset_id: str, df: pd.DataFrame, kind: str):
    b = df.to_csv(index=False).encode("utf-8")
    if kind == "source":
        _, rel = storage.save_source(dataset_id, "data.csv", b)
    else:
        _, rel = storage.save_generated(dataset_id, "synthetic_data.csv", b)
    return rel, len(b)


def _mk_pair(db: Session, settings: Settings, owner: User, real_df: pd.DataFrame, synth_df: pd.DataFrame, suffix: str):
    storage = SynthMedStorageService(settings)
    sid = f"11111111-1111-1111-1111-1111111111{suffix}"
    gid = f"22222222-2222-2222-2222-2222222222{suffix}"
    srel, ssize = _save_df(storage, sid, real_df, "source")
    grel, gsize = _save_df(storage, gid, synth_df, "generated")
    src = SynthMedSourceDataset(
        id=sid,
        owner_id=owner.id,
        dataset_name=f"src{suffix}",
        original_filename="data.csv",
        stored_path=srel,
        file_format="CSV",
        file_size_bytes=ssize,
        checksum_sha256="s",
        row_count=len(real_df),
        column_count=len(real_df.columns),
    )
    gen = SynthMedGeneratedDataset(
        id=gid,
        owner_id=owner.id,
        source_dataset_id=sid,
        dataset_name=f"gen{suffix}",
        source_dataset_name=f"src{suffix}",
        generation_method="CTGAN",
        record_count=len(synth_df),
        column_count=len(synth_df.columns),
        file_format="CSV",
        file_size_bytes=gsize,
        checksum_sha256="g",
        stored_path=grel,
        status="Completed",
    )
    db.add_all([src, gen])
    db.commit()
    return src, gen


def _base_real(n=120):
    rng = pd.Series(range(n))
    return pd.DataFrame(
        {
            "Age": (20 + (rng % 50)).astype(int),
            "Gender": ["Male" if i % 2 == 0 else "Female" for i in range(n)],
            "Disease": ["Diabetes" if i % 3 == 0 else "Hypertension" if i % 3 == 1 else "Healthy" for i in range(n)],
            "Systolic_BP": 110 + (rng % 40),
            "Diastolic_BP": 70 + (rng % 20),
            "BMI": 20 + (rng % 15) * 0.5,
        }
    )


def _base_synth(real: pd.DataFrame) -> pd.DataFrame:
    df = real.copy()
    df["Systolic_BP"] = df["Systolic_BP"] + (pd.Series(range(len(df))) % 5 - 2)
    df["BMI"] = df["BMI"] + ((pd.Series(range(len(df))) % 3) - 1) * 0.2
    return df


def _payload(src: SynthMedSourceDataset, gen: SynthMedGeneratedDataset, **overrides):
    p = {
        "sourceDatasetId": src.id,
        "generatedDatasetId": gen.id,
        "modelName": "LogisticRegression",
        "targetColumn": "Disease",
        "featureColumns": ["Systolic_BP", "Diastolic_BP", "BMI"],
        "trainTestSplit": {"testSize": 0.2, "randomSeed": 42, "stratify": True},
        "evaluationType": "BOTH",
    }
    p.update(overrides)
    return p


def _create(db_session: Session, app, email: str, suffix: str, real=None, synth=None, **payload_overrides):
    settings: Settings = app.state.settings
    owner = _user(db_session, email)
    real_df = _base_real() if real is None else real
    synth_df = _base_synth(real_df) if synth is None else synth
    src, gen = _mk_pair(db_session, settings, owner, real_df, synth_df, suffix)
    row = utility_evaluation_service.create_utility_evaluation(
        db_session,
        user=owner,
        settings=settings,
        payload=_payload(src, gen, **payload_overrides),
    )
    return settings, owner, src, gen, row


def _regression_real() -> pd.DataFrame:
    real = _base_real()
    real["Glucose"] = 80 + (pd.Series(range(len(real))) % 40)
    return real


def _regression_overrides(**overrides):
    payload = {
        "targetColumn": "Glucose",
        "featureColumns": ["Systolic_BP", "BMI"],
        "modelName": "LinearRegression",
        "preprocessing": {"taskType": "regression"},
    }
    payload.update(overrides)
    return payload


def test_tstr_uses_only_synthetic_training(db_session: Session, app):
    _, _, _, _, row = _create(db_session, app, "tstr@test.com", "01")
    assert row.status == "Completed"
    assert row.metrics_json["tstr"]["trainSource"] == "synthetic"


def test_trtr_uses_only_real_training(db_session: Session, app):
    _, _, _, _, row = _create(db_session, app, "trtr@test.com", "02")
    trtr = row.metrics_json["trtr"]
    assert trtr["trainSource"] == "real"
    assert trtr["trainRecords"] < trtr["trainRecords"] + trtr["testRecords"]


def test_same_held_out_real_test_partition(db_session: Session, app):
    _, _, _, _, row = _create(db_session, app, "same@test.com", "03", modelName="RandomForestClassifier")
    assert row.metrics_json["tstr"]["testRecords"] == row.metrics_json["trtr"]["testRecords"]


def test_preprocessing_fit_train_only(db_session: Session, app):
    _, _, _, _, row = _create(db_session, app, "prep@test.com", "04")
    report = utility_evaluation_service.to_response(row)["report"]
    controls = report["methodology"]["leakageControls"]
    assert any("Preprocessing fitted only on training data" in c for c in controls)


def test_stratified_split_and_class_imbalance_metrics(db_session: Session, app):
    real = _base_real(150)
    real.loc[real.index[:120], "Disease"] = "Healthy"
    real.loc[real.index[120:135], "Disease"] = "Diabetes"
    real.loc[real.index[135:], "Disease"] = "Hypertension"
    _, _, _, _, row = _create(
        db_session,
        app,
        "imb@test.com",
        "05",
        real=real,
        modelName="RandomForestClassifier",
    )
    m = row.metrics_json["tstr"]["metrics"]
    assert "f1Macro" in m and "balancedAccuracy" in m and "perClass" in m


def test_duplicate_record_leakage_prevention(db_session: Session, app):
    real = pd.concat([_base_real(80), _base_real(80).iloc[[0, 1, 2]]], ignore_index=True)
    _, _, _, _, row = _create(
        db_session,
        app,
        "dup@test.com",
        "06",
        real=real,
        modelName="DecisionTreeClassifier",
    )
    assert any("Duplicate rows were removed" in w for w in row.warnings_json)


def test_no_source_test_rows_in_training(db_session: Session, app):
    real = _base_real()
    _, _, _, _, row = _create(db_session, app, "leak@test.com", "07", real=real)
    trtr = row.metrics_json["trtr"]
    assert trtr["trainRecords"] + trtr["testRecords"] <= len(real.drop_duplicates())


def test_feature_target_leakage_rejection(db_session: Session, app):
    real = _base_real()
    real["Disease_copy"] = real["Disease"]
    _, _, _, _, row = _create(
        db_session,
        app,
        "feat@test.com",
        "08",
        real=real,
        synth=real.copy(),
        featureColumns=["Disease_copy", "Systolic_BP", "BMI"],
    )
    assert row.status == "Completed"
    assert "Disease_copy" not in row.feature_columns_json


def test_unsupported_target_type_handling(db_session: Session, app):
    real = _base_real()
    real["constant"] = "x"
    with pytest.raises(HTTPException):
        _create(
            db_session,
            app,
            "target@test.com",
            "09",
            real=real,
            synth=real.copy(),
            targetColumn="constant",
        )


def test_unsupported_task_type_handling(db_session: Session, app):
    real = _base_real()
    _, _, _, _, row = _create(
        db_session,
        app,
        "task@test.com",
        "10",
        real=real,
        targetColumn="Systolic_BP",
        featureColumns=["Diastolic_BP", "BMI"],
        modelName="Ridge",
        preprocessing={"taskType": "regression"},
    )
    assert row.status == "Completed"
    assert row.preprocessing_config_json["taskType"] == "regression"
    assert set(row.metrics_json["tstr"]["metrics"]) == {"mae", "mse", "rmse", "r2"}


def test_invalid_target_selection_rejection(db_session: Session, app):
    with pytest.raises(HTTPException):
        _create(db_session, app, "invalid@test.com", "11", targetColumn="Age")


def test_classification_metrics_correctness(db_session: Session, app):
    _, _, _, _, row = _create(db_session, app, "metrics@test.com", "12")
    m = row.metrics_json["tstr"]["metrics"]
    keys = [
        "accuracy",
        "balancedAccuracy",
        "precisionMacro",
        "recallMacro",
        "f1Macro",
        "f1Weighted",
        "confusionMatrix",
        "perClass",
        "rocAuc",
        "classificationReport",
    ]
    for k in keys:
        assert k in m


def test_regression_metrics_correctness(db_session: Session, app):
    real = _regression_real()
    _, _, _, _, row = _create(db_session, app, "reg@test.com", "13", real=real, **_regression_overrides())
    assert row.status == "Completed"
    m = row.metrics_json["tstr"]["metrics"]
    assert set(m) == {"mae", "mse", "rmse", "r2"}
    assert all(isinstance(m[key], float) for key in m)
    assert m["mae"] >= 0 and m["mse"] >= 0 and m["rmse"] >= 0
    assert m["rmse"] == pytest.approx(math.sqrt(m["mse"]))
    assert -1.000001 <= m["r2"] <= 1.0
    trtr_m = row.metrics_json["trtr"]["metrics"]
    assert set(trtr_m) == {"mae", "mse", "rmse", "r2"}
    assert "rocAuc" not in m and "accuracy" not in m
    assert set(row.comparison_summary_json["gap"]) == {"mae", "mse", "rmse", "r2"}
    assert "lower" in row.comparison_summary_json["interpretation"].lower()
    assert "rocAuc" not in row.comparison_summary_json["gap"]
    assert row.metrics_json["taskType"] == "regression"
    assert row.preprocessing_config_json["taskType"] == "regression"


def test_utility_evaluation_record_creation(db_session: Session, app):
    _, _, _, _, row = _create(db_session, app, "rec@test.com", "14")
    assert db_session.get(SynthMedUtilityEvaluation, row.id) is not None


def test_status_transitions(db_session: Session, app):
    _, _, _, _, row = _create(db_session, app, "status@test.com", "15")
    assert row.status in {"Completed", "Failed"}
    assert row.completed_at is not None


def test_report_generation(db_session: Session, app):
    _, _, _, _, row = _create(db_session, app, "report@test.com", "16")
    assert row.report_path and row.report_path.endswith("utility_report.json")
    assert row.report_csv_path and row.report_csv_path.endswith("utility_report.csv")
    assert row.report_pdf_path and row.report_pdf_path.endswith("utility_report.pdf")


def test_report_download(db_session: Session, app):
    settings, _, _, _, row = _create(db_session, app, "dl@test.com", "17")
    path, media, name = utility_evaluation_service.report_download_path(row, settings, "json")
    assert path.exists()
    assert media == "application/json"
    assert name == "utility_report.json"


def test_failed_evaluation_status(db_session: Session, app):
    from sqlalchemy.orm import sessionmaker

    settings = app.state.settings
    owner = _user(db_session, "fail@test.com")
    real = _base_real()
    synth = real.drop(columns=["Disease"])
    src, gen = _mk_pair(db_session, settings, owner, real, synth, "18")
    row = SynthMedUtilityEvaluation(
        id="33333333-3333-3333-3333-333333333318",
        owner_id=owner.id,
        source_dataset_id=src.id,
        generated_dataset_id=gen.id,
        status="Queued",
        evaluation_name="x",
        evaluation_type="BOTH",
        model_name="LogisticRegression",
        target_column="Disease",
        feature_columns_json=["Systolic_BP"],
        train_test_split={"testSize": 0.2, "randomSeed": 42, "stratify": True},
        preprocessing_config_json={"taskType": "classification"},
        metrics_json={},
        comparison_summary_json={},
        warnings_json=[],
    )
    db_session.add(row)
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    out = utility_evaluation_service.run_utility_evaluation(row.id, settings, factory=factory)
    assert out is not None
    assert out.status == "Failed"
    assert out.error_json
    message = out.error_json["message"]
    assert "Disease" in message and "missing" in message.lower()
    assert "Traceback" not in message
    assert utility_evaluation_service.to_response(out)["error"] == message


def test_api_create_utility_evaluation(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    settings = app.state.settings
    owner = _user(db_session, "api19@test.com")
    app.dependency_overrides[get_current_user] = lambda: owner
    real = _base_real()
    src, gen = _mk_pair(db_session, settings, owner, real, _base_synth(real), "19")
    resp = client.post("/api/v1/synthmed/utility-evaluations", json=_payload(src, gen))
    assert resp.status_code == 201
    body = resp.json()
    assert body["targetColumn"] == "Disease"


def test_api_list_utility_evaluations(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    settings = app.state.settings
    owner = _user(db_session, "api20@test.com")
    app.dependency_overrides[get_current_user] = lambda: owner
    real = _base_real()
    src, gen = _mk_pair(db_session, settings, owner, real, _base_synth(real), "20")
    client.post("/api/v1/synthmed/utility-evaluations", json=_payload(src, gen))
    resp = client.get("/api/v1/synthmed/utility-evaluations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


def test_api_get_utility_evaluation(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    settings = app.state.settings
    owner = _user(db_session, "api21@test.com")
    app.dependency_overrides[get_current_user] = lambda: owner
    real = _base_real()
    src, gen = _mk_pair(db_session, settings, owner, real, _base_synth(real), "21")
    eid = client.post("/api/v1/synthmed/utility-evaluations", json=_payload(src, gen)).json()["id"]
    resp = client.get(f"/api/v1/synthmed/utility-evaluations/{eid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == eid


def test_api_get_utility_report(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    settings = app.state.settings
    owner = _user(db_session, "api22@test.com")
    app.dependency_overrides[get_current_user] = lambda: owner
    real = _base_real()
    src, gen = _mk_pair(db_session, settings, owner, real, _base_synth(real), "22")
    eid = client.post("/api/v1/synthmed/utility-evaluations", json=_payload(src, gen)).json()["id"]
    resp = client.get(f"/api/v1/synthmed/utility-evaluations/{eid}/report")
    assert resp.status_code == 200
    assert "metadata" in resp.json()


def test_report_export_json(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    settings = app.state.settings
    owner = _user(db_session, "api23@test.com")
    app.dependency_overrides[get_current_user] = lambda: owner
    real = _base_real()
    src, gen = _mk_pair(db_session, settings, owner, real, _base_synth(real), "23")
    eid = client.post("/api/v1/synthmed/utility-evaluations", json=_payload(src, gen)).json()["id"]
    resp = client.get(f"/api/v1/synthmed/utility-evaluations/{eid}/download?format=json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")


def test_report_export_csv(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    settings = app.state.settings
    owner = _user(db_session, "api24@test.com")
    app.dependency_overrides[get_current_user] = lambda: owner
    real = _base_real()
    src, gen = _mk_pair(db_session, settings, owner, real, _base_synth(real), "24")
    eid = client.post("/api/v1/synthmed/utility-evaluations", json=_payload(src, gen)).json()["id"]
    resp = client.get(f"/api/v1/synthmed/utility-evaluations/{eid}/download?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


def test_auth_and_ownership_enforcement(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    settings = app.state.settings
    owner = _user(db_session, "owner25@test.com")
    other = _user(db_session, "other25@test.com")
    real = _base_real()
    src, gen = _mk_pair(db_session, settings, owner, real, _base_synth(real), "25")
    app.dependency_overrides[get_current_user] = lambda: owner
    eid = client.post("/api/v1/synthmed/utility-evaluations", json=_payload(src, gen)).json()["id"]
    app.dependency_overrides[get_current_user] = lambda: other
    resp = client.get(f"/api/v1/synthmed/utility-evaluations/{eid}")
    assert resp.status_code == 403


def test_no_pii_in_reports(db_session: Session, app):
    real = _base_real()
    real["Patient_Name"] = "Jane Doe"
    real["Email"] = "x@example.com"
    _, _, _, _, row = _create(
        db_session,
        app,
        "pii@test.com",
        "26",
        real=real,
        synth=real.copy(),
        featureColumns=["Systolic_BP", "BMI"],
    )
    text = json.dumps(utility_evaluation_service.to_response(row)["report"])
    assert "Jane Doe" not in text
    assert "x@example.com" not in text


def test_no_source_record_exposure(db_session: Session, app):
    _, _, _, _, row = _create(db_session, app, "src27@test.com", "27")
    report = json.dumps(utility_evaluation_service.to_response(row)["report"]).lower()
    assert "patient_name" not in report
    assert "email" not in report
    assert "trainrecords" in report


def test_tstr_only_skips_trtr(db_session: Session, app):
    _, _, _, _, row = _create(db_session, app, "tonly@test.com", "28", evaluationType="TSTR")
    assert row.status == "Completed"
    assert "tstr" in row.metrics_json
    assert "trtr" not in row.metrics_json
    report = utility_evaluation_service.to_response(row)["report"]
    assert "tstr" in report
    assert "trtr" not in report
    assert "trtr" not in report["methodology"]
    assert row.comparison_summary_json["gap"] == {}
    assert "unavailable" in row.comparison_summary_json["interpretation"].lower()
    stored = json.loads(utility_evaluation_service.report_download_path(row, app.state.settings, "json")[0].read_text())
    assert "trtr" not in stored


def test_trtr_only_skips_tstr_and_keeps_real_split(db_session: Session, app):
    real = _base_real()
    _, _, _, _, row = _create(db_session, app, "ronly@test.com", "29", real=real, evaluationType="TRTR")
    assert row.status == "Completed"
    assert "trtr" in row.metrics_json
    assert "tstr" not in row.metrics_json
    trtr = row.metrics_json["trtr"]
    assert 0 < trtr["trainRecords"] < len(real.drop_duplicates())
    assert trtr["testRecords"] > 0
    report = utility_evaluation_service.to_response(row)["report"]
    assert "trtr" in report
    assert "tstr" not in report
    assert row.comparison_summary_json["gap"] == {}
    assert "unavailable" in row.comparison_summary_json["interpretation"].lower()


def test_evaluation_type_persisted(db_session: Session, app):
    _, _, _, _, row = _create(db_session, app, "etype@test.com", "30", evaluationType="TRTR")
    db_session.expire_all()
    stored = db_session.get(SynthMedUtilityEvaluation, row.id)
    assert stored.evaluation_type == "TRTR"
    assert utility_evaluation_service.to_response(stored)["evaluationType"] == "TRTR"


def test_auto_detect_regression_for_continuous_target(db_session: Session, app):
    real = _regression_real()
    _, _, _, _, row = _create(
        db_session,
        app,
        "auto@test.com",
        "31",
        real=real,
        targetColumn="Glucose",
        featureColumns=["Systolic_BP", "BMI"],
        modelName="GradientBoostingRegressor",
        preprocessing={},
    )
    assert row.status == "Completed"
    assert row.preprocessing_config_json["taskType"] == "regression"
    assert set(row.metrics_json["tstr"]["metrics"]) == {"mae", "mse", "rmse", "r2"}


def test_explicit_regression_requires_continuous_target(db_session: Session, app):
    _, _, _, _, row = _create(
        db_session,
        app,
        "disc@test.com",
        "32",
        modelName="LinearRegression",
        preprocessing={"taskType": "regression"},
    )
    assert row.status == "Failed"
    assert "regression" in row.error_json["message"].lower()
    assert "distinct" in row.error_json["message"].lower()


def test_pdf_report_generation_and_download(db_session: Session, app):
    settings, _, _, _, row = _create(db_session, app, "pdf@test.com", "33", evaluationName="ASCII PDF Report")
    assert row.report_pdf_path and row.report_pdf_path.endswith("utility_report.pdf")
    path, media, name = utility_evaluation_service.report_download_path(row, settings, "pdf")
    assert path.exists()
    assert media == "application/pdf"
    assert name == "utility_report.pdf"
    raw = path.read_bytes()
    assert raw.startswith(b"%PDF-1.4")
    assert b"%%EOF" in raw
    assert b"/BaseFont /Helvetica" in raw
    assert b"/Type /Page" in raw
    assert row.id.encode("ascii") in raw
    assert b"BOTH" in raw
    assert b"TSTR metric accuracy" in raw
    accuracy = row.metrics_json["tstr"]["metrics"]["accuracy"]
    assert str(accuracy).encode("ascii") in raw


def test_api_report_export_pdf(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    settings = app.state.settings
    owner = _user(db_session, "apipdf@test.com")
    app.dependency_overrides[get_current_user] = lambda: owner
    real = _base_real()
    src, gen = _mk_pair(db_session, settings, owner, real, _base_synth(real), "34")
    eid = client.post("/api/v1/synthmed/utility-evaluations", json=_payload(src, gen)).json()["id"]
    resp = client.get(f"/api/v1/synthmed/utility-evaluations/{eid}/download?format=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content.startswith(b"%PDF-1.4")


def test_async_submission_uses_executor(db_session: Session, app, monkeypatch: pytest.MonkeyPatch):
    settings = app.state.settings
    owner = _user(db_session, "async@test.com")
    real = _base_real()
    src, gen = _mk_pair(db_session, settings, owner, real, _base_synth(real), "35")
    monkeypatch.setattr(settings, "synthmed_generation_inline", False)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        utility_evaluation_service,
        "run_utility_evaluation",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    try:
        executor = utility_evaluation_service._get_executor(settings)
        assert isinstance(executor, ThreadPoolExecutor)
        assert executor.submit(lambda: 2 + 2).result(timeout=5) == 4
        row = utility_evaluation_service.create_utility_evaluation(
            db_session,
            user=owner,
            settings=settings,
            payload=_payload(src, gen),
        )
        assert row.status == "Queued"
        deadline = time.monotonic() + 5
        while not calls and time.monotonic() < deadline:
            time.sleep(0.01)
        assert calls
        assert calls[0][0][0] == row.id
    finally:
        utility_evaluation_service.shutdown_executor(wait=True)


def test_error_traceback_is_server_side_only(db_session: Session, app, monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):
        raise ValueError("regression target contains invalid values")

    monkeypatch.setattr(utility_evaluation_service, "_load_frames", boom)
    real = _regression_real()
    _, _, _, _, row = _create(db_session, app, "err@test.com", "36", real=real, **_regression_overrides())
    assert row.status == "Failed"
    assert row.error_json["message"] == "regression target contains invalid values"
    assert "Traceback" not in row.error_json["message"]
    assert "Traceback" in row.error_json["traceback"]
    assert utility_evaluation_service.to_response(row)["error"] == row.error_json["message"]


def test_report_checksums_are_recorded_and_downloads_are_verified(db_session: Session, app) -> None:
    settings, _, _, _, row = _create(db_session, app, "checksum@test.com", "61")
    storage = SynthMedStorageService(settings)

    assert row.report_sha256 == utility_evaluation_service._sha256_file(
        storage.resolve_report(row.report_path)
    )
    assert row.report_csv_sha256 == utility_evaluation_service._sha256_file(
        storage.resolve_report(row.report_csv_path)
    )
    assert row.report_pdf_sha256 == utility_evaluation_service._sha256_file(
        storage.resolve_report(row.report_pdf_path)
    )

    for format_name in ("json", "csv", "pdf"):
        path, _, _ = utility_evaluation_service.report_download_path(row, settings, format_name)
        assert path.exists()


def test_tampered_report_download_is_blocked(db_session: Session, app) -> None:
    settings, _, _, _, row = _create(db_session, app, "tamper@test.com", "62")
    path, _, _ = utility_evaluation_service.report_download_path(row, settings, "json")
    path.write_bytes(path.read_bytes() + b"\n")

    with pytest.raises(HTTPException) as raised:
        utility_evaluation_service.report_download_path(row, settings, "json")
    assert raised.value.status_code == 409


def test_report_writes_are_exclusive(db_session: Session, app) -> None:
    settings, _, _, _, row = _create(db_session, app, "exclusive@test.com", "63")
    storage = SynthMedStorageService(settings)

    with pytest.raises(FileExistsError):
        storage.save_report(row.id, "utility_report.json", b"{}")


def test_persisted_stratify_false_is_honored(db_session: Session, app) -> None:
    _, _, _, _, row = _create(
        db_session,
        app,
        "nostrat@test.com",
        "64",
        trainTestSplit={"testSize": 0.2, "randomSeed": 42, "stratify": False},
    )
    assert any("Stratified split was not requested" in warning for warning in row.warnings_json)


def test_labels_preserve_first_seen_order() -> None:
    labels = utility_evaluation_service._labels(
        pd.Series(["b", "a"]),
        pd.Series(["c", "b"]),
    )
    assert labels == ["b", "a", "c"]
