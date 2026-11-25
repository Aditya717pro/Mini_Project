"""create research reports

Revision ID: c4e8f1a2b3d9
Revises: a7d9e1f3c5b7
Create Date: 2026-11-23 23:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c4e8f1a2b3d9"
down_revision = "a7d9e1f3c5b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=64), nullable=False),
        sa.Column("report_type", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=True),
        sa.Column("dataset_version_id", sa.String(length=36), nullable=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        sa.Column("comparison_id", sa.String(length=36), nullable=True),
        sa.Column("privacy_evaluation_id", sa.String(length=36), nullable=True),
        sa.Column("utility_evaluation_id", sa.String(length=36), nullable=True),
        sa.Column("generation_job_id", sa.String(length=36), nullable=True),
        sa.Column("generated_dataset_id", sa.String(length=36), nullable=True),
        sa.Column("report_file_path", sa.Text(), nullable=False),
        sa.Column("file_checksum", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("template_version", sa.String(length=32), nullable=False),
        sa.Column("report_data_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_research_reports_owner_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["synthmed_experiments.id"], name="fk_research_reports_experiment_id_synthmed_experiments", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["comparison_id"], ["synthmed_comparisons.id"], name="fk_research_reports_comparison_id_synthmed_comparisons", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["privacy_evaluation_id"],
            ["synthmed_evaluation_reports.id"],
            name="fk_research_reports_privacy_evaluation_id_synthmed_evaluation_reports",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["utility_evaluation_id"],
            ["synthmed_utility_evaluations.id"],
            name="fk_research_reports_utility_evaluation_id_synthmed_utility_evaluations",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_reports"),
        sa.UniqueConstraint("report_id", name="uq_research_reports_report_id"),
    )
    op.create_index("ix_research_reports_report_id", "research_reports", ["report_id"], unique=True)
    op.create_index("ix_research_reports_report_type", "research_reports", ["report_type"])
    op.create_index("ix_research_reports_owner_id", "research_reports", ["owner_id"])
    op.create_index("ix_research_reports_dataset_id", "research_reports", ["dataset_id"])
    op.create_index("ix_research_reports_dataset_version_id", "research_reports", ["dataset_version_id"])
    op.create_index("ix_research_reports_generation_job_id", "research_reports", ["generation_job_id"])
    op.create_index("ix_research_reports_generated_dataset_id", "research_reports", ["generated_dataset_id"])
    op.create_index("ix_research_reports_status", "research_reports", ["status"])
    op.create_index("ix_research_reports_owner_created", "research_reports", ["owner_id", "created_at"])
    op.create_index("ix_research_reports_type_created", "research_reports", ["report_type", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_research_reports_type_created", table_name="research_reports")
    op.drop_index("ix_research_reports_owner_created", table_name="research_reports")
    op.drop_index("ix_research_reports_status", table_name="research_reports")
    op.drop_index("ix_research_reports_generated_dataset_id", table_name="research_reports")
    op.drop_index("ix_research_reports_generation_job_id", table_name="research_reports")
    op.drop_index("ix_research_reports_dataset_version_id", table_name="research_reports")
    op.drop_index("ix_research_reports_dataset_id", table_name="research_reports")
    op.drop_index("ix_research_reports_owner_id", table_name="research_reports")
    op.drop_index("ix_research_reports_report_type", table_name="research_reports")
    op.drop_index("ix_research_reports_report_id", table_name="research_reports")
    op.drop_table("research_reports")
