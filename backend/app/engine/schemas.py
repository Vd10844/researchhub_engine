"""Research Engine API schemas — request/response contracts for /api/v1/research/*.

These are the contracts frontend and backend teams code against. They are
exported as OpenAPI + JSON Schema via ``scripts/export_contracts.py``.

Design principles:
  - Every field is documented; no ambiguous types.
  - Error responses use a single envelope: ``{ error: { code, message, details? } }``.
  - Success responses use the engine's envelope: ``{ data: ... }``. At parent
    integration this is rewired to the parent's ``StandardResponse``
    (``{ message, status_code, data }``) via ``UnifiedAPIRoute`` — the field
    shape below is unchanged either way.
  - Idempotency is supported via ``X-Idempotency-Key`` header.
  - Per-document progress is tracked in ``documents[]`` on the job response.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

from app.engine.contracts import (
    Confidence,
    ErrorInfo,
    ProvenanceRecord,
    SourceOutcome,
    StepStatus,
)

T = TypeVar("T")


# ======================================================================
# ENUMS
# ======================================================================


class ResearchJobStatus(str, enum.Enum):
    """Lifecycle of a research job — persisted in ``research_jobs.status``.

    Transitions:
      queued   → running          (Celery worker picks it up)
      running  → completed        (all adapters returned designed outcome)
      running  → partial          (≥1 adapter hit an unexpected failure)
      running  → failed           (context resolution failed — no geocode, no parcel)
      queued   → cancelled        (cancel requested before the worker started)
      running  → cancelling       (cancel requested mid-run; worker drains then finalizes)
      cancelling → cancelled      (worker observed the cancellation and drained)
      completed | partial → reviewed   (human confirms the document set)
      reviewed → archived         (retention — hidden from the default list)
    """

    queued = "queued"
    running = "running"
    completed = "completed"
    partial = "partial"
    failed = "failed"
    cancelling = "cancelling"
    cancelled = "cancelled"
    reviewed = "reviewed"
    archived = "archived"


class ResearchDocStatus(str, enum.Enum):
    """Per-document progress — tracked in ``research_documents.status``.

    Transitions:
      queued    → fetching        (worker starts this document)
      fetching  → fetched         (orchestrator returned data)
      fetching  → failed          (adapter error after retries)
      fetched   → uploading       (S3 upload started)
      uploading → uploaded        (S3 upload complete + OrderFile created)
      uploading → failed          (S3 upload error)
      queued    → skipped         (doc type not applicable to this order)
    """

    queued = "queued"
    fetching = "fetching"
    fetched = "fetched"
    uploading = "uploading"
    uploaded = "uploaded"
    failed = "failed"
    skipped = "skipped"


class ResearchErrorCode(str, enum.Enum):
    """Machine-readable error codes for the ``error.code`` field.

    Grouped by source:
      - Client errors (4xx): bad input, conflicts, not found
      - Document errors (per-document): adapter-specific failures
      - System errors (5xx): internal, rate-limited, timeout
    """

    # Client errors (4xx)
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    ORDER_NOT_RESEARCHABLE = "ORDER_NOT_RESEARCHABLE"
    INVALID_DOC_TYPES = "INVALID_DOC_TYPES"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_NOT_RETRYABLE = "JOB_NOT_RETRYABLE"
    JOB_NOT_CANCELLABLE = "JOB_NOT_CANCELLABLE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    MISSING_ADDRESS = "MISSING_ADDRESS"

    # Document errors (per-document)
    GEOCODE_FAILED = "GEOCODE_FAILED"
    PARCEL_NOT_FOUND = "PARCEL_NOT_FOUND"
    DEED_UNAVAILABLE = "DEED_UNAVAILABLE"
    PLAT_UNAVAILABLE = "PLAT_UNAVAILABLE"
    FLOOD_UNAVAILABLE = "FLOOD_UNAVAILABLE"
    APPRAISER_UNAVAILABLE = "APPRAISER_UNAVAILABLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    S3_UPLOAD_FAILED = "S3_UPLOAD_FAILED"
    TIMEOUT = "TIMEOUT"

    # System errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMITED = "RATE_LIMITED"


# ======================================================================
# REQUEST SCHEMAS
# ======================================================================


class CreateResearchJobRequest(BaseModel):
    """Request to start a research job for an order.

    ``document_types`` is the list of document types to fetch (from the
    source registry). If empty, all applicable types are fetched.

    ``idempotency_key`` is optional; if omitted, the server generates one.
    Duplicate requests with the same key return the existing job.
    """

    order_id: UUID = Field(..., description="Order to research")
    document_types: list[str] = Field(
        default_factory=list,
        description=(
            "Document types to fetch, e.g. ['PARCEL_RECORD', 'FLOOD']. "
            "Empty = fetch all applicable types for the order's survey type."
        ),
    )
    idempotency_key: UUID | None = Field(
        default=None,
        description="Client-generated idempotency key. Auto-generated if not provided.",
    )


class RetryResearchJobRequest(BaseModel):
    """Request to retry failed documents from a completed/partial/failed job.

    If ``document_types`` is provided, only those types are retried.
    Otherwise, all failed documents from the original job are retried.

    Creates a NEW job (linked to the same order) — does not mutate the original.
    """

    document_types: list[str] | None = Field(
        default=None,
        description="Specific doc types to retry. None = retry all failed from original job.",
    )


class CancelJobRequest(BaseModel):
    """Request to cancel a running/queued job.

    In-flight documents complete their current step; queued documents are skipped.
    The job transitions to ``cancelled``.
    """

    reason: str | None = Field(
        default=None,
        description="Optional cancellation reason (for audit trail).",
    )


# ======================================================================
# RESPONSE SCHEMAS
# ======================================================================


class FileReference(BaseModel):
    """Reference to a file stored in S3 via the evidence module."""

    file_id: UUID = Field(..., description="Evidence module File.id")
    order_file_id: UUID = Field(..., description="OrderFile.id linking this file to the order")
    key: str = Field(..., description="S3 object key: tenants/{tenant}/orders/{order}/research/{file_id}/{name}")
    filename: str = Field(..., description="Original filename")
    size_bytes: int = Field(..., description="File size in bytes")
    sha256: str = Field(default="", description="SHA-256 digest of the file")
    mime_type: str = Field(default="application/pdf", description="MIME type")


class ResearchDocument(BaseModel):
    """Per-document status within a research job.

    One row per requested document type. Tracks fetch → upload → OrderFile creation.
    """

    id: UUID = Field(..., description="research_documents.id")
    doc_type: str = Field(..., description="Document type, e.g. 'PARCEL_RECORD'")
    status: ResearchDocStatus = Field(..., description="Current status of this document")
    source_outcome: SourceOutcome | None = Field(
        default=None,
        description="Why the source returned what it did (after fetch completes)",
    )
    confidence: Confidence | None = Field(
        default=None,
        description="How sure the engine is that this pertains to the property",
    )
    file: FileReference | None = Field(
        default=None,
        description="File reference (set after S3 upload completes)",
    )
    summary: str = Field(default="", description="One-line summary of what was found")
    link: str = Field(default="", description="Fallback deep-link when auto-fetch is not available")
    link_label: str = Field(default="", description="Display text for the link button")
    provenance: list[ProvenanceRecord] = Field(
        default_factory=list,
        description="Audit trail: every source hit that contributed to this document",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Per-document warnings (e.g. 'buffered match, verify location')",
    )
    error_code: ResearchErrorCode | None = Field(
        default=None,
        description="Structured error code when status == 'failed'",
    )
    error_message: str | None = Field(
        default=None,
        description="Human-readable error when status == 'failed'",
    )
    retryable: bool = Field(
        default=True,
        description="Whether this document can be retried",
    )
    retry_count: int = Field(default=0, description="Number of retry attempts")
    fetched_at: datetime | None = Field(
        default=None,
        description="Timestamp when the fetch completed",
    )


class ResearchJob(BaseModel):
    """Research job — the top-level resource returned by GET /research/jobs/{id}.

    Contains the job metadata + per-document progress in ``documents[]``.
    """

    id: UUID = Field(..., description="research_jobs.id")
    order_id: UUID = Field(..., description="Order this job belongs to")
    status: ResearchJobStatus = Field(..., description="Job lifecycle status")
    requested_doc_types: list[str] = Field(
        ..., description="Document types originally requested"
    )
    total_documents: int = Field(..., description="Total documents in this job")
    fetched_documents: int = Field(default=0, description="Documents successfully fetched")
    uploaded_documents: int = Field(default=0, description="Documents uploaded to S3")
    failed_documents: int = Field(default=0, description="Documents that failed")
    cancelled_documents: int = Field(default=0, description="Documents skipped due to cancellation")
    documents: list[ResearchDocument] = Field(
        default_factory=list, description="Per-document status (included in single-job GET)"
    )
    started_at: datetime | None = Field(
        default=None, description="When the job started running"
    )
    completed_at: datetime | None = Field(
        default=None, description="When the job completed/failed/cancelled"
    )
    created_at: datetime = Field(..., description="Job creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    created_by: UUID = Field(..., description="User who created this job")
    error_code: ResearchErrorCode | None = Field(
        default=None,
        description="Top-level error when status == 'failed'",
    )
    error_message: str | None = Field(
        default=None,
        description="Top-level error message when status == 'failed'",
    )
    cancel_reason: str | None = Field(
        default=None,
        description="Reason recorded when the job was cancelled (from CancelJobRequest.reason)",
    )


class ResearchJobSummary(BaseModel):
    """Compact job listing — used in GET /research/orders/{order_id}/jobs."""

    id: UUID
    order_id: UUID = Field(..., description="Order this job belongs to")
    status: ResearchJobStatus
    total_documents: int
    fetched_documents: int
    uploaded_documents: int
    failed_documents: int
    cancelled_documents: int = Field(default=0, description="Documents skipped due to cancellation")
    created_at: datetime
    completed_at: datetime | None
    cancel_reason: str | None = Field(
        default=None,
        description="Reason recorded when the job was cancelled (from CancelJobRequest.reason)",
    )


# ======================================================================
# ENVELOPE SCHEMAS (engine-local; parent's StandardResponse replaces
# DataEnvelope at merge — field shapes stay identical)
# ======================================================================


class DataEnvelope(BaseModel, Generic[T]):
    """Standard success envelope: ``{ data: T }``."""

    data: T


class ErrorDetail(BaseModel):
    """Structured error response: ``{ error: { code, message, details? } }``."""

    code: ResearchErrorCode = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(
        default=None,
        description="Additional context (e.g. which doc_type failed, validation errors)",
    )


class ErrorEnvelope(BaseModel):
    """Error envelope: ``{ error: ErrorDetail }``."""

    error: ErrorDetail


# ======================================================================
# TYPE ALIASES for endpoint return types
# ======================================================================

# POST /research/jobs              → DataEnvelope[ResearchJob]
# GET  /research/jobs/{job_id}     → DataEnvelope[ResearchJob]
# POST /research/jobs/{job_id}/retry  → DataEnvelope[ResearchJob]
# POST /research/jobs/{job_id}/cancel → DataEnvelope[ResearchJob]
# GET  /research/orders/{order_id}/jobs → DataEnvelope[list[ResearchJobSummary]]
# Error responses                   → ErrorEnvelope
