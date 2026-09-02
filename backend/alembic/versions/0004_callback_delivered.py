"""add research_jobs.callback_delivered

The completion callback is now delivered at-least-once with retry + backoff.
``callback_delivered`` records whether delivery ultimately succeeded, so an
external reaper can find jobs that carry a callback_url but never acknowledged
delivery and re-send them.

Existing rows default to false (their callbacks predate this column or were
never delivered retroactively).

Revision ID: 0004_callback_delivered
Revises: 0003_cancel_reason
Create Date: 2026-09-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_callback_delivered"
down_revision = "0003_cancel_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_jobs",
        sa.Column(
            "callback_delivered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("research_jobs", "callback_delivered")
