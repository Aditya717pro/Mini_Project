from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.models.enums import UserRole
from app.models.user import User
from app.synthmed.models import (
    SynthMedEvaluationReport,
    SynthMedGeneratedDataset,
    SynthMedGenerationConfigurationSnapshot,
    SynthMedGenerationJob,
    SynthMedSourceDataset,
    SynthMedUtilityEvaluation,
)
from app.synthmed.services import experiment_service, versioning_service
from app.synthmed.services.storage_service import SynthMedStorageService


def _user(db: Session, email: str, role=UserRole.RESEARCHER) -> User:
    user = User(email=email, full_name="Completion User", hashed_password="x", role=role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Age": [20, 21, 22, 23, 24, 25, 26, 27, 28, 29] * 3,
            "Gender": ["Male"] * 20 + ["Female"] * 10,
            "BMI": [22.0, 22.5, 23.0, 23.5, 24.0] * 6,
        }
    )


def _mk(
    db: Session,
    settings,
    owner: User,
    frame: pd.DataFrame | None = None,
    generated_frame: pd.DataFrame | None = None,
):
    frame = _frame() if frame is None else frame
    generated = _frame() if generated_frame is None else generated_frame
    storage = SynthMedStorageService(settings)
    source_id = str(uuid4())
    generated_id = str(uuid4())
    source_bytes = frame.to_csv(index=False).encode()
    generated_bytes = generated.to_csv(index=False).encode()
    _, source_path = storage.save_source(source_id, "data.csv", source_bytes)
    _, generated_path = storage.save_generated(generated_id, "synthetic_data.csv", generated_bytes)
    source = SynthMedSourceDataset(
        id=source_id,
        owner_id=owner.id,
        dataset_name="completion-source",
        original_filename="data.csv",
        stored_path=source_path,
        file_format="CSV",
        file_size_bytes=len(source_bytes),
        checksum_sha256="source-checksum",
        row_count=len(frame),
        column_count=len(frame.columns),
    )
    synthetic = SynthMedGeneratedDataset(
        id=generated_id,
        owner_id=owner.id,
        source_dataset_id=source_id,
        dataset_name="completion-generated",
        source_dataset_name="completion-source",
        generation_method="CTGAN",
        selected_model="CTGAN",
        record_count=len(generated),
        column_count=len(generated.columns),
        file_format="CSV",
        file_size_bytes=len(generated_bytes),
        checksum_sha256="generated-checksum",
        stored_path=generated_path,
        status="Completed",
    )
    db.add_all([source, synthetic])
    db.commit()
    return source, synthetic


def _replace_live(db: Session, settings, source: SynthMedSourceDataset, frame: pd.DataFrame) -> None:
    storage = SynthMedStorageService(settings)
    content = frame.to_csv(index=False).encode()
    _, relative = storage.save_source(source.id, Path(source.stored_path).name, content)
    source.stored_path = relative
    source.row_count = len(frame)
    db.commit()


def _job(
    db: Session, owner: User, source: SynthMedSourceDataset, config: dict, status: str = "Completed"
) -> SynthMedGenerationJob:
    job = SynthMedGenerationJob(
        id=str(uuid4()),
        owner_id=owner.id,
        source_dataset_id=source.id,
        status=status,
        model_name="CTGAN",
        generation_mode="Unconditional",
        selected_model="CTGAN",
        epochs=1,
        batch_size=100,
        seed=1,
        requested_record_count=10,
        generated_record_count=10,
        config_json=config,
    )
    db.add(job)
    db.commit()
    return job


def test_snapshots_are_immutable_and_store_original_live_path(db_session: Session, app) -> None:
    owner = _user(db_session, "completion-snapshot@test.com")
    source, _ = _mk(db_session, app.state.settings, owner)
    original_bytes = SynthMedStorageService(app.state.settings).resolve_source(source.stored_path).read_bytes()

    version_one = versioning_service.ensure_source_version(
        db_session, user=owner, settings=app.state.settings, source=source
    )
    assert version_one.stored_path.startswith(f"sources/{source.id}/versions/{version_one.id}/")
    assert version_one.metadata_json["originalStoredPath"] == source.stored_path
    snapshot = SynthMedStorageService(app.state.settings).resolve_source(version_one.stored_path)
    assert snapshot.read_bytes() == original_bytes
    assert version_one.checksum_sha256 == hashlib.sha256(original_bytes).hexdigest()

    changed = _frame()
    changed["Age"] = changed["Age"] + 1
    _replace_live(db_session, app.state.settings, source, changed)
    version_two = versioning_service.create_dataset_version(
        db_session, user=owner, settings=app.state.settings, kind="source", source=source
    )
    db_session.commit()

    assert snapshot.read_bytes() == original_bytes
    assert version_one.checksum_sha256 != version_two.checksum_sha256
    assert version_one.stored_path != version_two.stored_path
    assert version_two.metadata_json["originalStoredPath"] == source.stored_path


def test_restore_creates_fresh_snapshot_with_historical_bytes(db_session: Session, app) -> None:
    owner = _user(db_session, "completion-restore@test.com")
    source, _ = _mk(db_session, app.state.settings, owner)
    version_one = versioning_service.ensure_source_version(
        db_session, user=owner, settings=app.state.settings, source=source
    )
    historical_path = SynthMedStorageService(app.state.settings).resolve_source(version_one.stored_path)
    historical_bytes = historical_path.read_bytes()
    changed = _frame()
    changed["BMI"] = changed["BMI"] + 5
    _replace_live(db_session, app.state.settings, source, changed)
    version_two = versioning_service.create_dataset_version(
        db_session, user=owner, settings=app.state.settings, kind="source", source=source
    )
    db_session.commit()

    restored = versioning_service.restore_version(
        db_session, user=owner, settings=app.state.settings, dataset_id=source.id, version_id=version_one.id
    )
    assert restored.id not in {version_one.id, version_two.id}
    assert restored.checksum_sha256 == version_one.checksum_sha256
    assert restored.parent_version_id == version_one.id
    assert restored.restored_from_version_id == version_one.id
    assert restored.is_active and not version_two.is_active
    assert historical_bytes == historical_path.read_bytes()
    restored_path = SynthMedStorageService(app.state.settings).resolve_source(restored.stored_path)
    assert restored_path.read_bytes() == historical_bytes
    assert restored.transform_history_json[-1]["step"] == "restore"
    lineage = versioning_service.lineage_for_dataset(
        db_session, user=owner, settings=app.state.settings, dataset_id=source.id
    )
    assert any(
        event["eventType"] == "restore" and event["childResourceId"] == restored.id for event in lineage["lineage"]
    )


def test_generated_versions_are_numbered_per_generated_dataset(db_session: Session, app) -> None:
    owner = _user(db_session, "completion-numbering@test.com")
    source, generated_one = _mk(db_session, app.state.settings, owner)
    generated_two = SynthMedGeneratedDataset(
        id=str(uuid4()),
        owner_id=owner.id,
        source_dataset_id=source.id,
        dataset_name="second-generated",
        source_dataset_name=source.dataset_name,
        generation_method="TVAE",
        record_count=30,
        column_count=3,
        file_size_bytes=1,
        checksum_sha256="second",
        stored_path=generated_one.stored_path,
        status="Completed",
    )
    db_session.add(generated_two)
    db_session.commit()

    version_one = versioning_service.ensure_generated_version(
        db_session, user=owner, settings=app.state.settings, generated=generated_one
    )
    version_two = versioning_service.ensure_generated_version(
        db_session, user=owner, settings=app.state.settings, generated=generated_two
    )
    assert version_one.version_number == version_two.version_number == 1
    assert version_one.logical_dataset_id == generated_one.id
    assert version_two.logical_dataset_id == generated_two.id
    assert version_one.source_dataset_id == version_two.source_dataset_id == source.id


def test_semantic_version_labels(db_session: Session, app) -> None:
    owner = _user(db_session, "completion-labels@test.com")
    source, _ = _mk(db_session, app.state.settings, owner)
    first = versioning_service.ensure_source_version(
        db_session, user=owner, settings=app.state.settings, source=source
    )
    minor_change = _frame()
    minor_change["Age"] = minor_change["Age"] + 1
    _replace_live(db_session, app.state.settings, source, minor_change)
    second = versioning_service.create_dataset_version(
        db_session, user=owner, settings=app.state.settings, kind="source", source=source
    )
    schema_change = _frame()
    schema_change["NewColumn"] = 1
    _replace_live(db_session, app.state.settings, source, schema_change)
    third = versioning_service.create_dataset_version(
        db_session, user=owner, settings=app.state.settings, kind="source", source=source
    )
    db_session.commit()
    restored = versioning_service.restore_version(
        db_session, user=owner, settings=app.state.settings, dataset_id=source.id, version_id=first.id
    )

    assert [first.version_label, second.version_label, third.version_label] == ["v1.0", "v1.1", "v2.0"]
    assert restored.version_label == "v2.1"
    assert [first.version_number, second.version_number, third.version_number, restored.version_number] == [1, 2, 3, 4]


def test_compare_expanded_deltas(db_session: Session, app) -> None:
    owner = _user(db_session, "completion-compare@test.com")
    first_frame = _frame()
    first_frame.loc[0, "Age"] = None
    source, _ = _mk(db_session, app.state.settings, owner, frame=first_frame)
    version_one = versioning_service.ensure_source_version(
        db_session, user=owner, settings=app.state.settings, source=source
    )
    second_frame = _frame()
    second_frame["Age"] = [f"patient_{value}" for value in second_frame["Age"]]
    second_frame["Gender"] = ["Female"] * 20 + ["Male"] * 10
    second_frame.loc[1, "Age"] = None
    second_frame["BMI"] = second_frame["BMI"] + 3
    _replace_live(db_session, app.state.settings, source, second_frame)
    version_two = versioning_service.create_dataset_version(
        db_session, user=owner, settings=app.state.settings, kind="source", source=source
    )
    db_session.commit()

    result = versioning_service.compare_versions(
        db_session,
        user=owner,
        settings=app.state.settings,
        dataset_id=source.id,
        version_a_id=version_one.id,
        version_b_id=version_two.id,
    )
    assert any(change["column"] == "Age" for change in result["schema"]["dtypeChanges"])
    assert result["missing"]["deltas"]["Age"]["missingA"] == 1
    assert result["distributions"]["BMI"]["kind"] == "numeric"
    assert result["distributions"]["BMI"]["delta"]["mean"] != 0
    assert result["distributions"]["Gender"]["topValueA"] != result["distributions"]["Gender"]["topValueB"]
    assert result["metadata"]["checksumA"] == version_one.checksum_sha256
    assert result["metadata"]["checksumB"] == version_two.checksum_sha256
    assert result["metadata"]["checksumChanged"] is True


def test_compare_missing_version_file_returns_409(db_session: Session, app) -> None:
    owner = _user(db_session, "completion-compare-missing@test.com")
    source, _ = _mk(db_session, app.state.settings, owner)
    version = versioning_service.ensure_source_version(
        db_session, user=owner, settings=app.state.settings, source=source
    )
    SynthMedStorageService(app.state.settings).resolve_source(version.stored_path).unlink()

    with pytest.raises(HTTPException) as raised:
        versioning_service.compare_versions(
            db_session,
            user=owner,
            settings=app.state.settings,
            dataset_id=source.id,
            version_a_id=version.id,
            version_b_id=version.id,
        )
    assert raised.value.status_code == 409
    assert "missing" in str(raised.value.detail).lower()


def test_generated_compare_includes_real_privacy_and_utility_summaries(db_session: Session, app) -> None:
    owner = _user(db_session, "completion-generated-resources@test.com")
    source, generated = _mk(db_session, app.state.settings, owner)
    source_version = versioning_service.ensure_source_version(
        db_session, user=owner, settings=app.state.settings, source=source
    )
    generated_version = versioning_service.ensure_generated_version(
        db_session, user=owner, settings=app.state.settings, generated=generated
    )
    job = _job(db_session, owner, source, {"model": "CTGAN", "sourceDatasetId": source.id})
    report = SynthMedEvaluationReport(
        id=str(uuid4()),
        job_id=job.id,
        generated_dataset_id=generated.id,
        owner_id=owner.id,
        report_type="privacy",
        method="nearest-neighbour",
        score=0.75,
        report_json={"summary": {"risk": "low"}},
        file_path="reports/privacy.json",
    )
    utility = SynthMedUtilityEvaluation(
        id=str(uuid4()),
        owner_id=owner.id,
        source_dataset_id=source.id,
        generated_dataset_id=generated.id,
        status="Completed",
        evaluation_name="utility",
        evaluation_type="TSTR",
        model_name="LogisticRegression",
        target_column="Gender",
        feature_columns_json=["Age"],
        train_test_split={},
        preprocessing_config_json={},
        metrics_json={"accuracy": 0.8},
        comparison_summary_json={"accuracyDelta": 0.1},
        warnings_json=[],
        report_path="reports/utility.json",
    )
    db_session.add_all([report, utility])
    db_session.commit()

    generated_result = versioning_service.compare_versions(
        db_session,
        user=owner,
        settings=app.state.settings,
        dataset_id=generated.id,
        version_a_id=generated_version.id,
        version_b_id=generated_version.id,
    )
    resources = generated_result["generatedResources"]["a"]
    assert resources["available"] is True
    assert resources["privacyReports"][0]["score"] == 0.75
    assert resources["utilityEvaluations"][0]["metrics"] == {"accuracy": 0.8}

    source_result = versioning_service.compare_versions(
        db_session,
        user=owner,
        settings=app.state.settings,
        dataset_id=source.id,
        version_a_id=source_version.id,
        version_b_id=source_version.id,
    )
    assert source_result["generatedResources"]["a"]["available"] is False


def test_version_download_endpoint_checks_auth_and_checksum(client: TestClient, db_session: Session, app) -> None:
    owner = _user(db_session, "completion-download@test.com")
    other = _user(db_session, "completion-download-other@test.com")
    source, _ = _mk(db_session, app.state.settings, owner)
    version = versioning_service.ensure_source_version(
        db_session, user=owner, settings=app.state.settings, source=source
    )
    url = f"/api/v1/synthmed/datasets/{source.id}/versions/{version.id}/download"
    app.dependency_overrides[get_current_user] = lambda: owner
    response = client.get(url)
    assert response.status_code == 200
    assert version.checksum_sha256 == hashlib.sha256(response.content).hexdigest()

    app.dependency_overrides[get_current_user] = lambda: other
    assert client.get(url).status_code == 403

    app.dependency_overrides[get_current_user] = lambda: owner
    version.stored_path = "../../secrets/data.csv"
    db_session.commit()
    assert client.get(url).status_code == 409

    version.stored_path = f"sources/{source.id}/versions/{version.id}/tampered.csv"
    directory = SynthMedStorageService(app.state.settings).sources_root / source.id / "versions" / version.id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "tampered.csv").write_bytes(b"tampered")
    db_session.commit()
    assert client.get(url).status_code == 409


def test_experiment_validation_uses_dataset_and_owner(db_session: Session, app) -> None:
    owner = _user(db_session, "completion-experiment-validation@test.com")
    source_one, generated_one = _mk(db_session, app.state.settings, owner)
    source_two, _ = _mk(db_session, app.state.settings, owner)
    version_one = versioning_service.ensure_source_version(
        db_session, user=owner, settings=app.state.settings, source=source_one
    )
    job_one = _job(db_session, owner, source_one, {"model": "CTGAN", "sourceDatasetId": source_one.id})
    snapshot_one = versioning_service.snapshot_config(db_session, user=owner, job=job_one)
    db_session.flush()

    with pytest.raises(HTTPException) as raised:
        experiment_service.create_experiment(
            db_session,
            user=owner,
            settings=app.state.settings,
            payload={
                "name": "mismatched-version",
                "sourceDatasetId": source_two.id,
                "sourceVersionId": version_one.id,
            },
        )
    assert raised.value.status_code == 422

    with pytest.raises(HTTPException) as raised:
        experiment_service.create_experiment(
            db_session,
            user=owner,
            settings=app.state.settings,
            payload={
                "name": "mismatched-snapshot",
                "sourceDatasetId": source_two.id,
                "configurationSnapshotId": snapshot_one.id,
            },
        )
    assert raised.value.status_code == 422


def test_experiment_status_preserves_failed_and_derives_from_job(db_session: Session, app) -> None:
    owner = _user(db_session, "completion-status@test.com")
    source, generated = _mk(db_session, app.state.settings, owner)
    failed_job = _job(db_session, owner, source, {"model": "CTGAN", "sourceDatasetId": source.id}, status="Failed")
    completed_job = _job(db_session, owner, source, {"model": "CTGAN", "sourceDatasetId": source.id})

    failed = experiment_service.create_experiment(
        db_session,
        user=owner,
        settings=app.state.settings,
        payload={"name": "failed", "sourceDatasetId": source.id, "generationJobId": failed_job.id},
    )
    completed = experiment_service.create_experiment(
        db_session,
        user=owner,
        settings=app.state.settings,
        payload={"name": "completed", "sourceDatasetId": source.id, "generationJobId": completed_job.id},
    )
    assert failed.status == "Failed"
    assert completed.status == "Completed"

    with pytest.raises(HTTPException) as raised:
        experiment_service.create_experiment(
            db_session,
            user=owner,
            settings=app.state.settings,
            payload={
                "name": "invalid",
                "status": "Archived",
                "sourceDatasetId": source.id,
                "generatedDatasetId": generated.id,
            },
        )
    assert raised.value.status_code == 422


def test_reuse_appends_attempts_warnings_and_keeps_snapshot(client: TestClient, db_session: Session, app) -> None:
    owner = _user(db_session, "completion-reuse@test.com")
    source, _ = _mk(db_session, app.state.settings, owner)
    config = {
        "sourceDatasetId": source.id,
        "model": "UnknownModel",
        "sdvVersion": "0.0.0",
        "epochs": 1,
        "batchSize": 100,
        "recordCount": 10,
        "selectedColumns": ["Age", "Gender", "BMI"],
        "legacyOption": "do-not-use",
    }
    job = _job(db_session, owner, source, config)
    app.dependency_overrides[get_current_user] = lambda: owner
    experiment_id = client.post(
        "/api/v1/synthmed/experiments",
        json={"name": "reuse-experiment", "sourceDatasetId": source.id, "generationJobId": job.id},
    ).json()["id"]
    experiment = experiment_service.get_experiment(db_session, user=owner, experiment_id=experiment_id)
    snapshot_id = experiment.configuration_snapshot_id
    snapshot_hash = db_session.get(SynthMedGenerationConfigurationSnapshot, snapshot_id).config_hash

    first_reuse = client.post(f"/api/v1/synthmed/experiments/{experiment_id}/reuse-configuration")
    assert first_reuse.status_code == 200
    warnings = first_reuse.json()["config"]["reuseWarnings"]
    assert any("unsupported" in warning.lower() for warning in warnings)
    assert any("sdv version" in warning.lower() for warning in warnings)
    assert any("legacyOption" in warning for warning in warnings)

    second_reuse = client.post(f"/api/v1/synthmed/experiments/{experiment_id}/reuse-configuration")
    assert second_reuse.status_code == 200

    history = client.get(f"/api/v1/synthmed/experiments/{experiment_id}/history").json()
    assert len(history["attempts"]) == 2
    assert history["attempts"][0]["jobId"] != history["attempts"][1]["jobId"]
    assert history["attempts"][0]["warnings"]
    assert "lineage" in history
    configurations = client.get(f"/api/v1/synthmed/experiments/{experiment_id}/configurations").json()
    assert any(item["id"] == snapshot_id for item in configurations)

    snapshot = db_session.get(SynthMedGenerationConfigurationSnapshot, snapshot_id)
    assert snapshot.config_hash == snapshot_hash
    assert snapshot.config_json["model"] == "UnknownModel"


def test_reuse_as_new_experiment_keeps_original_results(client: TestClient, db_session: Session, app) -> None:
    owner = _user(db_session, "completion-reuse-new@test.com")
    source, _ = _mk(db_session, app.state.settings, owner)
    job = _job(db_session, owner, source, {"model": "CTGAN", "sourceDatasetId": source.id})
    app.dependency_overrides[get_current_user] = lambda: owner
    original_id = client.post(
        "/api/v1/synthmed/experiments",
        json={"name": "original", "sourceDatasetId": source.id, "generationJobId": job.id},
    ).json()["id"]
    response = client.post(
        f"/api/v1/synthmed/experiments/{original_id}/reuse-configuration",
        json={"reuseAsNewExperiment": True},
    )
    assert response.status_code == 200
    experiments = client.get("/api/v1/synthmed/experiments").json()
    new_experiment = next(item for item in experiments if item["id"] != original_id)
    assert new_experiment["name"] == "original (reuse)"
    assert (
        len(experiment_service.experiment_history(db_session, user=owner, experiment_id=original_id)["attempts"]) == 0
    )


def test_experiment_enrichment_marks_missing_resources_unavailable(db_session: Session, app) -> None:
    owner = _user(db_session, "completion-enrichment@test.com")
    source, generated = _mk(db_session, app.state.settings, owner)
    experiment = experiment_service.create_experiment(
        db_session,
        user=owner,
        settings=app.state.settings,
        payload={"name": "bare", "sourceDatasetId": source.id, "generatedDatasetId": generated.id},
    )
    payload = versioning_service.to_experiment_response(db_session, experiment)
    assert payload["privacyReport"]["available"] is False
    assert payload["utilityEvaluation"]["available"] is False
    assert payload["comparisonSummary"]["available"] is False
    assert payload["reportAvailability"] == {
        "privacyReport": False,
        "utilityReport": False,
        "utilityCsvReport": False,
        "utilityPdfReport": False,
        "comparisonReport": False,
    }
    assert isinstance(payload["lineage"], list)
