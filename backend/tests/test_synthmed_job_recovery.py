from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.security import hash_password
from app.main import create_app
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from app.synthmed.models import SynthMedGenerationJob
from app.synthmed.services import generation_service

ACTIVE_STATUSES = ("Queued", "Preprocessing", "Training", "Generating", "Validating")
TERMINAL_STATUSES = ("Completed", "Failed")


@pytest.fixture(autouse=True)
def reset_executor_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generation_service, "_executor", None)
    monkeypatch.setattr(generation_service, "_executor_stopping", False)


def _factory(db_session: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)


def _create_user(db_session: Session, email: str) -> User:
    user = User(
        email=email,
        full_name="Recovery Tester",
        hashed_password=hash_password("RecoveryTest!42"),
        role=UserRole.CONTRIBUTOR,
        organisation="Test Lab",
        title="Researcher",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_job(db_session: Session, owner_id: str, status: str) -> SynthMedGenerationJob:
    job = SynthMedGenerationJob(
        owner_id=owner_id,
        source_dataset_id="00000000-0000-4000-8000-000000000001",
        status=status,
        model_name="SDV CTGANSynthesizer",
        epochs=1,
        batch_size=20,
        requested_record_count=1,
        generated_record_count=0,
        config_json={},
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _settings(tmp_path, **overrides) -> Settings:
    values = {
        "environment": "test",
        "log_level": "WARNING",
        "database_url": "sqlite://",
        "raw_storage_dir": tmp_path / "raw",
        "processed_storage_dir": tmp_path / "processed",
        "synthmed_storage_dir": tmp_path / "synthmed",
        "synthmed_generation_inline": True,
        "synthmed_stale_job_recovery_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_recover_stale_jobs_recovers_active_and_preserves_terminal(
    client: TestClient, db_session: Session
) -> None:
    owner = _create_user(db_session, "recovery-owner@example.test")
    jobs = {status: _create_job(db_session, owner.id, status) for status in ACTIVE_STATUSES + TERMINAL_STATUSES}

    recovered = generation_service.recover_stale_jobs(_factory(db_session))
    assert recovered == len(ACTIVE_STATUSES)

    db_session.expire_all()
    for status in ACTIVE_STATUSES:
        job = db_session.get(SynthMedGenerationJob, jobs[status].id)
        assert job is not None
        assert job.status == "Failed"
        assert job.completed_at is not None
        assert (job.error_json or {}).get("type") == generation_service.INTERRUPTED_ERROR_TYPE
        assert (job.error_json or {}).get("message") == generation_service.INTERRUPTED_ERROR_MESSAGE
    for status in TERMINAL_STATUSES:
        job = db_session.get(SynthMedGenerationJob, jobs[status].id)
        assert job is not None
        assert job.status == status

    audits = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "synthmed.generation_interrupted")
    ).all()
    assert len(audits) == len(ACTIVE_STATUSES)


def test_recover_stale_jobs_is_idempotent(client: TestClient, db_session: Session) -> None:
    owner = _create_user(db_session, "recovery-idempotent@example.test")
    _create_job(db_session, owner.id, "Training")

    assert generation_service.recover_stale_jobs(_factory(db_session)) == 1
    assert generation_service.recover_stale_jobs(_factory(db_session)) == 0

    audits = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "synthmed.generation_interrupted")
    ).all()
    assert len(audits) == 1


def test_recover_stale_jobs_respects_age_cutoff(client: TestClient, db_session: Session) -> None:
    owner = _create_user(db_session, "recovery-cutoff@example.test")
    old = _create_job(db_session, owner.id, "Training")
    recent = _create_job(db_session, owner.id, "Generating")
    old_timestamp = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    db_session.execute(
        update(SynthMedGenerationJob)
        .where(SynthMedGenerationJob.id == old.id)
        .values(updated_at=old_timestamp)
    )
    db_session.commit()

    assert generation_service.recover_stale_jobs(_factory(db_session), stale_after_seconds=60) == 1

    db_session.expire_all()
    assert db_session.get(SynthMedGenerationJob, old.id).status == "Failed"
    assert db_session.get(SynthMedGenerationJob, recent.id).status == "Generating"


def test_startup_recovery_respects_disabled_flag(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(
        generation_service,
        "recover_stale_jobs",
        lambda *args, **kwargs: calls.append(kwargs),
    )
    app = create_app(_settings(tmp_path, synthmed_stale_job_recovery_enabled=False))

    with TestClient(app):
        pass

    assert calls == []


def test_startup_recovery_runs_when_enabled(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(
        generation_service,
        "recover_stale_jobs",
        lambda *args, **kwargs: calls.append(kwargs) or 0,
    )
    app = create_app(
        _settings(
            tmp_path,
            synthmed_stale_job_recovery_enabled=True,
            synthmed_stale_job_after_seconds=45,
        )
    )

    with TestClient(app):
        pass

    assert calls == [{"stale_after_seconds": 45}]


def test_startup_recovery_failure_does_not_block_startup(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args, **kwargs) -> int:
        raise RuntimeError("recovery unavailable")

    monkeypatch.setattr(generation_service, "recover_stale_jobs", fail)
    app = create_app(_settings(tmp_path, synthmed_stale_job_recovery_enabled=True))

    with TestClient(app) as test_client:
        assert test_client.get("/api/v1/health").status_code == 200


def test_shutdown_handles_executor_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingExecutor:
        def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
            raise RuntimeError("executor close failed")

    class RecordingLogger:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def exception(self, message: str) -> None:
            self.messages.append(message)

    logger = RecordingLogger()
    monkeypatch.setattr(generation_service, "_executor", FailingExecutor())
    monkeypatch.setattr(generation_service, "logger", logger)

    generation_service.shutdown_executor()

    assert generation_service._executor is None
    assert generation_service._executor_stopping is True
    assert logger.messages == ["SynthMed generation executor shutdown failed"]


def test_shutdown_calls_executor_shutdown(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StubExecutor:
        def __init__(self) -> None:
            self.calls: list[tuple[bool, bool]] = []

        def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
            self.calls.append((wait, cancel_futures))

    executor = StubExecutor()
    monkeypatch.setattr(generation_service, "_executor", executor)
    app = create_app(_settings(tmp_path))

    with TestClient(app):
        pass

    assert executor.calls == [(True, False)]
    assert generation_service._executor is None
