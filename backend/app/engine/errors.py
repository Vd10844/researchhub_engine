"""Engine exceptions — mapped to ResearchErrorCode + HTTP status in the router."""
from __future__ import annotations

from app.engine.schemas import ResearchErrorCode


class ResearchEngineError(Exception):
    """Base class for all engine exceptions."""

    code: ResearchErrorCode = ResearchErrorCode.INTERNAL_ERROR
    http_status: int = 500
    message: str = "Internal error"


class OrderNotFoundError(ResearchEngineError):
    code = ResearchErrorCode.ORDER_NOT_FOUND
    http_status = 404

    def __init__(self, order_id=None):
        super().__init__(f"Order {order_id} not found" if order_id else "Order not found")


class OrderNotResearchableError(ResearchEngineError):
    code = ResearchErrorCode.ORDER_NOT_RESEARCHABLE
    http_status = 422

    def __init__(self, message: str = "Order cannot be researched"):
        super().__init__(message)


class InvalidDocTypesError(ResearchEngineError):
    code = ResearchErrorCode.INVALID_DOC_TYPES
    http_status = 422


class JobNotFoundError(ResearchEngineError):
    code = ResearchErrorCode.JOB_NOT_FOUND
    http_status = 404

    def __init__(self, job_id=None):
        super().__init__(f"Job {job_id} not found" if job_id else "Job not found")


class JobNotRetryableError(ResearchEngineError):
    code = ResearchErrorCode.JOB_NOT_RETRYABLE
    http_status = 409

    def __init__(self, message: str = "Job is not in a retryable state"):
        super().__init__(message)


class JobNotCancellableError(ResearchEngineError):
    code = ResearchErrorCode.JOB_NOT_CANCELLABLE
    http_status = 409

    def __init__(self, message: str = "Job is not in a cancellable state"):
        super().__init__(message)


class IdempotencyConflictError(ResearchEngineError):
    code = ResearchErrorCode.IDEMPOTENCY_CONFLICT
    http_status = 409


class MissingAddressError(ResearchEngineError):
    code = ResearchErrorCode.MISSING_ADDRESS
    http_status = 422


class DocumentFetchError(ResearchEngineError):
    """Adapter failed to fetch a document — per-document, retryable."""

    http_status = 200  # surfaced inside the doc, not as HTTP error

    def __init__(self, code: ResearchErrorCode, message: str, retryable: bool = True):
        self.code = code
        self.message = message
        self.retryable = retryable
