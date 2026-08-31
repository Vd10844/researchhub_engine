"""Service-layer tests — run fully offline with injected fake dependencies."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.engine.errors import (
    JobNotFoundError,
    OrderNotResearchableError,
)
from app.engine.repository import ResearchDocumentRepository, ResearchJobRepository
from app.engine.schemas import ResearchDocStatus, ResearchJobStatus
from app.engine.service import FetchedDocument, OrderData, ResearchService

TENANT_ID = uuid.UUID("f0000000-0000-0000-0000-000000000001")
ACTOR_ID = uuid.UUID("f0000000-0000-0000-0000-000000000002")
ORDER_ID = uuid.UUID("f0000000-0000-0000-0000-000000000010")


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


def service_with(order: OrderData | None = make_order(), fetcher=None) -> ResearchService:
    return ResearchService(
        order_provider=lambda oid, tid: order,
        document_fetcher=fetcher or _ok_fetcher(),
        file_storage=MagicMock(),
    )


def _ok_fetcher(doc_type: str = "PARCEL_RECORD"):
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


# ------------------------------------------------------------------ create


def test_create_job_creates_rows_and_documents(test_db):
    svc = service_with()
    job = svc.create_job(
        test_db,
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        order_id=ORDER_ID,
        doc_types=["PARCEL_RECORD", "FEMA_FLOOD_ZONE_FIRM"],
        idempotency_key=None,
    )
    assert job.status == ResearchJobStatus.queued
    assert job.total_documents == 2
    docs = ResearchDocumentRepository.list_for_job(test_db, job.id)
    assert {d.doc_type for d in docs} == {"PARCEL_RECORD", "FEMA_FLOOD_ZONE_FIRM"}
    assert all(d.status == ResearchDocStatus.queued for d in docs)


def test_create_job_idempotent_same_key_returns_existing(test_db):
    svc = service_with()
    key = uuid.uuid4()
    j1 = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=["PARCEL_RECORD"],
        idempotency_key=key,
    )
    j2 = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=["PARCEL_RECORD"],
        idempotency_key=key,
    )
    assert j1.id == j2.id


def test_create_job_raises_when_order_missing(test_db):
    svc = service_with(order=None)
    from app.engine.errors import OrderNotFoundError

    with pytest.raises(OrderNotFoundError):
        svc.create_job(
            test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
            order_id=ORDER_ID, doc_types=["PARCEL_RECORD"],
            idempotency_key=None,
        )


def test_create_job_raises_when_order_has_no_address(test_db):
    order = make_order()
    order.address_line_1 = ""
    svc = service_with(order=order)
    with pytest.raises(OrderNotResearchableError):
        svc.create_job(
            test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
            order_id=ORDER_ID, doc_types=["PARCEL_RECORD"],
            idempotency_key=None,
        )


def test_create_job_rejects_empty_doc_types(test_db):
    svc = service_with()
    from app.engine.errors import InvalidDocTypesError

    with pytest.raises(InvalidDocTypesError):
        svc.create_job(
            test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
            order_id=ORDER_ID, doc_types=[], idempotency_key=None,
        )


# ------------------------------------------------------------------ get / list


def test_get_job_not_found_raises(test_db):
    svc = service_with()
    with pytest.raises(JobNotFoundError):
        svc.get_job(test_db, tenant_id=TENANT_ID, job_id=uuid.uuid4())


def test_list_order_jobs_returns_newest_first(test_db):
    svc = service_with()
    svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=["PARCEL_RECORD"], idempotency_key=None,
    )
    svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=["FEMA_FLOOD_ZONE_FIRM"], idempotency_key=None,
    )
    jobs = svc.list_order_jobs(test_db, tenant_id=TENANT_ID, order_id=ORDER_ID)
    assert len(jobs) == 2
    assert [j.total_documents for j in jobs][0] == 1  # newest first


# ------------------------------------------------------------------ retry / cancel


def test_retry_creates_new_job_with_failed_types(test_db):
    svc = service_with()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID,
        doc_types=["PARCEL_RECORD", "DEED_SUBJECT_PARCEL"],
        idempotency_key=None,
    )
    # Simulate one failure + a partial job state (as the worker would leave it).
    docs = ResearchDocumentRepository.list_for_job(test_db, job.id)
    docs[0].status = ResearchDocStatus.failed
    ResearchDocumentRepository.save(test_db, docs[0])
    job.status = ResearchJobStatus.partial
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    retried = svc.retry_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID, job_id=job.id
    )
    assert retried.id != job.id
    assert retried.total_documents == 1
    assert retried.requested_doc_types == [docs[0].doc_type]


def test_cancel_transitions_queued_job(test_db):
    svc = service_with()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=["PARCEL_RECORD"], idempotency_key=None,
    )
    cancelled = svc.cancel_job(test_db, tenant_id=TENANT_ID, job_id=job.id)
    assert cancelled.status == ResearchJobStatus.cancelled


def test_cancel_rejects_terminal_job(test_db):
    svc = service_with()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=["PARCEL_RECORD"], idempotency_key=None,
    )
    job.status = ResearchJobStatus.completed
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    with pytest.raises(OrderNotResearchableError):
        svc.cancel_job(test_db, tenant_id=TENANT_ID, job_id=job.id)


def test_cancel_queue_stores_reason(test_db):
    svc = service_with()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=["PARCEL_RECORD"], idempotency_key=None,
    )
    cancelled = svc.cancel_job(
        test_db, tenant_id=TENANT_ID, job_id=job.id, reason="duplicate order"
    )
    assert cancelled.status == ResearchJobStatus.cancelled
    assert cancelled.cancel_reason == "duplicate order"


def test_cancel_running_job_goes_cancelling_and_records_reason(test_db):
    """A running job enters `cancelling` (not a hard `cancelled`): the worker
    drains in-flight work, skips the rest, then finalizes. The reason is kept
    for the audit trail."""
    svc = service_with()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=["PARCEL_RECORD"], idempotency_key=None,
    )
    job.status = ResearchJobStatus.running
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    cancelled = svc.cancel_job(
        test_db, tenant_id=TENANT_ID, job_id=job.id, reason="client requested"
    )
    assert cancelled.status == ResearchJobStatus.cancelling
    assert cancelled.cancel_reason == "client requested"


# ------------------------------------------------------------------ review / archive


def test_mark_reviewed_from_completed(test_db):
    svc = service_with()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=["PARCEL_RECORD"], idempotency_key=None,
    )
    job.status = ResearchJobStatus.completed
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    reviewed = svc.mark_reviewed(test_db, tenant_id=TENANT_ID, job_id=job.id)
    assert reviewed.status == ResearchJobStatus.reviewed


def test_mark_reviewed_rejects_queued_job(test_db):
    svc = service_with()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=["PARCEL_RECORD"], idempotency_key=None,
    )
    with pytest.raises(OrderNotResearchableError):
        svc.mark_reviewed(test_db, tenant_id=TENANT_ID, job_id=job.id)


def test_archive_only_from_reviewed(test_db):
    svc = service_with()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=["PARCEL_RECORD"], idempotency_key=None,
    )
    job.status = ResearchJobStatus.reviewed
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    archived = svc.archive_job(test_db, tenant_id=TENANT_ID, job_id=job.id)
    assert archived.status == ResearchJobStatus.archived


def test_archive_rejects_non_reviewed(test_db):
    svc = service_with()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID, doc_types=["PARCEL_RECORD"], idempotency_key=None,
    )
    job.status = ResearchJobStatus.completed
    ResearchJobRepository.save(test_db, job)
    test_db.commit()

    with pytest.raises(OrderNotResearchableError):
        svc.archive_job(test_db, tenant_id=TENANT_ID, job_id=job.id)


# ------------------------------------------------------------------ counters/terminal


def test_recalc_job_counters(test_db):
    svc = service_with()
    job = svc.create_job(
        test_db, tenant_id=TENANT_ID, actor_id=ACTOR_ID,
        order_id=ORDER_ID,
        doc_types=["PARCEL_RECORD", "DEED_SUBJECT_PARCEL", "FLOOD"],
        idempotency_key=None,
    )
    docs = ResearchDocumentRepository.list_for_job(test_db, job.id)
    docs[0].status = ResearchDocStatus.uploaded
    docs[1].status = ResearchDocStatus.failed
    docs[2].status = ResearchDocStatus.skipped

    from app.engine.service import recalc_job_counters
    recalc_job_counters(job, docs)
    assert job.uploaded_documents == 1
    assert job.failed_documents == 1
    assert job.cancelled_documents == 1

    from app.engine.service import resolve_job_terminal_status
    assert resolve_job_terminal_status(test_db, job) == ResearchJobStatus.partial