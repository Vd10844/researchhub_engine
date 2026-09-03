"""Mappers — convert ORM rows to the frozen API contract models.

The ORM models carry a few columns the contract deliberately hides
(callback_url, idempotency_key, internal provenance format) and the
contract adds shape (FileReference next to file_id). These functions
are the single place that translation happens.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.engine.models import ResearchDocument, ResearchJob
from app.engine.repository import ResearchDocumentRepository
from app.engine.schemas import (
    FileReference,
    ResearchErrorCode,
    ResearchJobSummary,
)
from app.engine.schemas import (
    ResearchDocument as ResearchDocumentSchema,
)
from app.engine.schemas import (
    ResearchJob as ResearchJobSchema,
)


def _to_file_reference(
    doc: ResearchDocument,
) -> FileReference | None:
    """Build a FileReference for an uploaded document.

    Reads the stored File metadata (real key/size/sha) from the engine's
    evidence stand-in; at parent integration this reads the evidence module's
    File row instead.
    """
    if not doc.file_id or not doc.order_file_id:
        return None
    from app.engine.evidence_source import get_file_reference

    meta = get_file_reference(doc.file_id) or {}
    return FileReference(
        file_id=doc.file_id,
        order_file_id=doc.order_file_id,
        key=meta.get("key") or _s3_key(doc),
        filename=meta.get("filename") or f"{doc.doc_type}.pdf",
        size_bytes=meta.get("size_bytes") or 0,
        sha256=meta.get("sha256") or "",
        mime_type=meta.get("mime_type") or "application/pdf",
    )


def _s3_key(doc: ResearchDocument) -> str:
    # Path matches the parent's scheme; tenant prefix added by parent middleware.
    return f"orders/{doc.order_id}/research/{doc.file_id}/{doc.link_label or 'document.pdf'}"


def _to_error_code(value: str) -> ResearchErrorCode | None:
    """Map a stored error_code string to the contract enum, tolerating legacy values."""
    try:
        return ResearchErrorCode(value)
    except ValueError:
        return None


def to_document_schema(db: Session, doc: ResearchDocument) -> ResearchDocumentSchema:
    return ResearchDocumentSchema(
        id=doc.id,
        doc_type=doc.doc_type,
        status=doc.status,
        source_outcome=doc.source_outcome,
        confidence=doc.confidence,
        file=_to_file_reference(doc),
        summary=doc.summary or "",
        link=doc.link or "",
        link_label=doc.link_label or "",
        provenance=doc.provenance or [],
        warnings=doc.warnings or [],
        error_code=_to_error_code(doc.error_code) if doc.error_code else None,
        error_message=doc.error_message,
        retryable=doc.retryable,
        retry_count=doc.retry_count or 0,
        fetched_at=doc.fetched_at,
    )


def to_job_schema(
    db: Session,
    job: ResearchJob,
    with_documents: bool = True,
) -> ResearchJobSchema:
    docs = ResearchDocumentRepository.list_for_job(db, job.id) if with_documents else []
    return ResearchJobSchema(
        id=job.id,
        order_id=job.order_id,
        status=job.status,
        requested_doc_types=job.requested_doc_types,
        total_documents=job.total_documents,
        fetched_documents=job.fetched_documents,
        uploaded_documents=job.uploaded_documents,
        failed_documents=job.failed_documents,
        cancelled_documents=job.cancelled_documents,
        documents=[to_document_schema(db, d) for d in docs],
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
        created_by=job.created_by or job.tenant_id,
        error_code=_to_error_code(job.error_code) if job.error_code else None,
        error_message=job.error_message,
        cancel_reason=job.cancel_reason,
    )


def to_job_summary_schema(job: ResearchJob) -> ResearchJobSummary:
    """Compact job shape for GET /research/orders/{order_id}/jobs.

    Deliberately excludes the per-document array and audit-field noise — the
    list view only needs counters + lifecycle; detail is one GET /jobs/{id}
    away. Matches the declared contract alias (DataEnvelope[list[ResearchJobSummary]]).
    """
    return ResearchJobSummary(
        id=job.id,
        order_id=job.order_id,
        status=job.status,
        total_documents=job.total_documents,
        fetched_documents=job.fetched_documents,
        uploaded_documents=job.uploaded_documents,
        failed_documents=job.failed_documents,
        cancelled_documents=job.cancelled_documents,
        created_at=job.created_at,
        completed_at=job.completed_at,
        cancel_reason=job.cancel_reason,
    )
