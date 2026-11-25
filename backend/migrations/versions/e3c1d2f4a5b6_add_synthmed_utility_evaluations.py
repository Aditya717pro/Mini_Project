"""add synthmed utility evaluations

Revision ID: e3c1d2f4a5b6
Revises: b2f6d8a9c1e3
Create Date: 2026-11-22 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3c1d2f4a5b6"
down_revision: str | None = "b2f6d8a9c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "synthmed_utility_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("source_dataset_id", sa.String(length=36), nullable=False),
        sa.Column("generated_dataset_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Queued"),
        sa.Column("evaluation_name", sa.String(length=250), nullable=False, server_default=sa.text("''")),
        sa.Column("evaluation_type", sa.String(length=16), nullable=False, server_default="TSTR"),
        sa.Column("model_name", sa.String(length=120), nullable=False, server_default=sa.text("''")),
        sa.Column("target_column", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("feature_columns_json", sa.JSON(), nullable=False),
        sa.Column("train_test_split", sa.JSON(), nullable=False),
        sa.Column("preprocessing_config_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("comparison_summary_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("report_path", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("report_csv_path", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("report_pdf_path", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["generated_dataset_id"], ["synthmed_generated_datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_dataset_id"], ["synthmed_source_datasets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_synthmed_utility_owner_created", "synthmed_utility_evaluations", ["owner_id", "created_at"], unique=False)
    op.create_index("ix_synthmed_utility_status_created", "synthmed_utility_evaluations", ["status", "created_at"], unique=False)
    op.create_index("ix_synthmed_utility_generated_created", "synthmed_utility_evaluations", ["generated_dataset_id", "created_at"], unique=False)
    op.create_index("ix_synthmed_utility_evaluations_owner_id", "synthmed_utility_evaluations", ["owner_id"], unique=False)
    op.create_index("ix_synthmed_utility_evaluations_source_dataset_id", "synthmed_utility_evaluations", ["source_dataset_id"], unique=False)
    op.create_index("ix_synthmed_utility_evaluations_generated_dataset_id", "synthmed_utility_evaluations", ["generated_dataset_id"], unique=False)
    op.create_index("ix_synthmed_utility_evaluations_status", "synthmed_utility_evaluations", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_synthmed_utility_evaluations_status", table_name="synthmed_utility_evaluations")
    op.drop_index("ix_synthmed_utility_evaluations_generated_dataset_id", table_name="synthmed_utility_evaluations")
    op.drop_index("ix_synthmed_utility_evaluations_source_dataset_id", table_name="synthmed_utility_evaluations")
    op.drop_index("ix_synthmed_utility_evaluations_owner_id", table_name="synthmed_utility_evaluations")
    op.drop_index("ix_synthmed_utility_generated_created", table_name="synthmed_utility_evaluations")
    op.drop_index("ix_synthmed_utility_status_created", table_name="synthmed_utility_evaluations")
    op.drop_index("ix_synthmed_utility_owner_created", table_name="synthmed_utility_evaluations")
    op.drop_table("synthmed_utility_evaluations")
