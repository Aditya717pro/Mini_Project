"""add synthmed comparison history

Revision ID: c74e9b1a6d02
Revises: a1f4d7e9c2b6
Create Date: 2026-11-20 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c74e9b1a6d02"
down_revision: str | None = "a1f4d7e9c2b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "synthmed_comparisons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("source_dataset_id", sa.String(length=36), nullable=False),
        sa.Column("generated_dataset_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=250), server_default=sa.text("''"), nullable=False),
        sa.Column("method", sa.String(length=120), server_default=sa.text("''"), nullable=False),
        sa.Column("summary_score", sa.Float(), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("file_path", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["generated_dataset_id"], ["synthmed_generated_datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_dataset_id"], ["synthmed_source_datasets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_synthmed_comparison_owner_created",
        "synthmed_comparisons",
        ["owner_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_synthmed_comparison_generated_created",
        "synthmed_comparisons",
        ["generated_dataset_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_synthmed_comparisons_owner_id",
        "synthmed_comparisons",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        "ix_synthmed_comparisons_source_dataset_id",
        "synthmed_comparisons",
        ["source_dataset_id"],
        unique=False,
    )
    op.create_index(
        "ix_synthmed_comparisons_generated_dataset_id",
        "synthmed_comparisons",
        ["generated_dataset_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_synthmed_comparisons_generated_dataset_id", table_name="synthmed_comparisons")
    op.drop_index("ix_synthmed_comparisons_source_dataset_id", table_name="synthmed_comparisons")
    op.drop_index("ix_synthmed_comparisons_owner_id", table_name="synthmed_comparisons")
    op.drop_index("ix_synthmed_comparison_generated_created", table_name="synthmed_comparisons")
    op.drop_index("ix_synthmed_comparison_owner_created", table_name="synthmed_comparisons")
    op.drop_table("synthmed_comparisons")
