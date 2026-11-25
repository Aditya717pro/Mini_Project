import hashlib

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.user import User
from app.synthmed.models import SynthMedGeneratedDataset, SynthMedGenerationJob, SynthMedSourceDataset
from app.synthmed.services import experiment_service, versioning_service
from app.synthmed.services.storage_service import SynthMedStorageService


def _u(db: Session, email: str, role=UserRole.RESEARCHER):
    u = User(email=email, full_name="U", hashed_password="x", role=role, is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _df(n=30):
    return pd.DataFrame({
        "Age": [20 + i % 10 for i in range(n)],
        "Gender": ["Male" if i % 2 == 0 else "Female" for i in range(n)],
        "Disease": ["Diabetes" if i % 3 == 0 else "Hypertension" if i % 3 == 1 else "Healthy" for i in range(n)],
        "Systolic_BP": [120 + i % 5 for i in range(n)],
        "Diastolic_BP": [80 + i % 3 for i in range(n)],
        "BMI": [22.0 + (i % 4) for i in range(n)],
    })


def _mk(db: Session, settings, owner: User, sfx: int, df=None, gdf=None):
    df = _df() if df is None else df
    gdf = df.copy() if gdf is None else gdf
    storage = SynthMedStorageService(settings)
    sid = f"aaaaaaaa-aaaa-aaaa-aaaa-{sfx:012d}"[:36]
    gid = f"bbbbbbbb-bbbb-bbbb-bbbb-{sfx:012d}"[:36]
    sb = df.to_csv(index=False).encode()
    _, srel = storage.save_source(sid, "data.csv", sb)
    gb = gdf.to_csv(index=False).encode()
    _, grel = storage.save_generated(gid, "synthetic_data.csv", gb)
    src = SynthMedSourceDataset(
        id=sid,
        owner_id=owner.id,
        dataset_name=f"src{sfx}",
        original_filename="data.csv",
        stored_path=srel,
        file_format="CSV",
        file_size_bytes=len(sb),
        checksum_sha256="s",
        row_count=len(df),
        column_count=len(df.columns),
    )
    gen = SynthMedGeneratedDataset(
        id=gid,
        owner_id=owner.id,
        source_dataset_id=sid,
        dataset_name=f"gen{sfx}",
        source_dataset_name=f"src{sfx}",
        generation_method="CTGAN",
        record_count=len(gdf),
        column_count=len(gdf.columns),
        file_format="CSV",
        file_size_bytes=len(gb),
        checksum_sha256="g",
        stored_path=grel,
        status="Completed",
    )
    db.add_all([src, gen])
    db.commit()
    return src, gen


def test_p5_01_version_created_on_source_upload(db_session: Session, app):
    o = _u(db_session, "p501@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 1)
    v = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    assert v.dataset_kind == "source" and v.version_number == 1


def test_p5_02_version_created_on_synthetic_generation(db_session: Session, app):
    o = _u(db_session, "p502@test.com")
    src, gen = _mk(db_session, app.state.settings, o, 2)
    v = versioning_service.ensure_generated_version(db_session, user=o, settings=app.state.settings, generated=gen)
    assert v.dataset_kind == "generated" and v.source_dataset_id == src.id


def test_p5_03_version_metadata_persistence(db_session: Session, app):
    o = _u(db_session, "p503@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 3)
    v = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    r = versioning_service.to_version_response(v)
    assert r["checksumSha256"] and r["recordCount"] == 30 and "columns" in r["datasetSchema"]


def test_p5_04_parent_child_lineage_recording(db_session: Session, app):
    o = _u(db_session, "p504@test.com")
    src, gen = _mk(db_session, app.state.settings, o, 4)
    sv = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    gv = versioning_service.ensure_generated_version(db_session, user=o, settings=app.state.settings, generated=gen)
    lin = versioning_service.lineage_for_dataset(db_session, user=o, settings=app.state.settings, dataset_id=gen.id)
    assert any(e["parentResourceId"] == sv.id and e["childResourceId"] == gv.id for e in lin["lineage"])


def test_p5_05_immutable_version_preservation(db_session: Session, app):
    o = _u(db_session, "p505@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 5)
    v1 = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    storage = SynthMedStorageService(app.state.settings)
    df2 = _df()
    df2["Age"] = df2["Age"] + 1
    _, rel = storage.save_source(src.id, "data.csv", df2.to_csv(index=False).encode())
    src.stored_path = rel
    src.row_count = len(df2)
    db_session.commit()
    v2 = versioning_service.create_dataset_version(
        db_session, user=o, settings=app.state.settings, kind="source", source=src
    )
    db_session.commit()
    db_session.refresh(v1)
    assert v1.version_number == 1 and v2.version_number == 2 and v1.checksum_sha256 != v2.checksum_sha256


def test_p5_06_list_versions_api(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p506@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 6)
    app.dependency_overrides[get_current_user] = lambda: o
    r = client.get(f"/api/v1/synthmed/datasets/{src.id}/versions")
    assert r.status_code == 200 and len(r.json()) >= 1


def test_p5_07_get_version_api(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p507@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 7)
    v = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    app.dependency_overrides[get_current_user] = lambda: o
    r = client.get(f"/api/v1/synthmed/datasets/{src.id}/versions/{v.id}")
    assert r.status_code == 200 and r.json()["id"] == v.id


def test_p5_08_lineage_retrieval_api(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p508@test.com")
    src, gen = _mk(db_session, app.state.settings, o, 8)
    versioning_service.ensure_generated_version(db_session, user=o, settings=app.state.settings, generated=gen)
    app.dependency_overrides[get_current_user] = lambda: o
    r = client.get(f"/api/v1/synthmed/datasets/{gen.id}/lineage")
    assert r.status_code == 200 and "lineage" in r.json()


def test_p5_09_restore_creates_new_active_version(db_session: Session, app):
    o = _u(db_session, "p509@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 9)
    v1 = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    storage = SynthMedStorageService(app.state.settings)
    df2 = _df()
    df2["BMI"] = df2["BMI"] + 1
    _, rel = storage.save_source(src.id, "data_v2.csv", df2.to_csv(index=False).encode())
    src.stored_path = rel
    db_session.commit()
    v2 = versioning_service.create_dataset_version(
        db_session, user=o, settings=app.state.settings, kind="source", source=src
    )
    db_session.commit()
    restored = versioning_service.restore_version(
        db_session, user=o, settings=app.state.settings, dataset_id=src.id, version_id=v1.id
    )
    db_session.refresh(v1)
    db_session.refresh(v2)
    assert restored.is_active and restored.version_number > v2.version_number and not v2.is_active


def test_p5_10_restore_does_not_overwrite_history(db_session: Session, app):
    o = _u(db_session, "p510@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 10)
    v1 = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    v2 = versioning_service.restore_version(
        db_session, user=o, settings=app.state.settings, dataset_id=src.id, version_id=v1.id
    )
    db_session.refresh(v1)
    assert v1.id != v2.id and v1.checksum_sha256 == v2.checksum_sha256


def test_p5_11_compare_version_api(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p511@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 11)
    v1 = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    storage = SynthMedStorageService(app.state.settings)
    df2 = _df()
    df2["Age"] = df2["Age"] + 2
    _, rel = storage.save_source(src.id, "data.csv", df2.to_csv(index=False).encode())
    src.stored_path = rel
    db_session.commit()
    v2 = versioning_service.create_dataset_version(
        db_session, user=o, settings=app.state.settings, kind="source", source=src
    )
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: o
    r = client.post(
        f"/api/v1/synthmed/datasets/{src.id}/versions/compare",
        json={"versionAId": v1.id, "versionBId": v2.id},
    )
    assert r.status_code == 200 and r.json()["metadata"]["checksumChanged"] is True


def test_p5_12_compare_schema_differences(db_session: Session, app):
    o = _u(db_session, "p512@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 12)
    v1 = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    storage = SynthMedStorageService(app.state.settings)
    df2 = _df()
    df2["Extra"] = 1
    _, rel = storage.save_source(src.id, "data_v2.csv", df2.to_csv(index=False).encode())
    src.stored_path = rel
    db_session.commit()
    v2 = versioning_service.create_dataset_version(
        db_session, user=o, settings=app.state.settings, kind="source", source=src
    )
    db_session.commit()
    cmp = versioning_service.compare_versions(
        db_session,
        user=o,
        settings=app.state.settings,
        dataset_id=src.id,
        version_a_id=v1.id,
        version_b_id=v2.id,
    )
    assert "Extra" in cmp["schema"]["added"]


def test_p5_13_checksum_calculation_and_verification(db_session: Session, app):
    o = _u(db_session, "p513@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 13)
    v = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    p = SynthMedStorageService(app.state.settings).resolve_source(src.stored_path)
    assert v.checksum_sha256 == hashlib.sha256(p.read_bytes()).hexdigest()


def test_p5_14_restore_auth_enforcement(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p514@test.com")
    other = _u(db_session, "p514b@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 14)
    v = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    app.dependency_overrides[get_current_user] = lambda: other
    r = client.post(f"/api/v1/synthmed/datasets/{src.id}/versions/{v.id}/restore")
    assert r.status_code == 403


def test_p5_15_missing_file_blocks_restore(db_session: Session, app):
    o = _u(db_session, "p515@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 15)
    v = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    SynthMedStorageService(app.state.settings).resolve_source(src.stored_path).unlink()
    with pytest.raises(HTTPException):
        versioning_service.restore_version(
            db_session, user=o, settings=app.state.settings, dataset_id=src.id, version_id=v.id
        )


def test_p5_16_experiment_creation(db_session: Session, app):
    o = _u(db_session, "p516@test.com")
    src, gen = _mk(db_session, app.state.settings, o, 16)
    row = experiment_service.create_experiment(
        db_session,
        user=o,
        settings=app.state.settings,
        payload={"name": "Exp 1", "sourceDatasetId": src.id, "generatedDatasetId": gen.id},
    )
    assert row.name == "Exp 1" and row.source_dataset_id == src.id


def test_p5_17_experiment_api_create_list_get(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p517@test.com")
    src, gen = _mk(db_session, app.state.settings, o, 17)
    app.dependency_overrides[get_current_user] = lambda: o
    c = client.post(
        "/api/v1/synthmed/experiments",
        json={"name": "E17", "sourceDatasetId": src.id, "generatedDatasetId": gen.id},
    )
    assert c.status_code == 201
    eid = c.json()["id"]
    assert client.get("/api/v1/synthmed/experiments").status_code == 200
    assert client.get(f"/api/v1/synthmed/experiments/{eid}").status_code == 200


def test_p5_18_config_snapshot_reuse(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p518@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 18)
    job = SynthMedGenerationJob(
        id="11111111-1111-1111-1111-111111111118",
        owner_id=o.id,
        source_dataset_id=src.id,
        status="Completed",
        model_name="CTGAN",
        generation_mode="Unconditional",
        selected_model="CTGAN",
        epochs=1,
        batch_size=100,
        seed=1,
        requested_record_count=10,
        generated_record_count=10,
        config_json={
            "sourceDatasetId": src.id,
            "model": "CTGAN",
            "epochs": 1,
            "batchSize": 100,
            "recordCount": 10,
            "selectedColumns": ["Age", "Gender", "Disease", "Systolic_BP", "Diastolic_BP", "BMI"],
        },
    )
    db_session.add(job)
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: o
    eid = client.post(
        "/api/v1/synthmed/experiments",
        json={"name": "E18", "sourceDatasetId": src.id, "generationJobId": job.id},
    ).json()["id"]
    r = client.post(f"/api/v1/synthmed/experiments/{eid}/reuse-configuration")
    assert r.status_code in (200, 201)


def test_p5_19_experiment_report_endpoint(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p519@test.com")
    src, gen = _mk(db_session, app.state.settings, o, 19)
    app.dependency_overrides[get_current_user] = lambda: o
    eid = client.post(
        "/api/v1/synthmed/experiments",
        json={"name": "E19", "sourceDatasetId": src.id, "generatedDatasetId": gen.id},
    ).json()["id"]
    r = client.get(f"/api/v1/synthmed/experiments/{eid}/report")
    assert r.status_code == 200 and "experiment" in r.json()


def test_p5_20_restore_api(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p520@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 20)
    v = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    app.dependency_overrides[get_current_user] = lambda: o
    r = client.post(f"/api/v1/synthmed/datasets/{src.id}/versions/{v.id}/restore")
    assert r.status_code == 200 and r.json()["restoredFromVersionId"] == v.id


def test_p5_21_lineage_includes_generation(db_session: Session, app):
    o = _u(db_session, "p521@test.com")
    src, gen = _mk(db_session, app.state.settings, o, 21)
    versioning_service.ensure_generated_version(db_session, user=o, settings=app.state.settings, generated=gen)
    lin = versioning_service.lineage_for_dataset(db_session, user=o, settings=app.state.settings, dataset_id=src.id)
    assert len(lin["versions"]) >= 1


def test_p5_22_experiment_auth_enforcement(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p522@test.com")
    other = _u(db_session, "p522b@test.com")
    src, gen = _mk(db_session, app.state.settings, o, 22)
    app.dependency_overrides[get_current_user] = lambda: o
    eid = client.post(
        "/api/v1/synthmed/experiments",
        json={"name": "E22", "sourceDatasetId": src.id, "generatedDatasetId": gen.id},
    ).json()["id"]
    app.dependency_overrides[get_current_user] = lambda: other
    assert client.get(f"/api/v1/synthmed/experiments/{eid}").status_code == 403


def test_p5_23_compare_distribution_summary(db_session: Session, app):
    o = _u(db_session, "p523@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 23)
    v1 = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    storage = SynthMedStorageService(app.state.settings)
    df2 = _df()
    df2["BMI"] = df2["BMI"] + 5
    _, rel = storage.save_source(src.id, "data.csv", df2.to_csv(index=False).encode())
    src.stored_path = rel
    db_session.commit()
    v2 = versioning_service.create_dataset_version(
        db_session, user=o, settings=app.state.settings, kind="source", source=src
    )
    db_session.commit()
    cmp = versioning_service.compare_versions(
        db_session,
        user=o,
        settings=app.state.settings,
        dataset_id=src.id,
        version_a_id=v1.id,
        version_b_id=v2.id,
    )
    assert "BMI" in cmp["distributions"]


def test_p5_24_restore_checksum_mismatch_blocks(db_session: Session, app):
    o = _u(db_session, "p524@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 24)
    v = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    v.checksum_sha256 = "bad"
    db_session.commit()
    with pytest.raises(HTTPException):
        versioning_service.restore_version(
            db_session, user=o, settings=app.state.settings, dataset_id=src.id, version_id=v.id
        )


def test_p5_25_snapshot_immutable_flag(db_session: Session, app):
    o = _u(db_session, "p525@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 25)
    job = SynthMedGenerationJob(
        id="11111111-1111-1111-1111-111111111125",
        owner_id=o.id,
        source_dataset_id=src.id,
        status="Completed",
        model_name="CTGAN",
        generation_mode="Unconditional",
        selected_model="CTGAN",
        epochs=1,
        batch_size=100,
        seed=1,
        requested_record_count=10,
        generated_record_count=10,
        config_json={"model": "CTGAN"},
    )
    db_session.add(job)
    db_session.commit()
    snap = versioning_service.snapshot_config(db_session, user=o, job=job)
    assert snap.is_immutable is True and snap.config_hash


def test_p5_26_experiment_links_versions(db_session: Session, app):
    o = _u(db_session, "p526@test.com")
    src, gen = _mk(db_session, app.state.settings, o, 26)
    row = experiment_service.create_experiment(
        db_session,
        user=o,
        settings=app.state.settings,
        payload={"name": "E26", "sourceDatasetId": src.id, "generatedDatasetId": gen.id},
    )
    assert row.source_version_id and row.generated_version_id


def test_p5_27_compare_api_rejects_wrong_dataset(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p527@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 27)
    other, _ = _mk(db_session, app.state.settings, o, 28)
    v1 = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    v2 = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=other)
    app.dependency_overrides[get_current_user] = lambda: o
    r = client.post(
        f"/api/v1/synthmed/datasets/{src.id}/versions/compare",
        json={"versionAId": v1.id, "versionBId": v2.id},
    )
    assert r.status_code == 422


def test_p5_28_lineage_api_dataset_not_found(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p528@test.com")
    app.dependency_overrides[get_current_user] = lambda: o
    r = client.get("/api/v1/synthmed/datasets/does-not-exist/lineage")
    assert r.status_code == 404


def test_p5_29_restore_from_restored_version(db_session: Session, app):
    o = _u(db_session, "p529@test.com")
    src, _ = _mk(db_session, app.state.settings, o, 29)
    v1 = versioning_service.ensure_source_version(db_session, user=o, settings=app.state.settings, source=src)
    v2 = versioning_service.restore_version(
        db_session, user=o, settings=app.state.settings, dataset_id=src.id, version_id=v1.id
    )
    v3 = versioning_service.restore_version(
        db_session, user=o, settings=app.state.settings, dataset_id=src.id, version_id=v2.id
    )
    assert v3.restored_from_version_id == v2.id and v3.is_active


def test_p5_30_experiment_reuse_missing_snapshot_fails(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    o = _u(db_session, "p530@test.com")
    src, gen = _mk(db_session, app.state.settings, o, 30)
    app.dependency_overrides[get_current_user] = lambda: o
    eid = client.post(
        "/api/v1/synthmed/experiments",
        json={"name": "E30", "sourceDatasetId": src.id, "generatedDatasetId": gen.id},
    ).json()["id"]
    r = client.post(f"/api/v1/synthmed/experiments/{eid}/reuse-configuration")
    assert r.status_code == 422
