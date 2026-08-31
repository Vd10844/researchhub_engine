"""Auth dependency tests — the request boundary that had zero coverage.

``app.engine.dependencies.get_actor_id`` / ``get_tenant_id`` are placeholder
auth (swapped for the parent's Cognito user lookup at integration). They must
reject a request with 401 when the ``X-Actor-Id`` / ``X-Tenant-Id`` header is
missing or isn't a valid UUID.

The shared ``client`` fixture overrides these dependencies, so this suite builds
a TestClient with the real header deps and drives requests through the
endpoints (a 401 is raised by the dependency before any handler runs).
"""
from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def api_client(test_db):
    """TestClient with NO dependency overrides — real auth deps + real DB."""
    from fastapi.testclient import TestClient

    from app.db.base import get_db
    from app.main import app

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


VALID_TENANT = "f0000000-0000-0000-0000-000000000001"
VALID_ACTOR = "f0000000-0000-0000-0000-000000000002"

# A create body that would normally succeed (order_provider is real in the
# router's get_service — but we'll hit the auth dep FIRST, so provider never
# runs on these requests).
BODY = {"order_id": "f0000000-0000-0000-0000-000000000010", "document_types": ["PARCEL_RECORD"]}


def test_missing_actor_header_401(api_client):
    r = api_client.post(
        "/api/v1/research/jobs", json=BODY,
        headers={"X-Tenant-Id": VALID_TENANT},
    )
    assert r.status_code == 401
    assert "Missing X-Actor-Id" in r.json()["error"]["message"]


def test_invalid_actor_header_401(api_client):
    r = api_client.post(
        "/api/v1/research/jobs", json=BODY,
        headers={"X-Tenant-Id": VALID_TENANT, "X-Actor-Id": "not-a-uuid"},
    )
    assert r.status_code == 401
    assert "Invalid X-Actor-Id" in r.json()["error"]["message"]


def test_missing_tenant_header_401(api_client):
    r = api_client.post(
        "/api/v1/research/jobs", json=BODY,
        headers={"X-Actor-Id": VALID_ACTOR},
    )
    assert r.status_code == 401
    assert "Missing X-Tenant-Id" in r.json()["error"]["message"]


def test_invalid_tenant_header_401(api_client):
    r = api_client.post(
        "/api/v1/research/jobs", json=BODY,
        headers={"X-Tenant-Id": "nope", "X-Actor-Id": VALID_ACTOR},
    )
    assert r.status_code == 401
    assert "Invalid X-Tenant-Id" in r.json()["error"]["message"]


def test_valid_headers_reach_handler(api_client, monkeypatch):
    """Health is exempt from auth; this guard confirms valid headers 401 is NOT
    raised but the missing order does bubble up as a real handler error."""
    r = api_client.post(
        "/api/v1/research/jobs", json=BODY,
        headers={"X-Tenant-Id": VALID_TENANT, "X-Actor-Id": VALID_ACTOR},
    )
    # Order not found (provider returns None) — proves headers passed auth and
    # the request reached the handler, rather than being 401'd by the dep.
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_unit_direct_call_missing():
    """Direct-call the dependency functions to pin exact behavior."""
    from app.engine.dependencies import get_actor_id, get_tenant_id
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e1:
        get_actor_id(None)
    assert e1.value.status_code == 401

    with pytest.raises(HTTPException) as e2:
        get_tenant_id("bad")
    assert e2.value.status_code == 401
