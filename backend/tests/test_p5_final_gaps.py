import hashlib
import json
import math

import pandas as pd
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.user import User
from app.synthmed.models import (
    SynthMedGenerationJob,
    SynthMedUtilityEvaluation,
)
from app.synthmed.services import experiment_service, utility_evaluation_service, versioning_service
from app.synthmed.services.storage_service import SynthMedStorageService
from tests.test_synthmed_p5 import _df, _mk, _u
from tests.test_synthmed_utility_evaluation import (
    _create,
    _regression_overrides,
    _regression_real,
)


def _job(db: Session, owner: User, source_id: str, job_id: str) -> SynthMedGenerationJob:
    job = SynthMedGenerationJob(
        id=job_id,
        owner_id=owner.id,
        source_dataset_id=source_id,
        status="Completed",
        model_name="CTGAN",
        generation_mode="Unconditional",
        selected_model="CTGAN",
        epochs=1,
        batch_size=100,
        seed=7,
        requested_record_count=30,
        generated_record_count=30,
        config_json={"model": "CTGAN", "epochs": 1, "batchSize": 100, "recordCount": 30, "seed": 7},
    )
    db.add(job)
    db.commit()
    return job


def test_snapshot_records_library_versions_without_mutating_job(db_session: Session, app) -> None:
    owner = _u(db_session, "final-snapshot@test.com")
    source, _ = _mk(db_session, app.state.settings, owner, 1001)
    job = _job(db_session, owner, source.id, "cccccccc-cccc-cccc-cccc-000000001001")
    original = dict(job.config_json)

    snapshot = versioning_service.snapshot_config(db_session, user=owner, job=job)
    db_session.add(snapshot)
    db_session.commit()

    assert job.config_json == original
    assert snapshot.config_json["sdvVersion"]
    versions = snapshot.config_json["libraryVersions"]
    assert {"python", "numpy", "pandas", "scikitLearn", "sdv"}.issubset(versions)
    expected = hashlib.sha256(
        json.dumps(snapshot.config_json, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert snapshot.config_hash == expected
    assert snapshot.is_immutable is True


def test_compare_uses_bmi_values_from_actual_files(db_session: Session, app) -> None:
    owner = _u(db_session, "final-bmi@test.com")
    settings: Settings = app.state.settings
    first = _df(30)
    first["Height_cm"] = 170.0
    first["Weight_kg"] = first["BMI"] * 1.7**2
    second = first.copy()
    second["BMI"] = second["BMI"] + 5
    source, _ = _mk(db_session, settings, owner, 1002, df=first, gdf=first)
    old = versioning_service.ensure_source_version(db_session, user=owner, settings=settings, source=source)

    storage = SynthMedStorageService(settings)
    _, relative = storage.save_source(source.id, "data_v2.csv", second.to_csv(index=False).encode())
    source.stored_path = relative
    db_session.commit()
    new = versioning_service.create_dataset_version(
        db_session, user=owner, settings=settings, kind="source", source=source
    )
    db_session.commit()

    result = versioning_service.compare_versions(
        db_session,
        user=owner,
        settings=settings,
        dataset_id=source.id,
        version_a_id=old.id,
        version_b_id=new.id,
    )
    before = result["medicalConsistency"]["a"]
    after = result["medicalConsistency"]["b"]
    assert before["available"] is True and after["available"] is True
    assert before["rowsOutsideHalfUnit"] == 0
    assert after["rowsOutsideHalfUnit"] == 30
    assert result["metadata"]["checksumChanged"] is True
    assert result["distributions"]["BMI"]["b"]["mean"] > result["distributions"]["BMI"]["a"]["mean"]


def test_version_distribution_pseudonymizes_categorical_values(db_session: Session, app) -> None:
    owner = _u(db_session, "final-pii-distribution@test.com")
    df = _df(12)
    df["PatientName"] = [f"SUBJECT-SECRET-{index:03d}" for index in range(len(df))]
    source, _ = _mk(db_session, app.state.settings, owner, 1005, df=df, gdf=df)
    version = versioning_service.ensure_source_version(
        db_session, user=owner, settings=app.state.settings, source=source
    )

    payload = versioning_service.to_version_response(version)
    encoded = json.dumps(payload)
    assert "SUBJECT-SECRET-000" not in encoded
    categories = payload["distributionSummary"]["PatientName"]["topValues"]
    assert categories
    assert all(item["value"].startswith("value_") for item in categories)


def test_snapshot_config_removes_row_level_raw_values(db_session: Session, app) -> None:
    owner = _u(db_session, "final-pii-snapshot@test.com")
    source, _ = _mk(db_session, app.state.settings, owner, 1006)
    job = _job(db_session, owner, source.id, "cccccccc-cccc-cccc-cccc-000000001006")
    job.config_json = {
        "model": "CTGAN",
        "selectedColumns": ["Age", "Gender"],
        "clinicalSetup": {"medicalProfile": {"categoricalValues": [{"value": "SECRET-DIAGNOSIS"}]}},
        "sourcePreservationPlanInternal": {"anchors": [{"disease": "SECRET-DIAGNOSIS"}]},
    }
    db_session.commit()

    snapshot = versioning_service.snapshot_config(db_session, user=owner, job=job)
    db_session.add(snapshot)
    db_session.commit()

    encoded = json.dumps(snapshot.config_json)
    assert "SECRET-DIAGNOSIS" not in encoded
    assert "medicalProfile" not in snapshot.config_json
    assert "sourcePreservationPlanInternal" not in snapshot.config_json
    assert snapshot.config_json["selectedColumns"] == ["Age", "Gender"]


def test_compare_detects_actual_checksum_changes(db_session: Session, app) -> None:
    owner = _u(db_session, "final-checksum@test.com")
    settings: Settings = app.state.settings
    source, _ = _mk(db_session, settings, owner, 1007)
    old = versioning_service.ensure_source_version(db_session, user=owner, settings=settings, source=source)

    storage = SynthMedStorageService(settings)
    _, relative = storage.save_source(
        source.id,
        "data_v2.csv",
        pd.read_csv(versioning_service._version_path(settings, old)).to_csv(index=False).encode(),
    )
    source.stored_path = relative
    db_session.commit()
    new = versioning_service.create_dataset_version(
        db_session, user=owner, settings=settings, kind="source", source=source
    )
    db_session.commit()

    old_path = versioning_service._version_path(settings, old)
    original = old_path.read_bytes()
    old_path.write_bytes(original + b"\n")
    try:
        result = versioning_service.compare_versions(
            db_session,
            user=owner,
            settings=settings,
            dataset_id=source.id,
            version_a_id=old.id,
            version_b_id=new.id,
        )
    finally:
        old_path.write_bytes(original)
    assert result["metadata"]["checksumMatchesRecorded"] == {"a": False, "b": True}


def test_generated_version_rejects_non_medical_columns(db_session: Session, app) -> None:
    owner = _u(db_session, "final-medical-schema@test.com")
    df = _df(10)
    generated_frame = df.copy()
    generated_frame["PatientName"] = [f"SUBJECT-{index:03d}" for index in range(len(generated_frame))]
    source, generated = _mk(
        db_session, app.state.settings, owner, 1008, df=df, gdf=generated_frame
    )
    versioning_service.ensure_source_version(
        db_session, user=owner, settings=app.state.settings, source=source
    )

    with pytest.raises(HTTPException) as error:
        versioning_service.ensure_generated_version(
            db_session, user=owner, settings=app.state.settings, generated=generated
        )
    assert error.value.status_code == 422
    assert "medical output schema" in error.value.detail.lower()


def test_generated_restore_publishes_restored_bytes(db_session: Session, app) -> None:
    owner = _u(db_session, "final-generated-restore@test.com")
    settings: Settings = app.state.settings
    first = _df(12)
    second = first.copy()
    second["BMI"] = second["BMI"] + 1
    source, generated = _mk(db_session, settings, owner, 1009, df=first, gdf=first)
    original = versioning_service.ensure_generated_version(
        db_session, user=owner, settings=settings, generated=generated
    )

    storage = SynthMedStorageService(settings)
    _, relative = storage.save_generated(
        generated.id, "synthetic_data_v2.csv", second.to_csv(index=False).encode()
    )
    generated.stored_path = relative
    generated.checksum_sha256 = "changed"
    db_session.commit()
    versioning_service.create_dataset_version(
        db_session, user=owner, settings=settings, kind="generated", generated=generated
    )
    db_session.commit()

    historical_bytes = versioning_service._version_path(settings, original).read_bytes()
    restored = versioning_service.restore_version(
        db_session, user=owner, settings=settings, dataset_id=generated.id, version_id=original.id
    )
    live_path = versioning_service._dataset_path(settings, "generated", generated.stored_path)
    assert restored.is_active
    assert live_path.read_bytes() == historical_bytes
    assert generated.checksum_sha256 == original.checksum_sha256


def test_experiment_lineage_excludes_other_owner_events(db_session: Session, app) -> None:
    owner = _u(db_session, "final-lineage-owner@test.com")
    other = _u(db_session, "final-lineage-other@test.com")
    settings: Settings = app.state.settings
    source, _ = _mk(db_session, settings, owner, 1003)
    version = versioning_service.ensure_source_version(db_session, user=owner, settings=settings, source=source)
    experiment = experiment_service.create_experiment(
        db_session,
        user=owner,
        settings=settings,
        payload={
            "name": "Lineage isolation",
            "sourceDatasetId": source.id,
            "sourceVersionId": version.id,
        },
    )
    own_event = versioning_service.record_lineage(
        db_session,
        owner_id=owner.id,
        event_type="experiment_record",
        parent_type="synthmed_dataset_version",
        parent_id=version.id,
        child_type="synthmed_experiment",
        child_id=experiment.id,
    )
    foreign_event = versioning_service.record_lineage(
        db_session,
        owner_id=other.id,
        event_type="experiment_record",
        parent_type="synthmed_dataset_version",
        parent_id=version.id,
        child_type="synthmed_experiment",
        child_id="foreign-experiment",
    )
    db_session.commit()

    payload = versioning_service.to_experiment_response(db_session, experiment)
    ids = [event["id"] for event in payload["lineage"]]
    assert own_event.id in ids
    assert foreign_event.id not in ids


def test_regression_evaluation_persists_type_task_metrics_and_pdf(db_session: Session, app) -> None:
    settings, owner, source, generated, row = _create(
        db_session,
        app,
        "final-regression@test.com",
        "35",
        real=_regression_real(),
        **_regression_overrides(evaluationType="TSTR", evaluationName="Regression PDF Report"),
    )
    db_session.refresh(row)

    assert isinstance(row, SynthMedUtilityEvaluation)
    assert row.evaluation_type == "TSTR"
    assert row.status == "Completed"
    metrics = row.metrics_json["tstr"]["metrics"]
    assert set(metrics) == {"mae", "mse", "rmse", "r2"}
    assert "accuracy" not in metrics
    assert math.isclose(metrics["rmse"], math.sqrt(metrics["mse"]), rel_tol=1e-9)
    assert metrics["mae"] >= 0
    assert metrics["r2"] <= 1
    assert row.metrics_json["taskType"] == "regression"

    assert row.report_pdf_path and row.report_csv_path and row.report_path
    path, media, name = utility_evaluation_service.report_download_path(row, settings, "pdf")
    raw = path.read_bytes()
    assert media == "application/pdf" and name == "utility_report.pdf"
    assert raw.startswith(b"%PDF-1.4")
    assert b"TSTR metric mae:" in raw
    assert b"TSTR metric rmse:" in raw
    assert b"TSTR metric r2:" in raw
    assert b"Task type: regression" in raw
    assert b"TSTR metric accuracy" not in raw

    experiment = experiment_service.create_experiment(
        db_session,
        user=owner,
        settings=settings,
        payload={
            "name": "Regression experiment",
            "sourceDatasetId": source.id,
            "generatedDatasetId": generated.id,
            "utilityEvaluationId": row.id,
        },
    )
    enriched = versioning_service.to_experiment_response(db_session, experiment)
    assert enriched["utilityEvaluation"]["evaluationType"] == "TSTR"
    assert enriched["utilityEvaluation"]["taskType"] == "regression"
    assert enriched["reportAvailability"]["utilityPdfReport"] is True
    assert enriched["reportAvailability"]["utilityCsvReport"] is True


def test_utility_status_phase_reports_requested_runs() -> None:
    assert utility_evaluation_service._run_phase_status("Training", do_tstr=True, do_trtr=True) == "Training TSTR/TRTR"
    assert utility_evaluation_service._run_phase_status("Evaluating", do_tstr=True, do_trtr=False) == "Evaluating TSTR"
    assert utility_evaluation_service._run_phase_status("Training", do_tstr=False, do_trtr=True) == "Training TRTR"


def test_regression_metrics_helper_uses_sklearn_values() -> None:
    actual = pd.Series([1.0, 2.0, 3.0, 4.0])
    predicted = pd.Series([1.5, 2.5, 2.5, 3.5])
    metrics = utility_evaluation_service._regression_metrics(actual, predicted)
    assert math.isclose(metrics["mae"], 0.5)
    assert math.isclose(metrics["mse"], 0.25)
    assert math.isclose(metrics["rmse"], 0.5)
    assert math.isclose(metrics["r2"], 0.8)
    comparison = utility_evaluation_service._comparison(metrics, metrics, "regression", "BOTH")
    assert set(comparison["gap"]) == {"mae", "mse", "rmse", "r2"}
    assert all(value == 0 for value in comparison["gap"].values())


def test_classification_model_rejects_regression_target(db_session: Session, app) -> None:
    settings, _, _, _, row = _create(
        db_session,
        app,
        "final-mismatch@test.com",
        "36",
        real=_regression_real(),
        **_regression_overrides(modelName="LogisticRegression", evaluationType="BOTH"),
    )
    db_session.refresh(row)
    assert row.status == "Failed"
    assert "regression" in row.error_json["message"].lower()


def test_restore_authorization_is_enforced(client, db_session: Session, app) -> None:
    from app.api.deps import get_current_user

    owner = _u(db_session, "final-restore-owner@test.com")
    other = _u(db_session, "final-restore-other@test.com")
    settings: Settings = app.state.settings
    source, _ = _mk(db_session, settings, owner, 1004)
    version = versioning_service.ensure_source_version(db_session, user=owner, settings=settings, source=source)
    app.dependency_overrides[get_current_user] = lambda: other

    response = client.post(f"/api/v1/synthmed/datasets/{source.id}/versions/{version.id}/restore")
    assert response.status_code == 403

    with pytest.raises(HTTPException) as error:
        versioning_service.restore_version(
            db_session, user=other, settings=settings, dataset_id=source.id, version_id=version.id
        )
    assert error.value.status_code == 403
