"""API tests — exercise the /api/v1/research/* endpoints end-to-end.

Uses the real service but a mocked order_provider + document_fetcher
(see app.engine.router.get_service). To keep tests hermetic, we need the
adapters wired to fakes — the monkeypatch below replaces ``order_provider``
and ``build_document_fetcher`` used by the router's ``get_service``.
"""
from __future__ import annotations

import uuid

import pytest

from app.engine.service import FetchedDocument, OrderData
from app.engine.schemas import ResearchDocStatus

ORDER_ID = "f0000000-0000-0000-0000-000000000010"


@pytest.fixture(autouse=True)
def _wire_fakes(monkeypatch):
    """Point the router's get_service at fake adapters for every test.

    ``get_service`` imports ``order_provider`` / ``build_document_fetcher``
    from ``app.engine.adapters`` at call time, so patching the adapters
    module is sufficient.
    """
    import app.engine.adapters as adapters

    def fake_order_provider(order_id, tenant_id):
        return OrderData(
            id=uuid.UUID(str(order_id)),
            address_line_1="1015 E Palmetto St",
            city="Lakeland",
            state="FL",
            county="Polk",
            parcel_id="242819216500002011",
        )

    def fake_build_document_fetcher():
        def fetch(order, doc_types):
            return {
                t: FetchedDocument(
                    doc_type=t,
                    status=ResearchDocStatus.uploaded,
                    summary="Fetched",
                    file_key=f"orders/{order.id}/research/{t}/x.pdf",
                    file_name="x.pdf",
                    file_size=10,
                )
                for t in doc_types
            }

        return fetch

    monkeypatch.setattr(adapters, "order_provider", fake_order_provider)
    monkeypatch.setattr(adapters, "build_document_fetcher", fake_build_document_fetcher)


# ------------------------------------------------------------------ POST /jobs


def test_create_job_returns_contract(client):
    r = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD", "FEMA_FLOOD_ZONE_FIRM"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "data" in body
    data = body["data"]
    assert data["status"] == "queued"
    assert data["order_id"] == ORDER_ID
    assert data["total_documents"] == 2
    assert len(data["documents"]) == 2
    for doc in data["documents"]:
        assert doc["status"] == "queued"
        assert "doc_type" in doc


def test_create_job_rejects_empty_doc_types(client):
    r = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": []},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_DOC_TYPES"


def test_create_job_missing_order_returns_404(client, monkeypatch):
    import app.engine.adapters as adapters

    monkeypatch.setattr(adapters, "order_provider", lambda oid, tid: None)
    r = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD"]},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "ORDER_NOT_FOUND"


# ------------------------------------------------------------------ GET /jobs/{id}


def test_get_job_roundtrip(client):
    created = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD"]},
    ).json()["data"]

    r = client.get(f"/api/v1/research/jobs/{created['id']}")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["id"] == created["id"]
    assert data["status"] == "queued"


def test_get_job_not_found(client):
    r = client.get(f"/api/v1/research/jobs/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "JOB_NOT_FOUND"


# ------------------------------------------------------------------ POST /jobs/{id}/retry


def test_retry_rejects_nonterminal_job(client):
    """A queued/running job is not retryable — 422 rather than a new job."""
    created = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD", "DEED_SUBJECT_PARCEL"]},
    ).json()["data"]["id"]

    r = client.post(f"/api/v1/research/jobs/{created}/retry")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "ORDER_NOT_RESEARCHABLE"


# ------------------------------------------------------------------ POST /jobs/{id}/cancel


def test_cancel_queued_job(client):
    created = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD"]},
    ).json()["data"]

    r = client.post(f"/api/v1/research/jobs/{created['id']}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "cancelled"


# ------------------------------------------------------------------ GET /orders/{id}/jobs


def test_list_order_jobs(client):
    client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD"]},
    )
    r = client.get(f"/api/v1/research/orders/{ORDER_ID}/jobs")
    assert r.status_code == 200, r.text
    jobs = r.json()["data"]
    assert isinstance(jobs, list)
    assert len(jobs) >= 1