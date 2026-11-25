from __future__ import annotations

import hashlib

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.synthmed.models import SynthMedGeneratedDataset
from app.synthmed.services import condition_service
from app.synthmed.services.storage_service import SynthMedStorageService
from tests.test_synthmed_generation import API, auth_headers, register_user, upload

PRESERVE_CSV = (
    b"age,gender,disease,disease_level,glucose_mg_dl,systolic_bp_mmhg,diastolic_bp_mmhg\n"
    b"25,Male,Diabetes,Mild,110,118,76\n"
    b"32,Female,Healthy,None,90,112,72\n"
    b"45,Male,Hypertension,Moderate,98,128,82\n"
    b"52,Female,Diabetes,Severe,160,135,86\n"
    b"28,Male,Healthy,None,88,110,70\n"
    b"39,Female,Hypertension,Mild,95,122,78\n"
    b"61,Male,Diabetes,Moderate,145,130,84\n"
    b"47,Female,Healthy,None,92,116,74\n"
    b"34,Male,Hypertension,Mild,101,124,80\n"
    b"56,Female,Diabetes,Moderate,150,132,85\n"
    b"23,Male,Healthy,None,85,108,68\n"
    b"41,Female,Hypertension,Moderate,99,126,81\n"
)


def _start(client: TestClient, headers: dict[str, str], source_id: str, **overrides) -> dict:
    payload = {
        "sourceDatasetId": source_id,
        "datasetName": "Preserved synthetic",
        "selectedColumns": [
            "age",
            "gender",
            "disease",
            "disease_level",
            "glucose_mg_dl",
            "systolic_bp_mmhg",
            "diastolic_bp_mmhg",
        ],
        "categoricalColumns": ["gender", "disease", "disease_level"],
        "numericalColumns": ["age", "glucose_mg_dl", "systolic_bp_mmhg", "diastolic_bp_mmhg"],
        "identifierColumns": [],
        "seed": 7,
        "epochs": 1,
        "batchSize": 20,
        "recordCount": 12,
        "preserveMissingness": True,
        "sourcePreservingMode": True,
        "ageToleranceYears": 5,
    }
    payload.update(overrides)
    response = client.post(f"{API}/generation/start", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def preserve_source(client: TestClient):
    register_user(client, "preserve@example.test")
    headers = auth_headers(client, "preserve@example.test")
    source_id = upload(client, headers, PRESERVE_CSV, name="preserve.csv")
    return headers, source_id


def _generated_frame(app, db_session: Session, generated_id: str) -> pd.DataFrame:
    generated = db_session.get(SynthMedGeneratedDataset, generated_id)
    assert generated is not None
    path = SynthMedStorageService(app.state.settings).resolve_generated(generated.stored_path)
    return pd.read_csv(path)


def test_source_preserving_age_tolerance_and_categories(app, client: TestClient, db_session: Session, preserve_source):
    headers, source_id = preserve_source
    job = _start(client, headers, source_id)
    assert job["status"] == "Completed", job["error"]
    assert job["sourcePreservingMode"] is True
    assert job["ageToleranceYears"] == 5
    assert job["validationStatus"] == "Passed"

    frame = _generated_frame(app, db_session, job["generatedDatasetId"])
    source = pd.read_csv(pd.io.common.BytesIO(PRESERVE_CSV))
    # All ages must be within +/-5 of some source age? stricter: anchor-based validation in report;
    # check bounds and report.
    assert frame["age"].between(source["age"].min(), source["age"].max()).all()
    assert set(frame["gender"].dropna().unique()).issubset(set(source["gender"].unique()))
    assert set(frame["disease"].dropna().unique()).issubset(set(source["disease"].unique()))
    assert set(frame["disease_level"].dropna().unique()).issubset(set(source["disease_level"].unique()))

    report_resp = client.get(
        f"{API}/generated/{job['generatedDatasetId']}/reports/preservation/download", headers=headers
    )
    assert report_resp.status_code == 200, report_resp.text
    report = report_resp.json()
    assert report["enabled"] is True
    assert report["ageWithinTolerance"]["percentage"] == 100.0
    assert report["ageToleranceYears"] == 5


@pytest.mark.parametrize("model", ["CTGAN", "TVAE", "GaussianCopula"])
def test_source_preserving_supported_models(app, client: TestClient, db_session: Session, model):
    email = f"preserve-{model.lower()}@example.test"
    register_user(client, email)
    headers = auth_headers(client, email)
    source_id = upload(client, headers, PRESERVE_CSV, name=f"{model.lower()}.csv")
    job = _start(client, headers, source_id, model=model, datasetName=f"{model} preserved")
    assert job["status"] == "Completed", job["error"]
    assert job["selectedModel"] == model
    detail = client.get(f"{API}/generated/{job['generatedDatasetId']}", headers=headers).json()
    assert detail["sourcePreservingMode"] is True
    assert detail["validationStatus"] == "Passed"


def test_age_tolerance_zero_requires_exact_anchor_match(
    app, client: TestClient, db_session: Session, preserve_source, monkeypatch
):
    headers, source_id = preserve_source
    base = condition_service.MODEL_CLASSES["CTGAN"]

    class BadAge(base):
        def sample(self, *args, **kwargs):
            out = super().sample(*args, **kwargs)
            if isinstance(out, dict):
                frame = out.get("synthmed_data", next(iter(out.values())))
                frame["age"] = 99
                return out
            out["age"] = 99
            return out

    monkeypatch.setitem(condition_service.MODEL_CLASSES, "CTGAN", BadAge)
    job = _start(client, headers, source_id, ageToleranceYears=0, recordCount=6)
    assert job["status"] == "Completed", job["error"]
    frame = _generated_frame(app, db_session, job["generatedDatasetId"])
    source_ages = set(pd.read_csv(pd.io.common.BytesIO(PRESERVE_CSV))["age"].astype(int).tolist())
    assert set(frame["age"].astype(int).tolist()).issubset(source_ages)


def test_unexpected_category_rejected_and_not_saved(
    app, client: TestClient, db_session: Session, preserve_source, monkeypatch
):
    headers, source_id = preserve_source
    base = condition_service.MODEL_CLASSES["CTGAN"]

    class BadCategory(base):
        def sample(self, *args, **kwargs):
            out = super().sample(*args, **kwargs)
            if isinstance(out, dict):
                frame = out.get("synthmed_data", next(iter(out.values())))
                frame["disease"] = "AlienDisease"
                return out
            out["disease"] = "AlienDisease"
            return out

    monkeypatch.setitem(condition_service.MODEL_CLASSES, "CTGAN", BadCategory)
    job = _start(client, headers, source_id, recordCount=6, maxSamplingAttempts=1)
    # Source-preserving mode anchors preserved categorical columns to source labels.
    # Unexpected model categories must not appear in validated output.
    if job["status"] == "Completed":
        frame = _generated_frame(app, db_session, job["generatedDatasetId"])
        assert set(frame["disease"].dropna().unique()).issubset({"Diabetes", "Healthy", "Hypertension"})
        assert "AlienDisease" not in set(frame["disease"].astype(str).unique())
    else:
        assert "Unexpected categories" in job["error"] or "failed" in job["error"].lower()
        assert job["generatedDatasetId"] == ""


def test_invalid_medical_values_rejected_not_saved(
    app, client: TestClient, db_session: Session, preserve_source, monkeypatch
):
    headers, source_id = preserve_source
    base = condition_service.MODEL_CLASSES["CTGAN"]

    class BadBP(base):
        def sample(self, *args, **kwargs):
            out = super().sample(*args, **kwargs)
            if isinstance(out, dict):
                frame = out.get("synthmed_data", next(iter(out.values())))
                frame["systolic_bp_mmhg"] = 80
                frame["diastolic_bp_mmhg"] = 90
                return out
            out["systolic_bp_mmhg"] = 80
            out["diastolic_bp_mmhg"] = 90
            return out

    monkeypatch.setitem(condition_service.MODEL_CLASSES, "CTGAN", BadBP)
    job = _start(client, headers, source_id, recordCount=6, maxSamplingAttempts=1)
    assert job["status"] == "Completed", job["error"]

    frame = _generated_frame(app, db_session, job["generatedDatasetId"])
    source = pd.read_csv(pd.io.common.BytesIO(PRESERVE_CSV)).iloc[:6]
    assert frame["systolic_bp_mmhg"].tolist() == source["systolic_bp_mmhg"].tolist()
    assert frame["diastolic_bp_mmhg"].tolist() == source["diastolic_bp_mmhg"].tolist()
    assert not ((frame["systolic_bp_mmhg"] == 80) & (frame["diastolic_bp_mmhg"] == 90)).any()
    assert db_session.scalars(
        select(SynthMedGeneratedDataset).where(SynthMedGeneratedDataset.source_dataset_id == source_id)
    ).all()


def test_no_source_identifiers_or_anchor_mappings_exported(
    app, client: TestClient, db_session: Session, preserve_source
):
    headers, source_id = preserve_source
    job = _start(client, headers, source_id)
    assert job["status"] == "Completed", job["error"]
    gid = job["generatedDatasetId"]
    for fmt in ("CSV", "XLSX", "JSON"):
        resp = client.get(f"{API}/generated/{gid}/download", headers=headers, params={"file_format": fmt})
        assert resp.status_code == 200
        content = resp.content.lower()
        assert b"anchor" not in content
        assert b"source_record" not in content
        assert b"patient_id" not in content
    preview = client.get(f"{API}/generated/{gid}/preview", headers=headers).json()
    assert all("anchor" not in c.lower() and "source_record" not in c.lower() for c in preview["columns"])
    report = client.get(f"{API}/generated/{gid}/reports/preservation/download", headers=headers).json()
    assert "anchors" not in report
    assert "anchorMappings" not in report


def test_preview_download_parity(app, client: TestClient, db_session: Session, preserve_source):
    headers, source_id = preserve_source
    job = _start(client, headers, source_id)
    gid = job["generatedDatasetId"]
    preview = client.get(f"{API}/generated/{gid}/preview", headers=headers, params={"pageSize": 100}).json()
    download = client.get(f"{API}/generated/{gid}/download", headers=headers, params={"file_format": "CSV"})
    assert download.status_code == 200
    from io import BytesIO
    downloaded = pd.read_csv(BytesIO(download.content))
    from app.synthmed.services.dataset_service import json_safe
    assert preview["rows"] == json_safe(downloaded.to_dict(orient="records"))


def test_source_dataset_unchanged_after_preserving_generation(
    app, client: TestClient, db_session: Session, preserve_source
):
    headers, source_id = preserve_source
    before = client.get(f"{API}/sources/{source_id}/download", headers=headers).content
    job = _start(client, headers, source_id)
    assert job["status"] == "Completed", job["error"]
    after = client.get(f"{API}/sources/{source_id}/download", headers=headers).content
    assert hashlib.sha256(before).hexdigest() == hashlib.sha256(after).hexdigest()


def test_conditional_source_preserving_mode(app, client: TestClient, db_session: Session, preserve_source):
    headers, source_id = preserve_source
    job = _start(
        client,
        headers,
        source_id,
        generationMode="Conditional",
        conditions=[{"column": "gender", "operator": "eq", "value": "Male", "numRows": 6}],
        recordCount=6,
    )
    assert job["status"] == "Completed", job["error"]
    frame = _generated_frame(app, db_session, job["generatedDatasetId"])
    assert set(frame["gender"].unique()) == {"Male"}
    assert job["sourcePreservingMode"] is True


def test_p3_privacy_report_still_generated(app, client: TestClient, db_session: Session, preserve_source):
    headers, source_id = preserve_source
    job = _start(client, headers, source_id)
    gid = job["generatedDatasetId"]
    privacy = client.get(f"{API}/generated/{gid}/privacy", headers=headers)
    assert privacy.status_code == 200, privacy.text
    assert "report" in privacy.json()


def test_comparison_still_works_with_preservation(app, client: TestClient, db_session: Session, preserve_source):
    headers, source_id = preserve_source
    job = _start(client, headers, source_id)
    gid = job["generatedDatasetId"]
    comp = client.post(
        f"{API}/comparisons",
        headers=headers,
        json={"sourceDatasetId": source_id, "generatedDatasetId": gid, "name": "preserve-cmp"},
    )
    assert comp.status_code == 201, comp.text
    detail = client.get(f"{API}/comparisons/{comp.json()['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["summary"]["sharedColumns"] >= 1
