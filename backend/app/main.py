"""Research Engine — FastAPI application entrypoint.

Production app:
  - mounts the research router at /api/v1/research/*
  - health check at /api/health (probes DB + Redis)
  - CORS from settings (hardened: credentials, max_age)
  - request-ID correlation middleware + structured logging
  - rate limiting on the research endpoints (per-tenant, Redis-backed)
  - catches all exceptions into the ErrorEnvelope contract
  - creates tables at startup (dev), migrations via Alembic (prod)

Run locally:  uvicorn app.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware
from app.engine.errors import ResearchEngineError
from app.engine.router import router as research_router

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.RUN_ENV == "local":
        from app.db.base import Base, engine
        from app.engine import (
            evidence_source,  # noqa: F401  (register dev evidence tables)
            models,  # noqa: F401  (register tables)
            order_source,  # noqa: F401  (register dev orders table)
        )

        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Research Engine",
    version="0.2.0",
    description="Automated land-survey research: parcel, deed, plat, flood, control. Production-ready.",
    lifespan=lifespan,
)

app.include_router(research_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=600,
)
app.add_middleware(RequestIDMiddleware)


@app.exception_handler(ResearchEngineError)
async def research_error_handler(_, exc: ResearchEngineError):
    body = {"error": {"code": exc.code.value, "message": exc.message}}
    return JSONResponse(status_code=exc.http_status, content=body)


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException):
    # 429 originates from the rate limiter — keep the semantic code stable.
    code = "RATE_LIMIT_EXCEEDED" if exc.status_code == 429 else f"HTTP_{exc.status_code}"
    body = {"error": {"code": code, "message": str(exc.detail)}}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    """Never leak a stack trace to the client; always honor the ErrorEnvelope contract."""
    import structlog

    logger = structlog.get_logger("researchhub.main")
    logger.exception("unhandled_exception", error=str(exc))
    body = {"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}}
    return JSONResponse(status_code=500, content=body)


@app.get("/api/health", summary="Liveness + dependency probes")
def health():
    """Return 200 only if the process is up and its dependencies are reachable.

    Probes Postgres (SELECT 1) and Redis (PING). A 503 means the app is running
    but cannot process jobs — signal for the orchestrator to stop routing traffic.
    """
    from app.db.base import SessionLocal

    checks: dict[str, Any] = {"app": "research-engine", "env": settings.RUN_ENV, "status": "ok", "dependencies": {}}

    # Postgres probe
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            checks["dependencies"]["postgres"] = "ok"
        finally:
            db.close()
    except Exception:
        checks["dependencies"]["postgres"] = "unreachable"
        checks["status"] = "degraded"

    # Redis probe
    try:
        import redis

        r = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
        checks["dependencies"]["redis"] = "ok"
    except Exception:
        checks["dependencies"]["redis"] = "unreachable"
        checks["status"] = "degraded"

    return JSONResponse(
        status_code=200 if checks["status"] == "ok" else 503,
        content=checks,
    )


@app.get("/api/health/live", summary="Liveness only")
def liveness():
    """Cheap liveness — the process is up (does not probe dependencies)."""
    return {"status": "ok", "env": settings.RUN_ENV}
