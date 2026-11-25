from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.etl.pipeline import run_pipeline
from app.models.audit import AuditLog
from app.models.enums import FileFormat
from app.services.audit_service import log_audit
from app.services.storage_service import StorageService
from app.synthmed.models import SynthMedDatasetVersion
from app.synthmed.services import versioning_service
from app.synthmed.services.storage_service import SynthMedStorageService
from tests.test_synthmed_generation import FICTIONAL_CSV, auth_headers, register_user, upload
from tests.test_synthmed_utility_evaluation import _base_real, _base_synth, _mk_pair, _user


def test_audit_details_redact_sensitive_information(db_session: Session) -> None:
    entry = log_audit(
        db_session,
        action="test.audit",
        resource_type="test",
        details={
            "email": "private@example.test",
            "filename": "cohort.csv",
            "targetColumn": "Disease",
            "versionId": "version-1",
            "nested": {
                "path": str(Path.cwd() / "private" / "cohort.csv"),
                "parentVersionId": "version-0",
            },
        },
    )
    db_session.commit()
    db_session.refresh(entry)

    details = entry.details_json
    assert details["email"] == "[REDACTED]"
    assert details["filename"] == "[REDACTED]"
    assert details["targetColumn"] == "[REDACTED]"
    assert details["versionId"] == "version-1"
    assert details["nested"]["path"] == "[REDACTED]"
    assert details["nested"]["parentVersionId"] == "version-0"


def test_source_upload_creates_initial_version_and_redacts_audit_details(
    client: TestClient, db_session: Session
) -> None:
    register_user(client, "safety-upload@example.test")
    headers = auth_headers(client, "safety-upload@example.test")
    source_id = upload(client, headers, FICTIONAL_CSV)

    versions = list(
        db_session.scalars(
            select(SynthMedDatasetVersion).where(
                SynthMedDatasetVersion.dataset_kind == "source",
                SynthMedDatasetVersion.logical_dataset_id == source_id,
            )
        )
    )
    assert len(versions) == 1
    assert versions[0].version_number == 1

    audit = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "synthmed.source_uploaded")
    ).first()
    assert audit is not None
    assert audit.details_json["filename"] == "[REDACTED]"


def test_generated_version_strict_validation_fails_closed_without_source_file(
    db_session: Session, app
) -> None:
    owner = _user(db_session, "safety-strict@example.test")
    real = _base_real()
    source, generated = _mk_pair(db_session, app.state.settings, owner, real, _base_synth(real), "91")
    SynthMedStorageService(app.state.settings).resolve_source(source.stored_path).unlink()

    with pytest.raises(HTTPException) as raised:
        versioning_service.create_dataset_version(
            db_session,
            user=owner,
            settings=app.state.settings,
            kind="generated",
            generated=generated,
        )
    assert raised.value.status_code == 409


def test_nested_version_access_rejects_wrong_dataset_kind(
    client: TestClient, db_session: Session, app
) -> None:
    owner = _user(db_session, "safety-scope@example.test")
    real = _base_real()
    source, generated = _mk_pair(db_session, app.state.settings, owner, real, _base_synth(real), "92")
    source_version = versioning_service.ensure_source_version(
        db_session, user=owner, settings=app.state.settings, source=source
    )
    generated_version = versioning_service.ensure_generated_version(
        db_session, user=owner, settings=app.state.settings, generated=generated
    )
    app.dependency_overrides[get_current_user] = lambda: owner

    wrong_on_source = client.get(
        f"/api/v1/synthmed/datasets/{source.id}/versions/{generated_version.id}"
    )
    wrong_on_generated = client.get(
        f"/api/v1/synthmed/datasets/{generated.id}/versions/{source_version.id}"
    )
    assert wrong_on_source.status_code == 404
    assert wrong_on_generated.status_code == 404


def test_version_response_masks_absolute_stored_paths(
    client: TestClient, db_session: Session, app
) -> None:
    owner = _user(db_session, "safety-paths@example.test")
    real = _base_real()
    source, _ = _mk_pair(db_session, app.state.settings, owner, real, _base_synth(real), "93")
    version = versioning_service.ensure_source_version(
        db_session, user=owner, settings=app.state.settings, source=source
    )
    version.stored_path = str(Path.cwd() / "private-storage" / "cohort.csv")
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: owner

    response = client.get(f"/api/v1/synthmed/datasets/{source.id}/versions/{version.id}")
    assert response.status_code == 200
    assert response.json()["storedPath"] == "cohort.csv"
    assert "private-storage" not in response.text


def test_pipeline_records_structured_unit_conversions(app, tmp_path: Path) -> None:
    raw_path = tmp_path / "unit-conversion.csv"
    raw_path.write_text("age_months\n24\n36\n", encoding="utf-8")

    result = run_pipeline(
        raw_path=raw_path,
        file_format=FileFormat.CSV,
        approved_mapping={"age_months": "age_years"},
        storage=StorageService(app.state.settings),
        dataset_id="unit-conversion-dataset",
        version_id="unit-conversion-version",
    )

    conversions = result.transformation_log["unit_conversions"]
    assert conversions
    assert conversions[0]["sourceColumn"] == "age_months"
    assert conversions[0]["targetColumn"] == "age_years"
    assert "months" in conversions[0]["note"].lower()
