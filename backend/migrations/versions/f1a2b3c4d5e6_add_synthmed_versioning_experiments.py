"""add synthmed p5 versioning and experiments

Revision ID: f1a2b3c4d5e6
Revises: e3c1d2f4a5b6
Create Date: 2026-11-23 01:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "e3c1d2f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "synthmed_dataset_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_kind", sa.String(length=32), nullable=False),
        sa.Column("logical_dataset_id", sa.String(length=36), nullable=False),
        sa.Column("source_dataset_id", sa.String(length=36), nullable=True),
        sa.Column("generated_dataset_id", sa.String(length=36), nullable=True),
        sa.Column("parent_version_id", sa.String(length=36), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("dataset_name", sa.String(length=250), nullable=False, server_default=""),
        sa.Column("file_format", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("stored_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("column_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("missing_summary_json", sa.JSON(), nullable=False),
        sa.Column("distribution_summary_json", sa.JSON(), nullable=False),
        sa.Column("transform_history_json", sa.JSON(), nullable=False),
        sa.Column("validation_summary_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("restored_from_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["generated_dataset_id"], ["synthmed_generated_datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["synthmed_dataset_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["restored_from_version_id"], ["synthmed_dataset_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_dataset_id"], ["synthmed_source_datasets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_kind", "logical_dataset_id", "version_number", name="uq_synthmed_logical_version_number"),
    )
    op.create_index("ix_synthmed_dataset_versions_owner_id", "synthmed_dataset_versions", ["owner_id"])
    op.create_index("ix_synthmed_dataset_versions_logical_dataset_id", "synthmed_dataset_versions", ["logical_dataset_id"])
    op.create_index("ix_synthmed_dataset_versions_dataset_kind", "synthmed_dataset_versions", ["dataset_kind"])
    op.create_index("ix_synthmed_dataset_versions_source_dataset_id", "synthmed_dataset_versions", ["source_dataset_id"])
    op.create_index("ix_synthmed_dataset_versions_generated_dataset_id", "synthmed_dataset_versions", ["generated_dataset_id"])
    op.create_index("ix_synthmed_dataset_versions_parent_version_id", "synthmed_dataset_versions", ["parent_version_id"])
    op.create_index("ix_synthmed_version_owner_created", "synthmed_dataset_versions", ["owner_id", "created_at"])
    op.create_index("ix_synthmed_version_kind_active", "synthmed_dataset_versions", ["dataset_kind", "is_active"])

    op.create_table(
        "synthmed_dataset_lineage",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("parent_resource_type", sa.String(length=64), nullable=False),
        sa.Column("parent_resource_id", sa.String(length=36), nullable=False),
        sa.Column("child_resource_type", sa.String(length=64), nullable=False),
        sa.Column("child_resource_id", sa.String(length=36), nullable=False),
        sa.Column("source_dataset_id", sa.String(length=36), nullable=True),
        sa.Column("generated_dataset_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_synthmed_dataset_lineage_owner_id", "synthmed_dataset_lineage", ["owner_id"])
    op.create_index("ix_synthmed_dataset_lineage_event_type", "synthmed_dataset_lineage", ["event_type"])
    op.create_index("ix_synthmed_dataset_lineage_parent_resource_id", "synthmed_dataset_lineage", ["parent_resource_id"])
    op.create_index("ix_synthmed_dataset_lineage_child_resource_id", "synthmed_dataset_lineage", ["child_resource_id"])
    op.create_index("ix_synthmed_dataset_lineage_source_dataset_id", "synthmed_dataset_lineage", ["source_dataset_id"])
    op.create_index("ix_synthmed_dataset_lineage_generated_dataset_id", "synthmed_dataset_lineage", ["generated_dataset_id"])
    op.create_index("ix_synthmed_lineage_parent", "synthmed_dataset_lineage", ["parent_resource_type", "parent_resource_id"])
    op.create_index("ix_synthmed_lineage_child", "synthmed_dataset_lineage", ["child_resource_type", "child_resource_id"])

    op.create_table(
        "synthmed_generation_config_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("source_dataset_id", sa.String(length=36), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("model_name", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("is_immutable", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_synthmed_generation_config_snapshots_owner_id", "synthmed_generation_config_snapshots", ["owner_id"])
    op.create_index("ix_synthmed_generation_config_snapshots_source_dataset_id", "synthmed_generation_config_snapshots", ["source_dataset_id"])
    op.create_index("ix_synthmed_generation_config_snapshots_job_id", "synthmed_generation_config_snapshots", ["job_id"])
    op.create_index("ix_synthmed_snapshot_owner_created", "synthmed_generation_config_snapshots", ["owner_id", "created_at"])

    op.create_table(
        "synthmed_experiments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Draft"),
        sa.Column("source_dataset_id", sa.String(length=36), nullable=True),
        sa.Column("source_version_id", sa.String(length=36), nullable=True),
        sa.Column("generated_dataset_id", sa.String(length=36), nullable=True),
        sa.Column("generated_version_id", sa.String(length=36), nullable=True),
        sa.Column("generation_job_id", sa.String(length=36), nullable=True),
        sa.Column("configuration_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("comparison_id", sa.String(length=36), nullable=True),
        sa.Column("utility_evaluation_id", sa.String(length=36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["configuration_snapshot_id"], ["synthmed_generation_config_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_synthmed_experiments_owner_id", "synthmed_experiments", ["owner_id"])
    op.create_index("ix_synthmed_experiments_status", "synthmed_experiments", ["status"])
    op.create_index("ix_synthmed_experiments_source_dataset_id", "synthmed_experiments", ["source_dataset_id"])
    op.create_index("ix_synthmed_experiments_source_version_id", "synthmed_experiments", ["source_version_id"])
    op.create_index("ix_synthmed_experiments_generated_dataset_id", "synthmed_experiments", ["generated_dataset_id"])
    op.create_index("ix_synthmed_experiments_generated_version_id", "synthmed_experiments", ["generated_version_id"])
    op.create_index("ix_synthmed_experiments_generation_job_id", "synthmed_experiments", ["generation_job_id"])
    op.create_index("ix_synthmed_experiments_configuration_snapshot_id", "synthmed_experiments", ["configuration_snapshot_id"])
    op.create_index("ix_synthmed_experiments_comparison_id", "synthmed_experiments", ["comparison_id"])
    op.create_index("ix_synthmed_experiments_utility_evaluation_id", "synthmed_experiments", ["utility_evaluation_id"])
    op.create_index("ix_synthmed_experiment_owner_created", "synthmed_experiments", ["owner_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_synthmed_experiment_owner_created", table_name="synthmed_experiments")
    op.drop_index("ix_synthmed_experiments_utility_evaluation_id", table_name="synthmed_experiments")
    op.drop_index("ix_synthmed_experiments_comparison_id", table_name="synthmed_experiments")
    op.drop_index("ix_synthmed_experiments_configuration_snapshot_id", table_name="synthmed_experiments")
    op.drop_index("ix_synthmed_experiments_generation_job_id", table_name="synthmed_experiments")
    op.drop_index("ix_synthmed_experiments_generated_version_id", table_name="synthmed_experiments")
    op.drop_index("ix_synthmed_experiments_generated_dataset_id", table_name="synthmed_experiments")
    op.drop_index("ix_synthmed_experiments_source_version_id", table_name="synthmed_experiments")
    op.drop_index("ix_synthmed_experiments_source_dataset_id", table_name="synthmed_experiments")
    op.drop_index("ix_synthmed_experiments_status", table_name="synthmed_experiments")
    op.drop_index("ix_synthmed_experiments_owner_id", table_name="synthmed_experiments")
    op.drop_table("synthmed_experiments")

    op.drop_index("ix_synthmed_snapshot_owner_created", table_name="synthmed_generation_config_snapshots")
    op.drop_index("ix_synthmed_generation_config_snapshots_job_id", table_name="synthmed_generation_config_snapshots")
    op.drop_index("ix_synthmed_generation_config_snapshots_source_dataset_id", table_name="synthmed_generation_config_snapshots")
    op.drop_index("ix_synthmed_generation_config_snapshots_owner_id", table_name="synthmed_generation_config_snapshots")
    op.drop_table("synthmed_generation_config_snapshots")

    op.drop_index("ix_synthmed_lineage_child", table_name="synthmed_dataset_lineage")
    op.drop_index("ix_synthmed_lineage_parent", table_name="synthmed_dataset_lineage")
    op.drop_index("ix_synthmed_dataset_lineage_generated_dataset_id", table_name="synthmed_dataset_lineage")
    op.drop_index("ix_synthmed_dataset_lineage_source_dataset_id", table_name="synthmed_dataset_lineage")
    op.drop_index("ix_synthmed_dataset_lineage_child_resource_id", table_name="synthmed_dataset_lineage")
    op.drop_index("ix_synthmed_dataset_lineage_parent_resource_id", table_name="synthmed_dataset_lineage")
    op.drop_index("ix_synthmed_dataset_lineage_event_type", table_name="synthmed_dataset_lineage")
    op.drop_index("ix_synthmed_dataset_lineage_owner_id", table_name="synthmed_dataset_lineage")
    op.drop_table("synthmed_dataset_lineage")

    op.drop_index("ix_synthmed_version_kind_active", table_name="synthmed_dataset_versions")
    op.drop_index("ix_synthmed_version_owner_created", table_name="synthmed_dataset_versions")
    op.drop_index("ix_synthmed_dataset_versions_logical_dataset_id", table_name="synthmed_dataset_versions")
    op.drop_index("ix_synthmed_dataset_versions_parent_version_id", table_name="synthmed_dataset_versions")
    op.drop_index("ix_synthmed_dataset_versions_generated_dataset_id", table_name="synthmed_dataset_versions")
    op.drop_index("ix_synthmed_dataset_versions_source_dataset_id", table_name="synthmed_dataset_versions")
    op.drop_index("ix_synthmed_dataset_versions_dataset_kind", table_name="synthmed_dataset_versions")
    op.drop_index("ix_synthmed_dataset_versions_owner_id", table_name="synthmed_dataset_versions")
    op.drop_table("synthmed_dataset_versions")
