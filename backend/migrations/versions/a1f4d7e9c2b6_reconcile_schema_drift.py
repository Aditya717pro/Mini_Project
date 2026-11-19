"""reconcile alembic and model schema drift

Revision ID: a1f4d7e9c2b6
Revises: f6b2c9d4e7a1
Create Date: 2026-11-19 13:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1f4d7e9c2b6"
down_revision: str | None = "f6b2c9d4e7a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("etl_mapping_decisions", schema=None) as batch_op:
        batch_op.drop_constraint("uq_etl_mapping_decisions_job_source", type_="unique")
        batch_op.create_index("uq_etl_mapping_decisions_job_source", ["job_id", "source"], unique=True)
    op.create_index(
        "ix_synthmed_generation_jobs_status",
        "synthmed_generation_jobs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_synthmed_generation_jobs_status", table_name="synthmed_generation_jobs")
    with op.batch_alter_table("etl_mapping_decisions", schema=None) as batch_op:
        batch_op.drop_index("uq_etl_mapping_decisions_job_source")
        batch_op.create_unique_constraint("uq_etl_mapping_decisions_job_source", ["job_id", "source"])
