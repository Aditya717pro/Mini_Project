from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User
from app.synthmed.models import SynthMedGeneratedDataset, SynthMedSourceDataset
from app.synthmed.services.storage_service import SynthMedStorageService

CSV_CONTENT = b"patient_id,age,outcome\nS001,34,stable\nS002,41,review\n"

register = "/api/v1/auth/register"
login = "/api/v1/auth/login"
upload_url = "/api/v1/synthmed/upload"


def register_user(client: TestClient, email: str) -> str:
    response = client.post(
        register,
        json={
            "email": email,
            "password": "SynthMedTest!42",
            "full_name": "SynthMed Tester",
            "organisation": "Test Lab",
            "title": "Researcher",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(login, json={"email": email, "password": "SynthMedTest!42"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload_csv(client: TestClient, headers: dict[str, str], filename: str = "cohort.csv") -> dict:
    response = client.post(
        upload_url,
        headers=headers,
        data={"dataset_name": "Test cohort", "description": "Synthetic test cohort"},
        files={"file": (filename, CSV_CONTENT, "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_source_upload_preserves_original_and_checksum(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    register_user(client, "owner@example.test")
    headers = auth_headers(client, "owner@example.test")
    body = upload_csv(client, headers)
    dataset = body["dataset"]

    assert dataset["datasetName"] == "Test cohort"
    assert dataset["originalFilename"] == "cohort.csv"
    assert dataset["fileFormat"] == "CSV"
    assert dataset["fileSizeBytes"] == len(CSV_CONTENT)
    assert dataset["checksumSha256"] == hashlib.sha256(CSV_CONTENT).hexdigest()
    assert dataset["uploadStatus"] == "Uploaded"
    assert dataset["uploadedBy"] == "SynthMed Tester"
    assert dataset["rowCount"] == 2
    assert dataset["columnCount"] == 3

    row = db_session.get(SynthMedSourceDataset, dataset["id"])
    assert row is not None
    assert row.stored_path.startswith("sources/")
    assert not Path(row.stored_path).is_absolute()
    stored = Path(app.state.settings.synthmed_storage_dir) / row.stored_path
    assert stored.read_bytes() == CSV_CONTENT

    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "synthmed.source_uploaded", AuditLog.resource_id == dataset["id"])
    )
    assert audit is not None

    detail = client.get(f"/api/v1/synthmed/sources/{dataset['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json() == dataset

    download = client.get(f"/api/v1/synthmed/sources/{dataset['id']}/download", headers=headers)
    assert download.status_code == 200
    assert download.content == CSV_CONTENT
    assert "attachment" in download.headers["content-disposition"]
    assert "cohort.csv" in download.headers["content-disposition"]

    downloads = client.get("/api/v1/synthmed/downloads", headers=headers)
    assert downloads.status_code == 200
    assert [item["id"] for item in downloads.json()["sources"]] == [dataset["id"]]
    assert downloads.json()["generated"] == []

    download_audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "synthmed.source_downloaded", AuditLog.resource_id == dataset["id"]
        )
    )
    assert download_audit is not None


def test_upload_validation_and_unauthorised_access(client: TestClient, db_session: Session) -> None:
    register_user(client, "alice@example.test")
    register_user(client, "bob@example.test")
    alice = auth_headers(client, "alice@example.test")
    bob = auth_headers(client, "bob@example.test")

    assert client.post(upload_url, data={"dataset_name": "No file"}).status_code == 401

    bad_extension = client.post(
        upload_url,
        headers=alice,
        data={"dataset_name": "Bad"},
        files={"file": ("notes.txt", CSV_CONTENT, "text/plain")},
    )
    assert bad_extension.status_code == 422

    bad_mime = client.post(
        upload_url,
        headers=alice,
        data={"dataset_name": "Bad"},
        files={"file": ("cohort.csv", CSV_CONTENT, "image/png")},
    )
    assert bad_mime.status_code == 422

    bad_content = client.post(
        upload_url,
        headers=alice,
        data={"dataset_name": "Bad"},
        files={"file": ("cohort.csv", b"not,a,csv\n", "text/csv")},
    )
    assert bad_content.status_code == 422

    assert db_session.scalar(select(SynthMedSourceDataset)) is None

    dataset = upload_csv(client, alice)["dataset"]
    dataset_id = dataset["id"]

    assert client.get(f"/api/v1/synthmed/sources/{dataset_id}").status_code == 401
    assert client.get(f"/api/v1/synthmed/sources/{dataset_id}/download").status_code == 401

    for path in (
        f"/api/v1/synthmed/sources/{dataset_id}",
        f"/api/v1/synthmed/sources/{dataset_id}/download",
    ):
        response = client.get(path, headers=bob)
        assert response.status_code == 403, response.text

    assert client.get("/api/v1/synthmed/sources/not-a-uuid", headers=alice).status_code == 404

    row = db_session.get(SynthMedSourceDataset, dataset_id)
    assert row is not None
    row.stored_path = "../raw/outside.csv"
    db_session.commit()
    traversal = client.get(f"/api/v1/synthmed/sources/{dataset_id}/download", headers=alice)
    assert traversal.status_code == 404


def test_generated_download_is_separate_and_authorised(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    register_user(client, "gen-owner@example.test")
    register_user(client, "gen-other@example.test")
    owner = auth_headers(client, "gen-owner@example.test")
    other = auth_headers(client, "gen-other@example.test")
    source = upload_csv(client, owner)["dataset"]
    owner_id = db_session.scalar(select(User.id).where(User.email == "gen-owner@example.test"))
    assert owner_id is not None

    storage = SynthMedStorageService(app.state.settings)
    generated_id = "11111111-1111-4111-8111-111111111111"
    generated_content = b"synthetic_id,age\nG001,35\n"
    _, relative = storage.save_generated(generated_id, "synthetic_data.csv", generated_content)
    db_session.add(
        SynthMedGeneratedDataset(
            id=generated_id,
            owner_id=owner_id,
            source_dataset_id=source["id"],
            source_dataset_name=source["datasetName"],
            dataset_name="Synthetic cohort",
            generation_method="Bootstrap resampling",
            record_count=1,
            column_count=2,
            file_format="CSV",
            file_size_bytes=len(generated_content),
            checksum_sha256=hashlib.sha256(generated_content).hexdigest(),
            stored_path=relative,
            status="Completed",
        )
    )
    db_session.commit()

    generated = client.get("/api/v1/synthmed/generated", headers=owner)
    assert generated.status_code == 200
    assert len(generated.json()) == 1
    assert generated.json()[0]["datasetName"] == "Synthetic cohort"
    assert generated.json()[0]["fileName"] == "synthetic_data.csv"

    downloads = client.get("/api/v1/synthmed/downloads", headers=owner).json()
    assert [item["id"] for item in downloads["sources"]] == [source["id"]]
    assert [item["id"] for item in downloads["generated"]] == [generated_id]

    response = client.get(f"/api/v1/synthmed/generated/{generated_id}/download", headers=owner)
    assert response.status_code == 200
    assert response.content == generated_content
    assert client.get(f"/api/v1/synthmed/generated/{generated_id}/download", headers=other).status_code == 403

    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "synthmed.generated_downloaded", AuditLog.resource_id == generated_id
        )
    )
    assert audit is not None


def test_json_upload_and_rejected_formats(client: TestClient, db_session: Session) -> None:
    register_user(client, "json@example.test")
    headers = auth_headers(client, "json@example.test")
    payload = b'[{"id":"S001","age":34},{"id":"S002","age":41}]'
    response = client.post(
        upload_url,
        headers=headers,
        data={"dataset_name": "JSON cohort"},
        files={"file": ("cohort.json", payload, "application/json")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["dataset"]["fileFormat"] == "JSON"
    assert response.json()["dataset"]["rowCount"] == 2

    for extension in (".txt", ".xml", ".exe"):
        rejected = client.post(
            upload_url,
            headers=headers,
            data={"dataset_name": "Rejected"},
            files={"file": (f"cohort{extension}", payload, "application/octet-stream")},
        )
        assert rejected.status_code == 422
