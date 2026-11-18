from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password, verify_password
from app.models.password_reset import PasswordResetOTP
from app.models.user import User


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _latest(db: Session, user: User) -> PasswordResetOTP | None:
    return db.scalar(
        select(PasswordResetOTP)
        .where(PasswordResetOTP.user_id == user.id)
        .order_by(PasswordResetOTP.created_at.desc())
    )


def issue_otp(db: Session, *, settings: Settings, user: User) -> str | None:
    latest = _latest(db, user)
    now = datetime.now(UTC)
    if (
        latest is not None
        and (now - _as_utc(latest.created_at)).total_seconds() < settings.otp_request_cooldown_seconds
    ):
        return None

    for previous in db.scalars(
        select(PasswordResetOTP).where(
            PasswordResetOTP.user_id == user.id,
            PasswordResetOTP.consumed_at.is_(None),
        )
    ):
        previous.consumed_at = now

    otp = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        PasswordResetOTP(
            user_id=user.id,
            otp_hash=hash_password(otp),
            expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
        )
    )
    db.commit()
    return otp


def verify_otp(db: Session, *, settings: Settings, user: User, otp: str) -> None:
    record = db.scalar(
        select(PasswordResetOTP)
        .where(
            PasswordResetOTP.user_id == user.id,
            PasswordResetOTP.consumed_at.is_(None),
        )
        .order_by(PasswordResetOTP.created_at.desc())
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset code")
    if record.attempts >= settings.otp_max_attempts:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many incorrect attempts")
    if datetime.now(UTC) > _as_utc(record.expires_at):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset code")

    if not verify_password(otp, record.otp_hash):
        record.attempts += 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset code")

    record.consumed_at = datetime.now(UTC)
    db.commit()
