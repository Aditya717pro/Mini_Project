import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.user import User
from app.synthmed.models import SynthMedSourceDataset
from app.synthmed.services import versioning_service
from app.synthmed.services.storage_service import SynthMedStorageService


def _user(db, email):
    u = User(email=email, full_name="U", hashed_password="x", role=UserRole.RESEARCHER, is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _src(db, settings, owner, suffix="01"):
    storage = SynthMedStorageService(settings)
    sid = f"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa{suffix}"
    df = pd.DataFrame({
        "Age": [20, 30],
        "Gender": ["Male", "Female"],
        "Disease": ["Diabetes", "Healthy"],
        "Systolic_BP": [120, 110],
        "Diastolic_BP": [80, 70],
        "BMI": [24.0, 22.0],
    })
    b = df.to_csv(index=False).encode("utf-8")
    _, rel = storage.save_source(sid, "data.csv", b)
    row = SynthMedSourceDataset(
        id=sid,
        owner_id=owner.id,
        dataset_name="src",
        original_filename="data.csv",
        stored_path=rel,
        file_format="CSV",
        file_size_bytes=len(b),
        checksum_sha256="s",
        row_count=2,
        column_count=6,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_version_creation_source(db_session: Session, app):
    owner = _user(db_session, "v1@test.com")
    src = _src(db_session, app.state.settings, owner, "01")
    v = versioning_service.ensure_source_version(db_session, user=owner, settings=app.state.settings, source=src)
    assert v.version_number == 1 and v.is_active


def test_lineage_endpoint(client: TestClient, db_session: Session, app):
    from app.api.deps import get_current_user

    owner = _user(db_session, "v2@test.com")
    src = _src(db_session, app.state.settings, owner, "02")
    app.dependency_overrides[get_current_user] = lambda: owner
    r = client.get(f"/api/v1/synthmed/datasets/{src.id}/lineage")
    assert r.status_code == 200
    body = r.json()
    assert body["datasetId"] == src.id
