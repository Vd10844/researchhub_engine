"""Callback_url delivery tests (validation-plan 2.3).

``job-lifecycle.md`` promises an optional ``callback_url`` POST on a job
reaching terminal state, delivered at-least-once with retry + backoff, where
delivery failures are logged but never fatal to the job. These tests exercise
``_fire_callback`` directly against a mocked httpx transport:

  - success marks ``callback_delivered=True`` with the correct payload shape
  - a 5xx/timeout from the callback does NOT touch the job's terminal status
  - retries are honored (attempts exhausted before giving up)
"""
from __future__ import annotations

import json
import uuid
from unittest import mock

import app.engine.worker as worker_mod
import pytest
import respx
from app.engine.models import ResearchJob
from app.engine.repository import ResearchJobRepository
from app.engine.schemas import ResearchJobStatus
from httpx import Response

TENANT = uuid.UUID("f0000000-0000-0000-0000-000000000001")
ORDER = uuid.UUID("f0000000-0000-0000-0000-000000000010")
CALLBACK = "https://example.test/hooks/research/job-complete"


@pytest.fixture
def completed_job(test_db):
    job = ResearchJob(
        tenant_id=TENANT,
        order_id=ORDER,
        status=ResearchJobStatus.completed,
        idempotency_key=uuid.uuid4(),
        requested_doc_types=["PARCEL_RECORD"],
        callback_url=CALLBACK,
    )
    ResearchJobRepository.save(test_db, job)
    test_db.commit()
    test_db.refresh(job)
    return job


def _no_sleep():
    """Patch out retry backoff sleeps so offline tests don't stall."""
    return mock.patch.object(worker_mod.settings, "CALLBACK_RETRY_SLEEP", False)


@respx.mock
def test_callback_success_marks_delivered(completed_job, test_db):
    route = respx.post(CALLBACK).mock(return_value=Response(200, json={"ok": True}))
    with _no_sleep():
        worker_mod._fire_callback(completed_job, test_db)

    assert route.called
    payload = json.loads(route.calls[0].request.content)
    assert payload["job_id"] == str(completed_job.id)
    assert payload["order_id"] == str(ORDER)
    assert payload["status"] == ResearchJobStatus.completed.value
    assert "total" in payload and "uploaded" in payload and "failed" in payload

    test_db.refresh(completed_job)
    assert completed_job.callback_delivered is True


@respx.mock
def test_callback_http_500_retries_then_gives_up(completed_job, test_db):
    route = respx.post(CALLBACK).mock(return_value=Response(500, json={}))
    with _no_sleep(), mock.patch.object(worker_mod.settings, "CALLBACK_RETRY_ATTEMPTS", 3):
        worker_mod._fire_callback(completed_job, test_db)

    # At-least-once: exhausted all 3 attempts.
    assert route.call_count == 3
    test_db.refresh(completed_job)
    assert completed_job.callback_delivered is False
    # Job terminal status untouched by callback failure
    assert completed_job.status == ResearchJobStatus.completed


@respx.mock
def test_callback_timeout_is_not_fatal_to_job(completed_job, test_db):
    def _timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    route = respx.post(CALLBACK).mock(side_effect=_timeout)
    with _no_sleep(), mock.patch.object(worker_mod.settings, "CALLBACK_RETRY_ATTEMPTS", 2):
        worker_mod._fire_callback(completed_job, test_db)

    assert route.call_count == 2
    test_db.refresh(completed_job)
    assert completed_job.callback_delivered is False
    assert completed_job.status == ResearchJobStatus.completed


@respx.mock
def test_callback_4xx_is_treated_as_failure(completed_job, test_db):
    respx.post(CALLBACK).mock(return_value=Response(400, json={}))
    with _no_sleep(), mock.patch.object(worker_mod.settings, "CALLBACK_RETRY_ATTEMPTS", 1):
        worker_mod._fire_callback(completed_job, test_db)

    test_db.refresh(completed_job)
    assert completed_job.callback_delivered is False
    assert completed_job.status == ResearchJobStatus.completed
