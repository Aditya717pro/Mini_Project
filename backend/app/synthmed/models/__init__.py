from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class SynthMedSourceDataset(Base, TimestampMixin):
    __tablename__ = "synthmed_source_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    dataset_name: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_format: Mapped[str] = mapped_column(String(16), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    upload_status: Mapped[str] = mapped_column(String(32), nullable=False, default="Uploaded")
    content_type: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    owner = relationship("User", foreign_keys=[owner_id])

    __table_args__ = (
        Index("ix_synthmed_source_owner_created", "owner_id", "created_at"),
    )


class SynthMedGeneratedDataset(Base, TimestampMixin):
    __tablename__ = "synthmed_generated_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("synthmed_source_datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    dataset_name: Mapped[str] = mapped_column(String(250), nullable=False)
    source_dataset_name: Mapped[str] = mapped_column(String(250), nullable=False)
    generation_method: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_format: Mapped[str] = mapped_column(String(16), nullable=False, default="CSV")
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    stored_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Completed")

    owner = relationship("User", foreign_keys=[owner_id])
    source_dataset = relationship("SynthMedSourceDataset", foreign_keys=[source_dataset_id])

    __table_args__ = (
        Index("ix_synthmed_generated_owner_created", "owner_id", "created_at"),
    )


class SynthMedGenerationJob(Base, TimestampMixin):
    __tablename__ = "synthmed_generation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("synthmed_source_datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    generated_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("synthmed_generated_datasets.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Queued", index=True)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False, default="CTGAN")
    epochs: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    training_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    owner = relationship("User", foreign_keys=[owner_id])
    source_dataset = relationship("SynthMedSourceDataset", foreign_keys=[source_dataset_id])
    generated_dataset = relationship("SynthMedGeneratedDataset", foreign_keys=[generated_dataset_id])

    __table_args__ = (
        Index("ix_synthmed_job_owner_created", "owner_id", "created_at"),
        Index("ix_synthmed_job_status_created", "status", "created_at"),
    )


class SynthMedGenerationConfig(Base, TimestampMixin):
    __tablename__ = "synthmed_generation_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(
        ForeignKey("synthmed_generation_jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    owner = relationship("User", foreign_keys=[owner_id])
    job = relationship("SynthMedGenerationJob", foreign_keys=[job_id])


class SynthMedEvaluationReport(Base, TimestampMixin):
    __tablename__ = "synthmed_evaluation_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(
        ForeignKey("synthmed_generation_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    generated_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("synthmed_generated_datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    method: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    file_path: Mapped[str] = mapped_column(Text, nullable=False, default="")

    owner = relationship("User", foreign_keys=[owner_id])
    job = relationship("SynthMedGenerationJob", foreign_keys=[job_id])
    generated_dataset = relationship("SynthMedGeneratedDataset", foreign_keys=[generated_dataset_id])

    __table_args__ = (
        UniqueConstraint("job_id", "report_type", name="uq_synthmed_eval_job_type"),
        Index("ix_synthmed_eval_generated_type", "generated_dataset_id", "report_type"),
    )

