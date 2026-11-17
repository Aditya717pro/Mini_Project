from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.dataset import Dataset

CREATED_AT = DateTime(timezone=True)


def utcnow() -> datetime:
    return datetime.now(UTC)


class QualityReport(Base):
    __tablename__ = "quality_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False
    )
    etl_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("etl_jobs.id", ondelete="SET NULL"), nullable=True
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    formula_version: Mapped[str] = mapped_column(String(20), nullable=False)
    dimensions_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    findings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    method: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        CREATED_AT, default=utcnow, server_default=func.now(), nullable=False
    )

    dataset: Mapped[Dataset] = relationship(back_populates="quality_reports")

    __table_args__ = (
        UniqueConstraint("dataset_version_id", "formula_version", name="uq_quality_report_version_formula"),
    )


class ReadinessReport(Base):
    __tablename__ = "readiness_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False
    )
    quality_report_id: Mapped[str | None] = mapped_column(
        ForeignKey("quality_reports.id", ondelete="SET NULL"), nullable=True
    )
    research_task: Mapped[str] = mapped_column(Text, nullable=False)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String(40), nullable=False)
    categories_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    limitations_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recommendations_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    method: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        CREATED_AT, default=utcnow, server_default=func.now(), nullable=False
    )

    dataset: Mapped[Dataset] = relationship(back_populates="readiness_reports")

    __table_args__ = (
        UniqueConstraint("dataset_version_id", "research_task", name="uq_readiness_report_version_task"),
    )


class RepresentativenessReport(Base):
    __tablename__ = "representativeness_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    age_bands_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    pregnancy_stages_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    paediatric_groups_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    geography_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_attributes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    coverage_notes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        CREATED_AT, default=utcnow, server_default=func.now(), nullable=False
    )

    dataset: Mapped[Dataset] = relationship(back_populates="representativeness_reports")
