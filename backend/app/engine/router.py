"""Research engine API router — ``/api/v1/research/*``.

Endpoints:
  POST   /research/jobs                 — create a research job
  GET    /research/jobs/{job_id}         — get job status + documents
  POST   /research/jobs/{job_id}/retry   — retry failed documents
  POST   /research/jobs/{job_id}/cancel  — cancel a running job
  GET    /research/orders/{order_id}/jobs — list jobs for an order

All endpoints require:
  - ``Authorization`` header (JWT from Cognito)
  - ``X-Tenant-ID`` header (resolved by auth middleware)
  - ``X-Idempotency-Key`` header (optional, for POST /jobs)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException

from app.engine.schemas import (
    CancelJobRequest,
    CreateResearchJobRequest,
    DataEnvelope,
    ErrorDetail,
    ErrorEnvelope,
    ResearchErrorCode,
    ResearchJob,
    RetryResearchJobRequest,
)

router = APIRouter(prefix="/api/v1/research", tags=["research"])


# ------------------------------------------------------------------ deps


async def get_current_user_id() -> UUID:
    """Placeholder — replaced by Cognito auth dependency."""
    raise HTTPException(status_code=401, detail="Not authenticated")


async def get_current_tenant_id() -> UUID:
    """Placeholder — replaced by tenant middleware dependency."""
    raise HTTPException(status_code=401, detail="Tenant not resolved")


# ------------------------------------------------------------------ POST /jobs


@router.post(
    "/jobs",
    response_model=DataEnvelope[ResearchJob],
    responses={
        400: {"model": ErrorEnvelope, "description": "Invalid request"},
        404: {"model": ErrorEnvelope, "description": "Order not found"},
        409: {"model": ErrorEnvelope, "description": "Idempotency conflict"},
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
    user_id: UUID = Depends(get_current_user_id),
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    # TODO: implement service layer
    raise HTTPException(status_code=501, detail="Not yet implemented")


# ------------------------------------------------------------------ GET /jobs/{job_id}


@router.get(
    "/jobs/{job_id}",
    response_model=DataEnvelope[ResearchJob],
    responses={
        404: {"model": ErrorEnvelope, "description": "Job not found"},
    },
    summary="Get research job status",
    description=(
        "Returns the job metadata and per-document progress. "
        "Poll this endpoint to track job completion."
    ),
)
async def get_research_job(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    # TODO: implement service layer
    raise HTTPException(status_code=501, detail="Not yet implemented")


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
    user_id: UUID = Depends(get_current_user_id),
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    # TODO: implement service layer
    raise HTTPException(status_code=501, detail="Not yet implemented")


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
    user_id: UUID = Depends(get_current_user_id),
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    # TODO: implement service layer
    raise HTTPException(status_code=501, detail="Not yet implemented")


# ------------------------------------------------------------------ GET /orders/{order_id}/jobs


@router.get(
    "/orders/{order_id}/jobs",
    response_model=DataEnvelope[list[ResearchJob]],
    summary="List research jobs for an order",
    description="Returns all research jobs for the given order, newest first.",
)
async def list_order_jobs(
    order_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    # TODO: implement service layer
    raise HTTPException(status_code=501, detail="Not yet implemented")
