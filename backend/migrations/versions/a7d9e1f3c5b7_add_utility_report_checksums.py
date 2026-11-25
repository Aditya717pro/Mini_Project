"""add utility report checksums

Revision ID: a7d9e1f3c5b7
Revises: f1a2b3c4d5e6
Create Date: 2026-11-23 18:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "a7d9e1f3c5b7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("synthmed_utility_evaluations") as batch_op:
        batch_op.add_column(sa.Column("report_sha256", sa.String(length=64), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("report_csv_sha256", sa.String(length=64), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("report_pdf_sha256", sa.String(length=64), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("synthmed_utility_evaluations") as batch_op:
        batch_op.drop_column("report_pdf_sha256")
        batch_op.drop_column("report_csv_sha256")
        batch_op.drop_column("report_sha256")
