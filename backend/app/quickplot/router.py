"""QuickPlot API (v2) — orders, the research hub and the Evidence Locker.

Every route is tenant-scoped. There is no auth yet by design; the tenant and the acting user
come from request headers so that dropping in a real identity provider later means replacing
two dependency functions and nothing else:

    X-Org-Id   tenant id           (default: QP_DEFAULT_ORG, "default")
    X-Actor    acting user's name  (default: "Researcher")

Full request/response reference with curl for every endpoint: docs/INTEGRATION.md
"""
from __future__ import annotations

import datetime
import io
import os
import re

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, or_, select

from ..db import SessionLocal
from ..services.storage import BACKEND as STORAGE_BACKEND
from . import catalog, research
from .locker import LockerError, audit, get_provider, purge_order_blobs, validate_doc_type
from .models import (AuditEvent, EvidenceDocument, Order, OrderSource, STAGE_LABELS,
                     ORDER_STAGES, _now, iso)

router = APIRouter(prefix="/api/v2", tags=["quickplot"])

DEFAULT_ORG = os.environ.get("QP_DEFAULT_ORG", "default")


# --------------------------------------------------------------------- dependencies
def org_of(x_org_id: str | None) -> str:
    """Resolve the tenant. Swap this for a token claim when auth lands."""
    return (x_org_id or DEFAULT_ORG).strip() or DEFAULT_ORG


def actor_of(x_actor: str | None) -> str:
    return (x_actor or "Researcher").strip() or "Researcher"


def _load(session, org_id: str, order_id: str) -> Order:
    o = session.get(Order, order_id)
    if not o or o.org_id != org_id:
        raise HTTPException(404, "order not found")
    return o


def _parse_dt(v) -> datetime.datetime | None:
    """Parse an ISO date/datetime. Raises on garbage rather than silently storing None —
    a typo in a due date should be corrected, not quietly dropped."""
    if v in (None, ""):
        return None
    if isinstance(v, datetime.datetime):
        return v
    try:
        return datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"'{v}' is not a valid date (use YYYY-MM-DD)")


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _valid_states() -> set[str]:
    from ..data import geography

    return {abbr for abbr, _name in geography.STATES.values()}


def _check_date_order(received, due) -> None:
    """Due before received is never what anyone meant."""
    if received and due and due < received:
        raise ValueError("due date cannot be earlier than the received date")


def _counts(session, order_id: str) -> dict:
    rows = session.execute(
        select(EvidenceDocument.status, func.count())
        .where(EvidenceDocument.order_id == order_id, EvidenceDocument.deleted.is_(False))
        .group_by(EvidenceDocument.status)).all()
    by = {k: int(v) for k, v in rows}
    locked, review = by.get("locked", 0), by.get("review_needed", 0)
    return {"documents": locked + review, "locked": locked, "review_needed": review}


# ------------------------------------------------------------------------- payloads
class _OrderFields(BaseModel):
    order_no: str = ""
    title: str = ""
    order_type: str = "Boundary Survey"
    survey_type: str = "Residential Land Survey"
    address: str = ""
    city: str = ""
    county: str = ""
    county_fips: str = ""
    state: str = ""
    postal: str = ""
    parcel_id: str = ""
    lot_area_sqft: float | None = None
    client: dict = Field(default_factory=dict)
    access_contact: dict = Field(default_factory=dict)
    buyer_owner: str = ""
    lender: str = ""
    title_company: str = ""
    underwriter: str = ""
    client_notes: str = ""
    legal_description: str = ""
    scope_tags: list[str] = Field(default_factory=list)
    received_at: str = ""
    due_at: str = ""
    researcher: str = ""
    stage: str = "placed"

    @field_validator("received_at", "due_at")
    @classmethod
    def _dates_parse(cls, v):
        _parse_dt(v)          # raises with a readable message on garbage
        return v

    @field_validator("state")
    @classmethod
    def _state_known(cls, v):
        if v and v.strip().upper() not in _valid_states():
            raise ValueError(f"'{v}' is not a US state code")
        return v.strip().upper() if v else v

    @field_validator("stage")
    @classmethod
    def _stage_known(cls, v):
        if v and v not in ORDER_STAGES:
            raise ValueError(f"'{v}' is not a known stage; expected one of {ORDER_STAGES}")
        return v

    @field_validator("client", "access_contact")
    @classmethod
    def _contact_shape(cls, v):
        email = (v or {}).get("email", "")
        if email and not _EMAIL_RE.match(str(email).strip()):
            raise ValueError(f"'{email}' is not a valid email address")
        return v

    @model_validator(mode="after")
    def _coherent(self):
        _check_date_order(_parse_dt(self.received_at), _parse_dt(self.due_at))
        return self


class OrderIn(_OrderFields):
    """Creating an order needs at least one thing that identifies it. A blank order is
    not a draft — it is a row nobody can find again."""

    @model_validator(mode="after")
    def _identifiable(self):
        if not any([(self.title or "").strip(), (self.address or "").strip(),
                    (self.order_no or "").strip(), (self.parcel_id or "").strip()]):
            raise ValueError("an order needs at least a title, order number, address "
                             "or parcel ID")
        return self


class OrderPatch(_OrderFields):
    """Partial update: only the fields actually sent are applied, so nothing is required."""

    order_type: str | None = None
    survey_type: str | None = None
    stage: str | None = None


class DocPatch(BaseModel):
    doc_type: str = ""


class LockIn(BaseModel):
    legible: bool = False
    matches_parcel: bool = False
    source_recorded: bool = False


class ReasonIn(BaseModel):
    reason: str = ""


class SubmitIn(BaseModel):
    note: str = ""


# ----------------------------------------------------------------------------- meta
@router.get("/meta")
def meta(x_org_id: str | None = Header(default=None)):
    """What the client needs to know about this deployment: tenant, providers, stages."""
    return {
        "org_id": org_of(x_org_id),
        "locker_provider": get_provider().name,
        "storage_backend": STORAGE_BACKEND,
        "stages": [{"key": k, "label": STAGE_LABELS[k]} for k in ORDER_STAGES],
        "doc_types": catalog.DOC_TYPES,
        "sources": catalog.CATALOG,
    }


@router.get("/doc-types")
def doc_types():
    return {"doc_types": catalog.DOC_TYPES}


# --------------------------------------------------------------------------- orders
@router.get("/orders")
def list_orders(q: str = "", stage: str = "", limit: int = 100,
                x_org_id: str | None = Header(default=None)):
    org = org_of(x_org_id)
    with SessionLocal() as s:
        stmt = select(Order).where(Order.org_id == org)
        if stage:
            stmt = stmt.where(Order.stage == stage)
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(Order.title.ilike(like), Order.order_no.ilike(like),
                                  Order.address.ilike(like), Order.parcel_id.ilike(like)))
        rows = s.execute(stmt.order_by(Order.updated_at.desc()).limit(limit)).scalars().all()
        return {"orders": [r.as_dict(counts=_counts(s, r.id)) for r in rows]}


@router.post("/orders", status_code=201)
def create_order(body: OrderIn, x_org_id: str | None = Header(default=None),
                 x_actor: str | None = Header(default=None)):
    org, actor = org_of(x_org_id), actor_of(x_actor)
    with SessionLocal() as s:
        if body.order_no.strip():
            clash = s.execute(select(Order).where(
                Order.org_id == org, Order.order_no == body.order_no.strip())
            ).scalars().first()
            if clash:
                raise HTTPException(409, f"order number '{body.order_no}' already exists")
        o = Order(org_id=org, created_by=actor)
        data = body.model_dump()
        for k, v in data.items():
            if k in ("received_at", "due_at"):
                setattr(o, k, _parse_dt(v))
            elif v is not None and hasattr(o, k):
                setattr(o, k, v)
        o.researcher = body.researcher or actor
        o.stage = body.stage or "placed"
        now = _now()
        o.stage_dates = {"created": iso(now),
                         **({"placed": iso(now)} if o.stage != "created" else {})}
        s.add(o)
        s.flush()
        audit(s, org_id=org, order_id=o.id, scope="order", action="order_created",
              title="Order created",
              subtitle=f"{o.survey_type} · {o.order_no or o.id[:8]} — routed to the assigned team.",
              actor=actor)
        audit(s, org_id=org, order_id=o.id, scope="order", action="order_details_captured",
              title="Order details captured",
              subtitle="Client, property, scope and team recorded on intake.", actor=actor)
        research.ensure_sources(s, o)
        s.commit()
        return o.as_dict(counts=_counts(s, o.id))


@router.get("/orders/{order_id}")
def get_order(order_id: str, x_org_id: str | None = Header(default=None)):
    org = org_of(x_org_id)
    with SessionLocal() as s:
        o = _load(s, org, order_id)
        return o.as_dict(counts=_counts(s, o.id))


@router.patch("/orders/{order_id}")
def patch_order(order_id: str, body: OrderPatch,
                x_org_id: str | None = Header(default=None),
                x_actor: str | None = Header(default=None)):
    org, actor = org_of(x_org_id), actor_of(x_actor)
    with SessionLocal() as s:
        o = _load(s, org, order_id)
        sent = body.model_dump(exclude_unset=True)

        # The model can only check the two dates against each other when both are sent.
        # On a partial update the other half already lives on the record, so the rule has
        # to be re-checked against the merged result.
        if "received_at" in sent or "due_at" in sent:
            merged_recv = (_parse_dt(sent["received_at"]) if "received_at" in sent
                           else o.received_at)
            merged_due = _parse_dt(sent["due_at"]) if "due_at" in sent else o.due_at
            try:
                _check_date_order(merged_recv, merged_due)
            except ValueError as e:
                raise HTTPException(422, str(e))

        new_no = (sent.get("order_no") or "").strip()
        if new_no and new_no != o.order_no:
            clash = s.execute(select(Order).where(
                Order.org_id == org, Order.order_no == new_no, Order.id != o.id)
            ).scalars().first()
            if clash:
                raise HTTPException(409, f"order number '{new_no}' already exists")

        changed = []
        for k, v in sent.items():
            if v is None or not hasattr(o, k):
                continue
            if k in ("received_at", "due_at"):
                v = _parse_dt(v)
            if getattr(o, k) != v:
                setattr(o, k, v)
                changed.append(k)
        if changed:
            audit(s, org_id=org, order_id=o.id, scope="order", action="order_updated",
                  title="Order details updated",
                  subtitle=", ".join(changed[:8]), actor=actor, detail={"fields": changed})
        s.commit()
        return o.as_dict(counts=_counts(s, o.id))


@router.delete("/orders/{order_id}")
def delete_order(order_id: str, x_org_id: str | None = Header(default=None)):
    org = org_of(x_org_id)
    with SessionLocal() as s:
        _load(s, org, order_id)
    # Remove the stored files first: if the row deletion then fails we have an orphaned
    # blob at worst, rather than a document row pointing at bytes that are already gone.
    purge_order_blobs(org, order_id)
    with SessionLocal() as s:
        o = _load(s, org, order_id)
        for d in s.execute(select(EvidenceDocument).where(
                EvidenceDocument.order_id == o.id)).scalars().all():
            s.delete(d)
        for r in s.execute(select(OrderSource).where(
                OrderSource.order_id == o.id)).scalars().all():
            s.delete(r)
        for e in s.execute(select(AuditEvent).where(
                AuditEvent.order_id == o.id)).scalars().all():
            s.delete(e)
        s.delete(o)
        s.commit()
    return {"ok": True}


@router.get("/orders/{order_id}/log")
def order_log(order_id: str, scope: str = "order",
              x_org_id: str | None = Header(default=None)):
    """Change log. scope=order → "Order information — change log";
    scope=locker → "Evidence locker — change log"; scope=all → both."""
    org = org_of(x_org_id)
    with SessionLocal() as s:
        _load(s, org, order_id)
        stmt = select(AuditEvent).where(AuditEvent.org_id == org,
                                        AuditEvent.order_id == order_id)
        if scope in ("order", "locker"):
            stmt = stmt.where(AuditEvent.scope == scope)
        rows = s.execute(stmt.order_by(AuditEvent.ts.desc(),
                                       AuditEvent.id.desc())).scalars().all()
        return {"scope": scope, "events": [r.as_dict() for r in rows]}


# -------------------------------------------------------------------------- research
@router.get("/orders/{order_id}/sources")
def get_sources(order_id: str, x_org_id: str | None = Header(default=None)):
    org = org_of(x_org_id)
    with SessionLocal() as s:
        o = _load(s, org, order_id)
        rows = research.ensure_sources(s, o)
        s.commit()
        order_ix = {c["key"]: i for i, c in enumerate(catalog.CATALOG)}
        out = sorted((r.as_dict() for r in rows), key=lambda r: order_ix.get(r["key"], 99))
        return {"sources": out, "run": research.run_status(order_id)}


@router.post("/orders/{order_id}/research/start")
def research_start(order_id: str, x_org_id: str | None = Header(default=None),
                   x_actor: str | None = Header(default=None)):
    """Move the order into Research and kick off the first auto-fetch."""
    org, actor = org_of(x_org_id), actor_of(x_actor)
    with SessionLocal() as s:
        o = _load(s, org, order_id)
        if o.research_state == "submitted":
            raise HTTPException(409, "research has already been submitted for this order; "
                                     "reopen it before running research again")
        if o.research_state == "not_started":
            o.research_state = "in_progress"
            o.research_started_at = _now()
            o.researcher = o.researcher or actor
            o.stage = "research"
            o.stage_dates = {**(o.stage_dates or {}), "research": iso(_now())}
            audit(s, org_id=org, order_id=o.id, scope="order", action="research_started",
                  title="Research started",
                  subtitle=f"Assigned to {o.researcher}.", actor=actor)
        research.ensure_sources(s, o)
        s.commit()
        out = o.as_dict(counts=_counts(s, o.id))
    run = research.start_run(order_id, actor)
    return {"order": out, "run": run}


@router.post("/orders/{order_id}/sources/{key}/fetch")
def source_fetch(order_id: str, key: str, x_org_id: str | None = Header(default=None),
                 x_actor: str | None = Header(default=None)):
    """Auto-fetch one source. The pipeline resolves the parcel first either way, so this
    runs the same job but only re-scores the requested registry row."""
    org, actor = org_of(x_org_id), actor_of(x_actor)
    if key not in catalog.BY_KEY:
        raise HTTPException(404, f"unknown source '{key}'")
    with SessionLocal() as s:
        _load(s, org, order_id)
    return {"run": research.start_run(order_id, actor, only=key)}


@router.post("/orders/{order_id}/sources/fetch-all")
def source_fetch_all(order_id: str, x_org_id: str | None = Header(default=None),
                     x_actor: str | None = Header(default=None)):
    org, actor = org_of(x_org_id), actor_of(x_actor)
    with SessionLocal() as s:
        _load(s, org, order_id)
    return {"run": research.start_run(order_id, actor)}


@router.get("/orders/{order_id}/research/status")
def research_status(order_id: str, x_org_id: str | None = Header(default=None)):
    org = org_of(x_org_id)
    with SessionLocal() as s:
        _load(s, org, order_id)
    return {"run": research.run_status(order_id), "phases":
            [{"key": k, "label": lbl} for k, lbl in research.PHASES]}


@router.get("/orders/{order_id}/checklist")
def checklist(order_id: str, x_org_id: str | None = Header(default=None)):
    """Research Checklist drawer: one row per required source, ticked when a LOCKED
    document of that type is in the locker."""
    org = org_of(x_org_id)
    with SessionLocal() as s:
        _load(s, org, order_id)
        locked = {d.doc_type for d in s.execute(
            select(EvidenceDocument).where(EvidenceDocument.order_id == order_id,
                                           EvidenceDocument.deleted.is_(False),
                                           EvidenceDocument.status == "locked")
        ).scalars().all()}
    items = [{"key": k, "label": catalog.BY_KEY[k]["label"],
              "requirement": catalog.BY_KEY[k]["requirement"], "done": k in locked}
             for k in catalog.CHECKLIST_KEYS]
    done = sum(1 for i in items if i["done"])
    pct = round(done / len(items) * 100) if items else 0
    return {"items": items, "done": done, "total": len(items), "percent": pct}


@router.post("/orders/{order_id}/research/submit")
def research_submit(order_id: str, body: SubmitIn,
                    x_org_id: str | None = Header(default=None),
                    x_actor: str | None = Header(default=None)):
    """Hand the order to the field survey team. Requires at least one locked document —
    an empty evidence set is not a research hand-off."""
    org, actor = org_of(x_org_id), actor_of(x_actor)
    with SessionLocal() as s:
        o = _load(s, org, order_id)
        if o.research_state == "submitted":
            raise HTTPException(409, "research has already been submitted for this order")
        c = _counts(s, o.id)
        if c["locked"] == 0:
            raise HTTPException(409, "lock at least one document before submitting research")
        o.research_state = "submitted"
        o.research_submitted_at = _now()
        o.researcher_note = body.note
        o.stage = "field_survey"
        sd = dict(o.stage_dates or {})
        sd.setdefault("research", iso(_now()))
        sd["field_survey"] = iso(_now())
        o.stage_dates = sd
        audit(s, org_id=org, order_id=o.id, scope="order", action="research_submitted",
              title="Research submitted",
              subtitle=(f"{c['locked']} locked · {c['documents']} files in the Evidence "
                        "Locker. Order moved to Field Survey."),
              reason=body.note, actor=actor, detail=c)
        s.commit()
        return {"order": o.as_dict(counts=c), "summary": c}


@router.get("/orders/{order_id}/research/summary")
def research_summary(order_id: str, x_org_id: str | None = Header(default=None)):
    """Numbers for the "Hand this order to the field survey team?" confirmation."""
    org = org_of(x_org_id)
    with SessionLocal() as s:
        o = _load(s, org, order_id)
        return {"counts": _counts(s, o.id), "assignee": o.researcher}


# ------------------------------------------------------------------------ documents
@router.get("/orders/{order_id}/documents")
def list_documents(order_id: str, q: str = "",
                   x_org_id: str | None = Header(default=None)):
    org = org_of(x_org_id)
    with SessionLocal() as s:
        _load(s, org, order_id)
    docs = get_provider().list_documents(org, order_id)
    if q:
        needle = q.strip().lower()
        docs = [d for d in docs if needle in (d.get("filename", "")
                                              + d.get("doc_type", "")).lower()]
    return {"documents": docs}


@router.post("/orders/{order_id}/documents", status_code=201)
async def upload_documents(order_id: str, files: list[UploadFile] = File(...),
                           doc_type: str = Form(default=""),
                           source_key: str = Form(default=""),
                           x_org_id: str | None = Header(default=None),
                           x_actor: str | None = Header(default=None)):
    """Manual upload. Accepts several files at once (the upload modal queues them);
    `doc_type` applies to all of them and may be left blank to classify later."""
    org, actor = org_of(x_org_id), actor_of(x_actor)
    with SessionLocal() as s:
        _load(s, org, order_id)
    try:
        validate_doc_type(doc_type)
    except LockerError as e:
        raise HTTPException(e.status, str(e))
    provider, out = get_provider(), []
    for f in files:
        data = await f.read()
        try:
            out.append(provider.add_document(
                org, order_id, filename=f.filename or "upload", data=data,
                doc_type=doc_type, source_key=source_key, origin="manual_upload",
                source_label="Manual upload", actor=actor,
                content_type=f.content_type or ""))
        except LockerError as e:
            raise HTTPException(e.status, str(e))
    if not out:
        raise HTTPException(422, "no usable file in the upload")
    return {"documents": out}


@router.patch("/orders/{order_id}/documents/{doc_id}")
def patch_document(order_id: str, doc_id: str, body: DocPatch,
                   x_org_id: str | None = Header(default=None),
                   x_actor: str | None = Header(default=None)):
    org, actor = org_of(x_org_id), actor_of(x_actor)
    try:
        return get_provider().set_doc_type(org, order_id, doc_id, body.doc_type, actor)
    except LockerError as e:
        raise HTTPException(e.status, str(e))


@router.delete("/orders/{order_id}/documents/{doc_id}")
def delete_document(order_id: str, doc_id: str, reason: str = "",
                    x_org_id: str | None = Header(default=None),
                    x_actor: str | None = Header(default=None)):
    org, actor = org_of(x_org_id), actor_of(x_actor)
    try:
        return get_provider().delete_document(org, order_id, doc_id, reason, actor)
    except LockerError as e:
        raise HTTPException(e.status, str(e))


@router.post("/orders/{order_id}/documents/{doc_id}/lock")
def lock_document(order_id: str, doc_id: str, body: LockIn,
                  x_org_id: str | None = Header(default=None),
                  x_actor: str | None = Header(default=None)):
    """Approve & Lock. All three reviewer confirmations are required and are stored with
    the document, so the locker can show *why* a file was accepted as evidence."""
    org, actor = org_of(x_org_id), actor_of(x_actor)
    try:
        return get_provider().lock_document(org, order_id, doc_id, body.model_dump(), actor)
    except LockerError as e:
        raise HTTPException(e.status, str(e))


@router.post("/orders/{order_id}/documents/{doc_id}/unlock")
def unlock_document(order_id: str, doc_id: str, body: ReasonIn,
                    x_org_id: str | None = Header(default=None),
                    x_actor: str | None = Header(default=None)):
    org, actor = org_of(x_org_id), actor_of(x_actor)
    try:
        return get_provider().unlock_document(org, order_id, doc_id, body.reason, actor)
    except LockerError as e:
        raise HTTPException(e.status, str(e))


@router.get("/orders/{order_id}/documents/{doc_id}/file")
def document_file(order_id: str, doc_id: str, download: bool = False,
                  x_org_id: str | None = Header(default=None)):
    org = org_of(x_org_id)
    try:
        blob = get_provider().read_document(org, order_id, doc_id)
    except LockerError as e:
        raise HTTPException(e.status, str(e))
    disp = "attachment" if download else "inline"
    if blob.get("path"):
        return FileResponse(blob["path"], filename=blob["filename"],
                            media_type=blob.get("content_type") or None,
                            content_disposition_type=disp)
    return StreamingResponse(
        io.BytesIO(blob["bytes"]),
        media_type=blob.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'{disp}; filename="{blob["filename"]}"'})


@router.get("/orders/{order_id}/locker/log")
def locker_log(order_id: str, x_org_id: str | None = Header(default=None)):
    org = org_of(x_org_id)
    with SessionLocal() as s:
        _load(s, org, order_id)
    return {"events": get_provider().change_log(org, order_id)}


# ----------------------------------------------------------------------------- demo
@router.post("/demo/seed")
def demo_seed(x_org_id: str | None = Header(default=None)):
    """Create the sample order used by the QuickPlot demo. Idempotent."""
    from . import demo

    return demo.seed(org_of(x_org_id))
