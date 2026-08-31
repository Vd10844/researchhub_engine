"""Execution scenarios — the engine's running system, not just its shapes.

Covers the three layers the older suites don't reach with one stroke:

  1. ``classify_exception`` unit matrix — every HTTP-status branch maps to the
     frozen outcome/code/retryable triple the contract documents.
  2. ``resolve_job_terminal_status`` boundaries — all-failed, zero-docs, and
     the new ``cancelling → cancelled`` drain path.
  3. The Celery worker task *body* (``research_job.run``) executed in-process
     against the real shared StaticPool DB — full success (with a real
     ``FileReference``), partial failure, and a cancel issued from another
     session mid-run.
  4. Step assembly — ``manual_review`` emission (the just-made-reachable
     outcome) and the fallback-raises last-resort link.

No network, no broker: ``research_job.run(...)`` calls the task body directly
and ``create_evidence`` writes through the same ``SessionLocal`` the worker
uses. Run: pytest tests/test_execution_scenarios.py -v
"""
from __future__ import annotations

import threading
import uuid

import pytest
import requests

from app.engine.contracts import Confidence, SourceOutcome, StepStatus
from app.engine.orchestration.sources import (
    FetchedSource,
    SourceAdapter,
    SourceError,
    classify_exception,
)
from app.engine.repository import ResearchDocumentRepository, ResearchJobRepository
from app.engine.schemas import ResearchDocStatus, ResearchJobStatus
from app.engine.service import FetchedDocument, OrderData, ResearchService

TENANT_ID = uuid.UUID("f0000000-0000-0000-0000-000000000001")
ACTOR_ID = uuid.UUID("f0000000-0000-0000-0000-000000000002")
ORDER_ID = uuid.UUID("f0000000-0000-0000-0000-000000000010")

PARCEL = "PARCEL_RECORD"
DEED = "DEED_SUBJECT_PARCEL"
FLOOD = "FEMA_FLOOD_ZONE_FIRM"


# ------------------------------------------------------------------ fixtures


def make_order() -> OrderData:
    return OrderData(
        id=ORDER_ID,
        address_line_1="1015 E Palmetto St",
        city="Lakeland",
        state="FL",
        county="Polk",
        parcel_id="242819216500002011",
        survey_type="MORTGAGE_LOCATION_SURVEY",
    )


def make_service(order: OrderData | None = None, fetcher=None) -> ResearchService:
    return ResearchService(
        order_provider=lambda oid, tid: order or make_order(),
        document_fetcher=fetcher or _ok_fetcher(),
        enqueue=None,  # job already created; no second enqueue
    )


def _ok_fetcher(*doc_types):
    """All requested docs come back 'uploaded' with real evidence rows."""
    from app.engine.evidence_source import create_evidence

    if not doc_types:
        doc_types = (PARCEL, DEED, FLOOD)

    def fetch(order, requested, tenant_id=None):
        out = {}
        for t in requested:
            if t not in doc_types:
                continue
            src_key = f"orders/{order.id}/research/{t}/x.pdf"
            file_id, order_file_id = create_evidence(
                order_id=order.id,
                tenant_id=tenant_id,
                storage_key=src_key,
                filename="x.pdf",
                file_size=10,
                sha256="feedface" * 8,
                mime_type="application/pdf",
            )
            out[t] = FetchedDocument(
                doc_type=t,
                status=ResearchDocStatus.uploaded,
                summary="Fetched",
                link="https://src.example.test/",
                link_label="Open source",
                file_key=src_key,
                file_name="x.pdf",
                file_size=10,
                sha256="feedface" * 8,
                mime_type="application/pdf",
                file_id=file_id,
                order_file_id=order_file_id,
            )
        return out

    return fetch


def _failed_fetcher(failed_types, error_code="FLOOD_UNAVAILABLE", retryable=False):
    from app.engine.schemas import ResearchErrorCode

    code = getattr(ResearchErrorCode, error_code, ResearchErrorCode.FLOOD_UNAVAILABLE)

    def fetch(order, requested, tenant_id=None):
        out = {}
        for t in requested:
            if t in failed_types:
                out[t] = FetchedDocument(
                    doc_type=t,
                    status=ResearchDocStatus.failed,
                    summary="couldn't reach the source",
                    link="https://src.example.test/",
                    link_label="Open",
                    error_code=code,
                    error_message="source returned 404",
                    retryable=retryable,
                )
            else:
                out[t] = _ok_fetcher(t)(make_order(), [t], tenant_id)[t]
        return out

    return fetch


@pytest.fixture
def adapters():
    """Snapshot + restore the source-adapter registry (mirrors the regression suite)."""
    from app.engine.orchestration.sources import ADAPTERS

    saved = dict(ADAPTERS)
    yield ADAPTERS
    ADAPTERS.clear()
    ADAPTERS.update(saved)


def _make_ctx(folder, parcel_ok=False, parcel=None, **overrides):
    from pathlib import Path as _P

    from app.engine.orchestration.context import PropertyContext, WarningBag

    folder.mkdir(parents=True, exist_ok=True)
    parcel = parcel or {"method": "arcgis-rest", "parcels": [], "address_match": False, "hints": {}}
    return PropertyContext(
        address="1 Test St",
        matched_address="1 Test St",
        lat=27.9,
        lon=-82.5,
        state="FL",
        state_fips="12",
        county="Hillsborough",
        county_fips="12057",
        geocoder="census",
        appraiser_url="https://pa.example.test/",
        parcel=parcel,
        parcel_id="PIN-1" if parcel_ok else "",
        parcel_ok=parcel_ok,
        parcel_hints={},
        clerk_ref={
            "official_records_search": "https://clerk.example.test/or/",
            "plat_search": "https://clerk.example.test/plat/",
        },
        job_number="A-1",
        order="ORD-1",
        name="A-1",
        folder=folder,
        appr={},
        warnings=WarningBag(),
        **overrides,
    )


def _create_job(test_db, doc_types):
    svc = make_service()
    return svc.create_job(
        test_db,
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        order_id=ORDER_ID,
        doc_types=doc_types,
        idempotency_key=None,
    )


def _wire_worker(monkeypatch, service):
    import app.engine.worker as worker_mod

    monkeypatch.setattr(worker_mod, "build_research_service", lambda: service)


# =======================================================================
# 1. classify_exception — the exception → outcome contract
# =======================================================================


def _http_error(status_code):
    err = requests.exceptions.HTTPError()
    err.response = type("R", (), {"status_code": status_code})()
    return err


@pytest.mark.parametrize("code", [401, 403, 406, 429])
def test_classify_waf_or_auth_codes_are_blocked_not_broken(code):
    outcome, err_code, _msg, retryable = classify_exception(_http_error(code))
    assert outcome == SourceOutcome.blocked
    assert err_code == f"HTTP_{code}"
    assert retryable is False


@pytest.mark.parametrize("code", [404, 410])
def test_classify_gone_urls_are_broken_not_retryable(code):
    outcome, err_code, _msg, retryable = classify_exception(_http_error(code))
    assert outcome == SourceOutcome.broken
    assert retryable is False


@pytest.mark.parametrize("code", [500, 502, 504])
def test_classify_server_errors_are_broken_and_retryable(code):
    outcome, _err_code, _msg, retryable = classify_exception(_http_error(code))
    assert outcome == SourceOutcome.broken
    assert retryable is True


def test_classify_timeout_is_retryable():
    outcome, err_code, _msg, retryable = classify_exception(requests.exceptions.Timeout())
    assert outcome == SourceOutcome.retryable
    assert err_code == "CONNECTION_FAILED"
    assert retryable is True


def test_classify_connection_error_is_retryable():
    outcome, _err_code, _msg, retryable = classify_exception(requests.exceptions.ConnectionError())
    assert outcome == SourceOutcome.retryable
    assert retryable is True


def test_classify_source_error_passes_through():
    e = SourceError(SourceOutcome.blocked, code="HTTP_403", message="waf", retryable=False)
    outcome, code, message, retryable = classify_exception(e)
    assert (outcome, code, message, retryable) == (
        SourceOutcome.blocked, "HTTP_403", "waf", False,
    )


def test_classify_ssl_error_is_retryable():
    outcome, err_code, _msg, retryable = classify_exception(requests.exceptions.SSLError())
    assert outcome == SourceOutcome.retryable
    assert retryable is True
    assert err_code in ("CONNECTION_FAILED", "SOURCE_UNAVAILABLE")


# =======================================================================
# 2. resolve_job_terminal_status — boundary branches
# =======================================================================


def test_terminal_zero_docs_is_failed(test_db):
    job = _create_job(test_db, [PARCEL])
    # Delete every document row — a job can be left with zero docs if the
    # worker's create step raced a soft-delete.
    for d in ResearchDocumentRepository.list_for_job(test_db, job.id):
        test_db.delete(d)
    test_db.commit()
    from app.engine.service import resolve_job_terminal_status

    assert resolve_job_terminal_status(test_db, job) == ResearchJobStatus.failed


def test_terminal_all_failed_is_failed(test_db):
    job = _create_job(test_db, [PARCEL, DEED])
    for d in ResearchDocumentRepository.list_for_job(test_db, job.id):
        d.status = ResearchDocStatus.failed
        ResearchDocumentRepository.save(test_db, d)
    test_db.commit()
    from app.engine.service import resolve_job_terminal_status

    assert resolve_job_terminal_status(test_db, job) == ResearchJobStatus.failed


def test_terminal_mixed_is_partial(test_db):
    job = _create_job(test_db, [PARCEL, DEED, FLOOD])
    docs = ResearchDocumentRepository.list_for_job(test_db, job.id)
    docs[0].status = ResearchDocStatus.uploaded
    docs[1].status = ResearchDocStatus.failed
    docs[2].status = ResearchDocStatus.skipped
    test_db.commit()
    from app.engine.service import resolve_job_terminal_status

    assert resolve_job_terminal_status(test_db, job) == ResearchJobStatus.partial


def test_terminal_cancelling_drains_to_cancelled(test_db):
    job = _create_job(test_db, [PARCEL, DEED])
    job.status = ResearchJobStatus.cancelling
    ResearchJobRepository.save(test_db, job)
    test_db.commit()
    from app.engine.service import resolve_job_terminal_status

    assert resolve_job_terminal_status(test_db, job) == ResearchJobStatus.cancelled


def test_terminal_all_uploaded_is_completed(test_db):
    job = _create_job(test_db, [PARCEL])
    for d in ResearchDocumentRepository.list_for_job(test_db, job.id):
        d.status = ResearchDocStatus.uploaded
        ResearchDocumentRepository.save(test_db, d)
    test_db.commit()
    from app.engine.service import resolve_job_terminal_status

    assert resolve_job_terminal_status(test_db, job) == ResearchJobStatus.completed


# =======================================================================
# 3. Celery worker task body (in-process, real DB)
# =======================================================================


def test_worker_full_success_resolves_completed_with_file_reference(test_db, monkeypatch):
    from app.engine.mappers import to_job_schema
    from app.engine.worker import research_job

    _wire_worker(monkeypatch, make_service(fetcher=_ok_fetcher(PARCEL, DEED)))
    job = _create_job(test_db, [PARCEL, DEED])

    research_job.run(job.id, TENANT_ID, ACTOR_ID)

    test_db.expire_all()
    job = ResearchJobRepository.get(test_db, job.id, TENANT_ID)
    assert job.status == ResearchJobStatus.completed
    assert job.started_at is not None and job.completed_at is not None
    assert job.uploaded_documents == 2
    assert job.failed_documents == 0

    schema = to_job_schema(test_db, job)
    for doc in schema.documents:
        assert doc.status == ResearchDocStatus.uploaded
        assert doc.file is not None
        assert str(doc.file.file_id)
        assert str(doc.file.order_file_id)
        assert doc.file.filename == "x.pdf"


def test_worker_partial_failure_resolves_partial_with_error_details(test_db, monkeypatch):
    from app.engine.mappers import to_job_schema
    from app.engine.worker import research_job

    _wire_worker(monkeypatch, make_service(fetcher=_failed_fetcher([FLOOD])))
    job = _create_job(test_db, [PARCEL, FLOOD])

    research_job.run(job.id, TENANT_ID, ACTOR_ID)

    test_db.expire_all()
    job = ResearchJobRepository.get(test_db, job.id, TENANT_ID)
    assert job.status == ResearchJobStatus.partial
    assert job.uploaded_documents == 1
    assert job.failed_documents == 1

    docs = {d.doc_type: d for d in ResearchDocumentRepository.list_for_job(test_db, job.id)}
    fa = docs[PARCEL]
    fi = docs[FLOOD]
    assert fa.status == ResearchDocStatus.uploaded
    assert fi.status == ResearchDocStatus.failed
    assert fi.error_code == "FLOOD_UNAVAILABLE"
    assert fi.retryable is False
    assert to_job_schema(test_db, job).documents[1].file is None


def test_worker_all_failed_resolves_failed(test_db, monkeypatch):
    from app.engine.worker import research_job

    _wire_worker(monkeypatch, make_service(fetcher=_failed_fetcher([PARCEL])))
    job = _create_job(test_db, [PARCEL])

    research_job.run(job.id, TENANT_ID, ACTOR_ID)

    test_db.expire_all()
    job = ResearchJobRepository.get(test_db, job.id, TENANT_ID)
    assert job.status == ResearchJobStatus.failed
    assert job.failed_documents == 1


def test_worker_observes_cancelling_mid_run_and_drains(test_db, monkeypatch):
    """A cancel from another session lands as `cancelling`; the worker skips
    the remaining docs and finalizes `cancelled` instead of `completed`."""
    from app.engine.worker import research_job

    entered = threading.Event()
    release = threading.Event()

    def blocking_fetcher(order, requested, tenant_id=None):
        for t in requested:
            if t == PARCEL:
                entered.set()
                if not release.wait(timeout=15):
                    raise TimeoutError("test setup: fetcher never released")
                # The cancel lands during this wait; we still return upload ok
                # for the doc that was already in flight.
                return {PARCEL: _ok_fetcher(PARCEL)(order, [PARCEL], tenant_id)[PARCEL]}
        return {t: _ok_fetcher(t)(order, [t], tenant_id)[t] for t in requested}

    svc = make_service(fetcher=blocking_fetcher)
    _wire_worker(monkeypatch, svc)
    job = _create_job(test_db, [PARCEL, DEED, FLOOD])

    result_holder = []

    def run_worker():
        result_holder.append(research_job.run(job.id, TENANT_ID, ACTOR_ID))

    worker_thread = threading.Thread(target=run_worker)
    worker_thread.start()
    assert entered.wait(timeout=15), "worker never reached the blocking fetch"

    # Simulate the API process cancelling mid-run. The test session's identity
    # map still has the queued-era job object (expire_on_commit=False), so
    # expire first — a real cancel request opens a fresh session and reads
    # `running` for a job the worker already picked up.
    test_db.expire_all()
    svc.cancel_job(test_db, tenant_id=TENANT_ID, job_id=job.id)
    assert ResearchJobRepository.get(test_db, job.id, TENANT_ID).status == ResearchJobStatus.cancelling

    release.set()
    worker_thread.join(timeout=15)
    assert not worker_thread.is_alive(), "worker did not drain after the cancel"

    test_db.expire_all()
    job = ResearchJobRepository.get(test_db, job.id, TENANT_ID)
    assert job.status == ResearchJobStatus.cancelled
    assert job.uploaded_documents == 1       # the in-flight parcel finished
    assert job.cancelled_documents == 2      # the remaining two were skipped


def test_worker_skips_delivered_after_cancel(test_db, monkeypatch):
    """A job that reaches the worker already cancelled must not be overwritten
    to `running` — every document drains to `skipped`."""
    from app.engine.worker import research_job

    calls = []

    def spy_fetcher(order, requested, tenant_id=None):
        calls.append(requested)
        return {t: _ok_fetcher(t)(order, [t], tenant_id)[t] for t in requested}

    _wire_worker(monkeypatch, make_service(fetcher=spy_fetcher))
    job = _create_job(test_db, [PARCEL, DEED])
    job.status = ResearchJobStatus.cancelling
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    research_job.run(job.id, TENANT_ID, ACTOR_ID)

    test_db.expire_all()
    job = ResearchJobRepository.get(test_db, job.id, TENANT_ID)
    assert job.status == ResearchJobStatus.cancelled
    assert job.cancelled_documents == 2
    assert calls == []  # zero fetches — the drain happened before any source hit


def test_worker_adapter_raises_unexpected_sets_internal_error(test_db, monkeypatch):
    """The worker's `except Exception` per-document branch (INTERNAL_ERROR) is
    the most common production failure path — pin it explicitly."""
    from app.engine.worker import research_job

    def boom_fetcher(order, requested, tenant_id=None):
        raise RuntimeError("unexpected boom")

    _wire_worker(monkeypatch, make_service(fetcher=boom_fetcher))
    job = _create_job(test_db, [PARCEL, DEED])

    research_job.run(job.id, TENANT_ID, ACTOR_ID)

    test_db.expire_all()
    job = ResearchJobRepository.get(test_db, job.id, TENANT_ID)
    assert job.status == ResearchJobStatus.failed
    assert job.failed_documents == 2
    docs = ResearchDocumentRepository.list_for_job(test_db, job.id)
    for d in docs:
        assert d.status == ResearchDocStatus.failed
        assert d.error_code == "INTERNAL_ERROR"
        assert "unexpected boom" in d.error_message
        assert d.retryable is True
        assert d.retry_count == 1


def test_worker_carries_provenance_and_warnings(test_db, monkeypatch):
    """Provenance + warnings on a fetched document must be persisted to the
    ORM row so the mapper can surface them in the API."""
    from app.engine.worker import research_job

    prov = [{"file": "x.pdf", "source": "https://s.test/f", "sha256": "abc", "fetched_utc": "2026-01-01T00:00:00Z"}]

    def fetcher(order, requested, tenant_id=None):
        out = {}
        for t in requested:
            src = _ok_fetcher(t)(order, [t], tenant_id)[t]
            src.provenance = prov
            src.warnings = ["verify the boundary"]
            out[t] = src
        return out

    _wire_worker(monkeypatch, make_service(fetcher=fetcher))
    job = _create_job(test_db, [PARCEL])

    research_job.run(job.id, TENANT_ID, ACTOR_ID)

    test_db.expire_all()
    docs = ResearchDocumentRepository.list_for_job(test_db, job.id)
    assert docs[0].provenance == prov
    assert docs[0].warnings == ["verify the boundary"]


def test_worker_fires_callback_on_completion(test_db, monkeypatch):
    """When a job has a callback_url, the worker POSTs the job summary on
    completion (payload verified, delivery mocked — offline)."""
    from app.engine.worker import research_job

    captured = {}

    class _FakeResp:
        status_code = 200

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        return _FakeResp()

    monkeypatch.setattr("httpx.post", fake_post)
    _wire_worker(monkeypatch, make_service(fetcher=_ok_fetcher(PARCEL)))
    job = _create_job(test_db, [PARCEL])
    job.callback_url = "https://example.test/cb"
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    research_job.run(job.id, TENANT_ID, ACTOR_ID)

    assert captured["url"] == "https://example.test/cb"
    payload = captured["payload"]
    assert payload["job_id"] == str(job.id)
    assert payload["status"] == "completed"
    assert payload["total"] == 1
    assert payload["uploaded"] == 1
    assert payload["failed"] == 0


def test_worker_callback_failure_is_nonfatal(test_db, monkeypatch):
    """A failing callback delivery is logged, not fatal — the job still
    resolves to its terminal status."""
    from app.engine.worker import research_job

    def fake_post(url, json=None, timeout=None):
        raise RuntimeError("callback down")

    monkeypatch.setattr("httpx.post", fake_post)
    _wire_worker(monkeypatch, make_service(fetcher=_ok_fetcher(PARCEL)))
    job = _create_job(test_db, [PARCEL])
    job.callback_url = "https://example.test/cb"
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    research_job.run(job.id, TENANT_ID, ACTOR_ID)

    test_db.expire_all()
    job = ResearchJobRepository.get(test_db, job.id, TENANT_ID)
    assert job.status == ResearchJobStatus.completed


def test_retry_from_cancelled_creates_new_job(test_db):
    """cancelled jobs are retryable (in the allowed-terminal set)."""
    from app.engine.service import ResearchService

    svc = make_service()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=[PARCEL, DEED], idempotency_key=None,
    )
    docs = ResearchDocumentRepository.list_for_job(test_db, job.id)
    docs[0].status = ResearchDocStatus.failed
    ResearchDocumentRepository.save(test_db, docs[0])
    job.status = ResearchJobStatus.cancelled
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    retried = svc.retry_job(test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID, job_id=job.id)
    assert retried.id != job.id
    assert retried.requested_doc_types == [docs[0].doc_type]


def test_retry_no_failed_docs_is_rejected(test_db):
    """Retrying a job with zero failed documents raises (nothing to redo)."""
    from app.engine.errors import OrderNotResearchableError

    svc = make_service()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=[PARCEL], idempotency_key=None,
    )
    job.status = ResearchJobStatus.completed
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    with pytest.raises(OrderNotResearchableError):
        svc.retry_job(test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID, job_id=job.id)


def test_mark_reviewed_from_partial_allowed(test_db):
    """A partial job (some docs failed) is still sign-off-able as reviewed."""
    svc = make_service()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=[PARCEL], idempotency_key=None,
    )
    job.status = ResearchJobStatus.partial
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    assert svc.mark_reviewed(test_db, tenant_id=TENANT_ID, job_id=job.id).status == ResearchJobStatus.reviewed


def test_mark_reviewed_rejects_failed(test_db):
    """A job that entirely failed cannot be signed off as reviewed."""
    from app.engine.errors import OrderNotResearchableError

    svc = make_service()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=[PARCEL], idempotency_key=None,
    )
    job.status = ResearchJobStatus.failed
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    with pytest.raises(OrderNotResearchableError):
        svc.mark_reviewed(test_db, tenant_id=TENANT_ID, job_id=job.id)


def test_archive_rejects_completed(test_db):
    """Only a reviewed job can be archived — `completed` must be rejected."""
    from app.engine.errors import OrderNotResearchableError

    svc = make_service()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=[PARCEL], idempotency_key=None,
    )
    job.status = ResearchJobStatus.completed
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    with pytest.raises(OrderNotResearchableError):
        svc.archive_job(test_db, tenant_id=TENANT_ID, job_id=job.id)


# =======================================================================
# 4. Step assembly — manual_review + last-resort fallback
# =======================================================================


def test_manual_review_outcome_reachable_for_buffered_parcel(tmp_path, adapters):
    """A parcel polygon found via a buffered point (no address confirmation)
    must surface as `manual_review` — the contract already declared the value,
    now an honest path through the adapter reaches it."""
    from app.engine.orchestration.steps import build_steps

    folder = tmp_path / "jobs" / "A-1" / "research"
    ctx = _make_ctx(
        folder,
        parcel_ok=False,
        parcel={
            "method": "arcgis-rest",
            "parcels": [{"folio": "PIN-1", "situs": "1 Buffered St"}],
            "buffered_match": True,
            "address_match": None,
            "hints": {},
            "source": "https://gis.example.test/",
        },
    )

    steps = build_steps(ctx, include=["parcel"])
    (step,) = steps
    assert step.status == StepStatus.link
    assert step.source_outcome == SourceOutcome.manual_review
    assert step.confidence == Confidence.low
    assert step.warnings, "a manual-review step must carry an actionable warning"
    assert step.error is None
    assert step.link == "https://pa.example.test/"


def test_plain_no_match_parcel_is_not_manual_review(tmp_path, adapters):
    """Absence of any polygon stays a plain `link_only` — the review flag is
    reserved for data-present-but-ambiguous, not for nothing-found."""
    from app.engine.orchestration.steps import build_steps

    folder = tmp_path / "jobs" / "A-2" / "research"
    ctx = _make_ctx(folder, parcel_ok=False, parcel={
        "method": "arcgis-rest", "parcels": [], "address_match": False, "hints": {},
    })

    (step,) = build_steps(ctx, include=["parcel"])
    assert step.source_outcome == SourceOutcome.link_only
    assert step.source_outcome != SourceOutcome.manual_review
    assert step.error is None


def test_fallback_internal_raise_yields_last_resort_link(tmp_path, adapters):
    """If an adapter both fails and its fallback raises, the step degrades to a
    blank link + structured error — never a raw traceback."""
    from app.engine.orchestration.steps import build_steps

    class _BoomAdapter(SourceAdapter):
        key = "flood"

        def fetch(self, ctx, docs_dir):
            raise RuntimeError("boom inside fetch")

        def fallback(self, ctx, error=None):
            raise RuntimeError("boom inside fallback")

    adapters["parcel"] = type("Q", (SourceAdapter,), {
        "key": "parcel",
        "fetch": lambda self, ctx, docs_dir: FetchedSource(status=StepStatus.ok, summary="ok"),
        "fallback": lambda self, ctx, error=None: FetchedSource(status=StepStatus.link),
    })()
    adapters["flood"] = _BoomAdapter()

    folder = tmp_path / "jobs" / "A-3" / "research"
    ctx = _make_ctx(folder)
    steps = build_steps(ctx, include=["parcel", "flood"])
    by_key = {s.key: s for s in steps}

    flood = by_key["flood"]
    assert flood.status == StepStatus.link
    assert flood.link == ""
    assert flood.summary == "Couldn't reach this source."
    assert flood.error is not None
    assert flood.error.code == "ADAPTER_ERROR"
    assert flood.error.retryable is True
    assert flood.source_outcome == SourceOutcome.retryable

    assert by_key["parcel"].status == StepStatus.ok
    assert by_key["parcel"].source_outcome == SourceOutcome.auto
    assert by_key["parcel"].confidence == Confidence.high


def test_step_result_keeps_frozen_fields_plus_additive(tmp_path, adapters):
    """Every assembled step carries the 17 frozen POC fields beside the
    additive engine fields — a renderer built for the POC keeps working."""
    from app.engine.orchestration.steps import build_steps

    for key in list(adapters):
        adapters[key] = type("F", (SourceAdapter,), {
            "key": key,
            "fetch": lambda self, ctx, docs_dir: FetchedSource(status=StepStatus.ok, summary="ok"),
            "fallback": lambda self, ctx, error=None: FetchedSource(status=StepStatus.link),
        })()

    folder = tmp_path / "jobs" / "A-4" / "research"
    ctx = _make_ctx(folder)
    step = build_steps(ctx, include=["parcel"])[0]

    frozen = {
        "key", "label", "requirement", "condition", "description", "summary",
        "status", "link", "link_label", "source_url", "saved_file", "data",
        "downloaded", "situs", "land_sqft", "land_acres", "address_match",
    }
    dumped = step.model_dump()
    assert frozen <= set(dumped)
    # additive fields are present and sane in the same payload
    assert dumped["source_outcome"] == "auto"
    assert dumped["confidence"] == "high"
    assert isinstance(dumped["provenance"], list)
    assert isinstance(dumped["warnings"], list)
    assert dumped["error"] is None