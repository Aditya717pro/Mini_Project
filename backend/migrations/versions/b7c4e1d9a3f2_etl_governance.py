"""etl governance lifecycle

Revision ID: b7c4e1d9a3f2
Revises: 0c33b0405545
Create Date: 2026-11-17 16:30:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'b7c4e1d9a3f2'
down_revision: str | None = '0c33b0405545'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_JOB_STATUS = ('Queued', 'Running', 'Review required', 'Completed', 'Failed')
NEW_JOB_STATUS = (
    'Queued',
    'Profiling',
    'Review required',
    'Approved',
    'Processing',
    'Completed',
    'Failed',
    'Cancelled',
    'Rejected',
)


def upgrade() -> None:
    op.add_column('etl_jobs', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('etl_jobs', sa.Column('approved_by_id', sa.String(length=36), nullable=True))
    op.add_column('etl_jobs', sa.Column('rejection_reason', sa.Text(), nullable=True))

    with op.batch_alter_table('etl_jobs', schema=None) as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.Enum(*OLD_JOB_STATUS, name='jobstatus', native_enum=False, length=32),
            type_=sa.Enum(*NEW_JOB_STATUS, name='jobstatus', native_enum=False, length=32),
            existing_nullable=False,
        )
        batch_op.create_foreign_key(
            'fk_etl_jobs_approved_by_id_users', 'users', ['approved_by_id'], ['id'], ondelete='SET NULL'
        )

    op.execute("UPDATE etl_jobs SET status = 'Processing' WHERE status = 'Running'")

    op.create_table(
        'etl_mapping_decisions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=False),
        sa.Column('proposed_target', sa.String(length=120), nullable=False),
        sa.Column('target', sa.String(length=120), nullable=True),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('decided_by_id', sa.String(length=36), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['decided_by_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['job_id'], ['etl_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'source', name='uq_etl_mapping_decisions_job_source'),
    )
    with op.batch_alter_table('etl_mapping_decisions', schema=None) as batch_op:
        batch_op.create_index('ix_etl_mapping_decisions_job', ['job_id'], unique=False)


def downgrade() -> None:
    op.drop_table('etl_mapping_decisions')

    op.execute("UPDATE etl_jobs SET status = 'Running' WHERE status = 'Processing'")

    with op.batch_alter_table('etl_jobs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_etl_jobs_approved_by_id_users', type_='foreignkey')
        batch_op.alter_column(
            'status',
            existing_type=sa.Enum(*NEW_JOB_STATUS, name='jobstatus', native_enum=False, length=32),
            type_=sa.Enum(*OLD_JOB_STATUS, name='jobstatus', native_enum=False, length=32),
            existing_nullable=False,
        )
    op.drop_column('etl_jobs', 'rejection_reason')
    op.drop_column('etl_jobs', 'approved_by_id')
    op.drop_column('etl_jobs', 'approved_at')
