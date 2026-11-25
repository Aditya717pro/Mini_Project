from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    AccessClassification,
    Dataset,
    DatasetStatus,
    DatasetVersion,
    ETLJob,
    FileFormat,
    JobStatus,
    ResearchReport,
    SynthMedComparison,
    SynthMedDatasetVersion,
    SynthMedEvaluationReport,
    SynthMedExperiment,
    SynthMedGeneratedDataset,
    SynthMedGenerationJob,
    SynthMedSourceDataset,
    SynthMedUtilityEvaluation,
    User,
    UserRole,
)
from app.research_reports.sanitize import NOT_AVAILABLE, clean_number, clean_text, safe_column_name
from app.research_reports.service import to_response
from app.schemas.research_reports import ResearchReportResponse
from app.services.storage_paths import relative_path
from app.services.storage_service import StorageService
from app.synthmed.services.generation_service import _build_source_preservation_report
from app.synthmed.services.storage_service import SynthMedStorageService

SOURCE_DATASET_ID = "11111111-1111-4111-8111-111111111111"
GENERATED_DATASET_ID = "22222222-2222-4222-8222-222222222222"
COMPARISON_ID = "33333333-3333-4333-8333-333333333333"


def _fictional_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "subject_id": [f"PRIVATE-SUBJECT-ZZ-{index:04d}" for index in range(30)],
            "Age": [20 + index % 40 for index in range(30)],
            "Outcome": ["Fictional A" if index % 2 else "Fictional B" for index in range(30)],
            "Score": [round(10 + index * 0.25, 2) for index in range(30)],
        }
    )


def _user(db: Session, email: str) -> User:
    user = User(
        email=email,
        full_name="Fictional Researcher",
        hashed_password=hash_password("correct-horse-1"),
        role=UserRole.RESEARCHER,
        organisation="Fictional Test Organisation",
        title="Researcher",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-1"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed(db: Session, app: Any) -> dict[str, str]:
    settings = app.state.settings
    owner = _user(db, "reports-owner@example.test")
    frame = _fictional_frame()
    content = frame.to_csv(index=False).encode("utf-8")

    storage = StorageService(settings)
    raw_path = storage.save_raw("core-dataset", "v1", "fictional.csv", content)
    raw_relative = relative_path(settings.raw_storage_dir, raw_path)

    dataset = Dataset(
        id="core-dataset",
        owner_id=owner.id,
        title="Fictional Report Dataset",
        description="Fictional test dataset",
        domain="Maternal health",
        access_classification=AccessClassification.CONTROLLED,
        status=DatasetStatus.AVAILABLE,
        format=FileFormat.CSV,
        original_filename="fictional.csv",
        original_path=raw_relative,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        file_size_bytes=len(content),
        record_count=len(frame),
        column_count=len(frame.columns),
        research_task="Method development",
    )
    version = DatasetVersion(
        id="core-version",
        dataset_id=dataset.id,
        version_number=1,
        version_label="v1",
        raw_file_path=raw_relative,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        file_size_bytes=len(content),
        record_count=len(frame),
        column_count=len(frame.columns),
        profile_json={"before": {"records": len(frame)}, "after": {"records": len(frame)}},
        transformation_log_json={
            "logs": [{"action": "rename_column", "column": "score", "message": "Fictional rename"}],
            "unit_conversions": [],
        },
        is_current=True,
    )
    etl_job = ETLJob(
        id="etl-job",
        dataset_id=dataset.id,
        dataset_version_id=version.id,
        initiated_by_id=owner.id,
        status=JobStatus.COMPLETED,
        current_stage="load",
        progress=100,
        rows_in=len(frame),
        rows_out=len(frame),
        profile_json={"before": {"records": len(frame)}, "after": {"records": len(frame)}},
    )
    db.add_all([dataset, version, etl_job])

    synth_storage = SynthMedStorageService(settings)
    _, source_rel = synth_storage.save_source(SOURCE_DATASET_ID, "fictional.csv", content)
    _, generated_rel = synth_storage.save_generated(GENERATED_DATASET_ID, "synthetic.csv", content)
    source = SynthMedSourceDataset(
        id=SOURCE_DATASET_ID,
        owner_id=owner.id,
        dataset_name="Fictional source",
        description="Fictional source for reports",
        original_filename="fictional.csv",
        stored_path=source_rel,
        file_format="CSV",
        file_size_bytes=len(content),
        checksum_sha256="source-checksum",
        row_count=len(frame),
        column_count=len(frame.columns),
    )
    generated = SynthMedGeneratedDataset(
        id=GENERATED_DATASET_ID,
        owner_id=owner.id,
        source_dataset_id=source.id,
        dataset_name="Fictional synthetic",
        source_dataset_name=source.dataset_name,
        generation_method="Fictional generator",
        generation_mode="Unconditional",
        selected_model="FictionalModel",
        record_count=len(frame),
        column_count=len(frame.columns),
        file_format="CSV",
        file_size_bytes=len(content),
        checksum_sha256="generated-checksum",
        stored_path=generated_rel,
        status="Completed",
    )
    job = SynthMedGenerationJob(
        id="generation-job",
        owner_id=owner.id,
        source_dataset_id=source.id,
        generated_dataset_id=generated.id,
        status="Completed",
        model_name="FictionalModel",
        generation_mode="Unconditional",
        selected_model="FictionalModel",
        epochs=3,
        batch_size=10,
        seed=42,
        requested_record_count=len(frame),
        generated_record_count=len(frame),
        training_duration_seconds=1.5,
        config_json={"epochs": 3, "batchSize": 10, "libraryVersion": "fictional-1.0"},
    )
    privacy = SynthMedEvaluationReport(
        id="privacy-evaluation",
        job_id=job.id,
        generated_dataset_id=generated.id,
        owner_id=owner.id,
        report_type="privacy",
        method="Fictional heuristic screening",
        score=0.91,
        report_json={
            "method": "Fictional heuristic screening",
            "exactOverlapRecords": 0,
            "exactOverlapPercentage": 0.0,
            "syntheticDuplicateRecords": 0,
            "realDuplicateRecords": 0,
            "nearestNeighbourDistance": {
                "minimum": 0.4,
                "median": 0.8,
                "p90": 0.95,
                "threshold": 0.05,
                "suspiciousRecords": 0,
            },
            "newRowSynthesisScore": 0.97,
            "warnings": ["Synthetic medical data is not automatically anonymous."],
            "limitations": ["Fictional limitation for testing."],
        },
    )
    utility = SynthMedUtilityEvaluation(
        id="utility-evaluation",
        owner_id=owner.id,
        source_dataset_id=source.id,
        generated_dataset_id=generated.id,
        status="Completed",
        evaluation_name="Fictional utility",
        evaluation_type="BOTH",
        model_name="FictionalClassifier",
        target_column="Outcome",
        feature_columns_json=["Age", "Score"],
        train_test_split={"testSize": 0.2, "randomSeed": 42},
        metrics_json={
            "taskType": "classification",
            "tstr": {
                "metrics": {"accuracy": 0.81, "f1Macro": 0.79},
                "trainSource": "synthetic",
                "trainRecords": 24,
                "testRecords": 6,
            },
            "trtr": {
                "metrics": {"accuracy": 0.88, "f1Macro": 0.86},
                "trainSource": "real",
                "trainRecords": 24,
                "testRecords": 6,
            },
        },
        comparison_summary_json={
            "gap": {"accuracy": -0.07, "f1Macro": -0.07},
            "interpretation": "Fictional utility gap.",
        },
        warnings_json=[],
    )
    comparison = SynthMedComparison(
        id=COMPARISON_ID,
        owner_id=owner.id,
        source_dataset_id=source.id,
        generated_dataset_id=generated.id,
        name="Fictional comparison",
        method="Fictional distribution comparison",
        report_json={
            "method": "Fictional distribution comparison",
            "summary": {"sourceRows": 30, "syntheticRows": 30, "rowDifference": 0, "comparedColumns": 2},
            "columns": [
                {
                    "name": "Score",
                    "metric": "Fictional distance",
                    "similarity": 0.93,
                    "sourceMissingPercentage": 0,
                    "syntheticMissingPercentage": 0,
                    "sourceUniqueCount": 30,
                    "syntheticUniqueCount": 30,
                }
            ],
            "charts": [{"column": "Score", "points": [{"bucket": "10-20", "original": 5, "synthetic": 6}]}],
            "limitations": ["Fictional comparison limitation."],
        },
    )
    source_version = SynthMedDatasetVersion(
        id="source-version",
        owner_id=owner.id,
        dataset_kind="source",
        logical_dataset_id=source.id,
        version_number=1,
        version_label="v1",
        is_active=True,
        dataset_name=source.dataset_name,
        file_format="CSV",
        stored_path=source_rel,
        checksum_sha256=source.checksum_sha256,
        record_count=len(frame),
        column_count=len(frame.columns),
    )
    experiment = SynthMedExperiment(
        id="experiment",
        owner_id=owner.id,
        name="Fictional experiment",
        description="Fictional experiment for report tests",
        status="Completed",
        source_dataset_id=source.id,
        source_version_id=source_version.id,
        generated_dataset_id=generated.id,
        generation_job_id=job.id,
        configuration_snapshot_id=None,
        comparison_id=comparison.id,
        utility_evaluation_id=utility.id,
    )
    db.add_all([source, generated, job, privacy, utility, comparison, source_version, experiment])
    db.commit()
    return {
        "datasetId": dataset.id,
        "datasetVersionId": version.id,
        "etlJobId": etl_job.id,
        "sourceDatasetId": source.id,
        "generatedDatasetId": generated.id,
        "generationJobId": job.id,
        "privacyEvaluationId": privacy.id,
        "utilityEvaluationId": utility.id,
        "comparisonId": comparison.id,
        "experimentId": experiment.id,
    }


@pytest.fixture()
def seeded(client: TestClient, db_session: Session, app: Any) -> dict[str, str]:
    del client
    return _seed(db_session, app)


_ENDPOINTS = [
    ("/api/v1/reports/dataset-profile", "datasetId", "datasetVersionId"),
    ("/api/v1/reports/etl", "datasetId", "etlJobId"),
    ("/api/v1/reports/synthmed/generation", "generationJobId", "generatedDatasetId"),
    ("/api/v1/reports/synthmed/comparison", "comparisonId", None),
    ("/api/v1/reports/synthmed/privacy", "privacyEvaluationId", "generatedDatasetId"),
    ("/api/v1/reports/synthmed/utility", "utilityEvaluationId", None),
    ("/api/v1/reports/synthmed/experiment", "experimentId", None),
]


def _payload(seeded: dict[str, str], primary: str, secondary: str | None) -> dict[str, str]:
    payload = {primary: seeded[primary]}
    if secondary:
        payload[secondary] = seeded[secondary]
    return payload


def test_all_report_types_generate_verifiable_pdfs(client: TestClient, seeded: dict[str, str]) -> None:
    headers = _login(client, "reports-owner@example.test")
    for endpoint, primary, secondary in _ENDPOINTS:
        response = client.post(endpoint, json=_payload(seeded, primary, secondary), headers=headers)
        assert response.status_code == 201, f"{endpoint}: {response.text}"
        body = response.json()
        assert body["status"] == "Completed"
        assert len(body["fileChecksum"]) == 64
        assert body["fileSize"] > 1000

        pdf = client.get(f"/api/v1/reports/{body['reportId']}/download", headers=headers)
        assert pdf.status_code == 200, f"{endpoint}: {pdf.text}"
        assert pdf.content.startswith(b"%PDF-")
        assert b"%%EOF" in pdf.content
        assert hashlib.sha256(pdf.content).hexdigest() == body["fileChecksum"]
        assert b"PRIVATE-SUBJECT-ZZ-9917" not in pdf.content
        assert b"patient_id" not in pdf.content


def test_privacy_report_marks_unimplemented_methods_not_evaluated(client: TestClient, seeded: dict[str, str]) -> None:
    headers = _login(client, "reports-owner@example.test")
    response = client.post(
        "/api/v1/reports/synthmed/privacy",
        json={"privacyEvaluationId": seeded["privacyEvaluationId"]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    report_id = response.json()["reportId"]
    pdf = client.get(f"/api/v1/reports/{report_id}/download", headers=headers).content
    assert b"NOT EVALUATED" in pdf
    assert b"Membership inference attack" in pdf
    assert b"Attribute disclosure attack" in pdf
    assert b"Differential privacy guarantee" in pdf
    assert b"Formal anonymity guarantee" in pdf
    assert b"differential privacy" in pdf
    assert b"not prove" in pdf


def test_report_history_counts_and_detail(client: TestClient, seeded: dict[str, str]) -> None:
    headers = _login(client, "reports-owner@example.test")
    created = client.post(
        "/api/v1/reports/dataset-profile",
        json={"datasetId": seeded["datasetId"], "datasetVersionId": seeded["datasetVersionId"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["reportId"]

    history = client.get("/api/v1/reports", headers=headers)
    assert history.status_code == 200
    body = history.json()
    assert body["total"] == 1
    assert body["counts"]["dataset-profile"] == 1

    detail = client.get(f"/api/v1/reports/{report_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["reportId"] == report_id

    status = client.get(f"/api/v1/reports/{report_id}/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["status"] == "Completed"


def test_report_ownership_and_validation(client: TestClient, db_session: Session, seeded: dict[str, str]) -> None:
    _user(db_session, "reports-other@example.test")
    owner_headers = _login(client, "reports-owner@example.test")
    other_headers = _login(client, "reports-other@example.test")

    created = client.post(
        "/api/v1/reports/dataset-profile",
        json={"datasetId": seeded["datasetId"], "datasetVersionId": seeded["datasetVersionId"]},
        headers=owner_headers,
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["reportId"]

    denied_detail = client.get(f"/api/v1/reports/{report_id}", headers=other_headers)
    assert denied_detail.status_code == 403
    denied_download = client.get(f"/api/v1/reports/{report_id}/download", headers=other_headers)
    assert denied_download.status_code == 403
    denied_create = client.post(
        "/api/v1/reports/synthmed/comparison",
        json={"comparisonId": seeded["comparisonId"]},
        headers=other_headers,
    )
    assert denied_create.status_code == 403

    missing = client.post("/api/v1/reports/synthmed/utility", json={}, headers=owner_headers)
    assert missing.status_code == 422
    assert "utilityEvaluationId" in missing.json()["detail"]


def test_checksum_mismatch_is_rejected(
    client: TestClient, db_session: Session, app: Any, seeded: dict[str, str]
) -> None:
    headers = _login(client, "reports-owner@example.test")
    created = client.post(
        "/api/v1/reports/dataset-profile",
        json={"datasetId": seeded["datasetId"], "datasetVersionId": seeded["datasetVersionId"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    row = db_session.query(ResearchReport).filter_by(report_id=created.json()["reportId"]).one()
    row.file_checksum = "0" * 64
    db_session.commit()

    download = client.get(f"/api/v1/reports/{row.report_id}/download", headers=headers)
    assert download.status_code == 409


def test_pdf_renderer_produces_multiple_pages_and_table_headers() -> None:
    from app.research_reports.pdf import render_report
    from app.research_reports.templates.common import build_payload, section, table

    rows = [[f"Column {index}", str(index), "Fictional value"] for index in range(60)]
    payload = build_payload(
        report_id="RR-TEST",
        report_type="dataset-profile",
        title="Pagination check",
        generated_at="2026-11-23T00:00:00+00:00",
        template_version="1.0",
        references=[],
        sections=[section("Dataset Structure", [table(["Column", "Value", "Note"], rows, title="Large table")])],
    )
    content = render_report(payload)
    assert content.startswith(b"%PDF-")
    assert b"%%EOF" in content
    assert content.count(b"/Type /Page ") > 2
    assert b"Page 2 of" in content


def test_queued_report_response_allows_missing_file_fields() -> None:
    row = ResearchReport(
        id="research-report-queued",
        report_id="RR-QUEUED",
        report_type="dataset-profile",
        title="Queued report",
        owner_id="owner",
        status="Queued",
        template_version="1.0",
    )
    response = ResearchReportResponse(**to_response(row))
    assert response.status == "Queued"
    assert response.fileChecksum is None
    assert response.fileSize is None


def test_sanitizer_redacts_identifiers_and_missing_values() -> None:
    value = clean_text(
        "Contact alice@example.test at +1 555 123 4567 "
        "using 123e4567-e89b-12d3-a456-426614174000 or MRN 123456"
    )
    assert "alice@example.test" not in value
    assert "+1 555 123 4567" not in value
    assert "123e4567-e89b-12d3-a456-426614174000" not in value
    assert "MRN 123456" not in value
    assert value.count("[REDACTED]") >= 4
    assert clean_text(None) == NOT_AVAILABLE
    assert clean_number(float("nan")) == NOT_AVAILABLE
    assert safe_column_name("patient_id") == "[REDACTED]"


def test_source_preservation_report_uses_persisted_rejection_counters() -> None:
    frame = pd.DataFrame({"Age": [30, 40], "Outcome": ["A", "B"]})
    report = _build_source_preservation_report(
        source=frame,
        synthetic=frame,
        config={},
        plan={"enabled": True, "ageColumn": "Age", "ageToleranceYears": 2, "ageBounds": {"min": 30, "max": 40}},
        anchor_meta={"ageDeviations": [0, 1]},
        validation={},
        rejection_report={"attempts": 3, "acceptedRecords": 2, "rejectedRecords": 1},
    )
    assert report["rejectedRecordCount"] == 1
    assert report["regenerationAttempts"] == 3
    assert report["acceptedBatchCount"] == 2
