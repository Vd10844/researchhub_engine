"""Celery app + the research job worker task.

The worker is the ONLY place that runs the orchestrator. It:
  1. Loads the pending job from the DB
  2. Marks each document ``fetching``
  3. Calls the document fetcher (orchestrator wrapper)
  4. Uploads results to S3 + creates File/OrderFile rows
  5. Marks documents ``uploaded`` / ``failed``
  6. Resolves the terminal job status + fires the callback

``task_acks_late=True`` + ``worker_prefetch_multiplier=1`` mean a worker
crash requeues the task instead of silently dropping it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from celery import Celery

from app.config import settings
from app.db.base import SessionLocal
from app.engine.adapters import build_research_service
from app.engine.repository import ResearchDocumentRepository, ResearchJobRepository
from app.engine.schemas import ResearchDocStatus, ResearchJobStatus
from app.engine.service import (
    recalc_job_counters,
    resolve_job_terminal_status,
)

celery_app = Celery(
    "researchhub",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_default_queue="research",
    task_routes={"app.engine.worker.research_job": {"queue": "research"}},
)


def enqueue_research_job(*, job_id, tenant_id, actor_id) -> None:
    """Publish the job's Celery task to the ``research`` queue.

    Called by ``ResearchService.create_job`` once the job row is committed.
    Kept here (workers are the only place that may run the orchestrator).
    """
    import uuid as _uuid

    job_id = _uuid.UUID(str(job_id))
    tenant_id = _uuid.UUID(str(tenant_id))
    actor_id = _uuid.UUID(str(actor_id))
    research_job.delay(job_id, tenant_id, actor_id)


@celery_app.task(name="app.engine.worker.research_job", bind=True, max_retries=1)
def research_job(self, job_id, tenant_id, actor_id):
    """Process a research job: fetch all requested documents, upload to S3.

    Runs in the Celery worker. One task per job (parallelism happens
    *inside* the document fetcher via ThreadPoolExecutor).
    """
    service = build_research_service()
    db = SessionLocal()
    started = datetime.now(timezone.utc)
    try:
        job = ResearchJobRepository.get(db, job_id, tenant_id)
        if job is None:
            return  # job deleted/soft-deleted underneath us

        job.status = ResearchJobStatus.running
        job.started_at = started
        ResearchJobRepository.save(db, job)
        db.commit()

        docs = ResearchDocumentRepository.list_for_job(db, job_id)
        order = service.order_provider(job.order_id, tenant_id)

        for doc in docs:
            if job.status == ResearchJobStatus.cancelled:
                doc.status = ResearchDocStatus.skipped
                ResearchDocumentRepository.save(db, doc)
                continue

            doc.status = ResearchDocStatus.fetching
            ResearchDocumentRepository.save(db, doc)
            db.commit()

            try:
                fetched = service.document_fetcher(order, [doc.doc_type], tenant_id=tenant_id)[doc.doc_type]
                doc.status = fetched.status
                doc.summary = fetched.summary
                doc.link = fetched.link
                doc.link_label = fetched.link_label
                doc.provenance = fetched.provenance
                doc.warnings = fetched.warnings
                doc.fetched_at = datetime.now(timezone.utc)

                if fetched.status == ResearchDocStatus.uploaded and fetched.file_key:
                    doc.file_id = fetched.file_id
                    doc.order_file_id = fetched.order_file_id
                    doc.uploaded_at = datetime.now(timezone.utc)
                elif fetched.status == ResearchDocStatus.failed:
                    doc.error_code = fetched.error_code.value if fetched.error_code else None
                    doc.error_message = fetched.error_message
                    doc.retryable = fetched.retryable
                    doc.retry_count += 1
            except Exception as e:  # noqa: BLE001
                doc.status = ResearchDocStatus.failed
                doc.error_code = "INTERNAL_ERROR"
                doc.error_message = str(e)
                doc.retryable = True
                doc.retry_count += 1

            ResearchDocumentRepository.save(db, doc)
            db.commit()

        recalc_job_counters(job, docs)
        job.status = resolve_job_terminal_status(db, job)
        job.completed_at = datetime.now(timezone.utc)
        ResearchJobRepository.save(db, job)
        db.commit()

        if job.callback_url:
            _fire_callback(job, db)

    except Exception:  # noqa: BLE001
        db.rollback()
        raise self.retry(countdown=30)
    finally:
        db.close()


def _fire_callback(job, db):
    """POST job summary to callback_url (optional delivery; failures logged, not fatal)."""
    import logging

    import httpx

    logger = logging.getLogger("researchhub.worker")
    docs = ResearchDocumentRepository.list_for_job(db, job.id)
    payload = {
        "job_id": str(job.id),
        "order_id": str(job.order_id),
        "status": job.status.value,
        "total": len(docs),
        "uploaded": job.uploaded_documents,
        "failed": job.failed_documents,
    }
    try:
        httpx.post(job.callback_url, json=payload, timeout=10)
    except Exception as e:  # noqa: BLE001
        logger.warning("callback delivery failed for job %s: %s", job.id, e)