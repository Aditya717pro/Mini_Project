"""add conditional generation metadata

Revision ID: b2f6d8a9c1e3
Revises: c74e9b1a6d02
Create Date: 2026-11-20 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2f6d8a9c1e3"
down_revision: str | None = "c74e9b1a6d02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("synthmed_generated_datasets") as batch:
        batch.add_column(
            sa.Column(
                "generation_mode",
                sa.String(length=16),
                server_default="Unconditional",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "selected_model",
                sa.String(length=80),
                server_default="CTGAN",
                nullable=False,
            )
        )

    with op.batch_alter_table("synthmed_generation_jobs") as batch:
        batch.add_column(
            sa.Column(
                "generation_mode",
                sa.String(length=16),
                server_default="Unconditional",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "selected_model",
                sa.String(length=80),
                server_default="CTGAN",
                nullable=False,
            )
        )
        batch.add_column(sa.Column("normalized_conditions_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("condition_validation_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("satisfaction_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("synthmed_generation_jobs") as batch:
        batch.drop_column("satisfaction_json")
        batch.drop_column("condition_validation_json")
        batch.drop_column("normalized_conditions_json")
        batch.drop_column("selected_model")
        batch.drop_column("generation_mode")

    with op.batch_alter_table("synthmed_generated_datasets") as batch:
        batch.drop_column("selected_model")
        batch.drop_column("generation_mode")
