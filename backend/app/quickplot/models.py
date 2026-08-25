"""QuickPlot ORM models — orders, evidence documents, per-order source registry, audit log.

These share `db.Base` (and therefore the engine/session factory), so `db.init_db()` creates
them alongside the v1 index tables. SQLite in dev, Postgres in prod — no dialect-specific
column types are used.

Tenancy: every row carries `org_id`. There is no auth yet; the org is resolved from the
`X-Org-Id` request header with a configurable default. When auth lands, only the dependency
that resolves `org_id` changes — the queries are already scoped.
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String,
                        Text)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _uid() -> str:
    return uuid.uuid4().hex


def iso(dt) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.isoformat()


# --------------------------------------------------------------------------- orders
#: Order lifecycle. The design's stage rail renders these in order.
ORDER_STAGES = ["created", "placed", "research", "field_survey", "cad_drafting", "delivered"]
STAGE_LABELS = {
    "created": "Order Created", "placed": "Order Placed", "research": "Research",
    "field_survey": "Field Survey", "cad_drafting": "CAD Drafting", "delivered": "Delivered",
}
#: Research sub-state, independent of the stage rail (drives the banner on the order page).
RESEARCH_STATES = ["not_started", "in_progress", "submitted"]


class Order(Base):
    """A survey order. The research hub is one stage of its life."""

    __tablename__ = "qp_orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(String(64), index=True, default="default")

    order_no: Mapped[str] = mapped_column(String(64), default="", index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    order_type: Mapped[str] = mapped_column(String(80), default="Boundary Survey")
    survey_type: Mapped[str] = mapped_column(String(80), default="Residential Land Survey")

    stage: Mapped[str] = mapped_column(String(24), default="created", index=True)
    #: {stage: ISO timestamp} — populates the ticks under the stage rail.
    stage_dates: Mapped[dict] = mapped_column(JSON, default=dict)
    research_state: Mapped[str] = mapped_column(String(24), default="not_started", index=True)

    # ---- property ----
    address: Mapped[str] = mapped_column(Text, default="")
    matched_address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    county: Mapped[str] = mapped_column(String(120), default="")
    county_fips: Mapped[str] = mapped_column(String(8), default="")
    state: Mapped[str] = mapped_column(String(8), default="")
    postal: Mapped[str] = mapped_column(String(16), default="")
    parcel_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    lot_area_sqft: Mapped[float | None] = mapped_column(Float, nullable=True)
    lot_area_acres: Mapped[float | None] = mapped_column(Float, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ---- parties (JSON so the intake form can grow without a migration) ----
    client: Mapped[dict] = mapped_column(JSON, default=dict)          # {name, role, email, phone}
    access_contact: Mapped[dict] = mapped_column(JSON, default=dict)  # {name, phone}
    buyer_owner: Mapped[str] = mapped_column(String(255), default="")
    lender: Mapped[str] = mapped_column(String(255), default="")
    title_company: Mapped[str] = mapped_column(String(255), default="")
    underwriter: Mapped[str] = mapped_column(String(255), default="")

    client_notes: Mapped[str] = mapped_column(Text, default="")
    legal_description: Mapped[str] = mapped_column(Text, default="")
    scope_tags: Mapped[list] = mapped_column(JSON, default=list)

    received_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    due_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    created_by: Mapped[str] = mapped_column(String(120), default="")
    researcher: Mapped[str] = mapped_column(String(120), default="")
    research_started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    research_submitted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    researcher_note: Mapped[str] = mapped_column(Text, default="")

    #: Folder name of the v1 research job this order's auto-fetch produced (jobs/<name>).
    job_name: Mapped[str] = mapped_column(String(255), default="")

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    def as_dict(self, *, counts: dict | None = None) -> dict:
        return {
            "id": self.id, "org_id": self.org_id,
            "order_no": self.order_no, "title": self.title,
            "order_type": self.order_type, "survey_type": self.survey_type,
            "stage": self.stage, "stage_dates": self.stage_dates or {},
            "research_state": self.research_state,
            "address": self.address, "matched_address": self.matched_address,
            "city": self.city, "county": self.county, "county_fips": self.county_fips,
            "state": self.state, "postal": self.postal,
            "parcel_id": self.parcel_id,
            "lot_area_sqft": self.lot_area_sqft, "lot_area_acres": self.lot_area_acres,
            "lat": self.lat, "lon": self.lon,
            "client": self.client or {}, "access_contact": self.access_contact or {},
            "buyer_owner": self.buyer_owner, "lender": self.lender,
            "title_company": self.title_company, "underwriter": self.underwriter,
            "client_notes": self.client_notes, "legal_description": self.legal_description,
            "scope_tags": self.scope_tags or [],
            "received_at": iso(self.received_at), "due_at": iso(self.due_at),
            "created_by": self.created_by, "researcher": self.researcher,
            "research_started_at": iso(self.research_started_at),
            "research_submitted_at": iso(self.research_submitted_at),
            "researcher_note": self.researcher_note,
            "job_name": self.job_name,
            "created_at": iso(self.created_at), "updated_at": iso(self.updated_at),
            **({"counts": counts} if counts is not None else {}),
        }


# ----------------------------------------------------------------- evidence documents
DOC_STATUSES = ["review_needed", "locked"]
DOC_ORIGINS = ["auto_fetch", "manual_upload"]


class EvidenceDocument(Base):
    """One file in an order's Evidence Locker.

    Locking is the point of the locker: a locked document is immutable evidence — it cannot be
    re-typed, replaced or deleted until someone explicitly unlocks it, and every transition is
    written to the audit log. `lock_seal` is the short digest shown in the change log
    ("sealed f10d34") so a locked file can be identified without exposing the storage key.
    """

    __tablename__ = "qp_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    org_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    order_id: Mapped[str] = mapped_column(String(32), ForeignKey("qp_orders.id"), index=True)

    filename: Mapped[str] = mapped_column(String(255), default="")
    doc_type: Mapped[str] = mapped_column(String(64), default="")     # "" = needs classifying
    source_key: Mapped[str] = mapped_column(String(64), default="")   # registry source that produced it
    origin: Mapped[str] = mapped_column(String(24), default="manual_upload")
    status: Mapped[str] = mapped_column(String(24), default="review_needed", index=True)

    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(120), default="")
    pages: Mapped[int] = mapped_column(Integer, default=0)

    source_label: Mapped[str] = mapped_column(String(160), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")

    storage_key: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")

    retrieved_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    retrieved_by: Mapped[str] = mapped_column(String(120), default="")

    locked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    locked_by: Mapped[str] = mapped_column(String(120), default="")
    lock_seal: Mapped[str] = mapped_column(String(32), default="")
    #: The three reviewer confirmations recorded at lock time (legible / matches / recorded).
    lock_checks: Mapped[dict] = mapped_column(JSON, default=dict)

    deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    delete_reason: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "order_id": self.order_id,
            "filename": self.filename, "doc_type": self.doc_type,
            "source_key": self.source_key, "origin": self.origin, "status": self.status,
            "size_bytes": self.size_bytes, "content_type": self.content_type,
            "pages": self.pages,
            "source_label": self.source_label, "source_url": self.source_url,
            "sha256": self.sha256,
            "retrieved_at": iso(self.retrieved_at), "retrieved_by": self.retrieved_by,
            "locked_at": iso(self.locked_at), "locked_by": self.locked_by,
            "lock_seal": self.lock_seal, "lock_checks": self.lock_checks or {},
            "url": f"/api/v2/orders/{self.order_id}/documents/{self.id}/file",
        }


Index("ix_qp_documents_order_status", EvidenceDocument.order_id, EvidenceDocument.status)


# ------------------------------------------------------------- per-order source registry
SOURCE_STATES = ["idle", "fetching", "fetched", "failed", "unavailable"]


class OrderSource(Base):
    """State of one research source (Deed, Plat, FEMA…) for one order — what the right-hand
    Source registry rail renders. Rows are created lazily from the document matrix."""

    __tablename__ = "qp_order_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    order_id: Mapped[str] = mapped_column(String(32), ForeignKey("qp_orders.id"), index=True)

    key: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(160), default="")
    requirement: Mapped[str] = mapped_column(String(24), default="mandatory")
    state: Mapped[str] = mapped_column(String(24), default="idle")
    message: Mapped[str] = mapped_column(Text, default="")
    open_url: Mapped[str] = mapped_column(Text, default="")
    doc_count: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "requirement": self.requirement,
                "state": self.state, "message": self.message, "open_url": self.open_url,
                "doc_count": self.doc_count, "last_run_at": iso(self.last_run_at)}


Index("ix_qp_sources_order_key", OrderSource.order_id, OrderSource.key, unique=True)


# ------------------------------------------------------------------------- audit log
class AuditEvent(Base):
    """Append-only change log. `scope` splits the two logs the design shows:
    'order' -> "Order information — change log", 'locker' -> "Evidence locker — change log"."""

    __tablename__ = "qp_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    order_id: Mapped[str] = mapped_column(String(32), index=True, default="")

    scope: Mapped[str] = mapped_column(String(16), default="order", index=True)
    action: Mapped[str] = mapped_column(String(48), default="", index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    subtitle: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(120), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ts: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now, index=True)

    def as_dict(self) -> dict:
        return {"id": self.id, "order_id": self.order_id, "scope": self.scope,
                "action": self.action, "title": self.title, "subtitle": self.subtitle,
                "reason": self.reason, "actor": self.actor, "detail": self.detail or {},
                "ts": iso(self.ts)}
