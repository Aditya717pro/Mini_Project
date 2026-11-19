"""initial schema

Revision ID: 0c33b0405545
Revises:
Create Date: 2026-11-17 11:15:38.651859

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0c33b0405545"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("hashed_password", sa.String(length=500), nullable=False),
        sa.Column(
            "role",
            sa.Enum("Administrator", "Researcher", "Contributor", name="userrole", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("organisation", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)
        batch_op.create_index("ix_users_role_active", ["role", "is_active"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_audit_logs_actor_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.create_index("ix_audit_logs_actor_created", ["actor_id", "created_at"], unique=False)
        batch_op.create_index("ix_audit_logs_resource", ["resource_type", "resource_id"], unique=False)

    op.create_table(
        "datasets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=100), nullable=False),
        sa.Column(
            "access_classification",
            sa.Enum("Open", "Controlled", "Restricted", name="accessclassification", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "Processing",
                "Pending review",
                "Changes requested",
                "Available",
                "Failed",
                name="datasetstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "format", sa.Enum("CSV", "XLSX", "JSON", name="fileformat", native_enum=False, length=8), nullable=False
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=False),
        sa.Column("missing_rate", sa.Float(), nullable=False),
        sa.Column("duplicate_rate", sa.Float(), nullable=False),
        sa.Column("research_task", sa.String(length=250), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.String(length=36), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_id"], ["users.id"], name=op.f("fk_datasets_approved_by_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_datasets_owner_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
    )
    with op.batch_alter_table("datasets", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_datasets_checksum_sha256"), ["checksum_sha256"], unique=False)
        batch_op.create_index("ix_datasets_domain_status", ["domain", "status"], unique=False)
        batch_op.create_index("ix_datasets_owner_created", ["owner_id", "created_at"], unique=False)

    op.create_table(
        "access_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("requester_id", sa.String(length=36), nullable=False),
        sa.Column("project_title", sa.String(length=250), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("Pending", "Approved", "Rejected", "Withdrawn", name="requeststatus", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("decided_by_id", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name=op.f("fk_access_requests_dataset_id_datasets"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"], ["users.id"], name=op.f("fk_access_requests_decided_by_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"], ["users.id"], name=op.f("fk_access_requests_requester_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_requests")),
    )
    with op.batch_alter_table("access_requests", schema=None) as batch_op:
        batch_op.create_index("ix_access_requests_dataset_status", ["dataset_id", "status"], unique=False)
        batch_op.create_index("ix_access_requests_requester_status", ["requester_id", "status"], unique=False)

    op.create_table(
        "dataset_metadata",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("age_range", sa.String(length=100), nullable=False),
        sa.Column("geography", sa.JSON(), nullable=False),
        sa.Column("study_design", sa.String(length=120), nullable=False),
        sa.Column("license", sa.String(length=100), nullable=False),
        sa.Column("ethics_approved", sa.Boolean(), nullable=False),
        sa.Column("data_dictionary_available", sa.Boolean(), nullable=False),
        sa.Column("consent_scope", sa.String(length=200), nullable=False),
        sa.Column("intended_tasks", sa.JSON(), nullable=False),
        sa.Column("label_column", sa.String(length=120), nullable=True),
        sa.Column("collection_period", sa.String(length=120), nullable=False),
        sa.Column("additional_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name=op.f("fk_dataset_metadata_dataset_id_datasets"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_metadata")),
        sa.UniqueConstraint("dataset_id", name=op.f("uq_dataset_metadata_dataset_id")),
    )
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(length=20), nullable=False),
        sa.Column("raw_file_path", sa.Text(), nullable=False),
        sa.Column("processed_file_path", sa.Text(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("transformation_log_json", sa.JSON(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name=op.f("fk_dataset_versions_dataset_id_datasets"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_versions")),
        sa.UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version_number"),
    )
    with op.batch_alter_table("dataset_versions", schema=None) as batch_op:
        batch_op.create_index("ix_dataset_versions_dataset_current", ["dataset_id", "is_current"], unique=False)

    op.create_table(
        "etl_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_version_id", sa.String(length=36), nullable=False),
        sa.Column("initiated_by_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "Queued",
                "Running",
                "Review required",
                "Completed",
                "Failed",
                name="jobstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("current_stage", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("suggested_mapping_json", sa.JSON(), nullable=False),
        sa.Column("approved_mapping_json", sa.JSON(), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("rows_in", sa.Integer(), nullable=False),
        sa.Column("rows_out", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name=op.f("fk_etl_jobs_dataset_id_datasets"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_etl_jobs_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_id"], ["users.id"], name=op.f("fk_etl_jobs_initiated_by_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_etl_jobs")),
    )
    with op.batch_alter_table("etl_jobs", schema=None) as batch_op:
        batch_op.create_index("ix_etl_jobs_dataset_status", ["dataset_id", "status"], unique=False)
        batch_op.create_index("ix_etl_jobs_status_created", ["status", "created_at"], unique=False)

    op.create_table(
        "representativeness_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_version_id", sa.String(length=36), nullable=False),
        sa.Column("age_bands_json", sa.JSON(), nullable=False),
        sa.Column("pregnancy_stages_json", sa.JSON(), nullable=False),
        sa.Column("paediatric_groups_json", sa.JSON(), nullable=False),
        sa.Column("geography_json", sa.JSON(), nullable=False),
        sa.Column("missing_attributes_json", sa.JSON(), nullable=False),
        sa.Column("coverage_notes_json", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_representativeness_reports_dataset_id_datasets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_representativeness_reports_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_representativeness_reports")),
        sa.UniqueConstraint("dataset_version_id", name=op.f("uq_representativeness_reports_dataset_version_id")),
    )
    op.create_table(
        "etl_job_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["etl_jobs.id"], name=op.f("fk_etl_job_logs_job_id_etl_jobs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_etl_job_logs")),
    )
    with op.batch_alter_table("etl_job_logs", schema=None) as batch_op:
        batch_op.create_index("ix_etl_job_logs_job_created", ["job_id", "created_at"], unique=False)

    op.create_table(
        "quality_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_version_id", sa.String(length=36), nullable=False),
        sa.Column("etl_job_id", sa.String(length=36), nullable=True),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("formula_version", sa.String(length=20), nullable=False),
        sa.Column("dimensions_json", sa.JSON(), nullable=False),
        sa.Column("findings_json", sa.JSON(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name=op.f("fk_quality_reports_dataset_id_datasets"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_quality_reports_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["etl_job_id"], ["etl_jobs.id"], name=op.f("fk_quality_reports_etl_job_id_etl_jobs"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quality_reports")),
        sa.UniqueConstraint("dataset_version_id", "formula_version", name="uq_quality_report_version_formula"),
    )
    op.create_table(
        "readiness_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_version_id", sa.String(length=36), nullable=False),
        sa.Column("quality_report_id", sa.String(length=36), nullable=True),
        sa.Column("research_task", sa.Text(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=40), nullable=False),
        sa.Column("categories_json", sa.JSON(), nullable=False),
        sa.Column("limitations_json", sa.JSON(), nullable=False),
        sa.Column("recommendations_json", sa.JSON(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name=op.f("fk_readiness_reports_dataset_id_datasets"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_readiness_reports_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["quality_report_id"],
            ["quality_reports.id"],
            name=op.f("fk_readiness_reports_quality_report_id_quality_reports"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_readiness_reports")),
        sa.UniqueConstraint("dataset_version_id", "research_task", name="uq_readiness_report_version_task"),
    )


def downgrade() -> None:
    op.drop_table("readiness_reports")
    op.drop_table("quality_reports")
    with op.batch_alter_table("etl_job_logs", schema=None) as batch_op:
        batch_op.drop_index("ix_etl_job_logs_job_created")

    op.drop_table("etl_job_logs")
    op.drop_table("representativeness_reports")
    with op.batch_alter_table("etl_jobs", schema=None) as batch_op:
        batch_op.drop_index("ix_etl_jobs_status_created")
        batch_op.drop_index("ix_etl_jobs_dataset_status")

    op.drop_table("etl_jobs")
    with op.batch_alter_table("dataset_versions", schema=None) as batch_op:
        batch_op.drop_index("ix_dataset_versions_dataset_current")

    op.drop_table("dataset_versions")
    op.drop_table("dataset_metadata")
    with op.batch_alter_table("access_requests", schema=None) as batch_op:
        batch_op.drop_index("ix_access_requests_requester_status")
        batch_op.drop_index("ix_access_requests_dataset_status")

    op.drop_table("access_requests")
    with op.batch_alter_table("datasets", schema=None) as batch_op:
        batch_op.drop_index("ix_datasets_owner_created")
        batch_op.drop_index("ix_datasets_domain_status")
        batch_op.drop_index(batch_op.f("ix_datasets_checksum_sha256"))

    op.drop_table("datasets")
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_logs_resource")
        batch_op.drop_index("ix_audit_logs_actor_created")

    op.drop_table("audit_logs")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_role_active")
        batch_op.drop_index(batch_op.f("ix_users_email"))

    op.drop_table("users")
