"""Shared pytest fixtures for the research engine suite.

Every test runs against a throwaway SQLite database with a patched SQLite
compiler (JSONB/UUID → JSON/text) so the engine's Postgres-oriented models
work in-memory. Env vars are set BEFORE any app import.
"""
from __future__ import annotations

import os
import sys

# ------------------------- ENV (must precede app imports) -------------------------
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["RUN_ENV"] = "test"
os.environ["S3_ARTIFACTS_BUCKET"] = "test-artifacts"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"

_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# ------------------------- PATCH SQLite for Postgres-only types -------------------------
import pytest  # noqa: E402
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402

# JSONB is Postgres-only; render it as JSON on SQLite.
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]


# ------------------------------------------------------------------ fixtures


@pytest.fixture(scope="session")
def engine():
    from app.db.base import Base, engine as _engine

    yield _engine


@pytest.fixture(scope="function")
def test_db(engine):
    """A fresh database per test function."""
    from app.db.base import Base, SessionLocal

    import app.engine.models  # noqa: F401  (register research tables)
    import app.engine.order_source  # noqa: F401  (register dev orders/tenants)
    import app.engine.evidence_source  # noqa: F401  (register dev files/order_files)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    """FastAPI TestClient with DB + auth dependency overrides."""
    from fastapi.testclient import TestClient

    from app.db.base import get_db
    from app.engine.dependencies import get_actor_id, get_tenant_id
    from app.main import app

    def override_get_db():
        yield test_db

    TENANT_ID = "f0000000-0000-0000-0000-000000000001"
    ACTOR_ID = "f0000000-0000-0000-0000-000000000002"

    async def override_actor():
        import uuid
        return uuid.UUID(ACTOR_ID)

    async def override_tenant():
        import uuid
        return uuid.UUID(TENANT_ID)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_actor_id] = override_actor
    app.dependency_overrides[get_tenant_id] = override_tenant

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def load_fixture(name: str) -> dict:
    """Load a captured POC result fixture as a dict."""
    import json

    from pathlib import Path

    p = Path(__file__).parent / "fixtures" / "poc_results" / name
    with open(p, encoding="utf-8") as f:
        return json.load(f)