from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import JobStatus

if TYPE_CHECKING:
    from app.models.dataset import Dataset, DatasetVersion
    from app.models.user import User

JOB_STATUS_ENUM = Enum(
    JobStatus,
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    length=32,
)


class ETLJob(Base, TimestampMixin):
    __tablename__ = "etl_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False
    )
    initiated_by_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        JOB_STATUS_ENUM, nullable=False, default=JobStatus.QUEUED
    )
    current_stage: Mapped[str] = mapped_column(String(32), nullable=False, default="extract")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suggested_mapping_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    approved_mapping_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    profile_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rows_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    dataset: Mapped[Dataset] = relationship(back_populates="etl_jobs")
    dataset_version: Mapped[DatasetVersion] = relationship(back_populates="etl_jobs")
    initiator: Mapped[User] = relationship(back_populates="etl_jobs", foreign_keys=[initiated_by_id])
    approver: Mapped[User | None] = relationship(foreign_keys=[approved_by_id])
    logs: Mapped[list[ETLJobLog]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="ETLJobLog.created_at"
    )
    mapping_decisions: Mapped[list[ETLMappingDecision]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="ETLMappingDecision.decided_at"
    )

    __table_args__ = (
        Index("ix_etl_jobs_dataset_status", "dataset_id", "status"),
        Index("ix_etl_jobs_status_created", "status", "created_at"),
    )


class ETLJobLog(Base):
    __tablename__ = "etl_job_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(ForeignKey("etl_jobs.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False, default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    job: Mapped[ETLJob] = relationship(back_populates="logs")

    __table_args__ = (Index("ix_etl_job_logs_job_created", "job_id", "created_at"),)


class ETLMappingDecision(Base):
    __tablename__ = "etl_mapping_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(ForeignKey("etl_jobs.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    proposed_target: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    target: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decided_by_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    job: Mapped[ETLJob] = relationship(back_populates="mapping_decisions")
    decided_by: Mapped[User] = relationship()

    __table_args__ = (
        Index("ix_etl_mapping_decisions_job", "job_id"),
        Index("uq_etl_mapping_decisions_job_source", "job_id", "source", unique=True),
    )

