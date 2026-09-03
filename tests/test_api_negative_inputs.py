"""Negative / malformed API input tests (validation-plan 2.2).

The production contract says the API is hostile-surface safe: every bad input
returns the ErrorEnvelope shape with a ResearchErrorCode, never a traceback or
an uncaught 500. These parametrized tests probe the malformed-UUID, unknown-
doc-type, missing/extra body field, wrong-content-type and auth-header paths.
"""
from __future__ import annotations

import uuid

import pytest
from app.main import app
from fastapi.testclient import TestClient

# A tenant/order that will never exist, so we reach the code under test
TENANT = "f0000000-0000-0000-0000-000000000001"
ACTOR = "f0000000-0000-0000-0000-000000000002"
ORDER_ID = str(uuid.uuid4())


@pytest.fixture
def api_client(test_db):
    """TestClient with ONLY the DB override — real auth header deps active."""
    from app.db.base import get_db

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def authed_client(test_db):
    """TestClient with DB + auth overrides (same as the shared ``client``)."""
    from app.db.base import get_db
    from app.engine.dependencies import get_actor_id, get_tenant_id

    def override_get_db():
        yield test_db

    async def override_actor():
        return uuid.UUID(ACTOR)

    async def override_tenant():
        return uuid.UUID(TENANT)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_actor_id] = override_actor
    app.dependency_overrides[get_tenant_id] = override_tenant
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _headers(**overrides):
    h = {"X-Tenant-Id": TENANT, "X-Actor-Id": ACTOR}
    # allow overriding the auth headers by name (upper/lower insensitive lookup)
    for key, val in overrides.items():
        lowered = key.lower().replace("_", "-")
        target = next((k for k in h if k.lower() == lowered), None)
        if target:
            h[target] = val
        else:
            h[key] = val
    return h


# ------------------------------------------------------------------ auth


def test_missing_tenant_header_is_401(api_client):
    r = api_client.get(
        f"/api/v1/research/jobs/{uuid.uuid4()}", headers={"X-Actor-Id": ACTOR}
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "HTTP_401"


def test_missing_actor_header_is_401(api_client):
    r = api_client.get(
        f"/api/v1/research/jobs/{uuid.uuid4()}", headers={"X-Tenant-Id": TENANT}
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "HTTP_401"


def test_invalid_tenant_uuid_is_401(api_client):
    r = api_client.get(
        f"/api/v1/research/jobs/{uuid.uuid4()}", headers=_headers(X_Tenant_Id="not-a-uuid")
    )
    assert r.status_code == 401


def test_invalid_actor_uuid_is_401(api_client):
    r = api_client.get(
        f"/api/v1/research/jobs/{uuid.uuid4()}", headers=_headers(X_Actor_Id="nope")
    )
    assert r.status_code == 401


# ------------------------------------------------------------------ malformed path


def test_malformed_job_id_path_is_422(authed_client):
    r = authed_client.get("/api/v1/research/jobs/not-a-uuid")
    assert r.status_code == 422


def test_malformed_order_id_path_is_422(authed_client):
    r = authed_client.get("/api/v1/research/orders/not-a-uuid/jobs")
    assert r.status_code == 422


def test_malformed_job_id_retry_is_422(authed_client):
    r = authed_client.post("/api/v1/research/jobs/zzz/retry")
    assert r.status_code == 422


def test_malformed_job_id_cancel_is_422(authed_client):
    r = authed_client.post("/api/v1/research/jobs/zzz/cancel")
    assert r.status_code == 422


def test_unknown_endpoint_is_404(authed_client):
    r = authed_client.get("/api/v1/research/nope")
    assert r.status_code == 404


# ------------------------------------------------------------------ invalid body


def test_missing_order_id_body_is_422(authed_client):
    r = authed_client.post("/api/v1/research/jobs", json={"document_types": []})
    assert r.status_code == 422


def test_unknown_extra_body_field_is_tolerated(authed_client):
    """Pydantic v2 by default IGNORES unknown fields (extra='ignore').

    The contract invariant is: an extra field must never crash the request or
    leak a traceback — it must flow to a normal ErrorEnvelope response. Here
    the random order id yields ORDER_NOT_FOUND (404), which proves the extra
    field was tolerated and the request handled cleanly.
    """
    r = authed_client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": [], "bogus": "x"},
    )
    assert r.status_code == 404
    body = r.json()
    assert "error" in body and body["error"]["code"] == "ORDER_NOT_FOUND"


def test_order_id_wrong_type_is_422(authed_client):
    r = authed_client.post(
        "/api/v1/research/jobs", json={"order_id": 12345, "document_types": []}
    )
    assert r.status_code == 422


def test_document_types_not_a_list_is_422(authed_client):
    r = authed_client.post(
        "/api/v1/research/jobs", json={"order_id": ORDER_ID, "document_types": "PARCEL_RECORD"}
    )
    assert r.status_code == 422


def test_wrong_content_type_is_422(authed_client):
    r = authed_client.post(
        "/api/v1/research/jobs",
        headers=_headers(X_Content_Type="text/plain"),
        content="not json",
    )
    assert r.status_code == 422


# ------------------------------------------------------------------ errors keep envelope


def test_404_surfaces_error_envelope(authed_client):
    r = authed_client.get(f"/api/v1/research/jobs/{uuid.uuid4()}")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]
