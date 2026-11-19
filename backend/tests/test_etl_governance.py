import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Dataset, DatasetVersion, ETLJob
from app.models.enums import JobStatus, UserRole
from app.services.job_service import claim_job
from app.services.storage_service import StorageService
from tests.test_workflows import create_user, login

SYNTHETIC_CSV = (
    "participant_id,age,sex,region,visit_date,outcome,weight_kg,notes\n"
    "P001,34,Female,England,2025-01-01,0,61.2,ok\n"
    "P002,29,Female,England,2025-01-02,1,58.0,follow-up\n"
    "P003,,Male,Scotland,2025-01-03,0,70.5,missing age\n"
    "P004,41,Male,Wales,not-a-date,1,82.1,date issue\n"
    "P005,34,Female,England,2025-01-01,0,61.2,ok\n"
)


def metadata(title: str = "Synthetic governance cohort") -> dict:
    return {
        "title": title,
        "description": "Synthetic data only; no real patient records.",
        "domain": "Women's health",
        "access": "Controlled",
        "tags": ["synthetic"],
        "age_range": "18-45 years",
        "geography": ["England"],
        "study_design": "Retrospective cohort",
        "license": "Synthetic research use only",
        "ethics_approved": True,
        "data_dictionary_available": True,
        "intended_tasks": ["Synthetic classification"],
        "label_column": "outcome",
        "research_task": "Synthetic classification",
    }


def contributor_headers(
    client: TestClient,
    db_session: Session,
    email: str = "etl-contributor@example.org",
) -> dict[str, str]:
    create_user(db_session, email, UserRole.CONTRIBUTOR)
    return login(client, email)


def upload(
    client: TestClient,
    headers: dict[str, str],
    content: str | bytes,
    title: str = "Synthetic governance cohort",
) -> dict:
    if isinstance(content, str):
        content = content.encode("utf-8")
    response = client.post(
        "/api/v1/datasets/",
        headers=headers,
        files={"file": ("synthetic.csv", content, "text/csv")},
        data={"metadata": json.dumps(metadata(title))},
    )
    assert response.status_code == 201, response.text
    return response.json()


def profile(client: TestClient, headers: dict[str, str], job_id: str) -> dict:
    response = client.post(f"/api/v1/etl/jobs/{job_id}/profile", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def decisions_for(job: dict, overrides: dict[str, dict] | None = None) -> list[dict]:
    overrides = overrides or {}
    result = []
    for item in job["mappings"]:
        source = item["source"]
        if source in overrides:
            result.append({"source": source, **overrides[source]})
            continue
        target = item["target"]
        result.append(
            {
                "source": source,
                "decision": "Approved" if target else "Unmapped",
                "target": target,
                "note": "Synthetic review decision",
            }
        )
    return result


def approve_and_prepare(
    client: TestClient,
    headers: dict[str, str],
    job_id: str,
    overrides: dict | None = None,
) -> dict:
    profiled = profile(client, headers, job_id)
    saved = client.post(
        f"/api/v1/etl/jobs/{job_id}/mappings",
        headers=headers,
        json=decisions_for(profiled, overrides),
    )
    assert saved.status_code == 200, saved.text
    approved = client.post(f"/api/v1/etl/jobs/{job_id}/approve", headers=headers, json={})
    assert approved.status_code == 200, approved.text
    return approved.json()


def run_job(client: TestClient, headers: dict[str, str], job_id: str) -> dict:
    response = client.post(f"/api/v1/etl/jobs/{job_id}/run", headers=headers, json={"task": "Synthetic classification"})
    assert response.status_code == 200, response.text
    job = client.get(f"/api/v1/etl/jobs/{job_id}", headers=headers)
    assert job.status_code == 200, job.text
    return job.json()


def test_etl_admin_can_view_and_list_other_users_jobs(client: TestClient, db_session: Session) -> None:
    owner_headers = contributor_headers(client, db_session, "etl-owner-access@example.org")
    other_headers = contributor_headers(client, db_session, "etl-other-access@example.org")
    job_id = upload(client, owner_headers, SYNTHETIC_CSV, "Admin access cohort")["jobId"]
    create_user(db_session, "etl-admin-access@example.org", UserRole.ADMINISTRATOR)
    admin_headers = login(client, "etl-admin-access@example.org")

    detail_path = f"/api/v1/etl/jobs/{job_id}"
    assert client.get(detail_path, headers=owner_headers).status_code == 200
    assert client.get(detail_path, headers=other_headers).status_code == 403
    assert client.get(detail_path, headers=admin_headers).status_code == 200

    def job_ids(headers: dict[str, str]) -> list[str]:
        response = client.get("/api/v1/etl/jobs", headers=headers)
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()]

    assert job_id in job_ids(owner_headers)
    assert job_id not in job_ids(other_headers)
    assert job_id in job_ids(admin_headers)


def test_upload_creates_queued_job_without_approvals(client: TestClient, db_session: Session) -> None:
    headers = contributor_headers(client, db_session)
    payload = upload(client, headers, SYNTHETIC_CSV)
    job_id = payload["jobId"]

    job = client.get(f"/api/v1/etl/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "Queued"
    assert all(item["decision"] is None for item in job["mappings"])

    stored = db_session.get(ETLJob, job_id)
    assert stored is not None and stored.approved_mapping_json == {}

    blocked = client.post(f"/api/v1/etl/jobs/{job_id}/run", headers=headers, json={"task": "Synthetic classification"})
    assert blocked.status_code == 409

    profiled = profile(client, headers, job_id)
    assert profiled["status"] == "Review required"
    assert profiled["profile"]["row_count"] == 5
    assert profiled["mappings"]


def test_partial_review_blocks_approval(client: TestClient, db_session: Session) -> None:
    headers = contributor_headers(client, db_session)
    job_id = upload(client, headers, SYNTHETIC_CSV)["jobId"]
    profiled = profile(client, headers, job_id)

    partial = client.post(
        f"/api/v1/etl/jobs/{job_id}/mappings",
        headers=headers,
        json=decisions_for(profiled)[:1],
    )
    assert partial.status_code == 200

    blocked = client.post(f"/api/v1/etl/jobs/{job_id}/approve", headers=headers, json={})
    assert blocked.status_code == 422
    assert "Unreviewed" in blocked.json()["detail"]

    saved = client.post(
        f"/api/v1/etl/jobs/{job_id}/mappings",
        headers=headers,
        json=decisions_for(profiled),
    )
    assert saved.status_code == 200
    approved = client.post(f"/api/v1/etl/jobs/{job_id}/approve", headers=headers, json={"note": "Reviewed"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "Approved"
    assert approved.json()["approvedBy"]


def test_rejected_mapping_leaves_source_unmapped(client: TestClient, db_session: Session) -> None:
    headers = contributor_headers(client, db_session)
    job_id = upload(client, headers, SYNTHETIC_CSV)["jobId"]
    profiled = profile(client, headers, job_id)
    overrides = {"age": {"decision": "Rejected", "target": None, "note": "Age meaning is unclear"}}
    saved = client.post(
        f"/api/v1/etl/jobs/{job_id}/mappings",
        headers=headers,
        json=decisions_for(profiled, overrides),
    )
    assert saved.status_code == 200
    age_mapping = next(item for item in saved.json()["mappings"] if item["source"] == "age")
    assert age_mapping["target"] == ""
    assert age_mapping["decision"] == "Rejected"
    approved = client.post(f"/api/v1/etl/jobs/{job_id}/approve", headers=headers, json={})
    assert approved.status_code == 200
    stored = db_session.get(ETLJob, job_id)
    assert stored is not None and stored.approved_mapping_json["age"] is None


def test_ambiguous_dates_are_flagged_and_not_parsed(client: TestClient, db_session: Session) -> None:
    headers = contributor_headers(client, db_session, "dates@example.org")
    content = "participant_id,visit_date\nP001,03/04/2025\nP002,2025-01-02\n"
    job_id = upload(client, headers, content, "Synthetic date cohort")["jobId"]
    approve_and_prepare(client, headers, job_id)
    finished = run_job(client, headers, job_id)

    profile_issues = finished["profile"]["issues"]
    assert any(issue["code"] == "ambiguous_date" and issue["field"] == "visit_date" for issue in profile_issues)
    assert finished["transformationSummary"]["warnings"].get("visit_date") == 1
    assert any(issue["code"] == "review_value" for issue in finished["transformationSummary"]["rowIssues"])

    version = db_session.scalar(
        select(DatasetVersion).join(Dataset).where(Dataset.title == "Synthetic date cohort")
    )
    assert version is not None and version.processed_file_path
    processed = StorageService(client.app.state.settings).resolve(
        version.processed_file_path, kind="processed"
    ).read_text(encoding="utf-8")
    assert "03/04/2025" in processed
    assert "visit_date:review" in processed
    assert "2025-01-02" in processed


def test_duplicate_column_names_rejected(client: TestClient, db_session: Session) -> None:
    headers = contributor_headers(client, db_session, "duplicates@example.org")
    response = client.post(
        "/api/v1/datasets/",
        headers=headers,
        files={"file": ("duplicate.csv", b"participant_id,participant_id\nP001,P002\n", "text/csv")},
        data={"metadata": json.dumps(metadata("Synthetic duplicate headers"))},
    )
    assert response.status_code == 422
    assert "Duplicate CSV column names" in response.json()["detail"]
    assert db_session.scalar(select(Dataset).where(Dataset.title == "Synthetic duplicate headers")) is None


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"a,b\n1,2,3\n4,5\n", "Malformed CSV"),
        (b"a,b\n\xff,2\n", "UTF-8"),
    ],
)
def test_malformed_csv_rejected(client: TestClient, db_session: Session, content: bytes, message: str) -> None:
    headers = contributor_headers(client, db_session, f"invalid-{abs(hash(content))}@example.org")
    response = client.post(
        "/api/v1/datasets/",
        headers=headers,
        files={"file": ("invalid.csv", content, "text/csv")},
        data={"metadata": json.dumps(metadata("Synthetic invalid file"))},
    )
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_atomic_publish_preserves_previous_output(tmp_path: Path) -> None:
    storage = StorageService(
        Settings(
            environment="test",
            raw_storage_dir=tmp_path / "raw",
            processed_storage_dir=tmp_path / "processed",
        )
    )
    target = storage.processed_target("dataset-1", "version-1", "processed.csv")
    storage.publish_processed_batch(
        "dataset-1",
        "version-1",
        [("processed.csv", b"previous", lambda path: None)],
    )
    assert target.read_bytes() == b"previous"

    def fail(_: Path) -> None:
        raise ValueError("validation failed")

    with pytest.raises(ValueError, match="validation failed"):
        storage.publish_processed_batch(
            "dataset-1",
            "version-1",
            [("processed.csv", b"partial", fail)],
        )
    assert target.read_bytes() == b"previous"
    assert not list(target.parent.glob("*.tmp"))
    assert not list(target.parent.glob(".*.tmp"))

    storage.publish_processed_batch(
        "dataset-1",
        "version-1",
        [("processed.csv", b"updated", lambda path: None)],
    )
    assert target.read_bytes() == b"updated"
    assert len(list(target.parent.glob("*processed.csv"))) == 1

    with pytest.raises(ValueError, match="Unsafe storage path"):
        storage.processed_target("../escape", "version-1", "processed.csv")


def test_job_lock_prevents_double_run(client: TestClient, db_session: Session) -> None:
    headers = contributor_headers(client, db_session, "locks@example.org")
    job_id = upload(client, headers, SYNTHETIC_CSV, "Synthetic lock cohort")["jobId"]
    approve_and_prepare(client, headers, job_id)
    job = db_session.get(ETLJob, job_id)
    assert job is not None

    assert claim_job(
        db_session,
        job,
        expected={JobStatus.APPROVED},
        next_status=JobStatus.RUNNING,
        stage="extract",
        progress=20,
    )
    blocked = client.post(f"/api/v1/etl/jobs/{job_id}/run", headers=headers, json={"task": "Synthetic classification"})
    assert blocked.status_code == 409
    assert not claim_job(
        db_session,
        job,
        expected={JobStatus.APPROVED},
        next_status=JobStatus.RUNNING,
        stage="extract",
        progress=20,
    )


def test_cancel_and_reject_lifecycle(client: TestClient, db_session: Session) -> None:
    headers = contributor_headers(client, db_session, "lifecycle@example.org")
    create_user(db_session, "lifecycle-admin@example.org", UserRole.ADMINISTRATOR)
    admin_headers = login(client, "lifecycle-admin@example.org")

    job_id = upload(client, headers, SYNTHETIC_CSV, "Synthetic cancel cohort")["jobId"]
    cancelled = client.post(f"/api/v1/etl/jobs/{job_id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "Cancelled"
    blocked = client.post(f"/api/v1/etl/jobs/{job_id}/run", headers=headers, json={"task": "Synthetic classification"})
    assert blocked.status_code == 409

    other_id = upload(client, headers, SYNTHETIC_CSV, "Synthetic reject cohort")["jobId"]
    rejected = client.post(
        f"/api/v1/etl/jobs/{other_id}/reject",
        headers=admin_headers,
        json={"reason": "Synthetic policy rejection"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "Rejected"
    assert rejected.json()["rejectionReason"] == "Synthetic policy rejection"


def test_duplicate_records_and_missing_values_are_preserved(client: TestClient, db_session: Session) -> None:
    headers = contributor_headers(client, db_session, "duplicates-rows@example.org")
    content = (
        "participant_id,age,sex\n"
        "P001,34,Female\n"
        "P002,,Male\n"
        "P001,34,Female\n"
    )
    payload = upload(client, headers, content, "Synthetic duplicate rows")
    dataset_id = payload["dataset"]["id"]
    job_id = payload["jobId"]
    approve_and_prepare(client, headers, job_id)
    finished = run_job(client, headers, job_id)
    assert finished["transformationSummary"]["duplicates"] == 1

    version = db_session.scalar(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id))
    assert version is not None and version.processed_file_path
    lines = StorageService(client.app.state.settings).resolve(
        version.processed_file_path, kind="processed"
    ).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    assert "_duplicate_record" in lines[0]
    assert "_validation_flags" in lines[0]
    p002 = next(line for line in lines if "P002" in line)
    assert ",," in p002
