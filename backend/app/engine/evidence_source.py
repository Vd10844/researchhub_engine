"""Dev/standalone evidence linkage for the engine.

The parent's evidence module owns ``File`` + ``OrderFile`` rows (the blob →
order link that makes the evidence set defensible). This module is the
engine's self-contained stand-in, mirroring the parent's table/column names
so migrations and the mapper keep working. ``_upload_artifact`` creates one
``File`` (with the real storage key, size, sha256) plus the ``OrderFile``
link whenever a document's blob lands in storage.

At parent integration, these models and the repository reads are swapped for
``app/modules/evidence`` — nothing above ``FetchedDocument.file_id`` /
``order_file_id`` changes.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TimestampMixin


class File(Base, TimestampMixin, SoftDeleteMixin):
    """Stand-in for the parent's evidence ``files`` table."""

    __tablename__ = "files"
    __versioned__: dict = {}

    filename: Mapped[str] = mapped_column(nullable=False)
    content_key: Mapped[str | None] = mapped_column(
        nullable=True, comment="Blob storage key (tenant/order/...) of the artifact."
    )
    mime_type: Mapped[str | None] = mapped_column(nullable=True)
    size: Mapped[int | None] = mapped_column(nullable=True, comment="File size in bytes.")
    sha256: Mapped[str | None] = mapped_column(nullable=True)


class OrderFile(Base, TimestampMixin, SoftDeleteMixin):
    """Stand-in for the parent's evidence ``order_files`` join table."""

    __tablename__ = "order_files"
    __versioned__: dict = {}

    order_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, index=True, comment="Order this file belongs to."
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, index=True, comment="Linked File.id."
    )


def create_evidence(
    *,
    order_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    storage_key: str,
    filename: str,
    file_size: int,
    sha256: str,
    mime_type: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Persist the File + OrderFile rows for an uploaded artifact.

    Returns ``(file_id, order_file_id)``. Uses its own session so it composes
    with the caller's transaction (worker / E2E). Raises on failure — callers
    map it to ``S3_UPLOAD_FAILED``.
    """
    from app.db.base import SessionLocal

    db = SessionLocal()
    try:
        file = File(
            filename=filename,
            content_key=storage_key,
            mime_type=mime_type or "application/pdf",
            size=file_size,
            sha256=sha256,
        )
        db.add(file)
        db.flush()
        link = OrderFile(order_id=order_id, file_id=file.id)
        db.add(link)
        db.commit()
        return file.id, link.id
    finally:
        db.close()


def get_file_reference(file_id: uuid.UUID) -> dict | None:
    """Fetch the stored File metadata for a document (standalone evidence)."""
    from app.db.base import SessionLocal

    db = SessionLocal()
    try:
        f = db.query(File).filter(File.id == file_id, File.deleted_at.is_(None)).first()
        if f is None:
            return None
        return {
            "key": f.content_key or "",
            "filename": f.filename,
            "size_bytes": f.size or 0,
            "sha256": f.sha256 or "",
            "mime_type": f.mime_type or "application/pdf",
        }
    finally:
        db.close()