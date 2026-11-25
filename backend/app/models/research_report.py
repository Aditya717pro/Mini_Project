from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class ResearchReport(Base, TimestampMixin):
    __tablename__ = "research_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    report_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    report_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    dataset_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    experiment_id: Mapped[str | None] = mapped_column(
        ForeignKey("synthmed_experiments.id", ondelete="SET NULL"), nullable=True
    )
    comparison_id: Mapped[str | None] = mapped_column(
        ForeignKey("synthmed_comparisons.id", ondelete="SET NULL"), nullable=True
    )
    privacy_evaluation_id: Mapped[str | None] = mapped_column(
        ForeignKey("synthmed_evaluation_reports.id", ondelete="SET NULL"), nullable=True
    )
    utility_evaluation_id: Mapped[str | None] = mapped_column(
        ForeignKey("synthmed_utility_evaluations.id", ondelete="SET NULL"), nullable=True
    )
    generation_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    generated_dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    report_file_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    file_checksum: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    template_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    report_data_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="Queued", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    owner = relationship("User", foreign_keys=[owner_id])

    __table_args__ = (
        UniqueConstraint("report_id", name="uq_research_reports_report_id"),
        Index("ix_research_reports_owner_created", "owner_id", "created_at"),
        Index("ix_research_reports_type_created", "report_type", "created_at"),
    )
