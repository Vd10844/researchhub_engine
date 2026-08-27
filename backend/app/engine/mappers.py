"""Mappers — convert ORM rows to the frozen API contract models.

The ORM models carry a few columns the contract deliberately hides
(callback_url, idempotency_key, internal provenance format) and the
contract adds shape (FileReference next to file_id). These functions
are the single place that translation happens.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.models import ResearchDocument, ResearchJob
from app.engine.repository import ResearchDocumentRepository
from app.engine.schemas import (
    FileReference,
    ResearchDocument as ResearchDocumentSchema,
    ResearchJob as ResearchJobSchema,
)


def _to_file_reference(
    doc: ResearchDocument,
) -> FileReference | None:
    """Build a FileReference from the stored file metadata on the doc row.

    Full filename/size/sha come from the evidence module's File row during
    integration; the engine stores what it knows on the document row.
    """
    if not doc.file_id or not doc.order_file_id:
        return None
    return FileReference(
        file_id=doc.file_id,
        order_file_id=doc.order_file_id,
        key=_s3_key(doc),
        filename=doc.link_label or f"{doc.doc_type}.pdf",
        size_bytes=0,
        sha256="",
        mime_type="application/pdf",
    )


def _s3_key(doc: ResearchDocument) -> str:
    # Path matches the parent's scheme; tenant prefix added by parent middleware.
    return f"orders/{doc.order_id}/research/{doc.file_id}/{doc.link_label or 'document.pdf'}"


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
        error_code=doc.error_code,
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
        created_by=job.created_by,
        error_code=job.error_code,
        error_message=job.error_message,
    )