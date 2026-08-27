"""Service layer — business logic for research jobs.

The service orchestrates:
  1. Order validation + context resolution (address, county, state, parcel_id)
  2. Job + document row creation
  3. Enqueuing the Celery worker
  4. Processing each document (orchestrator → S3 → File/OrderFile rows)
  5. Progress/counter updates, retry, cancel

THE ORDER MODULE: ``OrderData`` is the minimal interface the engine needs.
During integration into the parent repo, an adapter fetches this from
``app/modules/orders``. For the standalone engine, tests provide it directly.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.engine.errors import (
    DocumentFetchError,
    IdempotencyConflictError,
    InvalidDocTypesError,
    JobNotFoundError,
    OrderNotFoundError,
    OrderNotResearchableError,
)
from app.engine.models import ResearchDocument, ResearchJob
from app.engine.repository import ResearchDocumentRepository, ResearchJobRepository
from app.engine.schemas import (
    ResearchDocStatus,
    ResearchErrorCode,
    ResearchJobStatus,
)

# ------------------------------------------------------------------ domain


@dataclass
class OrderData:
    """Minimal order context the engine needs to run research.

    Populated during integration by reading ``app/modules/orders`` models.
    """

    id: uuid.UUID
    address_line_1: str
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    county: str | None = None
    parcel_id: str | None = None
    lat: float | None = None
    lon: float | None = None
    survey_type: str | None = None


@dataclass
class FetchedDocument:
    """Result of fetching one document type via the orchestrator."""

    doc_type: str
    status: ResearchDocStatus
    summary: str = ""
    link: str = ""
    link_label: str = ""
    file_key: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    sha256: str = ""
    mime_type: str | None = None
    file_id: uuid.UUID | None = None
    order_file_id: uuid.UUID | None = None
    provenance: list = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_code: ResearchErrorCode | None = None
    error_message: str | None = None
    retryable: bool = True


# ------------------------------------------------------------------ job state helpers


def recalc_job_counters(job: ResearchJob, docs: list[ResearchDocument]) -> None:
    """Recompute the job's denormalized counters from its documents."""
    job.total_documents = len(docs)
    job.fetched_documents = sum(
        d.status in (ResearchDocStatus.fetched, ResearchDocStatus.uploaded) for d in docs
    )
    job.uploaded_documents = sum(
        d.status == ResearchDocStatus.uploaded for d in docs
    )
    job.failed_documents = sum(d.status == ResearchDocStatus.failed for d in docs)
    job.cancelled_documents = sum(d.status == ResearchDocStatus.skipped for d in docs)


def resolve_job_terminal_status(db, job: ResearchJob) -> ResearchJobStatus:
    """Compute the job's terminal status from its documents.

    - all uploaded/fetched  → completed
    - some failed           → partial
    - all failed            → failed
    """
    docs = ResearchDocumentRepository.list_for_job(db, job.id)
    total = len(docs)
    if total == 0:
        return ResearchJobStatus.failed
    failed = sum(d.status == ResearchDocStatus.failed for d in docs)
    uploaded_ok = total - failed - sum(d.status == ResearchDocStatus.skipped for d in docs)
    if failed == 0:
        return ResearchJobStatus.completed
    if uploaded_ok == 0:
        return ResearchJobStatus.failed
    return ResearchJobStatus.partial


# ------------------------------------------------------------------ service


class ResearchService:
    """Public API surface used by the router and Celery worker."""

    def __init__(
        self,
        *,
        order_provider=None,
        document_fetcher=None,
        file_storage=None,
        enqueue=None,
    ):
        """Dependencies are injected for testability.

        - ``order_provider``: callable(order_id, tenant_id) → OrderData
        - ``document_fetcher``: callable(order: OrderData, doc_types: list[str]) → dict[str, FetchedDocument]
        - ``file_storage``: object with ``save_file(tenant_id, order_id, doc_id, filename, content) → dict``
        - ``enqueue``: callable(job_id, tenant_id, actor_id) — publishes the job's
          Celery task to the broker. ``None`` skips enqueueing (standalone/tests);
          production wiring passes ``app.engine.worker.enqueue_research_job``.
        """
        self.order_provider = order_provider
        self.document_fetcher = document_fetcher
        self.file_storage = file_storage
        self.enqueue = enqueue

    # ---------------------------------------------------------- create

    def create_job(self, db, *, tenant_id, actor_id, order_id, doc_types, idempotency_key, callback_url=None):
        order = self._resolve_order(db, tenant_id, order_id)
        doc_types = self._validate_doc_types(doc_types)

        # Idempotency: same key → return the existing job.
        if idempotency_key:
            existing = ResearchJobRepository.get_by_idempotency(db, idempotency_key, tenant_id)
            if existing:
                return existing

        job = ResearchJobRepository.create(
            db,
            order_id=order.id,
            tenant_id=tenant_id,
            created_by=actor_id,
            idempotency_key=idempotency_key or uuid.uuid4(),
            requested_doc_types=doc_types,
            callback_url=callback_url,
        )
        for doc_type in doc_types:
            ResearchDocumentRepository.create(
                db, job_id=job.id, order_id=order.id, doc_type=doc_type
            )
        db.commit()
        db.refresh(job)
        if self.enqueue is not None:
            self.enqueue(
                job_id=job.id, tenant_id=tenant_id, actor_id=actor_id
            )
        return job

    # ---------------------------------------------------------- get / list

    def get_job(self, db, *, tenant_id, job_id) -> ResearchJob:
        job = ResearchJobRepository.get(db, job_id, tenant_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def list_order_jobs(self, db, *, tenant_id, order_id) -> list[ResearchJob]:
        return ResearchJobRepository.list_for_order(db, order_id, tenant_id)

    # ---------------------------------------------------------- retry

    def retry_job(self, db, *, tenant_id, actor_id, job_id, doc_types=None) -> ResearchJob:
        original = self.get_job(db, tenant_id=tenant_id, job_id=job_id)
        if original.status not in (
            ResearchJobStatus.completed,
            ResearchJobStatus.partial,
            ResearchJobStatus.failed,
            ResearchJobStatus.cancelled,
        ):
            raise OrderNotResearchableError("Original job is not in a retryable state")

        failed = ResearchDocumentRepository.list_failed(db, job_id)
        failed_types = [d.doc_type for d in failed]
        if doc_types is None:
            doc_types = failed_types
        else:
            doc_types = [t for t in doc_types if t in failed_types]

        if not doc_types:
            raise OrderNotResearchableError("No failed documents to retry")

        return self.create_job(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            order_id=original.order_id,
            doc_types=doc_types,
            idempotency_key=None,
        )

    # ---------------------------------------------------------- cancel

    def cancel_job(self, db, *, tenant_id, job_id) -> ResearchJob:
        job = self.get_job(db, tenant_id=tenant_id, job_id=job_id)
        if job.status not in (ResearchJobStatus.queued, ResearchJobStatus.running):
            raise OrderNotResearchableError("Job is not cancellable")

        job.status = ResearchJobStatus.cancelled
        job.completed_at = None  # set by worker on actual completion
        ResearchJobRepository.save(db, job)
        db.commit()
        db.refresh(job)
        return job

    # ---------------------------------------------------------- internals

    def _resolve_order(self, db, tenant_id, order_id) -> OrderData:
        if self.order_provider is None:
            raise OrderNotResearchableError("Order provider not configured")
        order = self.order_provider(order_id, tenant_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        if not order.address_line_1:
            raise OrderNotResearchableError("Order has no address — cannot research")
        return order

    def _validate_doc_types(self, doc_types: list[str]) -> list[str]:
        from app.engine.adapters import DOC_TYPE_TO_STEP, STEP_TO_DOC_TYPE

        if not doc_types:
            raise InvalidDocTypesError("document_types must not be empty")

        canonical: list[str] = []
        unknown: list[str] = []
        for t in doc_types:
            if t in DOC_TYPE_TO_STEP:
                canonical.append(t)
            # Legacy alias: a step short-name (or its upper/lower variant),
            # e.g. "flood" -> FEMA_FLOOD_ZONE_FIRM. Normalize to canonical so
            # the stored value always resolves in the fetcher's include map.
            elif t.lower() in STEP_TO_DOC_TYPE:
                canonical.append(STEP_TO_DOC_TYPE[t.lower()])
            else:
                unknown.append(t)
        if unknown:
            raise InvalidDocTypesError(
                "unsupported document_types: %s (supported: %s)"
                % (", ".join(sorted(unknown)), ", ".join(sorted(DOC_TYPE_TO_STEP)))
            )
        # Deduplicate (an alias + its canonical form resolve to one document)
        # while preserving first-occurrence order.
        return list(dict.fromkeys(canonical))