from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.synthmed.models import SynthMedGeneratedDataset
from app.synthmed.services import condition_service
from app.synthmed.services.storage_service import SynthMedStorageService
from tests.test_synthmed_generation import API, auth_headers, register_user, upload

STRICT_CSV = (
    b"age,gender,disease,disease_level,glucose_mg_dl,systolic_bp_mmhg,diastolic_bp_mmhg\n"
    b"25,Male,Diabetes,Mild,110,118,76\n"
    b"32,Female,Healthy,None,90,112,72\n"
    b"45,Male,Hypertension,Moderate,98,128,82\n"
    b"52,Female,Diabetes,Severe,160,135,86\n"
    b"28,Male,Healthy,None,88,110,70\n"
)

COLUMNS = [
    "age",
    "gender",
    "disease",
    "disease_level",
    "glucose_mg_dl",
    "systolic_bp_mmhg",
    "diastolic_bp_mmhg",
]
NUMERIC_TOLERANCES = {"glucose_mg_dl": 5.0, "systolic_bp_mmhg": 5.0, "diastolic_bp_mmhg": 5.0}


def _source() -> pd.DataFrame:
    return pd.read_csv(BytesIO(STRICT_CSV))


def _start(client: TestClient, headers: dict[str, str], source_id: str, **overrides) -> dict:
    payload = {
        "sourceDatasetId": source_id,
        "datasetName": "Strict preserved synthetic",
        "model": "GaussianCopula",
        "selectedColumns": COLUMNS,
        "categoricalColumns": ["gender", "disease", "disease_level"],
        "numericalColumns": ["age", "glucose_mg_dl", "systolic_bp_mmhg", "diastolic_bp_mmhg"],
        "identifierColumns": [],
        "seed": 7,
        "epochs": 1,
        "batchSize": 20,
        "recordCount": 5,
        "preserveMissingness": True,
        "sourcePreservingMode": True,
        "ageToleranceYears": 5,
        "numericTolerances": NUMERIC_TOLERANCES,
        "maxSamplingAttempts": 1,
    }
    payload.update(overrides)
    response = client.post(f"{API}/generation/start", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def strict_source(client: TestClient):
    register_user(client, "strict-preserve@example.test")
    headers = auth_headers(client, "strict-preserve@example.test")
    source_id = upload(client, headers, STRICT_CSV, name="strict-preserve.csv")
    return headers, source_id


def _generated_frame(app, db_session: Session, generated_id: str) -> pd.DataFrame:
    generated = db_session.get(SynthMedGeneratedDataset, generated_id)
    assert generated is not None
    path = SynthMedStorageService(app.state.settings).resolve_generated(generated.stored_path)
    return pd.read_csv(path)


def _preservation_report(client: TestClient, headers: dict[str, str], generated_id: str) -> dict:
    response = client.get(
        f"{API}/generated/{generated_id}/reports/preservation/download", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def _assert_record_alignment(source: pd.DataFrame, generated: pd.DataFrame) -> None:
    assert list(generated.columns) == list(source.columns)
    assert generated["gender"].tolist() == source["gender"].tolist()
    assert generated["disease"].tolist() == source["disease"].tolist()
    assert generated["disease_level"].tolist() == source["disease_level"].tolist()
    assert (generated["age"].astype(int) - source["age"].astype(int)).abs().le(5).all()
    for column, tolerance in NUMERIC_TOLERANCES.items():
        delta = (pd.to_numeric(generated[column]) - pd.to_numeric(source[column])).abs()
        assert delta.le(tolerance).all()


def test_strict_mode_preserves_source_row_order_and_record_values(
    app, client: TestClient, db_session: Session, strict_source
):
    headers, source_id = strict_source
    job = _start(client, headers, source_id)
    assert job["status"] == "Completed", job["error"]
    assert job["validationStatus"] == "Passed"

    generated = _generated_frame(app, db_session, job["generatedDatasetId"])
    _assert_record_alignment(_source(), generated)

    report = _preservation_report(client, headers, job["generatedDatasetId"])
    assert report["strict"] is True
    assert report["status"] == "Passed"
    assert report["sourceRecordCount"] == 5
    assert report["generatedRecordCount"] == 5
    assert report["genderMismatchCount"] == 0
    assert report["ageViolationCount"] == 0
    assert report["diseaseMismatchCount"] == 0
    assert report["diseaseLevelMismatchCount"] == 0
    assert report["numericViolationCount"] == 0
    assert report["missingRecordCount"] == 0
    assert report["extraRecordCount"] == 0
    assert report["rowOrderMismatchCount"] == 0
    assert report["ageWithinTolerance"]["percentage"] == 100.0


def test_strict_mode_repeats_source_rows_without_truncation(
    app, client: TestClient, db_session: Session, strict_source
):
    headers, source_id = strict_source
    job = _start(client, headers, source_id, recordCount=8)
    assert job["status"] == "Completed", job["error"]

    source = _source()
    expected = pd.concat([source, source.iloc[:3]], ignore_index=True)
    generated = _generated_frame(app, db_session, job["generatedDatasetId"])
    _assert_record_alignment(expected, generated)

    report = _preservation_report(client, headers, job["generatedDatasetId"])
    assert report["generatedRecordCount"] == 8
    assert report["duplicateRecords"] == 3
    assert report["missingRecordCount"] == 0
    assert report["extraRecordCount"] == 0


def test_strict_conditional_mode_keeps_matching_source_rows_in_order(
    app, client: TestClient, db_session: Session, strict_source
):
    headers, source_id = strict_source
    job = _start(
        client,
        headers,
        source_id,
        generationMode="Conditional",
        conditions=[{"column": "gender", "operator": "eq", "value": "Male", "numRows": 3}],
        recordCount=3,
    )
    assert job["status"] == "Completed", job["error"]

    generated = _generated_frame(app, db_session, job["generatedDatasetId"])
    expected = _source().loc[lambda frame: frame["gender"] == "Male"].reset_index(drop=True)
    _assert_record_alignment(expected, generated)


def test_strict_mode_rejects_invalid_model_values_without_clipping(
    app, client: TestClient, db_session: Session, strict_source, monkeypatch
):
    headers, source_id = strict_source
    base = condition_service.MODEL_CLASSES["GaussianCopula"]

    class BadSampler(base):
        def sample(self, *args, **kwargs):
            frame = super().sample(*args, **kwargs)
            if isinstance(frame, dict):
                frame = frame.get("synthmed_data", next(iter(frame.values())))
                result = frame.copy()
                result["age"] = 120
                result["glucose_mg_dl"] = 9999
                result["systolic_bp_mmhg"] = 999
                result["diastolic_bp_mmhg"] = 999
                out = frame
                if isinstance(out, dict):
                    key = "synthmed_data" if "synthmed_data" in out else next(iter(out))
                    out[key] = result
                else:
                    out = result
                return out
            out = frame.copy()
            out["age"] = 120
            out["glucose_mg_dl"] = 9999
            out["systolic_bp_mmhg"] = 999
            out["diastolic_bp_mmhg"] = 999
            return out

    monkeypatch.setitem(condition_service.MODEL_CLASSES, "GaussianCopula", BadSampler)
    job = _start(client, headers, source_id)
    assert job["status"] == "Completed", job["error"]

    generated = _generated_frame(app, db_session, job["generatedDatasetId"])
    _assert_record_alignment(_source(), generated)

    report = _preservation_report(client, headers, job["generatedDatasetId"])
    assert report["restoredValueCount"] > 0
    assert report["rejectedRecordCount"] > 0
    assert report["regenerationAttempts"] > 0
    assert report["status"] == "Passed"


def test_strict_mode_preview_download_export_and_report_have_no_internal_row_indices(
    app, client: TestClient, db_session: Session, strict_source
):
    headers, source_id = strict_source
    job = _start(client, headers, source_id)
    generated_id = job["generatedDatasetId"]

    preview = client.get(f"{API}/generated/{generated_id}/preview", headers=headers, params={"pageSize": 100})
    assert preview.status_code == 200, preview.text
    preview_payload = preview.json()
    assert "sourceRowIndex" not in preview_payload["columns"]
    assert "anchorCount" not in str(preview_payload["rows"])

    for file_format in ("CSV", "XLSX", "JSON"):
        download = client.get(
            f"{API}/generated/{generated_id}/download", headers=headers, params={"file_format": file_format}
        )
        assert download.status_code == 200, download.text
        assert b"sourcerowindex" not in download.content.lower()
        assert b"anchorcount" not in download.content.lower()

    for export_format in ("CSV", "XLSX", "JSON"):
        exported = client.post(
            f"{API}/generated/{generated_id}/export", headers=headers, json={"format": export_format}
        )
        assert exported.status_code in {200, 201}, exported.text

    report = _preservation_report(client, headers, generated_id)
    assert "sourceRowIndex" not in report
    assert "rows" not in report
    assert "anchors" not in report


def test_distribution_mode_is_not_subject_to_strict_record_alignment(
    app, client: TestClient, db_session: Session, strict_source
):
    headers, source_id = strict_source
    job = _start(client, headers, source_id, sourcePreservingMode=False)
    assert job["status"] == "Completed", job["error"]

    report = _preservation_report(client, headers, job["generatedDatasetId"])
    assert report["enabled"] is False
    assert report["strict"] is False
    assert "recordLevelValidation" not in report
