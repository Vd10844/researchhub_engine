"""create research_jobs and research_documents

Revision ID: 0001_research_tables
Revises:
Create Date: 2026-08-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_research_tables"
down_revision = "0002_dev_base_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_doc_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "completed", "partial", "failed",
                    "cancelling", "cancelled", name="research_job_status_enum"),
            nullable=False,
        ),
        sa.Column("total_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancelled_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("callback_url", sa.String(length=2048), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "jsonb_array_length(requested_doc_types) > 0",
            name="ck_research_job_nonempty_doc_types",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_research_job_idempotency_per_tenant",
        ),
    )
    op.create_index(
        "ix_research_jobs_tenant_id", "research_jobs", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_research_jobs_order_id", "research_jobs", ["order_id"], unique=False
    )
    op.create_index(
        "ix_research_jobs_status", "research_jobs", ["status"], unique=False
    )

    op.create_table(
        "research_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doc_type", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "fetching", "fetched", "uploading", "uploaded",
                    "failed", "skipped", name="research_doc_status_enum"),
            nullable=False,
        ),
        sa.Column(
            "source_outcome",
            sa.Enum("auto", "link_only", "blocked", "broken",
                    "retryable", "manual_review", name="source_outcome_enum"),
            nullable=True,
        ),
        sa.Column(
            "confidence",
            sa.Enum("high", "medium", "low", "none", name="confidence_enum"),
            nullable=True,
        ),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("order_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("link", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column("link_label", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_file_id"], ["order_files.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "doc_type", name="uq_research_doc_per_job_type"),
    )
    op.create_index(
        "ix_research_documents_job_id", "research_documents", ["job_id"], unique=False
    )
    op.create_index(
        "ix_research_documents_order_id", "research_documents", ["order_id"], unique=False
    )
    op.create_index(
        "ix_research_documents_status", "research_documents", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_table("research_documents")
    op.drop_table("research_jobs")
    op.execute("DROP TYPE IF EXISTS research_job_status_enum")
    op.execute("DROP TYPE IF EXISTS research_doc_status_enum")
    op.execute("DROP TYPE IF EXISTS source_outcome_enum")
    op.execute("DROP TYPE IF EXISTS confidence_enum")