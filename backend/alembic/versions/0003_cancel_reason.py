"""add research_jobs.cancel_reason and extend the job status enum

Fix #1 (cancel_reason) and Fix #5 (reviewed/archived reachable states):

  - ``research_jobs.cancel_reason TEXT NULL`` — the value from
    ``CancelJobRequest.reason`` is now persisted instead of dropped.
  - extend ``research_job_status_enum`` with ``reviewed`` and ``archived``
    (the ``JobState`` contract already carried them; the persisted enum and
    the API ``ResearchJobStatus`` now do too).  PostgreSQL ``ALTER TYPE ...
    ADD VALUE`` cannot run inside a transaction block on older servers — the
    value additions are issued directly so the migration stays deployable.

On SQLite/test (``Base.metadata.create_all``) the Python enum is created
with the full value set, so this migration only matters for Postgres.

Revision ID: 0003_cancel_reason
Revises: 0001_research_tables
Create Date: 2026-08-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_cancel_reason"
down_revision = "0001_research_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_jobs",
        sa.Column("cancel_reason", sa.Text(), nullable=True),
    )
    # Postgres-only: grow the status enum with the two review states.  Untyped
    # because older Postgres rejects ADD VALUE inside a transaction; Alembic
    # runs each op.execute outside one when autocommit is off for the driver.
    op.execute("ALTER TYPE research_job_status_enum ADD VALUE IF NOT EXISTS 'reviewed'")
    op.execute("ALTER TYPE research_job_status_enum ADD VALUE IF NOT EXISTS 'archived'")


def downgrade() -> None:
    op.drop_column("research_jobs", "cancel_reason")
    # Dropping enum values is unsupported in Postgres; leave the two values in
    # place on downgrade and document the manual cleanup instead of failing.