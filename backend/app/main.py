"""Research Engine — FastAPI application entrypoint.

Production app:
  - mounts the research router at /api/v1/research/*
  - health check at /api/health
  - CORS from settings
  - creates tables at startup (dev), migrations via Alembic (prod)

Run locally:  uvicorn app.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.engine.errors import ResearchEngineError
from app.engine.router import router as research_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.RUN_ENV == "local":
        from app.db.base import Base, engine
        from app.engine import models  # noqa: F401  (register tables)

        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Research Engine",
    version="0.1.0",
    description="Automated land-survey research: parcel, deed, plat, flood, control.",
    lifespan=lifespan,
)

app.include_router(research_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ResearchEngineError)
async def research_error_handler(_, exc: ResearchEngineError):
    body = {"error": {"code": exc.code.value, "message": exc.message}}
    return JSONResponse(status_code=exc.http_status, content=body)


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException):
    body = {"error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "research-engine", "env": settings.RUN_ENV}