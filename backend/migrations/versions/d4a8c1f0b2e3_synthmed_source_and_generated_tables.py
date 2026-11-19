"""synthmed source and generated dataset tables

Revision ID: d4a8c1f0b2e3
Revises: c9f2a7b41e60
Create Date: 2026-11-18 22:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4a8c1f0b2e3"
down_revision: str | None = "c9f2a7b41e60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "synthmed_source_datasets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_name", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("file_format", sa.String(length=16), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("column_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upload_status", sa.String(length=32), nullable=False, server_default="Uploaded"),
        sa.Column("content_type", sa.String(length=120), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_synthmed_source_owner", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_synthmed_source_datasets_owner_id", "synthmed_source_datasets", ["owner_id"], unique=False)
    op.create_index(
        "ix_synthmed_source_owner_created", "synthmed_source_datasets", ["owner_id", "created_at"], unique=False
    )

    op.create_table(
        "synthmed_generated_datasets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("source_dataset_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_name", sa.String(length=250), nullable=False),
        sa.Column("source_dataset_name", sa.String(length=250), nullable=False),
        sa.Column("generation_method", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("column_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_format", sa.String(length=16), nullable=False, server_default="CSV"),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("stored_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Completed"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_synthmed_generated_owner", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_dataset_id"],
            ["synthmed_source_datasets.id"],
            name="fk_synthmed_generated_source",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_synthmed_generated_datasets_owner_id", "synthmed_generated_datasets", ["owner_id"], unique=False
    )
    op.create_index(
        "ix_synthmed_generated_datasets_source_dataset_id",
        "synthmed_generated_datasets",
        ["source_dataset_id"],
        unique=False,
    )
    op.create_index(
        "ix_synthmed_generated_owner_created",
        "synthmed_generated_datasets",
        ["owner_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_synthmed_generated_owner_created", table_name="synthmed_generated_datasets")
    op.drop_index("ix_synthmed_generated_datasets_source_dataset_id", table_name="synthmed_generated_datasets")
    op.drop_index("ix_synthmed_generated_datasets_owner_id", table_name="synthmed_generated_datasets")
    op.drop_table("synthmed_generated_datasets")

    op.drop_index("ix_synthmed_source_owner_created", table_name="synthmed_source_datasets")
    op.drop_index("ix_synthmed_source_datasets_owner_id", table_name="synthmed_source_datasets")
    op.drop_table("synthmed_source_datasets")
