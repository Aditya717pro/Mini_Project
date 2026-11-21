from __future__ import annotations

import hashlib

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from app.synthmed.models import SynthMedGeneratedDataset, SynthMedGenerationJob, SynthMedSourceDataset
from app.synthmed.services import condition_service, generation_service
from app.synthmed.services.dataset_service import json_safe
from app.synthmed.services.storage_service import SynthMedStorageService

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
UPLOAD = "/api/v1/synthmed/upload"
API = "/api/v1/synthmed"

FICTIONAL_CSV = (
    b"patient_id,age,cholesterol,diagnosis,visit_date,smoker\n"
    b"P0001,34,180.5,stable,2025-01-01,true\n"
    b"P0002,41,195.0,review,2025-01-02,false\n"
    b"P0003,27,164.2,stable,2025-01-03,true\n"
    b"P0004,53,221.8,acute,2025-01-04,false\n"
    b"P0005,38,188.4,stable,2025-01-05,true\n"
    b"P0006,45,205.1,review,2025-01-06,false\n"
    b"P0007,31,171.6,stable,2025-01-07,true\n"
    b"P0008,49,215.3,acute,2025-01-08,false\n"
    b"P0009,36,,stable,2025-01-09,true\n"
    b"P0010,58,232.7,review,2025-01-10,false\n"
    b"P0011,29,166.8,stable,2025-01-11,true\n"
    b"P0012,47,209.4,review,2025-01-12,false\n"
    b"P0013,33,177.2,stable,2025-01-13,true\n"
    b"P0014,55,225.9,acute,2025-01-14,false\n"
    b"P0015,42,198.6,review,2025-01-15,true\n"
    b"P0016,26,160.3,stable,2025-01-16,false\n"
    b"P0017,51,218.1,acute,2025-01-17,true\n"
    b"P0018,39,190.7,stable,2025-01-18,false\n"
    b"P0019,44,203.5,review,2025-01-19,true\n"
    b"P0020,30,169.9,stable,2025-01-20,false\n"
)

IDENTIFIER_ONLY_CSV = "patient_id\n" + "".join(f"P{i:04d}\n" for i in range(12))


def register_user(client: TestClient, email: str) -> None:
    response = client.post(
        REGISTER,
        json={
            "email": email,
            "password": "SynthMedTest!42",
            "full_name": "CTGAN Tester",
            "organisation": "Test Lab",
            "title": "Researcher",
        },
    )
    assert response.status_code == 201, response.text


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(LOGIN, json={"email": email, "password": "SynthMedTest!42"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload(client: TestClient, headers: dict[str, str], content: bytes, name: str = "fictional_cohort.csv") -> str:
    response = client.post(
        UPLOAD,
        headers=headers,
        data={"dataset_name": "Fictional cohort", "description": "Fictional test data"},
        files={"file": (name, content, "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()["dataset"]["id"]


def start_job(client: TestClient, headers: dict[str, str], source_id: str, **overrides) -> dict:
    payload = {
        "sourceDatasetId": source_id,
        "datasetName": "Fictional synthetic cohort",
        "selectedColumns": ["patient_id", "age", "cholesterol", "diagnosis"],
        "categoricalColumns": ["diagnosis"],
        "numericalColumns": ["age", "cholesterol"],
        "identifierColumns": ["patient_id"],
        "primaryKey": "patient_id",
        "seed": 7,
        "epochs": 1,
        "batchSize": 20,
        "recordCount": 8,
        "preserveMissingness": True,
    }
    payload.update(overrides)
    response = client.post(f"{API}/generation/start", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_ctgan_workflow_end_to_end(app: FastAPI, client: TestClient, db_session: Session) -> None:
    register_user(client, "ctgan-owner@example.test")
    headers = auth_headers(client, "ctgan-owner@example.test")
    source_id = upload(client, headers, FICTIONAL_CSV)

    source_metadata = client.get(f"{API}/sources/{source_id}", headers=headers)
    assert source_metadata.status_code == 200, source_metadata.text
    assert source_metadata.json()["datasetName"] == "Fictional cohort"

    analysis_response = client.post(f"{API}/generation/analyse/{source_id}", headers=headers)
    assert analysis_response.status_code == 200, analysis_response.text
    analysis = analysis_response.json()
    assert analysis["datasetName"] == "Fictional cohort"
    assert analysis["totalRecords"] == 20
    assert analysis["totalColumns"] == 6
    assert "patient_id" in analysis["potentialIdentifierColumns"]
    assert "age" in analysis["numericalColumns"]
    assert "diagnosis" in analysis["categoricalColumns"]
    assert "visit_date" in analysis["datetimeColumns"]
    assert analysis["generationReady"] is True

    job = start_job(client, headers, source_id)
    assert job["status"] == "Completed", db_session.get(SynthMedGenerationJob, job["id"]).error_json
    assert job["modelName"] == "SDV CTGANSynthesizer"
    assert job["requestedRecordCount"] == 8
    assert job["generatedRecordCount"] == 8
    assert job["epochs"] == 1
    assert job["batchSize"] == 20
    assert job["seed"] == 7
    assert job["generatedDatasetId"]

    generated_id = job["generatedDatasetId"]
    detail_response = client.get(f"{API}/generated/{generated_id}", headers=headers)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["generationJobId"] == job["id"]
    assert detail["recordCount"] == 8
    assert detail["columnCount"] == 3, detail
    assert set(detail["availableFormats"]) == {"CSV", "XLSX", "JSON"}
    assert {"quality", "privacy", "preprocessing", "generation"}.issubset(set(detail["reportTypes"]))

    preview_response = client.get(f"{API}/generated/{generated_id}/preview", headers=headers, params={"pageSize": 3})
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["totalRecords"] == 8
    assert len(preview["rows"]) == 3
    assert "patient_id" not in preview["columns"]
    assert set(preview["columns"]) == {"age", "cholesterol", "diagnosis"}

    quality_response = client.get(f"{API}/generated/{generated_id}/quality", headers=headers)
    assert quality_response.status_code == 200, quality_response.text
    quality = quality_response.json()
    assert 0 <= quality["score"] <= 1
    assert quality["report"]["columnLevel"]
    assert quality["report"]["diagnostics"]

    privacy_response = client.get(f"{API}/generated/{generated_id}/privacy", headers=headers)
    assert privacy_response.status_code == 200, privacy_response.text
    privacy = privacy_response.json()
    assert privacy["report"]["exactOverlapRecords"] == 0
    assert privacy["report"]["syntheticDuplicateRecords"] == 0
    assert "No differential privacy mechanism is implemented." in privacy["report"]["limitations"]

    for file_format, content_type in [
        ("CSV", "text/csv"),
        ("XLSX", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("JSON", "application/json"),
    ]:
        download = client.get(
            f"{API}/generated/{generated_id}/download", headers=headers, params={"file_format": file_format}
        )
        assert download.status_code == 200, download.text
        assert download.headers["content-type"].startswith(content_type)
        assert len(download.content) > 20

    for report_type in ("generation", "preprocessing", "quality", "privacy"):
        report_download = client.get(f"{API}/generated/{generated_id}/reports/{report_type}/download", headers=headers)
        assert report_download.status_code == 200, report_download.text
        assert report_download.json()

    export = client.post(f"{API}/generated/{generated_id}/export", headers=headers, json={"format": "JSON"})
    assert export.status_code == 200, export.text
    assert export.json()["format"] == "JSON"

    jobs = client.get(f"{API}/generation/jobs", headers=headers)
    assert jobs.status_code == 200
    assert [item["id"] for item in jobs.json()] == [job["id"]]

    job_detail = client.get(f"{API}/generation/jobs/{job['id']}", headers=headers)
    assert job_detail.status_code == 200
    assert job_detail.json()["status"] == "Completed"

    source_download = client.get(f"{API}/sources/{source_id}/download", headers=headers)
    assert source_download.status_code == 200
    assert source_download.content == FICTIONAL_CSV
    assert db_session.get(SynthMedGenerationJob, job["id"]).error_json is None

    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "synthmed.generation_completed", AuditLog.resource_id == job["id"]
        )
    )
    assert audit is not None


def test_generation_authentication_ownership_and_failure(client: TestClient, db_session: Session) -> None:
    register_user(client, "ctgan-alice@example.test")
    register_user(client, "ctgan-bob@example.test")
    alice = auth_headers(client, "ctgan-alice@example.test")
    bob = auth_headers(client, "ctgan-bob@example.test")
    source_id = upload(client, alice, FICTIONAL_CSV)

    job = start_job(client, alice, source_id)
    generated_id = job["generatedDatasetId"]

    owner_detail = client.get(f"{API}/generation/jobs/{job['id']}", headers=alice)
    assert owner_detail.status_code == 200, owner_detail.text
    owner_jobs = client.get(f"{API}/generation/jobs", headers=alice)
    assert owner_jobs.status_code == 200, owner_jobs.text
    assert job["id"] in [item["id"] for item in owner_jobs.json()]

    for path in [
        f"{API}/generation/jobs/{job['id']}",
        f"{API}/sources/{source_id}/download",
        f"{API}/generated/{generated_id}",
        f"{API}/generated/{generated_id}/preview",
        f"{API}/generated/{generated_id}/quality",
        f"{API}/generated/{generated_id}/privacy",
        f"{API}/generated/{generated_id}/download",
        f"{API}/generated/{generated_id}/reports/quality/download",
    ]:
        assert client.get(path, headers=bob).status_code == 403, path

    bad_source = upload(client, alice, IDENTIFIER_ONLY_CSV, "identifier_only.csv")
    invalid = client.post(
        f"{API}/generation/start",
        headers=alice,
        json={
            "sourceDatasetId": bad_source,
            "datasetName": "Identifier-only cohort",
            "selectedColumns": ["patient_id"],
            "numericalColumns": [],
            "categoricalColumns": [],
            "identifierColumns": ["patient_id"],
            "primaryKey": "patient_id",
            "seed": 7,
            "epochs": 1,
            "batchSize": 20,
            "recordCount": 8,
            "preserveMissingness": True,
        },
    )
    assert invalid.status_code == 422, invalid.text
    assert "No medical output columns remain" in invalid.json()["detail"]


def test_admin_can_view_and_list_other_users_generation_jobs(
    client: TestClient, db_session: Session
) -> None:
    assert UserRole.ADMINISTRATOR.value == "Administrator"
    register_user(client, "ctgan-admin-owner@example.test")
    owner_headers = auth_headers(client, "ctgan-admin-owner@example.test")
    source_id = upload(client, owner_headers, FICTIONAL_CSV)
    job = start_job(client, owner_headers, source_id)

    admin = User(
        email="ctgan-admin@example.test",
        full_name="CTGAN Administrator",
        hashed_password=hash_password("SynthMedTest!42"),
        role=UserRole.ADMINISTRATOR,
        organisation="Test Lab",
        title="Administrator",
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    admin_headers = auth_headers(client, "ctgan-admin@example.test")

    detail = client.get(f"{API}/generation/jobs/{job['id']}", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["id"] == job["id"]

    jobs = client.get(f"{API}/generation/jobs", headers=admin_headers)
    assert jobs.status_code == 200, jobs.text
    assert job["id"] in [item["id"] for item in jobs.json()]


def test_generated_preview_and_download_use_generated_file(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    register_user(client, "generated-integrity@example.test")
    headers = auth_headers(client, "generated-integrity@example.test")
    source_id = upload(client, headers, FICTIONAL_CSV)
    job = start_job(client, headers, source_id)
    assert job["status"] == "Completed", job["error"]

    source = db_session.get(SynthMedSourceDataset, source_id)
    generated = db_session.get(SynthMedGeneratedDataset, job["generatedDatasetId"])
    assert source is not None
    assert generated is not None

    storage = SynthMedStorageService(app.state.settings)
    source_path = storage.resolve_source(source.stored_path)
    generated_path = storage.resolve_generated(generated.stored_path)
    assert source_path != generated_path

    stored_bytes = generated_path.read_bytes()
    assert hashlib.sha256(stored_bytes).hexdigest() == generated.checksum_sha256
    assert stored_bytes != FICTIONAL_CSV

    generated_download = client.get(f"{API}/generated/{generated.id}/download", headers=headers)
    assert generated_download.status_code == 200, generated_download.text
    assert generated_download.content == stored_bytes

    preview = client.get(f"{API}/generated/{generated.id}/preview", headers=headers, params={"pageSize": 100})
    assert preview.status_code == 200, preview.text
    assert preview.json()["rows"] == json_safe(pd.read_csv(generated_path).to_dict(orient="records"))

    stored_job = db_session.get(SynthMedGenerationJob, job["id"])
    assert stored_job is not None
    generated_paths = stored_job.config_json["generatedPaths"]
    for file_format in ("CSV", "XLSX", "JSON"):
        response = client.get(
            f"{API}/generated/{generated.id}/download", headers=headers, params={"file_format": file_format}
        )
        assert response.status_code == 200, response.text
        assert response.content == storage.resolve_generated(generated_paths[file_format]).read_bytes()

    source_download = client.get(f"{API}/sources/{source_id}/download", headers=headers)
    assert source_download.status_code == 200, source_download.text
    assert source_download.content == FICTIONAL_CSV
    assert source_path.read_bytes() == FICTIONAL_CSV


def test_conditional_generation_passes_conditions_to_sdv_sampling_api(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    register_user(client, "conditional-sampling@example.test")
    headers = auth_headers(client, "conditional-sampling@example.test")
    source_id = upload(client, headers, FICTIONAL_CSV)
    captured: list[list[dict]] = []
    base_class = condition_service.MODEL_CLASSES["CTGAN"]

    class RecordingCTGAN(base_class):
        def sample_from_conditions(self, *args, **kwargs):
            conditions = kwargs.get("conditions") or (args[0] if args else [])
            captured.append(
                [{"columnValues": dict(item.column_values), "numRows": item.num_rows} for item in conditions]
            )
            return super().sample_from_conditions(*args, **kwargs)

    monkeypatch.setitem(condition_service.MODEL_CLASSES, "CTGAN", RecordingCTGAN)
    job = start_job(
        client,
        headers,
        source_id,
        generationMode="Conditional",
        conditions=[{"column": "diagnosis", "operator": "eq", "value": "stable", "numRows": 8}],
    )
    assert job["status"] == "Completed", job["error"]
    assert captured
    assert all(
        batch == [{"columnValues": {"diagnosis": "stable"}, "numRows": 8}]
        for batch in captured
    )


def test_failed_evaluation_does_not_expose_generated_dataset(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    register_user(client, "failed-evaluation@example.test")
    headers = auth_headers(client, "failed-evaluation@example.test")
    source_id = upload(client, headers, FICTIONAL_CSV)

    def fail_evaluation(*args, **kwargs):
        raise RuntimeError("Evaluation failed")

    monkeypatch.setattr(generation_service, "build_quality_report", fail_evaluation)
    job = start_job(client, headers, source_id)
    assert job["status"] == "Failed"
    assert "Evaluation failed" in job["error"]
    assert job["generatedDatasetId"] == ""

    generated_rows = db_session.scalars(
        select(SynthMedGeneratedDataset).where(SynthMedGeneratedDataset.source_dataset_id == source_id)
    ).all()
    assert generated_rows == []

    listed = client.get(f"{API}/generated", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json() == []
