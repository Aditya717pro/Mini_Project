import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Dataset,
    DatasetVersion,
    ETLJob,
    QualityReport,
    ReadinessReport,
    RepresentativenessReport,
)
from app.models.enums import AccessClassification, DatasetStatus, UserRole
from app.services.storage_service import StorageService
from tests.test_workflows import create_user, login

SENTINEL = "PRIVATE-SUBJECT-ZZ-9917"
CSV_CONTENT = (
    "subject_code,age_years,sex_at_birth,region,visit_date,label,weight_kg,notes\n"
    f"{SENTINEL},34,Female,England,2025-01-01,0,61.2,intake\n"
    "SYNTH-BETA-2204,29,Female,England,2025-01-02,1,58.0,follow-up\n"
    "SYNTH-GAMMA-7781,,Male,Scotland,2025-01-03,0,70.5,missing age\n"
)


def metadata(title: str) -> dict:
    return {
        "title": title,
        "description": "Fictional cohort created solely for versioning tests.",
        "domain": "Women's health",
        "access": "Controlled",
        "tags": ["synthetic", "versioning"],
        "age_range": "18-45 years",
        "geography": ["England", "Scotland"],
        "study_design": "Retrospective cohort",
        "license": "Synthetic research use only",
        "ethics_approved": True,
        "data_dictionary_available": True,
        "intended_tasks": ["Synthetic classification"],
        "label_column": "label",
        "research_task": "Synthetic classification",
    }


def upload(client: TestClient, headers: dict[str, str], title: str, content: str = CSV_CONTENT) -> dict:
    response = client.post(
        "/api/v1/datasets/",
        headers=headers,
        files={"file": ("cohort.csv", content.encode("utf-8"), "text/csv")},
        data={"metadata": json.dumps(metadata(title))},
    )
    assert response.status_code == 201, response.text
    return response.json()


def prepare_and_run(client: TestClient, headers: dict[str, str], job_id: str) -> None:
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


def ordered_versions(db: Session, dataset_id: str) -> list[DatasetVersion]:
    return list(
        db.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number)
        )
    )


@pytest.fixture()
def processed_dataset(client: TestClient, db_session: Session) -> dict:
    contributor = create_user(db_session, "versioning.owner@example.org", UserRole.CONTRIBUTOR)
    headers = login(client, contributor.email)
    payload = upload(client, headers, "Fictional versioning cohort")
    dataset_id = payload["dataset"]["id"]
    job_id = payload["jobId"]
    original = ordered_versions(db_session, dataset_id)[0]
    snapshot = {
        "id": original.id,
        "raw_file_path": original.raw_file_path,
        "checksum": original.checksum_sha256,
        "record_count": original.record_count,
    }
    prepare_and_run(client, headers, job_id)
    return {
        "headers": headers,
        "dataset_id": dataset_id,
        "job_id": job_id,
        "original": snapshot,
        "owner": contributor,
    }


def storage(client: TestClient) -> StorageService:
    return StorageService(client.app.state.settings)


def test_upload_v1_and_etl_create_new_processed_version(
    client: TestClient,
    db_session: Session,
    processed_dataset: dict,
) -> None:
    dataset_id = processed_dataset["dataset_id"]
    original = processed_dataset["original"]
    store = storage(client)
    versions = ordered_versions(db_session, dataset_id)
    assert len(versions) == 2
    first, second = versions

    assert first.id == original["id"]
    assert first.version_label == "v1.0"
    assert first.is_current is False
    assert first.raw_file_path == original["raw_file_path"]
    assert first.processed_file_path is None
    assert first.checksum_sha256 == original["checksum"]
    assert first.record_count == original["record_count"]
    assert store.resolve(first.raw_file_path, kind="raw").read_bytes().startswith(b"subject_code,")

    assert second.version_number == 2
    assert second.version_label == "v1.1"
    assert second.is_current is True
    assert second.raw_file_path == original["raw_file_path"]
    assert second.transformation_log_json["parent_version_id"] == first.id
    assert second.transformation_log_json["lineage"]["etlJobId"] == processed_dataset["job_id"]
    assert second.processed_file_path
    assert Path(second.processed_file_path).name.startswith(second.id[:8])
    processed_file = store.resolve(second.processed_file_path, kind="processed")
    assert processed_file.exists()
    assert len(processed_file.read_bytes()) == second.file_size_bytes

    stored_job = db_session.get(ETLJob, processed_dataset["job_id"])
    assert stored_job is not None and stored_job.dataset_version_id == second.id

    for report_model in (QualityReport, ReadinessReport, RepresentativenessReport):
        report = db_session.scalar(select(report_model).where(report_model.dataset_id == dataset_id))
        assert report is not None and report.dataset_version_id == second.id

    audit = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "dataset.version_created", AuditLog.resource_id == dataset_id)
    ).all()
    assert len(audit) == 1
    assert audit[0].details_json["parentVersionId"] == first.id
    assert audit[0].details_json["versionId"] == second.id


def test_version_history_get_and_lineage_endpoints(
    client: TestClient,
    db_session: Session,
    processed_dataset: dict,
) -> None:
    dataset_id = processed_dataset["dataset_id"]
    headers = processed_dataset["headers"]
    first, second = ordered_versions(db_session, dataset_id)

    history = client.get(f"/api/v1/datasets/{dataset_id}/versions", headers=headers)
    assert history.status_code == 200, history.text
    payload = history.json()
    assert payload["datasetId"] == dataset_id
    assert payload["datasetName"] == "Fictional versioning cohort"
    assert payload["datasetType"] == "CSV"
    assert payload["ownerId"] == processed_dataset["owner"].id
    assert payload["currentVersion"] == "v1.1"
    assert payload["totalVersions"] == 2
    assert set(payload) >= {
        "datasetId",
        "datasetName",
        "datasetType",
        "ownerId",
        "currentVersion",
        "totalVersions",
        "lastUpdatedAt",
        "versions",
    }
    item = payload["versions"][0]
    assert item["id"] == second.id
    assert item["isCurrent"] is True
    assert item["kind"] == "Processed"
    assert item["parentVersionId"] == first.id
    assert item["creator"] == processed_dataset["owner"].id
    assert item["checksumSha256"] == second.checksum_sha256
    assert item["fileAvailable"] is True
    assert set(item) >= {
        "id",
        "versionNumber",
        "versionLabel",
        "kind",
        "recordCount",
        "columnCount",
        "createdAt",
        "creator",
        "checksumSha256",
        "isCurrent",
        "rawFilePath",
        "processedFilePath",
        "parentVersionId",
        "transformationHistory",
        "validationSummary",
        "fileAvailable",
    }

    original_item = client.get(f"/api/v1/datasets/{dataset_id}/versions/{first.id}", headers=headers)
    assert original_item.status_code == 200, original_item.text
    assert original_item.json()["kind"] == "Original"
    assert original_item.json()["processedFilePath"] is None
    assert original_item.json()["isCurrent"] is False

    lineage = client.get(f"/api/v1/datasets/{dataset_id}/lineage", headers=headers)
    assert lineage.status_code == 200, lineage.text
    assert lineage.json()["datasetId"] == dataset_id
    assert any(
        event["parentVersionId"] == first.id and event["childVersionId"] == second.id
        for event in lineage.json()["lineage"]
    )
    assert lineage.json()["lineage"] == lineage.json()["events"]

    scoped = client.get(f"/api/v1/datasets/{dataset_id}/versions/{second.id}/lineage", headers=headers)
    assert scoped.status_code == 200, scoped.text
    assert [item["id"] for item in scoped.json()["versions"]] == [second.id]
    assert scoped.json()["events"]


def test_compare_versions_rejects_foreign_and_missing_files(
    client: TestClient,
    db_session: Session,
    processed_dataset: dict,
) -> None:
    dataset_id = processed_dataset["dataset_id"]
    headers = processed_dataset["headers"]
    first, second = ordered_versions(db_session, dataset_id)

    response = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/compare",
        headers=headers,
        json={"versionAId": first.id, "versionBId": second.id},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["datasetId"] == dataset_id
    assert payload["a"]["id"] == first.id
    assert payload["b"]["id"] == second.id
    assert payload["comparison"]["checksumChanged"] is True
    assert payload["comparison"]["columnCountDelta"] > 0
    assert payload["comparison"]["recordCountDelta"] == 0
    assert payload["comparison"]["schema"]["added"]
    assert payload["comparison"]["dtypeChanges"] == []
    assert payload["b"]["checksumMatchesRecorded"] is True

    other_headers = login(client, create_user(db_session, "versioning.other@example.org", UserRole.CONTRIBUTOR).email)
    other_payload = upload(client, other_headers, "Unrelated fictional cohort")
    other_version = ordered_versions(db_session, other_payload["dataset"]["id"])[0]
    foreign = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/compare",
        headers=headers,
        json={"versionAId": first.id, "versionBId": other_version.id},
    )
    assert foreign.status_code == 422

    processed_file = storage(client).resolve(second.processed_file_path, kind="processed")
    backup = processed_file.read_bytes()
    processed_file.unlink()
    try:
        missing = client.post(
            f"/api/v1/datasets/{dataset_id}/versions/compare",
            headers=headers,
            json={"versionAId": first.id, "versionBId": second.id},
        )
        assert missing.status_code == 409
    finally:
        processed_file.write_bytes(backup)


def test_restore_version_valid_checksum_missing_file_and_permissions(
    client: TestClient,
    db_session: Session,
    processed_dataset: dict,
) -> None:
    dataset_id = processed_dataset["dataset_id"]
    headers = processed_dataset["headers"]
    original = processed_dataset["original"]
    first, second = ordered_versions(db_session, dataset_id)
    store = storage(client)

    response = client.post(f"/api/v1/datasets/{dataset_id}/versions/{first.id}/restore", headers=headers)
    assert response.status_code == 201, response.text
    restored_item = response.json()
    assert restored_item["parentVersionId"] == first.id
    assert restored_item["restoredFromVersionId"] == first.id
    assert restored_item["versionLabel"] == "v1.2"
    assert restored_item["isCurrent"] is True
    assert restored_item["rawFilePath"] != first.raw_file_path
    assert store.resolve(restored_item["rawFilePath"], kind="raw").read_bytes().startswith(b"subject_code,")
    assert first.raw_file_path == original["raw_file_path"]
    assert first.processed_file_path is None
    assert second.is_current is False

    raw_path = store.resolve(first.raw_file_path, kind="raw")
    good_bytes = raw_path.read_bytes()
    raw_path.write_bytes(b"tampered,content\n")
    try:
        mismatch = client.post(f"/api/v1/datasets/{dataset_id}/versions/{first.id}/restore", headers=headers)
        assert mismatch.status_code == 409
    finally:
        raw_path.write_bytes(good_bytes)

    renamed = raw_path.with_suffix(".held")
    raw_path.rename(renamed)
    try:
        missing = client.post(f"/api/v1/datasets/{dataset_id}/versions/{first.id}/restore", headers=headers)
        assert missing.status_code == 409
    finally:
        renamed.rename(raw_path)

    dataset = db_session.get(Dataset, dataset_id)
    assert dataset is not None
    dataset.status = DatasetStatus.AVAILABLE
    db_session.commit()
    other = login(client, create_user(db_session, "versioning.restore-other@example.org", UserRole.CONTRIBUTOR).email)
    forbidden = client.post(f"/api/v1/datasets/{dataset_id}/versions/{first.id}/restore", headers=other)
    assert forbidden.status_code == 403

    audit = db_session.scalars(
        select(AuditLog).where(
            AuditLog.action == "dataset.version_restored",
            AuditLog.resource_id == dataset_id,
        )
    ).all()
    assert len(audit) == 1
    assert audit[0].details_json["restoredFromVersionId"] == first.id


def test_version_responses_and_audit_contain_no_patient_identifiers(
    client: TestClient,
    db_session: Session,
    processed_dataset: dict,
) -> None:
    dataset_id = processed_dataset["dataset_id"]
    headers = processed_dataset["headers"]
    first, second = ordered_versions(db_session, dataset_id)

    endpoints = [
        f"/api/v1/datasets/{dataset_id}/versions",
        f"/api/v1/datasets/{dataset_id}/versions/{first.id}",
        f"/api/v1/datasets/{dataset_id}/versions/{second.id}",
        f"/api/v1/datasets/{dataset_id}/lineage",
    ]
    for endpoint in endpoints:
        response = client.get(endpoint, headers=headers)
        assert response.status_code == 200, response.text
        assert SENTINEL not in response.text
    comparison = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/compare",
        headers=headers,
        json={"versionAId": first.id, "versionBId": second.id},
    )
    assert comparison.status_code == 200
    assert SENTINEL not in comparison.text

    details = [entry.details_json for entry in db_session.scalars(select(AuditLog)).all()]
    assert SENTINEL not in json.dumps(details)


def test_version_download_verifies_checksum_and_access(
    client: TestClient,
    db_session: Session,
    processed_dataset: dict,
) -> None:
    dataset_id = processed_dataset["dataset_id"]
    headers = processed_dataset["headers"]
    first, second = ordered_versions(db_session, dataset_id)
    store = storage(client)

    processed_file = store.resolve(second.processed_file_path, kind="processed")
    good_bytes = processed_file.read_bytes()
    downloaded = client.get(f"/api/v1/datasets/{dataset_id}/versions/{second.id}/download", headers=headers)
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == good_bytes

    raw_download = client.get(f"/api/v1/datasets/{dataset_id}/versions/{first.id}/download", headers=headers)
    assert raw_download.status_code == 200
    assert raw_download.content.startswith(b"subject_code,")

    processed_file.write_bytes(b"corrupted,output\n")
    try:
        bad = client.get(f"/api/v1/datasets/{dataset_id}/versions/{second.id}/download", headers=headers)
        assert bad.status_code == 409
    finally:
        processed_file.write_bytes(good_bytes)

    reader = create_user(db_session, "versioning.reader@example.org", UserRole.RESEARCHER)
    researcher_headers = login(client, reader.email)
    denied = client.get(f"/api/v1/datasets/{dataset_id}/versions/{second.id}/download", headers=researcher_headers)
    assert denied.status_code == 403

    missing_version = client.get(f"/api/v1/datasets/{dataset_id}/versions/not-a-version/download", headers=headers)
    assert missing_version.status_code == 404


def test_snapshot_requires_change_or_explicit_note(client: TestClient, db_session: Session) -> None:
    contributor = create_user(db_session, "versioning.snapshot@example.org", UserRole.CONTRIBUTOR)
    headers = login(client, contributor.email)
    payload = upload(client, headers, "Fictional snapshot cohort")
    dataset_id = payload["dataset"]["id"]
    original = ordered_versions(db_session, dataset_id)[0]

    unchanged = client.post(f"/api/v1/datasets/{dataset_id}/versions", headers=headers, json={"note": ""})
    assert unchanged.status_code == 409
    assert ordered_versions(db_session, dataset_id)[0].id == original.id

    snapshot = client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        headers=headers,
        json={"note": "Metadata checkpoint for synthetic fixture"},
    )
    assert snapshot.status_code == 201, snapshot.text
    item = snapshot.json()
    assert item["versionLabel"] == "v1.1"
    assert item["kind"] == "Original"
    assert item["isCurrent"] is True
    assert item["parentVersionId"] == original.id
    assert item["note"] == "Metadata checkpoint for synthetic fixture"
    assert item["rawFilePath"] != original.raw_file_path
    assert storage(client).resolve(item["rawFilePath"], kind="raw").read_bytes().startswith(b"subject_code,")
    assert ordered_versions(db_session, dataset_id)[0].raw_file_path == original.raw_file_path


def test_snapshot_rejects_non_owner_even_when_dataset_is_available(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, "versioning.snapshot-owner@example.org", UserRole.CONTRIBUTOR)
    dataset_id = upload(client, login(client, owner.email), "Fictional shared snapshot cohort")["dataset"]["id"]
    original = ordered_versions(db_session, dataset_id)[0]
    dataset = db_session.get(Dataset, dataset_id)
    assert dataset is not None
    dataset.status = DatasetStatus.AVAILABLE
    db_session.commit()

    other = create_user(db_session, "versioning.snapshot-other@example.org", UserRole.CONTRIBUTOR)
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        headers=login(client, other.email),
        json={"note": "Unauthorised checkpoint"},
    )
    assert response.status_code == 403
    assert ordered_versions(db_session, dataset_id)[0].id == original.id


def test_restricted_version_metadata_requires_approved_access(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, "versioning.restricted-owner@example.org", UserRole.CONTRIBUTOR)
    headers = login(client, owner.email)
    dataset_id = upload(client, headers, "Fictional restricted cohort")["dataset"]["id"]
    dataset = db_session.get(Dataset, dataset_id)
    assert dataset is not None
    dataset.status = DatasetStatus.AVAILABLE
    dataset.access_classification = AccessClassification.RESTRICTED
    db_session.commit()

    reader = create_user(db_session, "versioning.restricted-reader@example.org", UserRole.RESEARCHER)
    denied = client.get(f"/api/v1/datasets/{dataset_id}/versions", headers=login(client, reader.email))
    assert denied.status_code == 403
    allowed = client.get(f"/api/v1/datasets/{dataset_id}/versions", headers=headers)
    assert allowed.status_code == 200


def test_history_masks_absolute_storage_paths(
    client: TestClient, db_session: Session, processed_dataset: dict
) -> None:
    dataset_id = processed_dataset["dataset_id"]
    headers = processed_dataset["headers"]
    version = ordered_versions(db_session, dataset_id)[0]
    version.raw_file_path = str(Path.cwd() / "private-storage" / "cohort.csv")
    version.processed_file_path = str(Path.cwd() / "private-storage" / "processed.csv")
    db_session.commit()

    response = client.get(f"/api/v1/datasets/{dataset_id}/versions/{version.id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["rawFilePath"] == "cohort.csv"
    assert response.json()["processedFilePath"] == "processed.csv"
    assert "private-storage" not in response.text
