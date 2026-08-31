"""Tenant isolation tests — a security boundary the earlier suites never exercised.

Every repository query is tenant-scoped via ``tenant_id`` (never from request
params). These prove that a user of tenant B cannot read, cancel, retry, review
or archive a job owned by tenant A, and that soft-deleted jobs vanish from all
query paths.

The shared ``client`` fixture hardcodes dependency overrides for actor/tenant,
so these tests build their own TestClient with ONLY the DB override — the real
``X-Tenant-Id`` / ``X-Actor-Id`` header dependencies stay active so cross-tenant
headers actually flow through ``dependencies.py``.
"""
from __future__ import annotations

import uuid

import pytest

from app.engine.repository import ResearchDocumentRepository, ResearchJobRepository
from app.engine.schemas import ResearchDocStatus, ResearchJobStatus
from app.engine.service import ResearchService

TENANT_A = uuid.UUID("a0000000-0000-0000-0000-000000000001")
TENANT_B = uuid.UUID("b0000000-0000-0000-0000-000000000002")
ACTOR = uuid.UUID("f0000000-0000-0000-0000-000000000002")


def _svc(test_db) -> ResearchService:
    # Real order_provider (reads the standalone orders/tenants tables) so
    # created jobs actually reference an Order row owned by the right tenant.
    from app.engine.adapters import order_provider

    return ResearchService(order_provider=order_provider, enqueue=None)


def _seed_order(test_db, tenant_id) -> uuid.UUID:
    from app.engine.order_source import seed_dev_order

    o = seed_dev_order(
        test_db,
        tenant_id=tenant_id,
        address_line_1="1015 E Palmetto St",
        city="Lakeland",
        state="FL",
        county="Polk",
        parcel_id="242819216500002011",
        survey_type="MORTGAGE_LOCATION_SURVEY",
    )
    return o.id


def _create_job(test_db, tenant_id, order_id) -> uuid.UUID:
    job = _svc(test_db).create_job(
        test_db,
        tenant_id=tenant_id,
        actor_id=ACTOR,
        order_id=order_id,
        doc_types=["PARCEL_RECORD"],
        idempotency_key=None,
    )
    return job.id


@pytest.fixture
def api_client(test_db):
    """TestClient with only the DB override — real header deps active."""
    from fastapi.testclient import TestClient

    from app.db.base import get_db
    from app.main import app

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _headers(tenant_id, actor=ACTOR) -> dict:
    return {"X-Tenant-Id": str(tenant_id), "X-Actor-Id": str(actor)}


# ------------------------------------------------------------------ API: cross-tenant


def test_get_job_cross_tenant_is_404(api_client, test_db):
    order_a = _seed_order(test_db, TENANT_A)
    job = _create_job(test_db, TENANT_A, order_a)

    # Tenant B asks for tenant A's job by id.
    r = api_client.get(f"/api/v1/research/jobs/{job}", headers=_headers(TENANT_B))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_list_jobs_cross_tenant_is_empty(api_client, test_db):
    order_a = _seed_order(test_db, TENANT_A)
    _create_job(test_db, TENANT_A, order_a)

    r = api_client.get(
        f"/api/v1/research/orders/{order_a}/jobs", headers=_headers(TENANT_B)
    )
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_cancel_cross_tenant_is_404(api_client, test_db):
    order_a = _seed_order(test_db, TENANT_A)
    job = _create_job(test_db, TENANT_A, order_a)

    r = api_client.post(
        f"/api/v1/research/jobs/{job}/cancel", headers=_headers(TENANT_B)
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_retry_cross_tenant_is_404(api_client, test_db):
    order_a = _seed_order(test_db, TENANT_A)
    job = _create_job(test_db, TENANT_A, order_a)

    r = api_client.post(
        f"/api/v1/research/jobs/{job}/retry", headers=_headers(TENANT_B)
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "JOB_NOT_FOUND"


# ------------------------------------------------------------------ service: cross-tenant


def test_service_get_job_cross_tenant_raises(test_db):
    order_a = _seed_order(test_db, TENANT_A)
    job = _create_job(test_db, TENANT_A, order_a)

    from app.engine.errors import JobNotFoundError

    with pytest.raises(JobNotFoundError):
        _svc(test_db).get_job(test_db, tenant_id=TENANT_B, job_id=job)


def test_service_review_cross_tenant_raises(test_db):
    from app.engine.errors import JobNotFoundError

    order_a = _seed_order(test_db, TENANT_A)
    job = _create_job(test_db, TENANT_A, order_a)
    with pytest.raises(JobNotFoundError):
        _svc(test_db).mark_reviewed(test_db, tenant_id=TENANT_B, job_id=job)


def test_service_archive_cross_tenant_raises(test_db):
    # Mark reviewed as tenant A first, then try to archive as tenant B.
    from app.engine.errors import JobNotFoundError

    order_a = _seed_order(test_db, TENANT_A)
    job_id = _create_job(test_db, TENANT_A, order_a)
    svc = _svc(test_db)
    job = svc.get_job(test_db, tenant_id=TENANT_A, job_id=job_id)
    job.status = ResearchJobStatus.reviewed
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    with pytest.raises(JobNotFoundError):
        svc.archive_job(test_db, tenant_id=TENANT_B, job_id=job_id)


# ------------------------------------------------------------------ soft delete


def test_soft_deleted_job_hidden_from_get(test_db):
    order_a = _seed_order(test_db, TENANT_A)
    job_id = _create_job(test_db, TENANT_A, order_a)

    job = ResearchJobRepository.get(test_db, job_id, TENANT_A)
    from datetime import datetime, timezone

    job.deleted_at = datetime.now(timezone.utc)
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    assert ResearchJobRepository.get(test_db, job_id, TENANT_A) is None

    from app.engine.errors import JobNotFoundError

    with pytest.raises(JobNotFoundError):
        _svc(test_db).get_job(test_db, tenant_id=TENANT_A, job_id=job_id)


def test_soft_deleted_job_hidden_from_list(test_db):
    order_a = _seed_order(test_db, TENANT_A)
    job_id = _create_job(test_db, TENANT_A, order_a)

    job = ResearchJobRepository.get(test_db, job_id, TENANT_A)
    from datetime import datetime, timezone

    job.deleted_at = datetime.now(timezone.utc)
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    jobs = ResearchJobRepository.list_for_order(test_db, order_a, TENANT_A)
    assert jobs == []


# ------------------------------------------------------------------ soft-delete docs


def test_soft_deleted_doc_hidden_from_list(test_db):
    order_a = _seed_order(test_db, TENANT_A)
    job_id = _create_job(test_db, TENANT_A, order_a)

    docs = ResearchDocumentRepository.list_for_job(test_db, job_id)
    assert docs, "expected at least one document row"
    from datetime import datetime, timezone

    docs[0].deleted_at = datetime.now(timezone.utc)
    ResearchDocumentRepository.save(test_db, docs[0])
    test_db.commit()

    remaining = ResearchDocumentRepository.list_for_job(test_db, job_id)
    assert docs[0].id not in {d.id for d in remaining}
