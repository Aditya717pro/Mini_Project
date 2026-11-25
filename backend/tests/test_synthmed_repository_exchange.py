from __future__ import annotations

import hashlib
import io
import json
from uuid import uuid4

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Dataset,
    DatasetVersion,
    ETLJob,
    SynthMedDatasetVersion,
    SynthMedGeneratedDataset,
    SynthMedGenerationJob,
    SynthMedSourceDataset,
)
from app.models.enums import DatasetStatus, JobStatus, UserRole
from app.synthmed.services import source_service
from app.synthmed.services.storage_service import SynthMedStorageService
from tests.test_workflows import create_user, login

REPOSITORY_CSV = b"age,gender,outcome\n34,Female,stable\n41,Male,review\n"
GENERATED_CSV = (
    b"Age,Gender,Disease,Disease_Level,Systolic_BP\n"
    b"34,Female,Hypertension,Mild,122\n"
    b"41,Male,Diabetes,Moderate,128\n"
)


def repository_metadata(title: str) -> dict:
    return {
        "title": title,
        "description": "Fictional cohort used only for repository exchange tests.",
        "domain": "Synthetic Health",
        "access": "Controlled",
        "tags": ["synthetic", "test"],
        "ageRange": "18-90 years",
        "geography": ["England"],
        "studyDesign": "Fictional cohort",
        "license": "Research use only",
        "ethicsApproved": True,
        "dataDictionaryAvailable": True,
        "intendedTasks": ["Classification"],
        "labelColumn": "outcome",
        "researchTask": "Classification",
    }


def registration_payload(title: str) -> dict:
    payload = repository_metadata(title)
    payload["access"] = "Open"
    payload["labelColumn"] = "Disease"
    return payload


def upload_repository_dataset(client: TestClient, headers: dict[str, str], title: str) -> dict:
    response = client.post(
        "/api/v1/datasets/",
        headers=headers,
        files={"file": ("fictional_cohort.csv", REPOSITORY_CSV, "text/csv")},
        data={"metadata": json.dumps(repository_metadata(title))},
    )
    assert response.status_code == 201, response.text
    return response.json()["dataset"]


def prepare_and_run_etl(client: TestClient, headers: dict[str, str], job_id: str) -> None:
    profiled = client.post(f"/api/v1/etl/jobs/{job_id}/profile", headers=headers)
    assert profiled.status_code == 200, profiled.text
    decisions = [
        {
            "source": item["source"],
            "decision": "Approved" if item["target"] or item["proposedTarget"] else "Unmapped",
            "target": item["target"] or item["proposedTarget"] or "",
            "note": "Fictional review decision",
        }
        for item in profiled.json()["mappings"]
    ]
    saved = client.post(f"/api/v1/etl/jobs/{job_id}/mappings", headers=headers, json=decisions)
    assert saved.status_code == 200, saved.text
    approved = client.post(f"/api/v1/etl/jobs/{job_id}/approve", headers=headers, json={})
    assert approved.status_code == 200, approved.text
    run = client.post(f"/api/v1/etl/jobs/{job_id}/run", headers=headers, json={"task": "Synthetic classification"})
    assert run.status_code == 200, run.text


def add_generated_dataset(
    db: Session,
    client: TestClient,
    *,
    owner_id: str,
    source_id: str,
    content: bytes,
    filename: str,
    file_format: str = "CSV",
    status: str = "Completed",
) -> SynthMedGeneratedDataset:
    storage = SynthMedStorageService(client.app.state.settings)
    _, relative_path = storage.save_generated(str(uuid4()), filename, content)
    generated_id = str(uuid4())
    row = SynthMedGeneratedDataset(
        id=generated_id,
        owner_id=owner_id,
        source_dataset_id=source_id,
        source_dataset_name="Fictional source",
        dataset_name="Fictional generated cohort",
        generation_method="SDV CTGAN",
        selected_model="CTGAN",
        record_count=2,
        column_count=5,
        file_format=file_format,
        file_size_bytes=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        stored_path=relative_path,
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_source(
    db: Session,
    client: TestClient,
    *,
    owner_id: str,
    content: bytes,
    filename: str,
) -> SynthMedSourceDataset:
    storage = SynthMedStorageService(client.app.state.settings)
    source_id = str(uuid4())
    _, relative_path = storage.save_source(source_id, filename, content)
    row = SynthMedSourceDataset(
        id=source_id,
        owner_id=owner_id,
        dataset_name="Fictional source",
        description="Fictional source used only for tests",
        original_filename=filename,
        stored_path=relative_path,
        file_format="CSV",
        file_size_bytes=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        row_count=2,
        column_count=2,
        upload_status="Uploaded",
        content_type="text/csv",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_repository_source_creation_preserves_repository_dataset_and_blocks_other_user(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, "repo.source.owner@example.org", UserRole.CONTRIBUTOR)
    other = create_user(db_session, "repo.source.other@example.org", UserRole.RESEARCHER)
    owner_headers = login(client, owner.email)
    other_headers = login(client, other.email)
    dataset = upload_repository_dataset(client, owner_headers, "Fictional repository cohort")
    dataset_id = dataset["id"]
    stored = db_session.get(Dataset, dataset_id)
    assert stored is not None
    original_checksum = stored.checksum_sha256
    original_size = stored.file_size_bytes
    original_updated = stored.updated_at

    denied = client.post(f"/api/v1/synthmed/sources/from-repository/{dataset_id}", headers=other_headers)
    assert denied.status_code == 403, denied.text

    response = client.post(f"/api/v1/synthmed/sources/from-repository/{dataset_id}", headers=owner_headers)
    assert response.status_code == 201, response.text
    source = response.json()
    assert source["datasetName"] == "Fictional repository cohort"
    assert source["originalFilename"] == "fictional_cohort.csv"
    assert source["fileFormat"] == "CSV"
    assert source["checksumSha256"] == original_checksum
    assert source["rowCount"] == dataset["records"]

    row = db_session.get(SynthMedSourceDataset, source["id"])
    assert row is not None
    assert row.owner_id == owner.id
    assert row.checksum_sha256 == original_checksum
    assert row.file_size_bytes == original_size
    assert row.content_type == "text/csv"

    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "synthmed.source_created_from_repository",
            AuditLog.resource_id == source["id"],
        )
    )
    assert audit is not None

    db_session.refresh(stored)
    assert stored.checksum_sha256 == original_checksum
    assert stored.file_size_bytes == original_size
    assert stored.updated_at == original_updated
    assert stored.status == DatasetStatus.PROCESSING

    repeat = client.post(f"/api/v1/synthmed/sources/from-repository/{dataset_id}", headers=owner_headers)
    assert repeat.status_code == 201, repeat.text
    assert repeat.json()["id"] == source["id"]
    assert len(db_session.scalars(select(SynthMedSourceDataset)).all()) == 1


def test_generated_registration_creates_synthetic_dataset_and_rejects_duplicate(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, "generated.register.owner@example.org", UserRole.CONTRIBUTOR)
    headers = login(client, owner.email)
    repository_dataset = upload_repository_dataset(client, headers, "Fictional source repository dataset")
    repository_row = db_session.get(Dataset, repository_dataset["id"])
    assert repository_row is not None
    repository_row.status = DatasetStatus.AVAILABLE
    db_session.commit()

    source_response = client.post(
        f"/api/v1/synthmed/sources/from-repository/{repository_dataset['id']}", headers=headers
    )
    assert source_response.status_code == 201, source_response.text
    source_id = source_response.json()["id"]

    generated = add_generated_dataset(
        db_session,
        client,
        owner_id=owner.id,
        source_id=source_id,
        content=GENERATED_CSV,
        filename="synthetic_cohort.csv",
    )
    job_id = str(uuid4())
    db_session.add(
        SynthMedGenerationJob(
            id=job_id,
            owner_id=owner.id,
            source_dataset_id=source_id,
            generated_dataset_id=generated.id,
            status="Completed",
            model_name="CTGAN",
            selected_model="CTGAN",
            epochs=1,
            batch_size=20,
            requested_record_count=2,
            generated_record_count=2,
        )
    )
    db_session.commit()

    response = client.post(
        "/api/v1/datasets/",
        headers=headers,
        data={
            "metadata": json.dumps(registration_payload("Fictional registered synthetic cohort")),
            "generated_dataset_id": generated.id,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    summary = body["dataset"]
    assert summary["origin"] == "Synthetic"
    assert summary["sourceGeneratedDatasetId"] == generated.id
    assert summary["sourceRepositoryDatasetId"] == repository_dataset["id"]
    assert summary["generationJobId"] == job_id
    assert summary["generationModel"] == "CTGAN"
    assert summary["checksum"] == generated.checksum_sha256
    assert summary["access"] == "Open"
    assert summary["status"] == DatasetStatus.PROCESSING.value
    assert summary["provenance"]["generatedDatasetId"] == generated.id
    assert summary["provenance"]["sourceDatasetName"] == "Fictional source"
    assert summary["provenance"]["sourceRepositoryDatasetId"] == repository_dataset["id"]
    assert summary["provenance"]["checksumSha256"] == generated.checksum_sha256
    assert summary["ageRange"] == "18-90 years"
    assert summary["geography"] == ["England"]
    assert summary["studyDesign"] == "Fictional cohort"
    assert summary["license"] == "Research use only"
    assert summary["ethicsApproved"] is True
    assert summary["dataDictionaryAvailable"] is True
    assert summary["intendedTasks"] == ["Classification"]
    assert summary["labelColumn"] == "Disease"

    dataset = db_session.get(Dataset, summary["id"])
    assert dataset is not None
    assert dataset.origin == "Synthetic"
    assert dataset.source_generated_dataset_id == generated.id
    assert dataset.source_repository_dataset_id == repository_dataset["id"]
    assert dataset.status == DatasetStatus.PROCESSING
    assert dataset.approved_by_id is None
    assert dataset.approved_at is None
    assert dataset.checksum_sha256 == generated.checksum_sha256
    assert dataset.research_task == "Classification"
    assert dataset.provenance_json["generationJobId"] == job_id
    assert dataset.provenance_json["ingestionPath"] == "shared-etl"
    assert dataset.provenance_json["storage"] == "independent-copy"
    etl_job = db_session.scalar(select(ETLJob).where(ETLJob.dataset_id == dataset.id))
    assert etl_job is not None
    assert etl_job.status == JobStatus.QUEUED

    generated_listing = client.get("/api/v1/synthmed/generated", headers=headers)
    assert generated_listing.status_code == 200, generated_listing.text
    listed = next(row for row in generated_listing.json() if row["id"] == generated.id)
    assert listed["repositoryRegistrationStatus"] == "In Repository ETL"
    assert listed["repositoryDatasetId"] == summary["id"]

    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "synthmed.generated_ingestion_queued",
            AuditLog.resource_id == summary["id"],
        )
    )
    assert audit is not None

    duplicate = client.post(
        f"/api/v1/synthmed/generated/{generated.id}/register-in-repository",
        headers=headers,
        json=registration_payload("Fictional duplicate synthetic cohort"),
    )
    assert duplicate.status_code == 409, duplicate.text
    assert summary["id"] in duplicate.json()["detail"]
    assert len(db_session.scalars(select(Dataset)).all()) == 2


def test_generated_registration_rejects_disallowed_columns_from_xlsx(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, "generated.columns.owner@example.org", UserRole.CONTRIBUTOR)
    headers = login(client, owner.email)
    source = add_source(
        db_session,
        client,
        owner_id=owner.id,
        content=b"Age,Gender\n34,Female\n",
        filename="fictional_source.csv",
    )
    frame = pd.DataFrame(
        {
            "Age": [34, 41],
            "patient_id": ["FICTIONAL-1", "FICTIONAL-2"],
            "Unknown_Marker": [1, 0],
        }
    )
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False, engine="openpyxl")
    generated = add_generated_dataset(
        db_session,
        client,
        owner_id=owner.id,
        source_id=source.id,
        content=buffer.getvalue(),
        filename="synthetic_with_bad_columns.xlsx",
        file_format="XLSX",
    )

    response = client.post(
        f"/api/v1/synthmed/generated/{generated.id}/register-in-repository",
        headers=headers,
        json=registration_payload("Fictional invalid synthetic cohort"),
    )
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert set(detail["offendingColumns"]) == {"patient_id", "Unknown_Marker"}
    assert db_session.scalar(
        select(Dataset).where(Dataset.source_generated_dataset_id == generated.id)
    ) is None


def test_repository_source_uses_exact_selected_version(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, "repository.version.owner@example.org", UserRole.CONTRIBUTOR)
    headers = login(client, owner.email)
    upload = client.post(
        "/api/v1/datasets/",
        headers=headers,
        files={"file": ("fictional_cohort.csv", REPOSITORY_CSV, "text/csv")},
        data={"metadata": json.dumps(repository_metadata("Fictional versioned cohort"))},
    )
    assert upload.status_code == 201, upload.text
    dataset_id = upload.json()["dataset"]["id"]
    prepare_and_run_etl(client, headers, upload.json()["jobId"])

    version = db_session.scalar(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id))
    assert version is not None
    source = source_service.create_source_from_repository(
        db_session,
        settings=client.app.state.settings,
        user=owner,
        dataset_id=dataset_id,
        version_id=version.id,
    )
    assert source.checksum_sha256 == version.checksum_sha256
    assert source.row_count == version.record_count
    assert source.column_count == version.column_count

    source_version = db_session.scalar(
        select(SynthMedDatasetVersion).where(
            SynthMedDatasetVersion.dataset_kind == "source",
            SynthMedDatasetVersion.logical_dataset_id == source.id,
        )
    )
    assert source_version is not None
    assert source_version.metadata_json["repositoryDatasetId"] == dataset_id
    assert source_version.metadata_json["repositoryVersionId"] == version.id
