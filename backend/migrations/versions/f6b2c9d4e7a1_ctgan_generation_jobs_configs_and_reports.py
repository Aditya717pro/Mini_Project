"""ctgan generation jobs configs and reports

Revision ID: f6b2c9d4e7a1
Revises: d4a8c1f0b2e3
Create Date: 2026-11-19 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6b2c9d4e7a1"
down_revision: str | None = "d4a8c1f0b2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "synthmed_generation_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("source_dataset_id", sa.String(length=36), nullable=False),
        sa.Column("generated_dataset_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Queued"),
        sa.Column("model_name", sa.String(length=80), nullable=False, server_default="CTGAN"),
        sa.Column("epochs", sa.Integer(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("requested_record_count", sa.Integer(), nullable=False),
        sa.Column("generated_record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("training_duration_seconds", sa.Float(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_synthmed_job_owner", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_dataset_id"],
            ["synthmed_source_datasets.id"],
            name="fk_synthmed_job_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["generated_dataset_id"],
            ["synthmed_generated_datasets.id"],
            name="fk_synthmed_job_generated",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_synthmed_generation_jobs_owner_id", "synthmed_generation_jobs", ["owner_id"], unique=False)
    op.create_index(
        "ix_synthmed_generation_jobs_source_dataset_id",
        "synthmed_generation_jobs",
        ["source_dataset_id"],
        unique=False,
    )
    op.create_index(
        "ix_synthmed_job_owner_created", "synthmed_generation_jobs", ["owner_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_synthmed_job_status_created", "synthmed_generation_jobs", ["status", "created_at"], unique=False
    )

    op.create_table(
        "synthmed_generation_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["synthmed_generation_jobs.id"], name="fk_synthmed_config_job", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_synthmed_config_owner", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_synthmed_config_job"),
    )
    op.create_index(
        "ix_synthmed_generation_configs_owner_id", "synthmed_generation_configs", ["owner_id"], unique=False
    )

    op.create_table(
        "synthmed_evaluation_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("generated_dataset_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("method", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["generated_dataset_id"],
            ["synthmed_generated_datasets.id"],
            name="fk_synthmed_eval_generated",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["synthmed_generation_jobs.id"], name="fk_synthmed_eval_job", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_synthmed_eval_owner", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "report_type", name="uq_synthmed_eval_job_type"),
    )
    op.create_index("ix_synthmed_evaluation_reports_job_id", "synthmed_evaluation_reports", ["job_id"], unique=False)
    op.create_index(
        "ix_synthmed_evaluation_reports_generated_dataset_id",
        "synthmed_evaluation_reports",
        ["generated_dataset_id"],
        unique=False,
    )
    op.create_index(
        "ix_synthmed_evaluation_reports_owner_id", "synthmed_evaluation_reports", ["owner_id"], unique=False
    )
    op.create_index(
        "ix_synthmed_eval_generated_type",
        "synthmed_evaluation_reports",
        ["generated_dataset_id", "report_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_synthmed_eval_generated_type", table_name="synthmed_evaluation_reports")
    op.drop_index("ix_synthmed_evaluation_reports_owner_id", table_name="synthmed_evaluation_reports")
    op.drop_index("ix_synthmed_evaluation_reports_generated_dataset_id", table_name="synthmed_evaluation_reports")
    op.drop_index("ix_synthmed_evaluation_reports_job_id", table_name="synthmed_evaluation_reports")
    op.drop_table("synthmed_evaluation_reports")

    op.drop_index("ix_synthmed_generation_configs_owner_id", table_name="synthmed_generation_configs")
    op.drop_table("synthmed_generation_configs")

    op.drop_index("ix_synthmed_job_status_created", table_name="synthmed_generation_jobs")
    op.drop_index("ix_synthmed_job_owner_created", table_name="synthmed_generation_jobs")
    op.drop_index("ix_synthmed_generation_jobs_source_dataset_id", table_name="synthmed_generation_jobs")
    op.drop_index("ix_synthmed_generation_jobs_owner_id", table_name="synthmed_generation_jobs")
    op.drop_table("synthmed_generation_jobs")
