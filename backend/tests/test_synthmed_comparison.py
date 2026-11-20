from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
API = "/api/v1/synthmed"
PASSWORD = "SynthMedTest!42"

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

ALTERNATE_CSV = (
    b"subject_id,bmi,group\n"
    b"S001,21.4,A\n"
    b"S002,23.8,B\n"
    b"S003,25.1,A\n"
    b"S004,27.9,B\n"
    b"S005,22.6,A\n"
)


def register_and_login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        REGISTER,
        json={
            "email": email,
            "password": PASSWORD,
            "full_name": "Comparison Tester",
            "organisation": "Test Lab",
            "title": "Researcher",
        },
    )
    assert response.status_code == 201, response.text
    login = client.post(LOGIN, json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def upload_source(client: TestClient, headers: dict[str, str], name: str, content: bytes = FICTIONAL_CSV) -> str:
    response = client.post(
        f"{API}/upload",
        headers=headers,
        data={"dataset_name": name, "description": "Fictional test data"},
        files={"file": (f"{name}.csv", content, "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()["dataset"]["id"]


def generate(client: TestClient, headers: dict[str, str], source_id: str, name: str) -> str:
    payload = {
        "sourceDatasetId": source_id,
        "datasetName": name,
        "selectedColumns": ["patient_id", "age", "cholesterol", "diagnosis", "visit_date", "smoker"],
        "categoricalColumns": ["diagnosis"],
        "numericalColumns": ["age", "cholesterol"],
        "identifierColumns": ["patient_id"],
        "primaryKey": "patient_id",
        "seed": 11,
        "epochs": 1,
        "batchSize": 20,
        "recordCount": 8,
        "preserveMissingness": True,
    }
    response = client.post(f"{API}/generation/start", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "Completed", body
    return body["generatedDatasetId"]


def create_comparison(
    client: TestClient, headers: dict[str, str], source_id: str, generated_id: str, name: str = "Baseline"
) -> dict:
    response = client.post(
        f"{API}/comparisons",
        headers=headers,
        json={"sourceDatasetId": source_id, "generatedDatasetId": generated_id, "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_comparison_workflow_uses_real_data(app: FastAPI, client: TestClient, db_session: Session) -> None:
    headers = register_and_login(client, "comparison-owner@example.test")
    source_id = upload_source(client, headers, "Original cohort")
    generated_id = generate(client, headers, source_id, "Synthetic cohort")

    detail = create_comparison(client, headers, source_id, generated_id, "Cohort comparison")
    summary = detail["summary"]
    assert detail["name"] == "Cohort comparison"
    assert detail["sourceDatasetId"] == source_id
    assert detail["generatedDatasetId"] == generated_id
    assert summary["sourceRows"] == 20
    assert summary["syntheticRows"] == 8
    assert summary["rowDifference"] == -12
    assert summary["sourceColumns"] == 6
    assert summary["syntheticColumns"] == 5
    assert summary["sharedColumns"] == 5
    assert summary["onlySourceColumns"] == ["patient_id"]
    assert summary["onlySyntheticColumns"] == []
    assert 0 <= summary["overallSimilarity"] <= 1
    assert 0 <= summary["numericSimilarity"] <= 1
    assert 0 <= summary["categoricalSimilarity"] <= 1
    assert summary["missingnessDeltaPercentage"] >= 0
    assert len(detail["columns"]) == 5
    assert any(column["metric"] == "1 − Kolmogorov-Smirnov distance" for column in detail["columns"])
    assert any(column["metric"] == "1 − categorical total variation distance" for column in detail["columns"])
    assert detail["charts"]
    assert any("clinical validity" in item for item in detail["limitations"])

    listed = client.get(f"{API}/comparisons", headers=headers)
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [detail["id"]]
    assert "columns" not in listed.json()[0]

    fetched = client.get(f"{API}/comparisons/{detail['id']}", headers=headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == detail

    report = client.get(f"{API}/comparisons/{detail['id']}/report/download", headers=headers)
    assert report.status_code == 200, report.text
    assert report.json()["summary"] == summary

    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "synthmed.comparison_created", AuditLog.resource_id == detail["id"])
    )
    assert audit is not None


def test_comparison_rejects_unrelated_datasets_and_enforces_ownership(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    owner_headers = register_and_login(client, "comparison-owner-2@example.test")
    source_id = upload_source(client, owner_headers, "Original cohort")
    generated_id = generate(client, owner_headers, source_id, "Synthetic cohort")
    other_source_id = upload_source(client, owner_headers, "Unrelated cohort", ALTERNATE_CSV)

    mismatch = client.post(
        f"{API}/comparisons",
        headers=owner_headers,
        json={
            "sourceDatasetId": other_source_id,
            "generatedDatasetId": generated_id,
            "name": "Invalid comparison",
        },
    )
    assert mismatch.status_code == 422, mismatch.text
    assert "not generated from" in mismatch.json()["detail"]

    comparison = create_comparison(client, owner_headers, source_id, generated_id)

    other_headers = register_and_login(client, "comparison-other@example.test")
    forbidden_detail = client.get(f"{API}/comparisons/{comparison['id']}", headers=other_headers)
    assert forbidden_detail.status_code == 403, forbidden_detail.text
    forbidden_report = client.get(f"{API}/comparisons/{comparison['id']}/report/download", headers=other_headers)
    assert forbidden_report.status_code == 403, forbidden_report.text

    missing = client.get(f"{API}/comparisons/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert missing.status_code == 404, missing.text
