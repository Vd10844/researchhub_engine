"""Research engine database models — ``research_jobs`` and ``research_documents``.

These models live in ``app.engine.models`` and will be migrated via Alembic
into the parent's Postgres. They follow the parent's conventions:
  - UUID primary key (via Base)
  - TenantMixin, AuditMixin, TimestampMixin where appropriate
  - SQLAlchemy 2.0 ``Mapped[]`` style
  - ``__versioned__: dict = {}`` for sqlalchemy-history

The tables:
  - ``research_jobs`` — one row per research run (created by POST /research/jobs)
  - ``research_documents`` — one row per document type within a job
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import AuditMixin, SoftDeleteMixin, TenantMixin, TimestampMixin
from app.engine.contracts import (
    Confidence,
    JobState,
    SourceOutcome,
)
from app.engine.schemas import ResearchDocStatus, ResearchJobStatus

if TYPE_CHECKING:
    from app.modules.evidence.models import File
    from app.modules.orders.models import Order


# ------------------------------------------------------------------ models


class ResearchJob(
    Base,
    TenantMixin,
    AuditMixin,
    TimestampMixin,
    SoftDeleteMixin,
):
    """One research run for an order.

    Created when the user clicks "Auto-Fetch All" or "Auto Fetch" on specific
    document types. The Celery worker transitions it through
    ``queued → running → completed | partial | failed | cancelled``.
    """

    __tablename__ = "research_jobs"
    __versioned__: dict = {}

    __table_args__ = (
        # One active (non-deleted) job per idempotency key per tenant.
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_research_job_idempotency_per_tenant",
        ),
        # A job cannot have zero document types.
        CheckConstraint(
            "jsonb_array_length(requested_doc_types) > 0",
            name="ck_research_job_nonempty_doc_types",
        ),
    )

    # --- foreign keys ------------------------------------------------

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Order this research job belongs to.",
    )

    # --- identity / idempotency --------------------------------------

    idempotency_key: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Client-generated or server-generated idempotency key.",
    )

    # --- configuration -----------------------------------------------

    requested_doc_types: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment='Ordered list of document types requested, e.g. ["PARCEL_RECORD", "FLOOD"].',
    )

    # --- lifecycle status --------------------------------------------

    status: Mapped[ResearchJobStatus] = mapped_column(
        SQLEnum(
            ResearchJobStatus,
            name="research_job_status_enum",
            create_type=True,
        ),
        default=ResearchJobStatus.queued,
        nullable=False,
        index=True,
        comment="Current lifecycle status of this research job.",
    )

    # --- progress counters (denormalized for fast listing queries) ----

    total_documents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total documents in this job.",
    )
    fetched_documents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Documents successfully fetched.",
    )
    uploaded_documents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Documents uploaded to S3 and linked to order.",
    )
    failed_documents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Documents that failed (adapter error).",
    )
    cancelled_documents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Documents skipped due to job cancellation.",
    )

    # --- timestamps --------------------------------------------------

    started_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="When the Celery worker started processing.",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="When the job reached a terminal state.",
    )

    # --- error (top-level, when status == failed) --------------------

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Top-level error code when the job failed.",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Top-level error message when the job failed.",
    )

    # --- callbacks ---------------------------------------------------

    callback_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        comment="Optional URL to POST job completion status to.",
    )

    # --- relationships -----------------------------------------------

    order: Mapped["Order"] = relationship()
    documents: Mapped[list["ResearchDocument"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ResearchDocument(Base, TimestampMixin, SoftDeleteMixin):
    """Per-document progress within a research job.

    One row per requested document type. Tracks the full lifecycle:
    ``queued → fetching → fetched → uploading → uploaded | failed | skipped``
    """

    __tablename__ = "research_documents"
    __versioned__: dict = {}

    __table_args__ = (
        # One active document row per job per doc_type.
        UniqueConstraint(
            "job_id",
            "doc_type",
            name="uq_research_doc_per_job_type",
        ),
    )

    # --- foreign keys ------------------------------------------------

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent research job.",
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Denormalized order reference for direct queries.",
    )

    # --- document type -----------------------------------------------

    doc_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Document type, e.g. 'PARCEL_RECORD'.",
    )

    # --- lifecycle status --------------------------------------------

    status: Mapped[ResearchDocStatus] = mapped_column(
        SQLEnum(
            ResearchDocStatus,
            name="research_doc_status_enum",
            create_type=True,
        ),
        default=ResearchDocStatus.queued,
        nullable=False,
        index=True,
        comment="Current status of this document.",
    )

    # --- outcome / confidence (set after fetch) ----------------------

    source_outcome: Mapped[SourceOutcome | None] = mapped_column(
        SQLEnum(
            SourceOutcome,
            name="source_outcome_enum",
            create_type=True,
        ),
        nullable=True,
        comment="Why the source returned what it did.",
    )
    confidence: Mapped[Confidence | None] = mapped_column(
        SQLEnum(
            Confidence,
            name="confidence_enum",
            create_type=True,
        ),
        nullable=True,
        comment="How sure the engine is that this pertains to the property.",
    )

    # --- file links (set after S3 upload) ----------------------------

    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id"),
        nullable=True,
        comment="Evidence module File.id (set after S3 upload).",
    )
    order_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("order_files.id"),
        nullable=True,
        comment="OrderFile.id linking this file to the order.",
    )

    # --- display fields ----------------------------------------------

    summary: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
        comment="One-line summary of what was found.",
    )
    link: Mapped[str] = mapped_column(
        String(2048),
        default="",
        nullable=False,
        comment="Fallback deep-link when auto-fetch is not available.",
    )
    link_label: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="Display text for the link button.",
    )

    # --- provenance / warnings (JSONB) -------------------------------

    provenance: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="Audit trail: every source hit that contributed to this document.",
    )
    warnings: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="Per-document warnings.",
    )

    # --- error (when status == failed) -------------------------------

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Structured error code when the document failed.",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable error when the document failed.",
    )
    retryable: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this document can be retried.",
    )

    # --- retry tracking ----------------------------------------------

    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of retry attempts for this document.",
    )

    # --- timestamps --------------------------------------------------

    fetched_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Timestamp when the fetch completed.",
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Timestamp when the S3 upload completed.",
    )

    # --- relationships -----------------------------------------------

    job: Mapped["ResearchJob"] = relationship(back_populates="documents")
    file: Mapped["File"] = relationship()
