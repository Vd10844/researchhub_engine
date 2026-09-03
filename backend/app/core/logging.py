"""Structured logging setup (structlog).

Production: JSON lines to stdout (container-friendly) with correlation fields.
Local: colorful console output for developer ergonomics.

A single module-level ``configure_logging()`` is idempotent and safe to call
from app startup, the worker, or the CLI entrypoints.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

from app.config import settings


def configure_logging() -> None:
    """Configure structlog + stdlib logging based on RUN_ENV."""
    import structlog

    if settings.RUN_ENV == "local":
        renderer: Any = structlog.dev.ConsoleRenderer()
        level = logging.INFO
    else:
        renderer = structlog.processors.JSONRenderer()
        level = logging.INFO

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(stream=sys.stdout, level=level)


def bind_request_context(*, request_id: str, tenant_id: str | None = None, actor_id: str | None = None) -> None:
    """Bind correlation context for the current request/worker scope."""
    import structlog

    ctx = {"request_id": request_id}
    if tenant_id:
        ctx["tenant_id"] = str(tenant_id)
    if actor_id:
        ctx["actor_id"] = str(actor_id)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**ctx)
