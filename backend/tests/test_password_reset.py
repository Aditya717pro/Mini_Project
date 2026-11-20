import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import auth as auth_routes
from app.models import AuditLog, PasswordResetOTP


@pytest.fixture()
def sent_otps(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(
        auth_routes,
        "send_password_reset_email",
        lambda *, settings, to_email, otp: captured.append(otp),
    )
    return captured


def register(client: TestClient, email: str = "user@example.com", phone: str | None = None) -> dict:
    payload = {
        "email": email,
        "password": "a-strong-password-1",
        "full_name": "Test User",
        "organisation": "Test Org",
        "title": "Researcher",
    }
    if phone is not None:
        payload["phone_number"] = phone
    return client.post("/api/v1/auth/register", json=payload).json()


def request_reset(client: TestClient, email: str = "user@example.com"):
    return client.post("/api/v1/auth/forgot-password", json={"email": email})


def test_registration_accepts_and_returns_phone(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "phone@example.com",
            "phone_number": "+15551234567",
            "password": "a-strong-password-1",
            "full_name": "Phone User",
        },
    )
    assert response.status_code == 201
    assert response.json()["phone_number"] == "+15551234567"


def test_registration_rejects_invalid_phone(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "bad@example.com",
            "phone_number": "12345",
            "password": "a-strong-password-1",
            "full_name": "Bad Phone",
        },
    )
    assert response.status_code == 422


def test_otp_reset_flow(client: TestClient, db_session: Session, sent_otps: list[str]) -> None:
    register(client)
    assert request_reset(client).status_code == 202
    assert len(sent_otps) == 1
    otp = sent_otps[0]
    assert len(otp) == 6 and otp.isdigit()

    wrong_otp = "000000" if otp != "000000" else "111111"
    wrong = client.post(
        "/api/v1/auth/forgot-password/verify",
        json={
            "email": "user@example.com",
            "otp": wrong_otp,
            "new_password": "new-strong-password-1",
        },
    )
    assert wrong.status_code == 400

    correct = client.post(
        "/api/v1/auth/forgot-password/verify",
        json={"email": "user@example.com", "otp": otp, "new_password": "new-strong-password-1"},
    )
    assert correct.status_code == 204

    assert client.post(
        "/api/v1/auth/login", json={"email": "user@example.com", "password": "a-strong-password-1"}
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login", json={"email": "user@example.com", "password": "new-strong-password-1"}
    ).status_code == 200


def test_otp_cannot_be_reused(client: TestClient, db_session: Session, sent_otps: list[str]) -> None:
    register(client)
    request_reset(client)
    otp = sent_otps[0]
    payload = {"email": "user@example.com", "otp": otp, "new_password": "new-strong-password-1"}
    assert client.post("/api/v1/auth/forgot-password/verify", json=payload).status_code == 204
    assert client.post("/api/v1/auth/forgot-password/verify", json=payload).status_code == 400


def test_expired_otp_is_rejected(
    client: TestClient, db_session: Session, sent_otps: list[str], app: FastAPI
) -> None:
    app.state.settings.otp_ttl_seconds = -1
    register(client)
    request_reset(client)
    response = client.post(
        "/api/v1/auth/forgot-password/verify",
        json={"email": "user@example.com", "otp": sent_otps[0], "new_password": "new-strong-password-1"},
    )
    assert response.status_code == 400


def test_unconfigured_smtp_returns_503_without_creating_otp(
    client: TestClient, db_session: Session, app: FastAPI, sent_otps: list[str]
) -> None:
    app.state.settings.smtp_host = ""
    register(client)

    response = request_reset(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "Password reset email is not configured."
    assert sent_otps == []
    assert db_session.scalars(select(PasswordResetOTP)).all() == []
    assert db_session.scalar(
        select(AuditLog).where(AuditLog.action == "user.password_reset_requested")
    ) is None


def test_otp_is_not_exposed_in_response_or_logs(
    client: TestClient, db_session: Session, sent_otps: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    register(client)
    with caplog.at_level("DEBUG"):
        response = request_reset(client)

    assert response.status_code == 202
    assert response.json() == {"message": "If the email is registered, a reset code has been sent."}
    assert len(sent_otps) == 1
    assert sent_otps[0] not in response.text
    assert sent_otps[0] not in caplog.text


def test_too_many_attempts(client: TestClient, db_session: Session, sent_otps: list[str], app: FastAPI) -> None:
    app.state.settings.otp_max_attempts = 1
    register(client)
    request_reset(client)
    client.post(
        "/api/v1/auth/forgot-password/verify",
        json={"email": "user@example.com", "otp": "000000", "new_password": "new-strong-password-1"},
    )
    response = client.post(
        "/api/v1/auth/forgot-password/verify",
        json={"email": "user@example.com", "otp": sent_otps[0], "new_password": "new-strong-password-1"},
    )
    assert response.status_code == 429


def test_unknown_email_is_generic(client: TestClient, db_session: Session, sent_otps: list[str]) -> None:
    response = request_reset(client, "missing@example.com")
    assert response.status_code == 202
    assert sent_otps == []


def test_reset_requests_are_throttled(client: TestClient, db_session: Session, sent_otps: list[str]) -> None:
    register(client)
    assert request_reset(client).status_code == 202
    assert request_reset(client).status_code == 202
    assert len(sent_otps) == 1


def test_delivery_failure_does_not_persist_otp(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_send(**kwargs: object) -> None:
        raise RuntimeError("SMTP unavailable")

    monkeypatch.setattr(auth_routes, "send_password_reset_email", fail_send)
    register(client)

    assert request_reset(client).status_code == 202
    assert db_session.scalars(select(PasswordResetOTP)).all() == []
    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "user.password_reset_requested")
    )
    assert audit is None
    assert client.post(
        "/api/v1/auth/forgot-password/verify",
        json={"email": "user@example.com", "otp": "000000", "new_password": "new-strong-password-1"},
    ).status_code == 400


def test_failed_resend_preserves_previous_otp(
    client: TestClient, db_session: Session, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    def send_success(**kwargs: object) -> None:
        captured.append(str(kwargs["otp"]))

    def fail_send(**kwargs: object) -> None:
        raise RuntimeError("SMTP unavailable")

    monkeypatch.setattr(auth_routes, "send_password_reset_email", send_success)
    register(client)
    assert request_reset(client).status_code == 202
    first_otp = captured[0]

    app.state.settings.otp_request_cooldown_seconds = 0
    monkeypatch.setattr(auth_routes, "send_password_reset_email", fail_send)
    assert request_reset(client).status_code == 202

    assert client.post(
        "/api/v1/auth/forgot-password/verify",
        json={"email": "user@example.com", "otp": first_otp, "new_password": "new-strong-password-1"},
    ).status_code == 204
