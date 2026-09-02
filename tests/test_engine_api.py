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
    # POST /jobs must not fire the worker in offline tests (CELERY eager would
    # run the whole pipeline synchronously and break the "queued" assertions).
    import app.engine.worker as worker_mod

    monkeypatch.setattr(worker_mod, "enqueue_research_job", lambda **_: None)


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


def test_create_job_empty_doc_types_means_all(client):
    """Empty document_types = fetch all applicable types (contract promise)."""
    r = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": []},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "queued"
    assert data["total_documents"] == 6  # all requestable types
    assert len(data["documents"]) == 6


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
    """A queued/running job is not retryable — 409 JOB_NOT_RETRYABLE."""
    created = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD", "DEED_SUBJECT_PARCEL"]},
    ).json()["data"]["id"]

    r = client.post(f"/api/v1/research/jobs/{created}/retry")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "JOB_NOT_RETRYABLE"


# ------------------------------------------------------------------ POST /jobs/{id}/cancel


def test_cancel_queued_job(client):
    created = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD"]},
    ).json()["data"]

    r = client.post(f"/api/v1/research/jobs/{created['id']}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "cancelled"


def test_cancel_records_reason_roundtrip(client):
    created = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD"]},
    ).json()["data"]

    r = client.post(
        f"/api/v1/research/jobs/{created['id']}/cancel",
        json={"reason": "duplicate order"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "cancelled"
    assert data["cancel_reason"] == "duplicate order"


def test_get_job_full_contract_json(client):
    """GET /jobs/{id} is the frozen+additive API shape — assert the full field
    surface and the defaults the contract promises (additive-safe)."""
    created = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD", "FEMA_FLOOD_ZONE_FIRM"]},
    ).json()["data"]

    r = client.get(f"/api/v1/research/jobs/{created['id']}")
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    for key in (
        "id", "order_id", "status", "requested_doc_types", "total_documents",
        "fetched_documents", "uploaded_documents", "failed_documents",
        "cancelled_documents", "documents", "started_at", "completed_at",
        "created_at", "updated_at", "created_by", "error_code", "error_message",
    ):
        assert key in data, f"missing top-level key {key}"

    assert data["status"] == "queued"
    assert data["cancel_reason"] is None      # additive default
    assert data["error_code"] is None
    assert data["error_message"] is None

    doc = data["documents"][0]
    for key in (
        "id", "doc_type", "status", "source_outcome", "confidence", "file",
        "summary", "link", "link_label", "provenance", "warnings", "error_code",
        "error_message", "retryable", "retry_count", "fetched_at",
    ):
        assert key in doc, f"missing doc key {key}"
    assert doc["status"] == "queued"
    assert doc["retryable"] is True           # additive default
    assert doc["source_outcome"] is None
    assert doc["confidence"] is None
    assert doc["file"] is None
    assert doc["retry_count"] == 0


# ------------------------------------------------------------------ GET /orders/{id}/jobs


def test_list_order_jobs_returns_compact_summaries(client):
    """The list endpoint returns the declared compact shape — counters + lifecycle
    only, no per-document array — matching DataEnvelope[list[ResearchJobSummary]]."""
    client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD", "FEMA_FLOOD_ZONE_FIRM"]},
    )
    r = client.get(f"/api/v1/research/orders/{ORDER_ID}/jobs")
    assert r.status_code == 200, r.text
    jobs = r.json()["data"]
    assert isinstance(jobs, list)
    assert len(jobs) >= 1

    job = jobs[0]
    assert job["order_id"] == ORDER_ID
    assert "documents" not in job
    assert "requested_doc_types" not in job
    assert "created_by" not in job
    for key in (
        "id", "order_id", "status", "total_documents", "fetched_documents",
        "uploaded_documents", "failed_documents", "cancelled_documents",
        "created_at", "completed_at", "cancel_reason",
    ):
        assert key in job, f"missing summary key {key}"
    assert job["cancel_reason"] is None


# ------------------------------------------------------------------ idempotency


def test_create_job_idempotency_same_key_same_job(client):
    """POST /jobs twice with the same X-Idempotency-Key returns the same job —
    no duplicate job/document rows."""
    from app.engine.repository import ResearchDocumentRepository

    key = str(uuid.uuid4())  # a realistic uuid (hex letters) — an all-digit
    # uuid round-trips through SQLite as a float and would corrupt read-back

    r1 = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD"]},
        headers={"X-Idempotency-Key": key},
    )
    assert r1.status_code == 200, r1.text
    id1 = r1.json()["data"]["id"]

    r2 = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD"]},
        headers={"X-Idempotency-Key": key},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["data"]["id"] == id1


# ------------------------------------------------------------------ request validation


def test_create_job_unknown_doc_type_422(client):
    r = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD", "BOGUS_TYPE"]},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_DOC_TYPES"


def test_create_job_invalid_order_uuid_422(client):
    r = client.post(
        "/api/v1/research/jobs",
        json={"order_id": "not-a-uuid", "document_types": ["PARCEL_RECORD"]},
    )
    assert r.status_code == 422


def test_get_job_invalid_uuid_422(client):
    r = client.get("/api/v1/research/jobs/not-a-uuid")
    assert r.status_code == 422


# ------------------------------------------------------------------ cancel terminal rejection


def test_cancel_terminal_job_rejected(client, test_db):
    created = client.post(
        "/api/v1/research/jobs",
        json={"order_id": ORDER_ID, "document_types": ["PARCEL_RECORD"]},
    ).json()["data"]["id"]

    # Flip the job to a terminal state directly (as a completed worker would).
    from app.engine.repository import ResearchJobRepository, ResearchDocumentRepository
    from app.engine.schemas import ResearchJobStatus

    job = ResearchJobRepository.get(test_db, uuid.UUID(created), uuid.UUID("f0000000-0000-0000-0000-000000000001"))
    job.status = ResearchJobStatus.completed
    for doc in ResearchDocumentRepository.list_for_job(test_db, uuid.UUID(created)):
        doc.status = ResearchDocStatus.uploaded
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    r = client.post(f"/api/v1/research/jobs/{created}/cancel")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "JOB_NOT_CANCELLABLE"


# ------------------------------------------------------------------ empty list


def test_list_jobs_empty_order_returns_empty(client):
    r = client.get(f"/api/v1/research/orders/{uuid.uuid4()}/jobs")
    assert r.status_code == 200
    assert r.json()["data"] == []


# ------------------------------------------------------------------ error envelope shape


def test_error_envelope_shape(client):
    """Every failure response is a single {error:{code,message}} envelope."""
    r = client.get(f"/api/v1/research/jobs/{uuid.uuid4()}")
    body = r.json()
    assert set(body.keys()) == {"error"}
    assert "code" in body["error"] and isinstance(body["error"]["code"], str)
    assert "message" in body["error"] and isinstance(body["error"]["message"], str)


# ------------------------------------------------------------------ health


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"