from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import RequestStatus

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.user import User

REQUEST_STATUS_ENUM = Enum(
    RequestStatus,
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    length=20,
)


class AccessRequest(Base):
    __tablename__ = "access_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    project_title: Mapped[str] = mapped_column(String(250), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RequestStatus] = mapped_column(
        REQUEST_STATUS_ENUM, nullable=False, default=RequestStatus.PENDING
    )
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    dataset: Mapped[Dataset] = relationship(back_populates="access_requests")
    requester: Mapped[User] = relationship(
        back_populates="access_requests", foreign_keys=[requester_id]
    )
    decider: Mapped[User | None] = relationship(
        back_populates="decided_requests", foreign_keys=[decided_by_id]
    )

    __table_args__ = (
        Index("ix_access_requests_dataset_status", "dataset_id", "status"),
        Index("ix_access_requests_requester_status", "requester_id", "status"),
    )
