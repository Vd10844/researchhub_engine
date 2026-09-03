"""Per-tenant rate limiter.

Applied as a FastAPI dependency (``Depends(rate_limit)``) rather than the
``@slowapi.Limiter.limit`` decorator. The decorator rewrites the endpoint
signature and, combined with ``from __future__ import annotations`` (forward
refs), makes FastAPI misclassify the Pydantic body as a query parameter. A
dependency keeps the endpoint signature intact and FastAPI's body detection
reliable.

Backed by the ``limits`` library. In production the storage is Redis (shared
across workers/processes); it falls back to an in-memory store when Redis is
absent. Enforcement is a no-op under ``RUN_ENV=test`` so the CI suite stays
deterministic, and ``RATE_LIMIT_RESEARCH=""`` disables it entirely.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import settings
from fastapi import HTTPException, Request
from limits import parse, strategies
from limits.storage import MemoryStorage, RedisStorage


@lru_cache
def _storage():
    if settings.REDIS_URL and settings.REDIS_URL.startswith("redis"):
        try:
            return RedisStorage(settings.REDIS_URL)
        except Exception:
            pass
    return MemoryStorage()


@lru_cache
def _moving_window():
    return strategies.MovingWindowRateLimiter(_storage())


def _identity(request: Request) -> str:
    return request.headers.get("X-Tenant-Id") or (
        request.client.host if request.client else "anon"
    )


def rate_limit(request: Request) -> None:
    """FastAPI dependency enforcing the per-tenant research rate limit.

    Returns 429 when the tenant exceeds the limit. No-op in test env.
    """
    rate = settings.RATE_LIMIT_RESEARCH
    if not rate or settings.RUN_ENV == "test":
        return
    item = parse(rate)
    identifier = f"research:{_identity(request)}"
    if not _moving_window().hit(item, identifier):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
