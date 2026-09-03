"""Request-ID middleware + correlation binding.

Generates (or trusts an inbound) ``X-Request-Id`` per request and binds it to
structlog context so every log line in a request carries the same id, enabling
cross-service correlation with the Celery worker and the parent repo.
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable
from typing import Callable

from app.core.logging import bind_request_context
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Ensure every request has an X-Request-Id and bind it to log context."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        bind_request_context(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
