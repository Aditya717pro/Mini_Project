from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.synthmed.models import SynthMedGenerationJob, SynthMedSourceDataset
from app.synthmed.services import condition_service
from tests.test_synthmed_generation import FICTIONAL_CSV, auth_headers, register_user, upload

API = "/api/v1/synthmed"
SELECTED = ["patient_id", "age", "cholesterol", "diagnosis"]


def _source(client: TestClient, db_session: Session, email: str) -> tuple[str, dict[str, str], SynthMedSourceDataset]:
    register_user(client, email)
    headers = auth_headers(client, email)
    source_id = upload(client, headers, FICTIONAL_CSV)
    source = db_session.scalar(select(SynthMedSourceDataset).where(SynthMedSourceDataset.id == source_id))
    assert source is not None
    return source_id, headers, source


def _base_config(**overrides) -> dict:
    config = {
        "model": "CTGAN",
        "conditions": [],
        "recordCount": 4,
        "selectedColumns": SELECTED,
        "identifierColumns": ["patient_id"],
        "primaryKey": "patient_id",
    }
    config.update(overrides)
    return config


def test_sdv_api_is_verified_for_all_supported_models() -> None:
    verification = condition_service.verify_sdv_api()
    assert verification == {"CTGAN": True, "TVAE": True, "GaussianCopula": True}

    for model in ("CTGAN", "TVAE", "GaussianCopula"):
        capability = condition_service.get_capabilities(model).as_dict()
        assert capability["samplingApi"] == "sample_from_conditions"
        assert capability["conditionalSampling"] is True
        assert capability["multipleConditions"] is True
        assert capability["exactEquality"] is True
        assert capability["rangeOperators"] is False
        assert capability["primaryKeyConditions"] is False
        assert capability["missingValueConditions"] is False

    assert condition_service.get_capabilities("CTGAN").sampling_strategy == "reject_sampling"
    assert condition_service.get_capabilities("TVAE").sampling_strategy == "reject_sampling"
    assert condition_service.get_capabilities("GaussianCopula").sampling_strategy == "gaussian_multivariate"


def test_eligible_columns_exclude_identifiers_and_constants(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    _, _, source = _source(client, db_session, "conditions-eligible@example.test")
    result = condition_service.validate_conditions(
        source=source, config=_base_config(), settings=app.state.settings
    )
    eligible_names = {item["name"] for item in result["eligibleColumns"]}
    ineligible = {item["name"]: item["reason"] for item in result["ineligibleColumns"]}
    assert eligible_names == {"age", "cholesterol", "diagnosis"}
    assert "patient_id" in ineligible
    assert "identifier" in ineligible["patient_id"].lower()


def test_patient_identifier_condition_is_rejected(app: FastAPI, client: TestClient, db_session: Session) -> None:
    _, _, source = _source(client, db_session, "conditions-identifier@example.test")
    config = _base_config(
        conditions=[{"column": "patient_id", "operator": "eq", "value": "P0001", "numRows": 4}]
    )
    result = condition_service.validate_conditions(source=source, config=config, settings=app.state.settings)
    assert result["valid"] is False
    assert any("patient identifier or primary key" in error for error in result["errors"])


def test_categorical_value_validation(app: FastAPI, client: TestClient, db_session: Session) -> None:
    _, _, source = _source(client, db_session, "conditions-categorical@example.test")
    valid = condition_service.validate_conditions(
        source=source,
        config=_base_config(
            conditions=[{"column": "diagnosis", "operator": "eq", "value": "stable", "numRows": 4}]
        ),
        settings=app.state.settings,
    )
    assert valid["valid"] is True
    assert valid["normalizedConditions"][0]["value"] == "stable"

    invalid = condition_service.validate_conditions(
        source=source,
        config=_base_config(
            conditions=[{"column": "diagnosis", "operator": "eq", "value": "unknown", "numRows": 4}]
        ),
        settings=app.state.settings,
    )
    assert invalid["valid"] is False
    assert any("not present in the source dataset" in error for error in invalid["errors"])


def test_numerical_range_and_operator_validation(app: FastAPI, client: TestClient, db_session: Session) -> None:
    _, _, source = _source(client, db_session, "conditions-numeric@example.test")
    valid = condition_service.validate_conditions(
        source=source,
        config=_base_config(conditions=[{"column": "age", "operator": "eq", "value": 34, "numRows": 4}]),
        settings=app.state.settings,
    )
    assert valid["valid"] is True
    assert valid["normalizedConditions"][0]["value"] == 34.0

    inverted = condition_service.validate_conditions(
        source=source,
        config=_base_config(
            conditions=[{"column": "age", "operator": "between", "min": 60, "max": 30, "numRows": 4}]
        ),
        settings=app.state.settings,
    )
    assert inverted["valid"] is False
    joined = " ".join(inverted["errors"])
    assert "min 60.0 greater than max 30.0" in joined
    assert "not supported by SDV 2.2.0" in joined

    unsupported = condition_service.validate_conditions(
        source=source,
        config=_base_config(conditions=[{"column": "age", "operator": "contains", "value": 3, "numRows": 4}]),
        settings=app.state.settings,
    )
    assert unsupported["valid"] is False
    assert any("Operator 'contains' is not supported" in error for error in unsupported["errors"])


def test_missing_values_multiple_conditions_and_conflicts(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    _, _, source = _source(client, db_session, "conditions-multiple@example.test")
    missing = condition_service.validate_conditions(
        source=source,
        config=_base_config(conditions=[{"column": "age", "operator": "eq", "value": None, "numRows": 4}]),
        settings=app.state.settings,
    )
    assert missing["valid"] is False
    assert any("cannot use a missing or empty value" in error for error in missing["errors"])

    multiple = condition_service.validate_conditions(
        source=source,
        config=_base_config(
            conditions=[
                {"column": "diagnosis", "operator": "eq", "value": "stable", "numRows": 2},
                {"column": "age", "operator": "eq", "value": 34, "numRows": 2},
            ]
        ),
        settings=app.state.settings,
    )
    assert multiple["valid"] is True
    assert len(multiple["normalizedConditions"]) == 2

    conflicting = condition_service.validate_conditions(
        source=source,
        config=_base_config(
            conditions=[
                {"column": "diagnosis", "operator": "eq", "value": "stable", "numRows": 2},
                {"column": "diagnosis", "operator": "eq", "value": "acute", "numRows": 2},
            ]
        ),
        settings=app.state.settings,
    )
    assert conflicting["valid"] is True
    assert any("multiple distinct exact condition values" in warning for warning in conflicting["warnings"])

    mismatched_rows = condition_service.validate_conditions(
        source=source,
        config=_base_config(
            conditions=[{"column": "diagnosis", "operator": "eq", "value": "stable", "numRows": 2}]
        ),
        settings=app.state.settings,
    )
    assert mismatched_rows["valid"] is False
    assert any("must equal the requested recordCount" in error for error in mismatched_rows["errors"])


def test_unknown_model_and_non_ctgan_capabilities(app: FastAPI, client: TestClient, db_session: Session) -> None:
    _, _, source = _source(client, db_session, "conditions-model@example.test")
    unknown = condition_service.validate_conditions(
        source=source, config=_base_config(model="MAGIC"), settings=app.state.settings
    )
    assert unknown["valid"] is False
    assert any("Unknown synthesis model" in error for error in unknown["errors"])

    tvae = condition_service.validate_conditions(
        source=source, config=_base_config(model="TVAE"), settings=app.state.settings
    )
    assert tvae["model"] == "TVAE"
    assert tvae["capabilities"]["samplingStrategy"] == "reject_sampling"

    copula = condition_service.validate_conditions(
        source=source, config=_base_config(model="Gaussian Copula"), settings=app.state.settings
    )
    assert copula["model"] == "GaussianCopula"
    assert copula["capabilities"]["samplingStrategy"] == "gaussian_multivariate"


def test_condition_validation_api_endpoint(client: TestClient, db_session: Session) -> None:
    source_id, headers, _ = _source(client, db_session, "conditions-api@example.test")
    payload = {
        "sourceDatasetId": source_id,
        "model": "TVAE",
        "recordCount": 4,
        "conditions": [{"column": "diagnosis", "operator": "eq", "value": "stable", "numRows": 4}],
        "selectedColumns": SELECTED,
        "identifierColumns": ["patient_id"],
        "primaryKey": "patient_id",
    }
    response = client.post(f"{API}/generation/validate-conditions", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    assert body["model"] == "TVAE"
    assert body["capabilities"]["samplingApi"] == "sample_from_conditions"
    assert "patient_id" not in {item["name"] for item in body["eligibleColumns"]}

    payload["conditions"] = [{"column": "patient_id", "operator": "eq", "value": "P0001", "numRows": 4}]
    invalid = client.post(f"{API}/generation/validate-conditions", headers=headers, json=payload)
    assert invalid.status_code == 200, invalid.text
    assert invalid.json()["valid"] is False
    assert any("patient identifier" in error for error in invalid.json()["errors"])


def _start_payload(source_id: str, model: str = "CTGAN", conditions: list[dict] | None = None) -> dict:
    return {
        "sourceDatasetId": source_id,
        "datasetName": f"{model} generation",
        "model": model,
        "generationMode": "Conditional" if conditions else "Unconditional",
        "conditions": conditions or [],
        "selectedColumns": SELECTED,
        "categoricalColumns": ["diagnosis"],
        "numericalColumns": ["age", "cholesterol"],
        "identifierColumns": ["patient_id"],
        "primaryKey": "patient_id",
        "seed": 7,
        "epochs": 1,
        "batchSize": 20,
        "recordCount": 8,
        "preserveMissingness": True,
    }


def test_conditional_generation_satisfies_conditions_and_persists_result(
    client: TestClient, db_session: Session
) -> None:
    source_id, headers, _ = _source(client, db_session, "conditions-generation@example.test")
    response = client.post(
        f"{API}/generation/start",
        headers=headers,
        json=_start_payload(
            source_id,
            "CTGAN",
            [{"column": "diagnosis", "operator": "eq", "value": "stable", "numRows": 8}],
        ),
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["status"] == "Completed", job["error"]
    assert job["generationMode"] == "Conditional"
    assert job["selectedModel"] == "CTGAN"
    assert job["generatedRecordCount"] == 8
    assert job["conditionSatisfaction"]["passed"] is True
    assert job["conditionSatisfaction"]["conditions"][0]["satisfactionPercentage"] == 100.0

    generated_id = job["generatedDatasetId"]
    preview = client.get(f"{API}/generated/{generated_id}/preview", headers=headers, params={"pageSize": 50})
    assert preview.status_code == 200, preview.text
    assert preview.json()["totalRecords"] == 8
    assert {row["diagnosis"] for row in preview.json()["rows"]} == {"stable"}

    detail = client.get(f"{API}/generated/{generated_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["generationMode"] == "Conditional"
    assert detail.json()["selectedModel"] == "CTGAN"
    assert detail.json()["conditions"][0]["value"] == "stable"
    assert "conditions" in detail.json()["reportTypes"]

    conditions = client.get(f"{API}/generated/{generated_id}/conditions", headers=headers)
    assert conditions.status_code == 200, conditions.text
    assert conditions.json()["report"]["allConditionsSatisfied"] is True
    assert conditions.json()["report"]["conditions"][0]["satisfyingRecords"] == 8

    job_conditions = client.get(f"{API}/generation/jobs/{job['id']}/conditions", headers=headers)
    assert job_conditions.status_code == 200, job_conditions.text
    assert job_conditions.json()["report"]["passed"] is True

    evaluation = client.get(f"{API}/generated/{generated_id}/evaluation", headers=headers)
    assert evaluation.status_code == 200, evaluation.text
    assert {"quality", "privacy", "conditions"}.issubset(set(evaluation.json()["availableReports"]))
    assert evaluation.json()["conditions"]["passed"] is True

    stored = db_session.get(SynthMedGenerationJob, job["id"])
    assert stored is not None
    assert stored.generation_mode == "Conditional"
    assert stored.selected_model == "CTGAN"
    assert stored.normalized_conditions_json[0]["value"] == "stable"
    assert stored.satisfaction_json["passed"] is True


def test_all_models_support_unconditional_and_conditional_generation(
    client: TestClient, db_session: Session
) -> None:
    source_id, headers, _ = _source(client, db_session, "conditions-models@example.test")
    for model in ("CTGAN", "TVAE", "GaussianCopula"):
        unconditional = client.post(f"{API}/generation/start", headers=headers, json=_start_payload(source_id, model))
        assert unconditional.status_code == 201, unconditional.text
        assert unconditional.json()["status"] == "Completed", unconditional.json()["error"]
        assert unconditional.json()["generationMode"] == "Unconditional"
        assert unconditional.json()["selectedModel"] == model
        assert unconditional.json()["generatedRecordCount"] == 8

        conditional = client.post(
            f"{API}/generation/start",
            headers=headers,
            json=_start_payload(
                source_id,
                model,
                [{"column": "diagnosis", "operator": "eq", "value": "stable", "numRows": 8}],
            ),
        )
        assert conditional.status_code == 201, conditional.text
        assert conditional.json()["status"] == "Completed", conditional.json()["error"]
        assert conditional.json()["generationMode"] == "Conditional"
        assert conditional.json()["conditionSatisfaction"]["allConditionsSatisfied"] is True

        preview = client.get(
            f"{API}/generated/{conditional.json()['generatedDatasetId']}/preview",
            headers=headers,
            params={"pageSize": 50},
        )
        assert preview.status_code == 200, preview.text
        assert {row["diagnosis"] for row in preview.json()["rows"]} == {"stable"}


def test_multiple_conditions_and_cohorts_are_satisfied(client: TestClient, db_session: Session) -> None:
    source_id, headers, _ = _source(client, db_session, "conditions-cohorts@example.test")
    combined = client.post(
        f"{API}/generation/start",
        headers=headers,
        json=_start_payload(
            source_id,
            "GaussianCopula",
            [
                {"column": "diagnosis", "operator": "eq", "value": "stable", "numRows": 8},
                {"column": "age", "operator": "eq", "value": 34, "numRows": 8},
            ],
        ),
    )
    assert combined.status_code == 201, combined.text
    body = combined.json()
    assert body["status"] == "Completed", body["error"]
    assert body["conditionSatisfaction"]["combined"]["satisfyingRecords"] == 8
    assert body["conditionSatisfaction"]["allConditionsSatisfied"] is True

    cohorts = client.post(
        f"{API}/generation/start",
        headers=headers,
        json=_start_payload(
            source_id,
            "CTGAN",
            [
                {"column": "diagnosis", "operator": "eq", "value": "stable", "numRows": 4},
                {"column": "diagnosis", "operator": "eq", "value": "acute", "numRows": 4},
            ],
        ),
    )
    assert cohorts.status_code == 201, cohorts.text
    cohort_body = cohorts.json()
    assert cohort_body["status"] == "Completed", cohort_body["error"]
    assert [cohort["satisfyingRecords"] for cohort in cohort_body["conditionSatisfaction"]["cohorts"]] == [4, 4]
    assert cohort_body["conditionSatisfaction"]["allConditionsSatisfied"] is True


def test_invalid_conditional_configuration_is_rejected(client: TestClient, db_session: Session) -> None:
    source_id, headers, _ = _source(client, db_session, "conditions-invalid-start@example.test")
    payload = _start_payload(
        source_id,
        "CTGAN",
        [{"column": "diagnosis", "operator": "eq", "value": "stable", "numRows": 4}],
    )
    response = client.post(f"{API}/generation/start", headers=headers, json=payload)
    assert response.status_code == 422, response.text
    assert "must equal the requested recordCount" in response.json()["detail"]

    missing_mode = _start_payload(source_id, "CTGAN", [])
    missing_mode["generationMode"] = "Conditional"
    response = client.post(f"{API}/generation/start", headers=headers, json=missing_mode)
    assert response.status_code == 422, response.text
    assert "requires at least one condition" in response.json()["detail"]
