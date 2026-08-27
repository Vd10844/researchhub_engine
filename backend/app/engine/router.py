"""Research engine API router — ``/api/v1/research/*``.

Endpoints:
  POST   /research/jobs                    — create a research job
  GET    /research/jobs/{job_id}           — get job status + documents
  POST   /research/jobs/{job_id}/retry     — retry failed documents
  POST   /research/jobs/{job_id}/cancel    — cancel a running job
  GET    /research/orders/{order_id}/jobs  — list jobs for an order

All endpoints require:
  - ``Authorization`` header (JWT from Cognito)
  - ``X-Tenant-ID`` header (resolved by auth middleware)
  - ``X-Idempotency-Key`` header (optional, for POST /jobs)

Auth deps currently resolve from headers via a shared placeholder — swap the
implemantation once Cognito wiring lands (see ``app/engine/dependencies.py``).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.engine.dependencies import get_actor_id, get_tenant_id
from app.engine.errors import ResearchEngineError
from app.engine.mappers import to_job_schema
from app.engine.schemas import (
    CancelJobRequest,
    CreateResearchJobRequest,
    DataEnvelope,
    ErrorEnvelope,
    ResearchJob,
    RetryResearchJobRequest,
)
from app.engine.service import ResearchService

router = APIRouter(prefix="/api/v1/research", tags=["research"])


# The app-level exception handlers live in app.main (they must be registered
# on the FastAPI instance, not the router).


def get_service(db: Session = Depends(get_db)) -> ResearchService:
    """Service singleton with the production dependencies injected."""
    from app.engine.adapters import build_document_fetcher, order_provider

    return ResearchService(
        order_provider=order_provider,
        document_fetcher=build_document_fetcher(),
        file_storage=None,  # wired at integration; local tests inject their own
    )


# ------------------------------------------------------------------ POST /jobs


@router.post(
    "/jobs",
    response_model=DataEnvelope[ResearchJob],
    responses={
        404: {"model": ErrorEnvelope, "description": "Order not found"},
        409: {"model": ErrorEnvelope, "description": "Idempotency conflict"},
        422: {"model": ErrorEnvelope, "description": "Invalid document types"},
    },
    summary="Create a research job",
    description=(
        "Starts auto-fetching documents for an order. "
        "Accepts a list of document types (from the source registry). "
        "Returns the created job with per-document status."
    ),
)
async def create_research_job(
    request: CreateResearchJobRequest,
    x_idempotency_key: UUID | None = Header(default=None, alias="X-Idempotency-Key"),
    actor_id: UUID = Depends(get_actor_id),
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    service: ResearchService = Depends(get_service),
):
    job = service.create_job(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        order_id=request.order_id,
        doc_types=request.document_types,
        idempotency_key=x_idempotency_key,
        callback_url=None,  # callback_url is not part of v1 contract
    )
    return DataEnvelope(data=to_job_schema(db, job))


# ------------------------------------------------------------------ GET /jobs/{job_id}


@router.get(
    "/jobs/{job_id}",
    response_model=DataEnvelope[ResearchJob],
    responses={404: {"model": ErrorEnvelope, "description": "Job not found"}},
    summary="Get research job status",
    description=(
        "Returns the job metadata and per-document progress. "
        "Poll this endpoint to track job completion."
    ),
)
async def get_research_job(
    job_id: UUID,
    actor_id: UUID = Depends(get_actor_id),
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    service: ResearchService = Depends(get_service),
):
    job = service.get_job(db, tenant_id=tenant_id, job_id=job_id)
    return DataEnvelope(data=to_job_schema(db, job))


# ------------------------------------------------------------------ POST /jobs/{job_id}/retry


@router.post(
    "/jobs/{job_id}/retry",
    response_model=DataEnvelope[ResearchJob],
    responses={
        404: {"model": ErrorEnvelope, "description": "Job not found"},
        409: {"model": ErrorEnvelope, "description": "Job not retryable"},
    },
    summary="Retry failed documents",
    description=(
        "Creates a new research job with the failed document types from the original job. "
        "The original job is not mutated."
    ),
)
async def retry_research_job(
    job_id: UUID,
    request: RetryResearchJobRequest | None = None,
    actor_id: UUID = Depends(get_actor_id),
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    service: ResearchService = Depends(get_service),
):
    doc_types = request.document_types if request else None
    job = service.retry_job(
        db, tenant_id=tenant_id, actor_id=actor_id, job_id=job_id, doc_types=doc_types
    )
    return DataEnvelope(data=to_job_schema(db, job))


# ------------------------------------------------------------------ POST /jobs/{job_id}/cancel


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=DataEnvelope[ResearchJob],
    responses={
        404: {"model": ErrorEnvelope, "description": "Job not found"},
        409: {"model": ErrorEnvelope, "description": "Job not cancellable"},
    },
    summary="Cancel a research job",
    description=(
        "Cancels a running/queued job. In-flight documents complete their current step; "
        "queued documents are skipped."
    ),
)
async def cancel_research_job(
    job_id: UUID,
    request: CancelJobRequest | None = None,
    actor_id: UUID = Depends(get_actor_id),
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    service: ResearchService = Depends(get_service),
):
    job = service.cancel_job(db, tenant_id=tenant_id, job_id=job_id)
    return DataEnvelope(data=to_job_schema(db, job))


# ------------------------------------------------------------------ GET /orders/{order_id}/jobs


@router.get(
    "/orders/{order_id}/jobs",
    response_model=DataEnvelope[list[ResearchJob]],
    summary="List research jobs for an order",
    description="Returns all research jobs for the given order, newest first.",
)
async def list_order_jobs(
    order_id: UUID,
    actor_id: UUID = Depends(get_actor_id),
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    service: ResearchService = Depends(get_service),
):
    jobs = service.list_order_jobs(db, tenant_id=tenant_id, order_id=order_id)
    return DataEnvelope(data=[to_job_schema(db, j) for j in jobs])