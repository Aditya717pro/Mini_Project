from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import AccessClassification, DatasetStatus, FileFormat

if TYPE_CHECKING:
    from app.models.access import AccessRequest
    from app.models.etl import ETLJob
    from app.models.reports import QualityReport, ReadinessReport, RepresentativenessReport
    from app.models.user import User

DATASET_STATUS_ENUM = Enum(
    DatasetStatus,
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    length=32,
)
ACCESS_ENUM = Enum(
    AccessClassification,
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    length=32,
)
FORMAT_ENUM = Enum(
    FileFormat,
    native_enum=False,
    values_callable=lambda values: [value.value for value in values],
    length=8,
)


class Dataset(Base, TimestampMixin):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    domain: Mapped[str] = mapped_column(String(100), nullable=False)
    access_classification: Mapped[AccessClassification] = mapped_column(
        ACCESS_ENUM, nullable=False, default=AccessClassification.CONTROLLED
    )
    status: Mapped[DatasetStatus] = mapped_column(
        DATASET_STATUS_ENUM, nullable=False, default=DatasetStatus.PROCESSING
    )
    format: Mapped[FileFormat] = mapped_column(FORMAT_ENUM, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    missing_rate: Mapped[float] = mapped_column(nullable=False, default=0.0)
    duplicate_rate: Mapped[float] = mapped_column(nullable=False, default=0.0)
    research_task: Mapped[str] = mapped_column(String(250), nullable=False, default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    owner: Mapped[User] = relationship(back_populates="datasets", foreign_keys=[owner_id])
    approver: Mapped[User | None] = relationship(
        back_populates="approved_datasets", foreign_keys=[approved_by_id]
    )
    metadata_record: Mapped[DatasetMetadata | None] = relationship(
        back_populates="dataset", uselist=False, cascade="all, delete-orphan"
    )
    versions: Mapped[list[DatasetVersion]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="DatasetVersion.version_number"
    )
    etl_jobs: Mapped[list[ETLJob]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="ETLJob.created_at"
    )
    quality_reports: Mapped[list[QualityReport]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="QualityReport.created_at"
    )
    readiness_reports: Mapped[list[ReadinessReport]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="ReadinessReport.created_at"
    )
    representativeness_reports: Mapped[list[RepresentativenessReport]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )
    access_requests: Mapped[list[AccessRequest]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_datasets_domain_status", "domain", "status"),
        Index("ix_datasets_owner_created", "owner_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"Dataset(id={self.id!r}, title={self.title!r}, status={self.status!r})"


class DatasetVersion(Base, TimestampMixin):
    __tablename__ = "dataset_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_file_path: Mapped[str] = mapped_column(Text, nullable=False)
    processed_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    profile_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    transformation_log_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    etl_jobs: Mapped[list[ETLJob]] = relationship(back_populates="dataset_version")

    __table_args__ = (
        UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version_number"),
        Index("ix_dataset_versions_dataset_current", "dataset_id", "is_current"),
    )


class DatasetMetadata(Base, TimestampMixin):
    __tablename__ = "dataset_metadata"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    age_range: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    geography: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    study_design: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    license: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    ethics_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_dictionary_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_scope: Mapped[str] = mapped_column(String(200), nullable=False, default="Not declared")
    intended_tasks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    label_column: Mapped[str | None] = mapped_column(String(120), nullable=True)
    collection_period: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    additional_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    dataset: Mapped[Dataset] = relationship(back_populates="metadata_record")
