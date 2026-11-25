"""add dataset provenance fields

Revision ID: d7f0a1b2c3e4
Revises: c4e8f1a2b3d9
Create Date: 2026-11-24 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d7f0a1b2c3e4"
down_revision = "c4e8f1a2b3d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("datasets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("origin", sa.String(length=24), nullable=False, server_default="Original"))
        batch_op.add_column(sa.Column("source_generated_dataset_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("source_repository_dataset_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("generation_job_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("generation_model", sa.String(length=80), nullable=True))
        batch_op.add_column(
            sa.Column("provenance_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch_op.create_foreign_key(
            "fk_datasets_source_generated_dataset_id_synthmed_generated_datasets",
            "synthmed_generated_datasets",
            ["source_generated_dataset_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_datasets_source_repository_dataset_id_datasets",
            "datasets",
            ["source_repository_dataset_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_datasets_source_generated_dataset_id", ["source_generated_dataset_id"])
        batch_op.create_index("ix_datasets_source_repository_dataset_id", ["source_repository_dataset_id"])
        batch_op.create_index("ix_datasets_generation_job_id", ["generation_job_id"])
        batch_op.create_index(
            "uq_datasets_source_generated_dataset_id", ["source_generated_dataset_id"], unique=True
        )


def downgrade() -> None:
    with op.batch_alter_table("datasets", schema=None) as batch_op:
        batch_op.drop_index("uq_datasets_source_generated_dataset_id")
        batch_op.drop_index("ix_datasets_generation_job_id")
        batch_op.drop_index("ix_datasets_source_repository_dataset_id")
        batch_op.drop_index("ix_datasets_source_generated_dataset_id")
        batch_op.drop_constraint(
            "fk_datasets_source_repository_dataset_id_datasets", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_datasets_source_generated_dataset_id_synthmed_generated_datasets", type_="foreignkey"
        )
        batch_op.drop_column("provenance_json")
        batch_op.drop_column("generation_model")
        batch_op.drop_column("generation_job_id")
        batch_op.drop_column("source_repository_dataset_id")
        batch_op.drop_column("source_generated_dataset_id")
        batch_op.drop_column("origin")
