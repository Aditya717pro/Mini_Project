from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.access import AccessRequest
    from app.models.audit import AuditLog
    from app.models.dataset import Dataset
    from app.models.etl import ETLJob

ROLE_ENUM = Enum(
    UserRole,
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    length=32,
)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[UserRole] = mapped_column(ROLE_ENUM, nullable=False, default=UserRole.CONTRIBUTOR)
    organisation: Mapped[str] = mapped_column(String(200), nullable=False, default="Independent")
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="Researcher")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    datasets: Mapped[list[Dataset]] = relationship(
        back_populates="owner", foreign_keys="Dataset.owner_id", cascade="all, delete-orphan"
    )
    approved_datasets: Mapped[list[Dataset]] = relationship(
        back_populates="approver", foreign_keys="Dataset.approved_by_id"
    )
    etl_jobs: Mapped[list[ETLJob]] = relationship(
        back_populates="initiator", foreign_keys="ETLJob.initiated_by_id"
    )
    access_requests: Mapped[list[AccessRequest]] = relationship(
        back_populates="requester", foreign_keys="AccessRequest.requester_id"
    )
    decided_requests: Mapped[list[AccessRequest]] = relationship(
        back_populates="decider", foreign_keys="AccessRequest.decided_by_id"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="actor")

    __table_args__ = (Index("ix_users_role_active", "role", "is_active"),)

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, email={self.email!r}, role={self.role!r})"
