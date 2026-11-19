import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import DatasetVersion, User
from app.models.enums import UserRole
from app.services.storage_service import StorageService


def create_user(db: Session, email: str, role: UserRole) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0].replace(".", " ").title(),
        hashed_password=hash_password("correct-horse-1"),
        role=role,
        organisation="Synthetic Test Organisation",
        title="Test User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-1"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_register_login_and_me(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "new.user@example.org",
            "password": "correct-horse-1",
            "full_name": "New User",
            "organisation": "Example Org",
            "title": "Researcher",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "Contributor"

    headers = login(client, "new.user@example.org")
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "new.user@example.org"


def test_upload_etl_reports_and_access_flow(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
) -> None:
    contributor = create_user(db_session, "contributor@example.org", UserRole.CONTRIBUTOR)
    researcher = create_user(db_session, "researcher@example.org", UserRole.RESEARCHER)
    create_user(db_session, "admin@example.org", UserRole.ADMINISTRATOR)
    contributor_headers = login(client, contributor.email)
    researcher_headers = login(client, researcher.email)
    admin_headers = login(client, "admin@example.org")

    csv_content = (
        "participant_id,age,sex,region,visit_date,outcome,weight_kg,notes\n"
        "P001,34,Female,England,2025-01-01,0,61.2,ok\n"
        "P002,29,Female,England,2025-01-02,1,58.0,follow-up\n"
        "P003,,Male,Scotland,2025-01-03,0,70.5,missing age\n"
        "P004,41,Male,Wales,not-a-date,1,82.1,date issue\n"
        "P005,34,Female,England,2025-01-01,0,61.2,ok\n"
    )
    metadata = {
        "title": "Synthetic Women's Health Cohort",
        "description": "Synthetic test dataset with no real patient data.",
        "domain": "Women's health",
        "access": "Controlled",
        "tags": ["synthetic", "test"],
        "age_range": "18-45 years",
        "geography": ["England", "Scotland", "Wales"],
        "study_design": "Retrospective cohort",
        "license": "Synthetic research use only",
        "ethics_approved": True,
        "data_dictionary_available": True,
        "intended_tasks": ["Readmission risk modelling"],
        "label_column": "outcome",
        "research_task": "Readmission risk modelling",
    }
    upload = client.post(
        "/api/v1/datasets/",
        headers=contributor_headers,
        files={"file": ("synthetic.csv", csv_content.encode(), "text/csv")},
        data={"metadata": json.dumps(metadata)},
    )
    assert upload.status_code == 201, upload.text
    payload = upload.json()
    dataset_id = payload["dataset"]["id"]
    job_id = payload["jobId"]
    assert payload["dataset"]["status"] == "Processing"

    job = client.get(f"/api/v1/etl/jobs/{job_id}", headers=contributor_headers)
    assert job.status_code == 200, job.text
    assert job.json()["status"] == "Queued"
    assert all(item["decision"] is None for item in job.json()["mappings"])

    blocked = client.post(
        f"/api/v1/etl/jobs/{job_id}/run",
        headers=contributor_headers,
        json={"task": "Readmission risk modelling"},
    )
    assert blocked.status_code == 409

    profiled = client.post(f"/api/v1/etl/jobs/{job_id}/profile", headers=contributor_headers)
    assert profiled.status_code == 200, profiled.text
    assert profiled.json()["status"] == "Review required"
    assert profiled.json()["profile"]["row_count"] == 5

    mappings = {
        "participant_id": "participant_id",
        "age": "age_years",
        "sex": "sex_at_birth",
        "region": "region",
        "visit_date": "visit_date",
        "outcome": "label",
        "weight_kg": "weight_kg",
        "notes": None,
    }
    decisions = [
        {
            "source": source,
            "decision": "Approved" if target else "Unmapped",
            "target": target,
            "note": "Synthetic fixture decision",
        }
        for source, target in mappings.items()
    ]
    saved = client.post(
        f"/api/v1/etl/jobs/{job_id}/mappings",
        headers=contributor_headers,
        json=decisions,
    )
    assert saved.status_code == 200, saved.text
    assert all(item["decision"] for item in saved.json()["mappings"])
    assert all(item["decidedBy"] for item in saved.json()["mappings"])

    approved = client.post(f"/api/v1/etl/jobs/{job_id}/approve", headers=contributor_headers, json={})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "Approved"
    assert approved.json()["approvedBy"] == contributor.email

    run = client.post(
        f"/api/v1/etl/jobs/{job_id}/run",
        headers=contributor_headers,
        json={"task": "Readmission risk modelling"},
    )
    assert run.status_code == 200, run.text
    finished_job = client.get(f"/api/v1/etl/jobs/{job_id}", headers=contributor_headers)
    assert finished_job.json()["status"] == "Completed"
    assert finished_job.json()["transformationSummary"]["errors"].get("visit_date") == 1
    assert any(
        issue["severity"] == "error" and issue["target"] == "visit_date"
        for issue in finished_job.json()["transformationSummary"]["rowIssues"]
    )

    detail = client.get(f"/api/v1/datasets/{dataset_id}", headers=contributor_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "Pending review"
    assert detail.json()["qualityScore"] is not None

    quality = client.get(f"/api/v1/datasets/{dataset_id}/quality", headers=contributor_headers)
    assert quality.status_code == 200, quality.text
    assert quality.json()["overall"] > 0

    readiness = client.get(f"/api/v1/datasets/{dataset_id}/readiness", headers=contributor_headers)
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["verdict"] in {"Ready", "Ready with caveats", "Not ready"}

    representativeness = client.get(
        f"/api/v1/datasets/{dataset_id}/representativeness",
        headers=contributor_headers,
    )
    assert representativeness.status_code == 200, representativeness.text
    assert representativeness.json()["missingAttributes"]

    denied = client.get(f"/api/v1/datasets/{dataset_id}/download", headers=researcher_headers)
    assert denied.status_code == 403

    approve = client.post(
        f"/api/v1/datasets/{dataset_id}/approve",
        headers=admin_headers,
        json={"reason": "Synthetic metadata and reports reviewed."},
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "Available"

    access = client.post(
        f"/api/v1/datasets/{dataset_id}/access-requests",
        headers=researcher_headers,
        json={
            "projectTitle": "Synthetic access test",
            "purpose": "Testing the governed access workflow without real patient data.",
        },
    )
    assert access.status_code == 201, access.text
    request_id = access.json()["id"]

    decision = client.patch(
        f"/api/v1/access-requests/{request_id}",
        headers=contributor_headers,
        json={"status": "Approved", "note": "Approved for synthetic testing only."},
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "Approved"

    download = client.get(f"/api/v1/datasets/{dataset_id}/download", headers=researcher_headers)
    assert download.status_code == 200
    assert download.content

    version = db_session.scalar(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id))
    assert version is not None
    storage = StorageService(client.app.state.settings)
    raw = storage.resolve(version.raw_file_path, kind="raw")
    processed = storage.resolve(version.processed_file_path or "", kind="processed")
    assert raw.exists() and raw.read_bytes().startswith(b"participant_id,")
    assert processed.exists()
    processed_text = processed.read_text(encoding="utf-8")
    assert "original__7__notes" in processed_text
    assert "visit_date:error" in processed_text

    outside = tmp_path / "outside.csv"
    outside.write_text("secret,not,a,dataset\n", encoding="utf-8")
    version.processed_file_path = None
    version.raw_file_path = str(outside)
    db_session.commit()
    rejected = client.get(f"/api/v1/datasets/{dataset_id}/download", headers=contributor_headers)
    assert rejected.status_code == 404
    assert b"secret" not in rejected.content

    version.raw_file_path = str(raw)
    db_session.commit()
    legacy = client.get(f"/api/v1/datasets/{dataset_id}/download", headers=contributor_headers)
    assert legacy.status_code == 200
    assert legacy.content.startswith(b"participant_id,")
