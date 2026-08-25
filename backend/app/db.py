"""Database layer — SQLAlchemy 2.0, SQLite in dev / Postgres in prod.

Mirrors the survey-automation pattern: one module holds the engine, session factory, the
DeclarativeBase, all ORM models, `init_db()` (create_all + lightweight additive migrations), and
a set of self-contained helper functions — each opens its own short-lived `with SessionLocal()`
block and returns plain dicts. There is no per-request session dependency.

The filesystem (jobs/, evidence/) remains the source of truth for documents; this DB is a fast,
queryable INDEX of jobs + evidence + a usage-event log. Every write is best-effort at the call
site, so a DB hiccup never breaks the research pipeline.
"""
from __future__ import annotations

import datetime

from sqlalchemy import (JSON, DateTime, Integer, String, Text, create_engine, func,
                        inspect, select, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DATABASE_URL

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
IS_PG = engine.dialect.name == "postgresql"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.isoformat()


class Base(DeclarativeBase):
    pass


class Job(Base):
    """One research job — indexed from its folder / result so Jobs can be queried, not scanned."""
    __tablename__ = "jobs"
    name: Mapped[str] = mapped_column(String(255), primary_key=True)   # "<job> - <address>"
    address: Mapped[str] = mapped_column(Text, default="")
    county: Mapped[str] = mapped_column(String(80), default="")
    state: Mapped[str] = mapped_column(String(8), default="")
    parcel_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    docs: Mapped[int] = mapped_column(Integer, default=0)
    generated: Mapped[str] = mapped_column(String(40), default="")     # ISO from the manifest
    locker_order: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    def as_dict(self) -> dict:
        return {"name": self.name, "address": self.address, "county": self.county,
                "state": self.state, "parcel_id": self.parcel_id, "docs": self.docs,
                "generated": self.generated, "locker_order": self.locker_order,
                "created_at": _iso(self.created_at), "updated_at": _iso(self.updated_at)}


class EvidenceRecord(Base):
    """A document sent to an order's Evidence Locker (mirrors locker.json for querying)."""
    __tablename__ = "evidence_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order: Mapped[str] = mapped_column(String(120), index=True)
    file: Mapped[str] = mapped_column(String(255))
    doc_key: Mapped[str] = mapped_column(String(64), default="")
    label: Mapped[str] = mapped_column(String(255), default="")
    source_job: Mapped[str] = mapped_column(String(255), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    def as_dict(self) -> dict:
        return {"order": self.order, "file": self.file, "key": self.doc_key,
                "label": self.label, "source_job": self.source_job,
                "source_url": self.source_url, "sent_at": _iso(self.sent_at)}


class Event(Base):
    """Append-only usage log — searches run, docs sent, etc. (analytics)."""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now, index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    job: Mapped[str] = mapped_column(String(255), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)

    def as_dict(self) -> dict:
        return {"ts": _iso(self.ts), "action": self.action, "job": self.job,
                "address": self.address, "detail": self.detail or {}}


def _add_col(table: str, col: str, ddl: str) -> None:
    """Add a column to an existing table if missing (create_all won't ALTER). SQLite/PG-safe."""
    try:
        cols = {c["name"] for c in inspect(engine).get_columns(table)}
        if col not in cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
    except Exception:  # noqa: BLE001
        pass


def init_db() -> None:
    """Create tables (and apply any additive column migrations). Idempotent; safe at import."""
    Base.metadata.create_all(engine)
    # Additive migrations for columns added after a DB already existed go here, e.g.:
    _add_col("jobs", "locker_order", "locker_order VARCHAR(120) DEFAULT ''")


# ---------------------------------------------------------------------------------
# Helpers (each opens its own short-lived session; callers wrap in try/except)
# ---------------------------------------------------------------------------------
def upsert_job(meta: dict) -> None:
    """Insert/update a job index row from a research result / manifest meta."""
    name = (meta.get("name") or meta.get("folder") or "").strip()
    if not name:
        return
    with SessionLocal() as s:
        j = s.get(Job, name)
        if not j:
            j = Job(name=name)
            s.add(j)
        j.address = meta.get("matched_address") or meta.get("address") or j.address or ""
        j.county = meta.get("county") or j.county or ""
        j.state = meta.get("state") or j.state or ""
        j.parcel_id = meta.get("parcel_id") or j.parcel_id or ""
        if meta.get("docs") is not None:
            j.docs = int(meta.get("docs") or 0)
        j.generated = meta.get("generated") or j.generated or _now().isoformat()
        if meta.get("locker_order"):
            j.locker_order = meta["locker_order"]
        s.commit()


def set_locker_order(name: str, order: str) -> None:
    with SessionLocal() as s:
        j = s.get(Job, name)
        if j:
            j.locker_order = order
            s.commit()


def list_jobs(limit: int = 500) -> list[dict]:
    with SessionLocal() as s:
        rows = s.execute(select(Job).order_by(Job.generated.desc()).limit(limit)).scalars().all()
        return [r.as_dict() for r in rows]


def record_event(action: str, job: str = "", address: str = "", detail: dict | None = None) -> None:
    with SessionLocal() as s:
        s.add(Event(action=action, job=job, address=address, detail=detail or {}))
        s.commit()


def add_evidence(order: str, items: list[dict], source_job: str = "") -> None:
    """Record sent documents (dedup by order+file)."""
    with SessionLocal() as s:
        have = {r.file for r in s.execute(
            select(EvidenceRecord).where(EvidenceRecord.order == order)).scalars().all()}
        for it in items:
            fn = (it.get("file") or "").strip()
            if not fn or fn in have:
                continue
            s.add(EvidenceRecord(order=order, file=fn, doc_key=it.get("key", ""),
                                 label=it.get("label", ""), source_job=source_job,
                                 source_url=it.get("source_url", "")))
            have.add(fn)
        s.commit()


def remove_evidence(order: str, file: str = "") -> None:
    with SessionLocal() as s:
        q = select(EvidenceRecord).where(EvidenceRecord.order == order)
        if file:
            q = q.where(EvidenceRecord.file == file)
        for r in s.execute(q).scalars().all():
            s.delete(r)
        s.commit()


def stats() -> dict:
    with SessionLocal() as s:
        jobs = s.scalar(select(func.count()).select_from(Job)) or 0
        events = s.scalar(select(func.count()).select_from(Event)) or 0
        orders = s.scalar(select(func.count(func.distinct(EvidenceRecord.order)))) or 0
        docs = s.scalar(select(func.count()).select_from(EvidenceRecord)) or 0
        searches = s.scalar(
            select(func.count()).select_from(Event).where(Event.action == "search")) or 0
        return {"backend": engine.dialect.name, "jobs": int(jobs), "events": int(events),
                "searches": int(searches), "locker_orders": int(orders),
                "locker_documents": int(docs)}
