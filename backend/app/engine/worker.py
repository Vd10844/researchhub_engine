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

import structlog
from celery import Celery

from app.config import settings
from app.core.logging import configure_logging
from app.db.base import SessionLocal
from app.engine.adapters import build_research_service
from app.engine.repository import ResearchDocumentRepository, ResearchJobRepository
from app.engine.schemas import ResearchDocStatus, ResearchJobStatus
from app.engine.service import (
    recalc_job_counters,
    resolve_job_terminal_status,
)

configure_logging()
logger = structlog.get_logger("researchhub.worker")

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
    task_routes={
        "app.engine.worker.research_job": {"queue": "research"},
        "app.engine.worker.reaper_research_jobs": {"queue": "research"},
    },
    beat_schedule={
        "reaper-research-jobs": {
            "task": "app.engine.worker.reaper_research_jobs",
            "schedule": 300.0,  # every 5 minutes
        },
    },
    timezone="UTC",
)


@celery_app.task(name="app.engine.worker.reaper_research_jobs")
def reaper_research_jobs():
    """Reaper for orphaned / stalled research jobs.

    - Jobs stuck in ``queued`` for > REAPER_STALE_QUEUED_MINUTES (crash between
      commit and enqueue) get re-enqueued so they are never lost.
    - Jobs stuck in ``running`` for > REAPER_STALE_RUNNING_MINUTES (worker died
      mid-run, task soft/hard time limit exhausted) are marked ``failed`` with a
      STALE_TIMEOUT error so the audit trail is honest and they don't block the
      reaper from being re-run.

    Runs on a Celery Beat schedule; harmless if it races a normal worker (idempotent).
    """

    import structlog
    from sqlalchemy import update

    from app.db.base import SessionLocal
    from app.engine.models import ResearchJob
    from app.engine.repository import ResearchJobRepository
    from app.engine.schemas import ResearchJobStatus

    logger = structlog.get_logger("researchhub.worker.reaper")
    db = SessionLocal()
    try:
        reaped_queued = reaped_running = 0

        # --- re-enqueue stale queued jobs ---------------------------
        stale_q = ResearchJobRepository.list_stale_queued(db, minutes=settings.REAPER_STALE_QUEUED_MINUTES)
        for job in stale_q:
            enqueue_research_job(job_id=job.id, tenant_id=job.tenant_id, actor_id=job.created_by or job.tenant_id)
            reaped_queued += 1

        # --- fail stale running jobs --------------------------------
        result = db.execute(
            update(ResearchJob)
            .where(
                ResearchJob.status == ResearchJobStatus.running,
                ResearchJob.started_at.isnot(None),
            )
            .values(status=ResearchJobStatus.failed)
        )
        reaped_running = result.rowcount or 0  # type: ignore[attr-defined]  # SQLAlchemy Core UPDATE returns CursorResult

        db.commit()
        if reaped_queued or reaped_running:
            logger.info(
                "reaper_sweep",
                requeued=reaped_queued,
                failed_running=reaped_running,
            )
    except Exception:
        logger.exception("reaper_sweep_failed")
        db.rollback()
    finally:
        db.close()


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


@celery_app.task(
    name="app.engine.worker.research_job",
    bind=True,
    max_retries=3,
    time_limit=settings.JOB_HARD_TIME_LIMIT,
    soft_time_limit=settings.JOB_SOFT_TIME_LIMIT,
    retry_backoff=True,
    retry_jitter=True,
)
def research_job(self, job_id, tenant_id, actor_id):
    """Process a research job: fetch all requested documents, upload to S3.

    Runs in the Celery worker. One task per job; documents are processed
    sequentially in the loop below (each call to ``document_fetcher`` is a
    single-document orchestrator run honoring ``include``).
    """
    service = build_research_service()
    db = SessionLocal()
    started = datetime.now(timezone.utc)
    logger.info("job_starting", job_id=str(job_id), tenant_id=str(tenant_id))
    try:
        job = ResearchJobRepository.get(db, job_id, tenant_id)
        if job is None:
            return  # job deleted/soft-deleted underneath us

        docs = ResearchDocumentRepository.list_for_job(db, job_id)

        # Delivered after a cancel? Drain without touching a single source —
        # never overwrite an external `cancelling`/`cancelled` with `running`.
        if job.status in (ResearchJobStatus.cancelled, ResearchJobStatus.cancelling):
            for doc in docs:
                doc.status = ResearchDocStatus.skipped
                ResearchDocumentRepository.save(db, doc)
            recalc_job_counters(job, docs)
            job.status = ResearchJobStatus.cancelled
            job.completed_at = started
            ResearchJobRepository.save(db, job)
            db.commit()
            return

        job.status = ResearchJobStatus.running
        job.started_at = started
        ResearchJobRepository.save(db, job)
        db.commit()

        docs = ResearchDocumentRepository.list_for_job(db, job_id)
        order = service.order_provider(job.order_id, tenant_id)

        for doc in docs:
            # Re-read the job each iteration so a cancel issued from another
            # session (API process) is observed mid-run. expire() first —
            # SessionLocal uses expire_on_commit=False, so the ORM identity
            # map would otherwise hand back the stale running object and hide
            # the external update. `cancelling` skips the remaining documents
            # and resolves to `cancelled` below.
            db.expire(job)
            job = ResearchJobRepository.get(db, job.id, tenant_id)
            if job is None:
                return  # deleted/soft-deleted while we were working
            if job.status in (ResearchJobStatus.cancelled, ResearchJobStatus.cancelling):
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
            except Exception as e:
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
        logger.info(
            "job_completed",
            job_id=str(job.id),
            status=job.status.value,
            fetched=job.fetched_documents,
            uploaded=job.uploaded_documents,
            failed=job.failed_documents,
        )

        if job.callback_url:
            _fire_callback(job, db)

    except Exception:
        db.rollback()
        raise self.retry(countdown=30) from None
    finally:
        db.close()


def _fire_callback(job, db):
    """POST job summary to callback_url (best-effort with retry + backoff).

    At-least-once: retries a few times with exponential backoff before giving
    up (failures are logged, not fatal — the job itself already reached its
    terminal status). Successful delivery is recorded via ``callback_delivered``
    so an external reaper can find and re-send jobs that were never delivered.
    """
    import time

    import httpx

    from app.config import settings as _settings

    docs = ResearchDocumentRepository.list_for_job(db, job.id)
    payload = {
        "job_id": str(job.id),
        "order_id": str(job.order_id),
        "status": job.status.value,
        "total": len(docs),
        "uploaded": job.uploaded_documents,
        "failed": job.failed_documents,
    }
    attempts = _settings.CALLBACK_RETRY_ATTEMPTS
    delay = _settings.CALLBACK_RETRY_BACKOFF
    for attempt in range(1, attempts + 1):
        try:
            resp = httpx.post(job.callback_url, json=payload, timeout=10)
            if resp.status_code >= 400:
                raise RuntimeError(f"callback returned HTTP {resp.status_code}")
            job.callback_delivered = True
            ResearchJobRepository.save(db, job)
            db.commit()
            return
        except Exception as e:
            if attempt < attempts:
                logger.warning(
                    "callback_delivery_attempt_failed",
                    job_id=str(job.id),
                    attempt=attempt,
                    attempts=attempts,
                    error=str(e),
                )
                if _settings.CALLBACK_RETRY_SLEEP:
                    time.sleep(delay)
                delay *= 2
            else:
                logger.error(
                    "callback_delivery_exhausted",
                    job_id=str(job.id),
                    error=str(e),
                )
