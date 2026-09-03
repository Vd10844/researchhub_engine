"""Repository layer — DB queries for research jobs and documents.

All queries are tenant-scoped. The tenant filter comes from the auth
middleware (via ``X-Tenant-ID``) — never from request params.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.models import ResearchDocument, ResearchJob
from app.engine.schemas import ResearchJobStatus


class ResearchJobRepository:
    """Queries for ``research_jobs``."""

    @staticmethod
    def get(db: Session, job_id: UUID, tenant_id: UUID) -> ResearchJob | None:
        return db.scalar(
            select(ResearchJob).where(
                ResearchJob.id == job_id,
                ResearchJob.tenant_id == tenant_id,
                ResearchJob.deleted_at.is_(None),
            )
        )

    @staticmethod
    def get_by_idempotency(
        db: Session, idempotency_key: UUID, tenant_id: UUID
    ) -> ResearchJob | None:
        return db.scalar(
            select(ResearchJob).where(
                ResearchJob.idempotency_key == idempotency_key,
                ResearchJob.tenant_id == tenant_id,
                ResearchJob.deleted_at.is_(None),
            )
        )

    @staticmethod
    def list_for_order(
        db: Session, order_id: UUID, tenant_id: UUID
    ) -> list[ResearchJob]:
        return list(
            db.scalars(
                select(ResearchJob)
                .where(
                    ResearchJob.order_id == order_id,
                    ResearchJob.tenant_id == tenant_id,
                    ResearchJob.deleted_at.is_(None),
                )
                .order_by(ResearchJob.created_at.desc())
            )
        )

    @staticmethod
    def create(
        db: Session,
        *,
        order_id: UUID,
        tenant_id: UUID,
        created_by: UUID,
        idempotency_key: UUID,
        requested_doc_types: list[str],
        callback_url: str | None = None,
    ) -> ResearchJob:
        job = ResearchJob(
            order_id=order_id,
            tenant_id=tenant_id,
            created_by=created_by,
            idempotency_key=idempotency_key,
            requested_doc_types=requested_doc_types,
            total_documents=len(requested_doc_types),
            callback_url=callback_url,
        )
        db.add(job)
        db.flush()
        return job

    @staticmethod
    def save(db: Session, job: ResearchJob) -> ResearchJob:
        db.add(job)
        db.flush()
        return job

    @staticmethod
    def list_stale_queued(db: Session, minutes: int) -> list[ResearchJob]:
        """Jobs still in ``queued`` longer than ``minutes`` — orphaned if a
        crash happened between DB commit and Celery enqueue."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return list(
            db.scalars(
                select(ResearchJob).where(
                    ResearchJob.status == ResearchJobStatus.queued,
                    ResearchJob.created_at.isnot(None),
                    ResearchJob.created_at < cutoff,
                    ResearchJob.deleted_at.is_(None),
                )
            )
        )


class ResearchDocumentRepository:
    """Queries for ``research_documents``."""

    @staticmethod
    def get(db: Session, doc_id: UUID) -> ResearchDocument | None:
        return db.get(ResearchDocument, doc_id)

    @staticmethod
    def list_for_job(db: Session, job_id: UUID) -> list[ResearchDocument]:
        return list(
            db.scalars(
                select(ResearchDocument)
                .where(
                    ResearchDocument.job_id == job_id,
                    ResearchDocument.deleted_at.is_(None),
                )
                .order_by(ResearchDocument.created_at)
            )
        )

    @staticmethod
    def list_failed(db: Session, job_id: UUID) -> list[ResearchDocument]:
        return list(
            db.scalars(
                select(ResearchDocument).where(
                    ResearchDocument.job_id == job_id,
                    ResearchDocument.status == "failed",
                    ResearchDocument.deleted_at.is_(None),
                )
            )
        )

    @staticmethod
    def create(
        db: Session,
        *,
        job_id: UUID,
        order_id: UUID,
        doc_type: str,
    ) -> ResearchDocument:
        doc = ResearchDocument(
            job_id=job_id,
            order_id=order_id,
            doc_type=doc_type,
        )
        db.add(doc)
        db.flush()
        return doc

    @staticmethod
    def save(db: Session, doc: ResearchDocument) -> ResearchDocument:
        db.add(doc)
        db.flush()
        return doc
