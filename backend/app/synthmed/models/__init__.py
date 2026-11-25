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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class SynthMedSourceDataset(Base, TimestampMixin):
    __tablename__ = "synthmed_source_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    dataset_name: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_format: Mapped[str] = mapped_column(String(16), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    upload_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Uploaded", server_default="Uploaded"
    )
    content_type: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default=text("''"))


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
    generation_method: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default=text("''"))
    generation_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="Unconditional", server_default="Unconditional"
    )
    selected_model: Mapped[str] = mapped_column(
        String(80), nullable=False, default="CTGAN", server_default="CTGAN"
    )
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    file_format: Mapped[str] = mapped_column(String(16), nullable=False, default="CSV", server_default="CSV")
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    stored_path: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Completed", server_default="Completed")


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
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Queued", server_default="Queued", index=True
    )
    model_name: Mapped[str] = mapped_column(String(80), nullable=False, default="CTGAN", server_default="CTGAN")
    generation_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="Unconditional", server_default="Unconditional"
    )
    selected_model: Mapped[str] = mapped_column(
        String(80), nullable=False, default="CTGAN", server_default="CTGAN"
    )
    epochs: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    training_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    normalized_conditions_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    condition_validation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    satisfaction_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
        ForeignKey("synthmed_generation_jobs.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    owner = relationship("User", foreign_keys=[owner_id])
    job = relationship("SynthMedGenerationJob", foreign_keys=[job_id])

    __table_args__ = (UniqueConstraint("job_id", name="uq_synthmed_config_job"),)


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
    method: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default=text("''"))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    file_path: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))

    owner = relationship("User", foreign_keys=[owner_id])
    job = relationship("SynthMedGenerationJob", foreign_keys=[job_id])
    generated_dataset = relationship("SynthMedGeneratedDataset", foreign_keys=[generated_dataset_id])

    __table_args__ = (
        UniqueConstraint("job_id", "report_type", name="uq_synthmed_eval_job_type"),
        Index("ix_synthmed_eval_generated_type", "generated_dataset_id", "report_type"),
    )


class SynthMedComparison(Base, TimestampMixin):
    __tablename__ = "synthmed_comparisons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("synthmed_source_datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    generated_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("synthmed_generated_datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(250), nullable=False, default="", server_default=text("''"))
    method: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default=text("''"))
    summary_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    file_path: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))

    owner = relationship("User", foreign_keys=[owner_id])
    source_dataset = relationship("SynthMedSourceDataset", foreign_keys=[source_dataset_id])
    generated_dataset = relationship("SynthMedGeneratedDataset", foreign_keys=[generated_dataset_id])

    __table_args__ = (
        Index("ix_synthmed_comparison_owner_created", "owner_id", "created_at"),
        Index("ix_synthmed_comparison_generated_created", "generated_dataset_id", "created_at"),
    )


class SynthMedUtilityEvaluation(Base, TimestampMixin):
    __tablename__ = "synthmed_utility_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("synthmed_source_datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    generated_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("synthmed_generated_datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Queued", server_default="Queued", index=True
    )
    evaluation_name: Mapped[str] = mapped_column(String(250), nullable=False, default="", server_default=text("''"))
    evaluation_type: Mapped[str] = mapped_column(String(16), nullable=False, default="TSTR", server_default="TSTR")
    model_name: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default=text("''"))
    target_column: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default=text("''"))
    feature_columns_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    train_test_split: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    preprocessing_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    comparison_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    report_path: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    report_csv_path: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    report_pdf_path: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    report_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    report_csv_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    report_pdf_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    owner = relationship("User", foreign_keys=[owner_id])
    source_dataset = relationship("SynthMedSourceDataset", foreign_keys=[source_dataset_id])
    generated_dataset = relationship("SynthMedGeneratedDataset", foreign_keys=[generated_dataset_id])

    __table_args__ = (
        Index("ix_synthmed_utility_owner_created", "owner_id", "created_at"),
        Index("ix_synthmed_utility_status_created", "status", "created_at"),
        Index("ix_synthmed_utility_generated_created", "generated_dataset_id", "created_at"),
    )


class SynthMedDatasetVersion(Base, TimestampMixin):
    __tablename__ = "synthmed_dataset_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    dataset_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # source|generated
    logical_dataset_id: Mapped[str] = mapped_column(String(36), nullable=False, default="", index=True)
    source_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("synthmed_source_datasets.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    generated_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("synthmed_generated_datasets.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    parent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("synthmed_dataset_versions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    is_active: Mapped[bool] = mapped_column(default=False, server_default="0", nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(250), nullable=False, default="", server_default=text("''"))
    file_format: Mapped[str] = mapped_column(String(16), nullable=False, default="", server_default=text("''"))
    stored_path: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    schema_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    missing_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    distribution_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    transform_history_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    validation_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    restored_from_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("synthmed_dataset_versions.id", ondelete="SET NULL"), nullable=True
    )

    owner = relationship("User", foreign_keys=[owner_id])
    source_dataset = relationship("SynthMedSourceDataset", foreign_keys=[source_dataset_id])
    generated_dataset = relationship("SynthMedGeneratedDataset", foreign_keys=[generated_dataset_id])
    parent_version = relationship("SynthMedDatasetVersion", remote_side=[id], foreign_keys=[parent_version_id])

    __table_args__ = (
        UniqueConstraint(
            "dataset_kind", "logical_dataset_id", "version_number", name="uq_synthmed_logical_version_number"
        ),
        Index("ix_synthmed_version_owner_created", "owner_id", "created_at"),
        Index("ix_synthmed_version_kind_active", "dataset_kind", "is_active"),
    )


class SynthMedDatasetLineage(Base, TimestampMixin):
    __tablename__ = "synthmed_dataset_lineage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parent_resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_resource_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    child_resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    child_resource_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    generated_dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    owner = relationship("User", foreign_keys=[owner_id])

    __table_args__ = (
        Index("ix_synthmed_lineage_parent", "parent_resource_type", "parent_resource_id"),
        Index("ix_synthmed_lineage_child", "child_resource_type", "child_resource_id"),
    )


class SynthMedGenerationConfigurationSnapshot(Base, TimestampMixin):
    __tablename__ = "synthmed_generation_config_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default=text("''"))
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    is_immutable: Mapped[bool] = mapped_column(default=True, server_default="1", nullable=False)

    owner = relationship("User", foreign_keys=[owner_id])

    __table_args__ = (Index("ix_synthmed_snapshot_owner_created", "owner_id", "created_at"),)


class SynthMedExperiment(Base, TimestampMixin):
    __tablename__ = "synthmed_experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft", server_default="Draft", index=True)
    source_dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    generated_dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    generated_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    generation_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    configuration_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("synthmed_generation_config_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    comparison_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    utility_evaluation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    owner = relationship("User", foreign_keys=[owner_id])
    configuration_snapshot = relationship(
        "SynthMedGenerationConfigurationSnapshot", foreign_keys=[configuration_snapshot_id]
    )

    __table_args__ = (Index("ix_synthmed_experiment_owner_created", "owner_id", "created_at"),)

