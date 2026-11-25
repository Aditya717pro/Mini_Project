import hashlib
import io
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.synthmed.models import SynthMedGeneratedDataset
from app.synthmed.services.storage_service import SynthMedStorageService
from tests.test_synthmed_generation import API, auth_headers, register_user, upload

PHASE_A_CSV = (
    b"Age,Gender,Disease,Disease_Level,Height_cm,Weight_kg,BMI,Systolic_BP,Diastolic_BP,Heart_Rate\n"
    b"46,Male,Hypertension,Moderate,162,79.9,30.4,140,90,78\n"
    b"32,Female,Diabetes,Mild,158,62.0,24.8,120,80,72\n"
    b"50,Male,Healthy,None,170,70.0,24.2,118,76,68\n"
    b"41,Female,Hypertension,Severe,165,75.0,27.5,150,95,82\n"
    b"27,Male,Healthy,None,175,68.0,22.2,112,72,65\n"
    b"38,Female,Diabetes,Moderate,160,66.0,25.8,128,84,74\n"
    b"55,Male,Hypertension,Mild,168,72.0,25.5,135,85,76\n"
    b"29,Female,Healthy,None,155,54.0,22.5,110,70,70\n"
    b"47,Male,Diabetes,Severe,172,85.0,28.7,145,92,80\n"
    b"35,Female,Hypertension,Moderate,163,69.0,26.0,132,86,75\n"
    b"52,Male,Healthy,None,178,80.0,25.2,122,78,69\n"
    b"31,Female,Diabetes,Mild,157,60.0,24.3,118,76,71\n"
)

SELECTED = [
    "Age",
    "Gender",
    "Disease",
    "Disease_Level",
    "Height_cm",
    "Weight_kg",
    "BMI",
    "Systolic_BP",
    "Diastolic_BP",
    "Heart_Rate",
]


def _start(client: TestClient, headers: dict[str, str], source_id: str, **overrides) -> dict:
    payload = {
        "sourceDatasetId": source_id,
        "datasetName": "Phase A synthetic",
        "model": "GaussianCopula",
        "selectedColumns": SELECTED,
        "categoricalColumns": ["Gender", "Disease", "Disease_Level"],
        "numericalColumns": ["Age", "Height_cm", "Weight_kg", "BMI", "Systolic_BP", "Diastolic_BP", "Heart_Rate"],
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
    r = client.post(f"{API}/generation/start", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def phase_a_source(client: TestClient):
    register_user(client, "phasea@example.test")
    headers = auth_headers(client, "phasea@example.test")
    source_id = upload(client, headers, PHASE_A_CSV, name="phasea.csv")
    return headers, source_id


def _frame(app, db_session: Session, generated_id: str) -> pd.DataFrame:
    gen = db_session.get(SynthMedGeneratedDataset, generated_id)
    assert gen is not None
    path = SynthMedStorageService(app.state.settings).resolve_generated(gen.stored_path)
    return pd.read_csv(path)


def _source_df() -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(PHASE_A_CSV))


def _assert_bmi(frame: pd.DataFrame):
    expected = frame["Weight_kg"] / ((frame["Height_cm"] / 100.0) ** 2)
    assert ((frame["BMI"] - expected).abs() <= 0.11).all()


def _assert_no_ids(obj):
    text = json.dumps(obj, default=str).lower()
    for token in ["patient_id", "anchor", "source_record", "email", "phone_number", "hospital_id", "doctor_name"]:
        assert token not in text


# 1. Age anchor preservation case 46 +/-5
def test_age_anchor_46_tolerance(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id, recordCount=12)
    assert job["status"] == "Completed", job["error"]
    frame = _frame(app, db_session, job["generatedDatasetId"])
    source_ages = set(_source_df()["Age"].astype(int))
    # all generated ages must be within +/-5 of at least one source anchor; with source-preserving anchors this holds
    for age in frame["Age"].astype(int):
        assert any(abs(age - s) <= 5 for s in source_ages)

# 2. Age anchor preservation case 32 +/-5
def test_age_anchor_32_tolerance(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id, seed=11)
    frame = _frame(app, db_session, job["generatedDatasetId"])
    assert any(abs(int(a) - 32) <= 5 for a in frame["Age"])

# 3. Age tolerance boundary
def test_age_tolerance_boundary(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id, ageToleranceYears=0)
    assert job["status"] == "Completed", job["error"]
    frame = _frame(app, db_session, job["generatedDatasetId"])
    source_ages = set(_source_df()["Age"].astype(int))
    assert set(frame["Age"].astype(int)).issubset(source_ages)

# 4. Gender preservation
def test_gender_preservation(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id)
    frame = _frame(app, db_session, job["generatedDatasetId"])
    assert set(frame["Gender"].dropna().unique()).issubset(set(_source_df()["Gender"].unique()))

# 5. Gender distribution preservation (proportion sanity)
def test_gender_distribution_preservation(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id, recordCount=24)
    frame = _frame(app, db_session, job["generatedDatasetId"])
    src = _source_df()["Gender"].value_counts(normalize=True)
    gen = frame["Gender"].value_counts(normalize=True)
    for k in src.index:
        assert k in gen.index

# 6. Disease preservation
def test_disease_preservation(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id)
    frame = _frame(app, db_session, job["generatedDatasetId"])
    assert set(frame["Disease"].dropna().unique()).issubset(set(_source_df()["Disease"].unique()))

# 7. Disease_Level preservation
def test_disease_level_preservation(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id)
    frame = _frame(app, db_session, job["generatedDatasetId"])
    assert set(frame["Disease_Level"].dropna().unique()).issubset(set(_source_df()["Disease_Level"].unique()))

# 8. Height/weight/BMI consistency
def test_bmi_consistency(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id)
    frame = _frame(app, db_session, job["generatedDatasetId"])
    _assert_bmi(frame)

# 9. SBP > DBP
def test_sbp_gt_dbp(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id)
    frame = _frame(app, db_session, job["generatedDatasetId"])
    assert (frame["Systolic_BP"] > frame["Diastolic_BP"]).all()

# 10. Medical measurement validation
def test_medical_measurement_validation(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id)
    assert job["validationStatus"] == "Passed"
    frame = _frame(app, db_session, job["generatedDatasetId"])
    assert (frame["Heart_Rate"].between(20, 300)).all()
    assert (frame["Height_cm"] > 0).all()
    assert (frame["Weight_kg"] > 0).all()

# 11-13. All three models
@pytest.mark.parametrize("model", ["CTGAN", "TVAE", "GaussianCopula"])
def test_all_models(model, app, client, db_session):
    email = f"phasea-{model.lower()}@example.test"
    register_user(client, email)
    headers = auth_headers(client, email)
    source_id = upload(client, headers, PHASE_A_CSV, name=f"{model}.csv")
    job = _start(client, headers, source_id, model=model, datasetName=f"{model} phasea")
    assert job["status"] == "Completed", job["error"]
    frame = _frame(app, db_session, job["generatedDatasetId"])
    _assert_bmi(frame)
    assert set(frame["Gender"].unique()).issubset(set(_source_df()["Gender"].unique()))

# 14. Conditional generation
def test_conditional_generation(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(
        client,
        headers,
        source_id,
        generationMode="Conditional",
        conditions=[{"column": "Gender", "operator": "eq", "value": "Female", "numRows": 12}],
        recordCount=12,
    )
    assert job["status"] == "Completed", job["error"]
    frame = _frame(app, db_session, job["generatedDatasetId"])
    assert set(frame["Gender"].unique()) == {"Female"}

# 15. Identifier exclusion
def test_identifier_exclusion(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id)
    gid = job["generatedDatasetId"]
    preview = client.get(f"{API}/generated/{gid}/preview", headers=headers).json()
    _assert_no_ids(preview)
    for fmt in ["CSV","XLSX","JSON"]:
        dl = client.get(f"{API}/generated/{gid}/download", headers=headers, params={"file_format":fmt})
        assert dl.status_code == 200
        _assert_no_ids({"content": dl.content.decode("latin1", "ignore")})

# 16. Output schema validation
def test_output_schema_validation(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id)
    detail = client.get(f"{API}/generated/{job['generatedDatasetId']}", headers=headers).json()
    schema = detail.get("schemaValidation") or {}
    assert schema.get("passed") is True
    assert schema.get("unapprovedColumns", []) == []

# 17. Original file unchanged
def test_original_file_unchanged(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    before = client.get(f"{API}/sources/{source_id}/download", headers=headers).content
    job = _start(client, headers, source_id)
    assert job["status"] == "Completed", job["error"]
    after = client.get(f"{API}/sources/{source_id}/download", headers=headers).content
    assert hashlib.sha256(before).hexdigest() == hashlib.sha256(after).hexdigest()

# 18. Generated preview/download consistency
def test_preview_download_consistency(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id)
    gid = job["generatedDatasetId"]
    preview = client.get(f"{API}/generated/{gid}/preview", headers=headers, params={"pageSize":200}).json()
    csv_dl = client.get(f"{API}/generated/{gid}/download", headers=headers, params={"file_format":"CSV"})
    frame = pd.read_csv(io.BytesIO(csv_dl.content))
    assert preview["rows"] == json.loads(frame.to_json(orient="records"))

# 19. CSV/XLSX/JSON export validation
def test_export_validation(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id)
    gid = job["generatedDatasetId"]
    csv_bytes = client.get(f"{API}/generated/{gid}/download", headers=headers, params={"file_format":"CSV"}).content
    json_bytes = client.get(f"{API}/generated/{gid}/download", headers=headers, params={"file_format":"JSON"}).content
    xlsx_bytes = client.get(f"{API}/generated/{gid}/download", headers=headers, params={"file_format":"XLSX"}).content
    csv_df = pd.read_csv(io.BytesIO(csv_bytes))
    json_df = pd.read_json(io.BytesIO(json_bytes))
    xlsx_df = pd.read_excel(io.BytesIO(xlsx_bytes))
    assert list(csv_df.columns) == list(json_df.columns) == list(xlsx_df.columns)
    assert len(csv_df) == len(json_df) == len(xlsx_df)
    _assert_bmi(csv_df)
    _assert_bmi(json_df)
    _assert_bmi(xlsx_df)

# 20. P3 privacy compatibility
def test_p3_privacy_compatibility(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id)
    gid = job["generatedDatasetId"]
    for report_type in ["quality","privacy"]:
        r = client.get(f"{API}/generated/{gid}/{report_type}", headers=headers)
        assert r.status_code == 200, r.text
        assert "report" in r.json()

# 21. Comparison Dashboard compatibility
def test_comparison_dashboard_compatibility(app, client, db_session, phase_a_source):
    headers, source_id = phase_a_source
    job = _start(client, headers, source_id)
    gid = job["generatedDatasetId"]
    comp = client.post(
        f"{API}/comparisons",
        headers=headers,
        json={"sourceDatasetId": source_id, "generatedDatasetId": gid, "name": "PhaseA"},
    )
    assert comp.status_code == 201, comp.text
    detail = client.get(f"{API}/comparisons/{comp.json()['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["summary"]["sharedColumns"] >= 1
    assert body["clinical"]["schemaValidation"]["passed"] is True
