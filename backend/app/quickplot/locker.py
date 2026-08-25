"""Evidence Locker service — the swappable layer.

Everything the UI does to a locker goes through a `LockerProvider`. Two implementations ship:

* `LocalLockerProvider`  — documents live in our own DB + blob storage (the default).
* `RemoteLockerProvider` — documents live in Mapperty's Evidence Locker service and we
  proxy to its REST API.

Pick one with the environment:

    QP_LOCKER_PROVIDER = local | remote        (default: local)
    QP_LOCKER_API_BASE = https://api.mapperty.example/v1
    QP_LOCKER_API_KEY  = <bearer token>

The router never imports a provider directly — it calls `get_provider()` — so switching
backends is a config change, not a code change. Both providers return the same document
shape (see `EvidenceDocument.as_dict`), which is the contract documented in
`docs/INTEGRATION.md`.
"""
from __future__ import annotations

import datetime
import mimetypes
import os
import pathlib
import re
from typing import Any, Protocol

from sqlalchemy import select

from ..db import SessionLocal
from ..services.storage import (MAX_UPLOAD_BYTES, build_key, sha256_bytes,
                                store)
from .models import AuditEvent, EvidenceDocument, _now, _uid

PROVIDER_NAME = os.environ.get("QP_LOCKER_PROVIDER", "local").strip().lower()
API_BASE = os.environ.get("QP_LOCKER_API_BASE", "").rstrip("/")
API_KEY = os.environ.get("QP_LOCKER_API_KEY", "")


class LockerError(Exception):
    """Raised for a locker rule violation (locked file, missing doc). Maps to HTTP 4xx."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- helpers
_PAGE_RE = re.compile(rb"/Type\s*/Page[^s]")


def _page_count(data: bytes, content_type: str) -> int:
    """Best-effort page count for the review modal's "688 KB · 3 pages" line.

    PDFs only, by counting page objects — no PDF dependency for what is a cosmetic label.
    Returns 0 for anything else, which the UI reads as "unknown" and omits: an HTML
    report has no page count, and claiming "1 page" for one is a small lie.
    """
    if "pdf" not in (content_type or "").lower():
        return 0
    try:
        return max(1, len(_PAGE_RE.findall(data[:4_000_000])))
    except Exception:  # noqa: BLE001
        return 0


def _safe_filename(name: str) -> str:
    base = pathlib.PurePath((name or "file").replace("\\", "/")).name
    return re.sub(r"[^A-Za-z0-9._ ()-]+", "_", base)[:160] or "file"


def validate_doc_type(doc_type: str) -> None:
    """A document type has to be one the checklist and the source registry understand;
    a free-text value would silently never satisfy a checklist row."""
    if not doc_type:
        return
    from .catalog import DOC_TYPES

    if doc_type not in {t["key"] for t in DOC_TYPES}:
        raise LockerError(f"unknown document type '{doc_type}'", 422)


def purge_order_blobs(org_id: str, order_id: str) -> int:
    """Delete every stored blob for an order. Called when the order itself is removed so
    the object store does not accumulate files nothing points at any more."""
    n = 0
    with SessionLocal() as s:
        rows = s.execute(select(EvidenceDocument).where(
            EvidenceDocument.org_id == org_id,
            EvidenceDocument.order_id == order_id)).scalars().all()
        for d in rows:
            if d.storage_key:
                store.delete(d.storage_key)
                n += 1
    return n


def audit(session, *, org_id: str, order_id: str, scope: str, action: str, title: str,
          subtitle: str = "", reason: str = "", actor: str = "", detail: dict | None = None):
    session.add(AuditEvent(org_id=org_id, order_id=order_id, scope=scope, action=action,
                           title=title, subtitle=subtitle, reason=reason, actor=actor,
                           detail=detail or {}))


def _get_doc(session, org_id: str, order_id: str, doc_id: str) -> EvidenceDocument:
    doc = session.get(EvidenceDocument, doc_id)
    if not doc or doc.org_id != org_id or doc.order_id != order_id or doc.deleted:
        raise LockerError("document not found", 404)
    return doc


# --------------------------------------------------------------------------- interface
class LockerProvider(Protocol):
    name: str

    def list_documents(self, org_id: str, order_id: str) -> list[dict]: ...
    def add_document(self, org_id: str, order_id: str, *, filename: str, data: bytes,
                     **kw: Any) -> dict: ...
    def set_doc_type(self, org_id: str, order_id: str, doc_id: str, doc_type: str,
                     actor: str) -> dict: ...
    def delete_document(self, org_id: str, order_id: str, doc_id: str, reason: str,
                        actor: str) -> dict: ...
    def lock_document(self, org_id: str, order_id: str, doc_id: str, checks: dict,
                      actor: str) -> dict: ...
    def unlock_document(self, org_id: str, order_id: str, doc_id: str, reason: str,
                        actor: str) -> dict: ...
    def read_document(self, org_id: str, order_id: str, doc_id: str) -> dict: ...
    def change_log(self, org_id: str, order_id: str) -> list[dict]: ...


# ----------------------------------------------------------------------------- local
class LocalLockerProvider:
    """Documents in our Postgres/SQLite + blob storage. Enforces the locking rules."""

    name = "local"

    # -- reads -------------------------------------------------------------
    def list_documents(self, org_id: str, order_id: str) -> list[dict]:
        with SessionLocal() as s:
            rows = s.execute(
                select(EvidenceDocument)
                .where(EvidenceDocument.org_id == org_id,
                       EvidenceDocument.order_id == order_id,
                       EvidenceDocument.deleted.is_(False))
                .order_by(EvidenceDocument.created_at)
            ).scalars().all()
            return [r.as_dict() for r in rows]

    def read_document(self, org_id: str, order_id: str, doc_id: str) -> dict:
        with SessionLocal() as s:
            doc = _get_doc(s, org_id, order_id, doc_id)
            path = store.local_path(doc.storage_key)
            payload = None if path else store.get(doc.storage_key)
            return {"filename": doc.filename, "content_type": doc.content_type,
                    "path": str(path) if path else None, "bytes": payload}

    def change_log(self, org_id: str, order_id: str) -> list[dict]:
        with SessionLocal() as s:
            rows = s.execute(
                select(AuditEvent)
                .where(AuditEvent.org_id == org_id, AuditEvent.order_id == order_id,
                       AuditEvent.scope == "locker")
                .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
            ).scalars().all()
            return [r.as_dict() for r in rows]

    # -- writes ------------------------------------------------------------
    def add_document(self, org_id: str, order_id: str, *, filename: str, data: bytes,
                     doc_type: str = "", source_key: str = "", origin: str = "manual_upload",
                     source_label: str = "", source_url: str = "", actor: str = "",
                     content_type: str = "") -> dict:
        validate_doc_type(doc_type)
        if not data:
            raise LockerError("the file is empty", 422)
        if len(data) > MAX_UPLOAD_BYTES:
            raise LockerError(
                f"file is {len(data) // (1024 * 1024)} MB; the limit is "
                f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB", 413)
        fname = _safe_filename(filename)
        ctype = content_type or mimetypes.guess_type(fname)[0] or "application/octet-stream"
        with SessionLocal() as s:
            # Generate the id up front. A column default is only applied at flush, so
            # reading doc.id before then yields None — which used to produce the storage
            # key "<org>/<order>/None.pdf" for every document in the order.
            doc_id = _uid()
            doc = EvidenceDocument(
                id=doc_id,
                org_id=org_id, order_id=order_id, filename=fname, doc_type=doc_type,
                source_key=source_key, origin=origin, status="review_needed",
                content_type=ctype, size_bytes=len(data), pages=_page_count(data, ctype),
                source_label=source_label, source_url=source_url,
                sha256=sha256_bytes(data), retrieved_by=actor, retrieved_at=_now(),
            )
            doc.storage_key = build_key(org_id, order_id, doc_id, fname)
            store.put(doc.storage_key, data)
            s.add(doc)
            audit(s, org_id=org_id, order_id=order_id, scope="locker",
                  action="uploaded" if origin == "manual_upload" else "auto_fetched",
                  title=f"{'Uploaded to record' if origin == 'manual_upload' else 'Auto-fetched'} — {fname}",
                  subtitle="Order Intake" if origin == "manual_upload" else "Research hub",
                  actor=actor, detail={"document_id": doc.id, "source_key": source_key})
            s.commit()
            return doc.as_dict()

    def set_doc_type(self, org_id: str, order_id: str, doc_id: str, doc_type: str,
                     actor: str = "") -> dict:
        validate_doc_type(doc_type)
        with SessionLocal() as s:
            doc = _get_doc(s, org_id, order_id, doc_id)
            if doc.status == "locked":
                raise LockerError("document is locked — unlock it before changing its type", 409)
            before, doc.doc_type = doc.doc_type, doc_type
            audit(s, org_id=org_id, order_id=order_id, scope="locker", action="doc_type_set",
                  title=f"Document type set — {doc.filename}",
                  subtitle=f"{before or 'unclassified'} → {doc_type or 'unclassified'}",
                  actor=actor, detail={"document_id": doc.id})
            s.commit()
            return doc.as_dict()

    def delete_document(self, org_id: str, order_id: str, doc_id: str, reason: str = "",
                        actor: str = "") -> dict:
        with SessionLocal() as s:
            doc = _get_doc(s, org_id, order_id, doc_id)
            if doc.status == "locked":
                raise LockerError("locked documents cannot be deleted — unlock first", 409)
            # Soft-delete: the change log has to keep pointing at a real row, and a deleted
            # piece of evidence is exactly the thing an audit later asks about.
            doc.deleted, doc.deleted_at, doc.delete_reason = True, _now(), reason
            store.delete(doc.storage_key)
            audit(s, org_id=org_id, order_id=order_id, scope="locker", action="deleted",
                  title=f"Deleted from Locker — {doc.filename}", subtitle="Research hub",
                  reason=reason, actor=actor, detail={"document_id": doc.id})
            s.commit()
            return {"ok": True, "id": doc_id}

    def lock_document(self, org_id: str, order_id: str, doc_id: str, checks: dict,
                      actor: str = "") -> dict:
        required = ("legible", "matches_parcel", "source_recorded")
        missing = [k for k in required if not checks.get(k)]
        if missing:
            raise LockerError(f"confirm all three checks before locking: missing {missing}")
        with SessionLocal() as s:
            doc = _get_doc(s, org_id, order_id, doc_id)
            if doc.status == "locked":
                return doc.as_dict()
            if not doc.doc_type:
                raise LockerError("set the document type before locking")
            doc.status = "locked"
            doc.locked_at, doc.locked_by = _now(), actor
            doc.lock_checks = dict(checks)
            # Seal = first 6 of the content digest. Shown in the log so a locked file is
            # identifiable, and re-computable from the bytes to prove nothing was swapped.
            doc.lock_seal = (doc.sha256 or "")[:6]
            audit(s, org_id=org_id, order_id=order_id, scope="locker", action="locked",
                  title=f"Reviewed and Locked — {doc.filename}",
                  subtitle=f"Research hub · sealed {doc.lock_seal}",
                  actor=actor, detail={"document_id": doc.id, "checks": doc.lock_checks})
            s.commit()
            return doc.as_dict()

    def unlock_document(self, org_id: str, order_id: str, doc_id: str, reason: str = "",
                        actor: str = "") -> dict:
        with SessionLocal() as s:
            doc = _get_doc(s, org_id, order_id, doc_id)
            if doc.status != "locked":
                return doc.as_dict()
            doc.status = "review_needed"
            doc.locked_at, doc.locked_by, doc.lock_seal = None, "", ""
            doc.lock_checks = {}
            audit(s, org_id=org_id, order_id=order_id, scope="locker", action="unlocked",
                  title=f"Unlocked — {doc.filename}", subtitle="Research hub",
                  reason=reason, actor=actor, detail={"document_id": doc.id})
            s.commit()
            return doc.as_dict()


# ---------------------------------------------------------------------------- remote
class RemoteLockerProvider:
    """Proxy to Mapperty's Evidence Locker REST API.

    Wire format is the same document shape the local provider returns, so the UI is unchanged.
    Endpoints and headers are documented in `docs/INTEGRATION.md` §"Remote locker provider" —
    keep the two in sync if the upstream contract changes.
    """

    name = "remote"

    def __init__(self, base: str = API_BASE, key: str = API_KEY):
        if not base:
            raise RuntimeError("QP_LOCKER_PROVIDER=remote needs QP_LOCKER_API_BASE")
        self.base, self.key = base.rstrip("/"), key

    # -- plumbing ----------------------------------------------------------
    def _headers(self, org_id: str) -> dict:
        h = {"Accept": "application/json", "X-Org-Id": org_id}
        if self.key:
            h["Authorization"] = f"Bearer {self.key}"
        return h

    def _call(self, method: str, path: str, org_id: str, **kw):
        from ..services.http import session as http_session  # lazy: shared pooled session

        r = http_session.request(method, f"{self.base}{path}",
                                 headers={**self._headers(org_id), **kw.pop("headers", {})},
                                 timeout=kw.pop("timeout", 30), **kw)
        if r.status_code >= 400:
            raise LockerError(f"locker api {r.status_code}: {r.text[:300]}", r.status_code)
        return r.json() if r.content else {}

    # -- interface ---------------------------------------------------------
    def list_documents(self, org_id, order_id):
        return self._call("GET", f"/orders/{order_id}/documents", org_id).get("documents", [])

    def add_document(self, org_id, order_id, *, filename, data, doc_type="", source_key="",
                     origin="manual_upload", source_label="", source_url="", actor="",
                     content_type=""):
        files = {"file": (filename, data,
                          content_type or mimetypes.guess_type(filename)[0]
                          or "application/octet-stream")}
        form = {"doc_type": doc_type, "source_key": source_key, "origin": origin,
                "source_label": source_label, "source_url": source_url, "actor": actor}
        return self._call("POST", f"/orders/{order_id}/documents", org_id,
                          files=files, data=form)

    def set_doc_type(self, org_id, order_id, doc_id, doc_type, actor=""):
        return self._call("PATCH", f"/orders/{order_id}/documents/{doc_id}", org_id,
                          json={"doc_type": doc_type, "actor": actor})

    def delete_document(self, org_id, order_id, doc_id, reason="", actor=""):
        return self._call("DELETE", f"/orders/{order_id}/documents/{doc_id}", org_id,
                          json={"reason": reason, "actor": actor})

    def lock_document(self, org_id, order_id, doc_id, checks, actor=""):
        return self._call("POST", f"/orders/{order_id}/documents/{doc_id}/lock", org_id,
                          json={"checks": checks, "actor": actor})

    def unlock_document(self, org_id, order_id, doc_id, reason="", actor=""):
        return self._call("POST", f"/orders/{order_id}/documents/{doc_id}/unlock", org_id,
                          json={"reason": reason, "actor": actor})

    def read_document(self, org_id, order_id, doc_id):
        from ..services.http import session as http_session

        r = http_session.get(f"{self.base}/orders/{order_id}/documents/{doc_id}/file",
                             headers=self._headers(org_id), timeout=60)
        if r.status_code >= 400:
            raise LockerError(f"locker api {r.status_code}", r.status_code)
        return {"filename": doc_id, "content_type": r.headers.get("Content-Type", ""),
                "path": None, "bytes": r.content}

    def change_log(self, org_id, order_id):
        return self._call("GET", f"/orders/{order_id}/documents/log", org_id).get("events", [])


# ------------------------------------------------------------------------- selection
_provider: LockerProvider | None = None


def get_provider() -> LockerProvider:
    """Resolve the configured provider once, falling back to local if remote is misconfigured
    (a bad env var must not take the whole research hub down)."""
    global _provider
    if _provider is None:
        if PROVIDER_NAME == "remote":
            try:
                _provider = RemoteLockerProvider()
            except Exception as e:  # noqa: BLE001
                print(f"[locker] remote provider unavailable ({e}); using local")
                _provider = LocalLockerProvider()
        else:
            _provider = LocalLockerProvider()
    return _provider


def utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
