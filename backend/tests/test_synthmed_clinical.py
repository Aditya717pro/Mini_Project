from __future__ import annotations

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.synthmed.services import clinical_reference_service, medical_schema_service
from tests.test_synthmed_comparison import create_comparison
from tests.test_synthmed_generation import FICTIONAL_CSV, auth_headers, register_user, upload

API = "/api/v1/synthmed"

CLINICAL_CSV = (
    b"Age,Gender,Disease,Disease_Level,Systolic_BP,Diastolic_BP,Blood_Glucose,Glucose_Context\n"
    b"30,Female,Stable,Mild,112,72,86,fasting\n"
    b"34,Male,Stable,Mild,118,76,91,fasting\n"
    b"41,Female,Review,Moderate,116,74,88,fasting\n"
    b"45,Male,Review,Moderate,113,71,94,fasting\n"
    b"52,Female,Acute,Severe,119,78,97,fasting\n"
    b"38,Male,Stable,Mild,110,70,83,fasting\n"
    b"29,Female,Stable,Mild,114,73,89,fasting\n"
    b"36,Male,Review,Moderate,117,75,92,fasting\n"
    b"48,Female,Acute,Severe,115,74,95,fasting\n"
    b"33,Male,Stable,Mild,111,69,84,fasting\n"
    b"43,Female,Review,Moderate,116,77,93,fasting\n"
    b"27,Male,Stable,Mild,109,68,82,fasting\n"
)

APPROVED = [
    "Age",
    "Gender",
    "Disease",
    "Disease_Level",
    "Systolic_BP",
    "Diastolic_BP",
    "Blood_Glucose",
]

CLINICAL_VARIABLES = [
    {
        "column": "Systolic_BP",
        "measurement": "Systolic_BP",
        "unit": "mmHg",
        "context": "resting",
        "ageColumn": "Age",
        "sexColumn": "Gender",
    },
    {
        "column": "Diastolic_BP",
        "measurement": "Diastolic_BP",
        "unit": "mmHg",
        "context": "resting",
        "ageColumn": "Age",
        "sexColumn": "Gender",
    },
    {
        "column": "Blood_Glucose",
        "measurement": "Blood_Glucose",
        "unit": "mg/dL",
        "context": "fasting",
        "ageColumn": "Age",
        "sexColumn": "Gender",
    },
]


def _source(client: TestClient, email: str, content: bytes = FICTIONAL_CSV) -> tuple[str, dict[str, str]]:
    register_user(client, email)
    headers = auth_headers(client, email)
    return upload(client, headers, content), headers


def test_medical_schema_profiling_detects_identifiers_units_and_unknown_columns() -> None:
    frame = pd.DataFrame(
        {
            "patient_id": [f"P{i:03d}" for i in range(8)],
            "Age": [30, 40, 35, 42, 28, 33, 47, 39],
            "Gender": ["Female", "Male", "Female", "Male", "Female", "Male", "Female", "Male"],
            "diagnosis": ["Stable", "Review", "Stable", "Review", "Stable", "Review", "Stable", "Review"],
            "Systolic_BP_mmHg": [120, 118, 115, 122, 119, 117, 121, 116],
            "smoker": [True, False, True, False, True, False, True, False],
        }
    )
    profile = medical_schema_service.profile_medical_schema(frame)
    assert "patient_id" in profile["excludedIdentifierColumns"]
    assert "Age" in profile["demographicColumns"]
    assert "diagnosis" in profile["diseaseColumns"]
    assert "Systolic_BP_mmHg" in profile["clinicalMeasurementColumns"]
    assert "smoker" not in profile["approvedOutputColumns"]
    measurement = next(item for item in profile["columns"] if item["originalName"] == "Systolic_BP_mmHg")
    assert measurement["unit"] == "mmHg"
    assert measurement["standardisedName"] == "Systolic_BP"


def test_reference_catalogue_has_provenance_and_unavailable_entries() -> None:
    references = {item["key"]: item for item in clinical_reference_service.reference_catalog()}
    systolic = references["bp_systolic_adult"]
    assert systolic["sourceUrl"].startswith("https://")
    assert systolic["citation"]
    assert systolic["approvalStatus"] == "Approved"
    assert systolic["available"] is True

    pediatric = clinical_reference_service.select_reference("Systolic_BP", age_years=8, context="resting", unit="mmHg")
    assert pediatric["available"] is False
    assert "Unavailable" in pediatric["reason"]

    child_heart_rate = clinical_reference_service.select_reference(
        "Heart_Rate", age_years=8, context="resting", unit="bpm"
    )
    assert child_heart_rate["available"] is True
    assert child_heart_rate["lower"] == 70
    assert child_heart_rate["upper"] == 110


def test_classification_distinguishes_normal_abnormal_and_implausible_values() -> None:
    reference = clinical_reference_service.select_reference(
        "Blood_Glucose", age_years=30, context="fasting", unit="mg/dL"
    )
    assert (
        clinical_reference_service.classify_value(85, reference, unit="mg/dL", context="fasting")["classification"]
        == "normal"
    )
    assert (
        clinical_reference_service.classify_value(150, reference, unit="mg/dL", context="fasting")["classification"]
        == "abnormal_plausible"
    )
    assert (
        clinical_reference_service.classify_value(5000, reference, unit="mg/dL", context="fasting")["classification"]
        == "implausible"
    )

    converted = clinical_reference_service.classify_value(5.5, reference, unit="mmol/L", context="fasting")
    assert converted["classification"] == "normal"
    assert converted["valueInReferenceUnit"] == pytest.approx(99.1, abs=0.2)


def test_relationship_validation_flags_implausible_combinations() -> None:
    frame = pd.DataFrame(
        {
            "Systolic_BP": [70, 120],
            "Diastolic_BP": [90, 80],
            "BMI": [40, 22.9],
            "Height_cm": [170, 175],
            "Weight_kg": [70, 70],
        }
    )
    checks = clinical_reference_service.validate_relationships(frame, generation_profile="ClinicalDistribution")
    by_name = {check["name"]: check for check in checks}
    assert by_name["blood_pressure_order"]["failedRecords"] == 1
    assert by_name["bmi_consistency"]["failedRecords"] == 1


def test_clinical_reference_and_profile_endpoints(app: FastAPI, client: TestClient, db_session: Session) -> None:
    source_id, headers = _source(client, "clinical-profile@example.test")

    references = client.get(f"{API}/clinical/references", headers=headers)
    assert references.status_code == 200, references.text
    assert references.json()["count"] >= 10
    assert any(item["sourceUrl"] for item in references.json()["references"])

    profile = client.get(f"{API}/sources/{source_id}/medical-profile", headers=headers)
    assert profile.status_code == 200, profile.text
    payload = profile.json()["profile"]
    assert "patient_id" in payload["excludedIdentifierColumns"]
    assert "cholesterol" in payload["clinicalMeasurementColumns"]
    assert "smoker" not in payload["approvedOutputColumns"]

    validation = client.post(
        f"{API}/sources/{source_id}/clinical-validation",
        headers=headers,
        json={"sourceDatasetId": source_id, "generationProfile": "Standard"},
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["generationProfile"] == "Standard"


def test_standard_generation_excludes_non_medical_columns_and_house_number(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    source_csv = (
        b"house_number,age,gender,diagnosis,Systolic_BP,patient_name\n"
        b"12A,28,Female,stable,118,Alice Example\n"
        b"14B,33,Male,review,122,Bob Example\n"
        b"16C,41,Female,stable,116,Carol Example\n"
        b"18D,37,Male,acute,124,David Example\n"
        b"20E,52,Female,review,120,Eve Example\n"
        b"22F,29,Male,stable,119,Frank Example\n"
        b"24G,46,Female,acute,121,Grace Example\n"
        b"26H,31,Male,review,117,Heidi Example\n"
        b"28J,39,Female,stable,123,Ivan Example\n"
        b"30K,44,Male,review,115,Judy Example\n"
        b"32L,35,Female,stable,118,Kevin Example\n"
        b"34M,48,Male,acute,120,Liam Example\n"
    )
    source_id, headers = _source(client, "standard-output-filter@example.test", source_csv)
    payload = {
        "sourceDatasetId": source_id,
        "datasetName": "Filtered synthetic cohort",
        "model": "GaussianCopula",
        "seed": 9,
        "recordCount": 6,
        "categoricalColumns": ["gender", "diagnosis"],
        "numericalColumns": ["age", "Systolic_BP"],
        "approvedOutputColumns": [
            "house_number",
            "age",
            "gender",
            "diagnosis",
            "Systolic_BP",
            "patient_name",
        ],
    }
    response = client.post(f"{API}/generation/start", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["status"] == "Completed", job

    preview = client.get(f"{API}/generated/{job['generatedDatasetId']}/preview", headers=headers)
    assert preview.status_code == 200, preview.text
    assert set(preview.json()["columns"]) == {"age", "gender", "diagnosis", "Systolic_BP"}
    assert "house_number" not in preview.json()["columns"]
    assert "patient_name" not in preview.json()["columns"]


def test_normal_range_strict_generation_saves_clinical_report(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    source_id, headers = _source(client, "clinical-normal@example.test", CLINICAL_CSV)
    payload = {
        "sourceDatasetId": source_id,
        "datasetName": "Normal-range synthetic cohort",
        "model": "GaussianCopula",
        "seed": 11,
        "recordCount": 6,
        "generationProfile": "NormalRange",
        "enforceStrictSchema": True,
        "approvedOutputColumns": APPROVED,
        "clinicalVariables": CLINICAL_VARIABLES,
        "categoricalColumns": ["Gender", "Disease", "Disease_Level"],
        "numericalColumns": ["Age", "Systolic_BP", "Diastolic_BP", "Blood_Glucose"],
        "maxSamplingAttempts": 6,
    }
    response = client.post(f"{API}/generation/start", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["status"] == "Completed", job
    assert job["generationProfile"] == "NormalRange"
    assert job["clinicalValidation"]
    assert set(job["clinicalValidation"]["classificationCounts"]) >= {"normal", "abnormal_plausible"}

    generated_id = job["generatedDatasetId"]
    preview = client.get(f"{API}/generated/{generated_id}/preview", headers=headers)
    assert preview.status_code == 200, preview.text
    assert set(preview.json()["columns"]) == set(APPROVED)
    assert "patient_id" not in preview.json()["columns"]

    clinical = client.get(f"{API}/generated/{generated_id}/clinical", headers=headers)
    assert clinical.status_code == 200, clinical.text
    assert clinical.json()["report"]["schemaValidation"]["passed"] is True
    assert clinical.json()["report"]["rejectionSampling"]["generationProfile"] == "NormalRange"

    detail = client.get(f"{API}/generated/{generated_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert "clinical" in detail.json()["reportTypes"]

    comparison = create_comparison(client, headers, source_id, generated_id, "Clinical comparison")
    assert comparison["clinical"]["generationProfile"] == "NormalRange"
    assert comparison["clinical"]["syntheticValidation"]["classificationCounts"]
    assert comparison["clinical"]["schemaValidation"]["passed"] is True
    assert comparison["clinical"]["rejectionSampling"]["acceptedRecords"] == 6


def test_clinical_rejection_failure_does_not_save_generated_dataset(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    source_id, headers = _source(client, "clinical-failure@example.test", CLINICAL_CSV)
    payload = {
        "sourceDatasetId": source_id,
        "datasetName": "Impossible normal-range cohort",
        "model": "GaussianCopula",
        "seed": 12,
        "recordCount": 4,
        "generationProfile": "NormalRange",
        "enforceStrictSchema": True,
        "approvedOutputColumns": APPROVED,
        "clinicalVariables": CLINICAL_VARIABLES,
        "referenceOverrides": [{"key": "bp_systolic_adult", "plausibleLower": 0, "plausibleUpper": 1}],
        "categoricalColumns": ["Gender", "Disease", "Disease_Level"],
        "numericalColumns": ["Age", "Systolic_BP", "Diastolic_BP", "Blood_Glucose"],
        "maxSamplingAttempts": 2,
    }
    response = client.post(f"{API}/generation/start", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["status"] == "Failed", job
    assert job["generatedDatasetId"] == ""
    assert "Clinical validation could not produce" in job["error"]
