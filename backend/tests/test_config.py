import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_accept_comma_separated_env_value() -> None:
    settings = Settings(
        environment="test",
        cors_origins="http://localhost:5173, http://127.0.0.1:5173",
    )

    assert settings.cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_cors_origins_accept_comma_separated_process_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://example.test,http://api.test")

    settings = Settings(_env_file=None, environment="test")

    assert settings.cors_origins == ["http://example.test", "http://api.test"]


def test_api_prefix_is_normalized() -> None:
    settings = Settings(environment="test", api_v1_prefix="/api/v2/")

    assert settings.api_v1_prefix == "/api/v2"


def test_api_prefix_must_start_with_slash() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="test", api_v1_prefix="api/v1")


def test_synthmed_stale_job_recovery_defaults() -> None:
    settings = Settings(environment="test")

    assert settings.synthmed_stale_job_recovery_enabled is True
    assert settings.synthmed_stale_job_after_seconds == 0


def test_synthmed_stale_job_after_seconds_must_not_be_negative() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="test", synthmed_stale_job_after_seconds=-1)
