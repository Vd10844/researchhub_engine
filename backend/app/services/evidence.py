"""Evidence Locker — the researcher's hand-off store.

A researcher gathers the survey documents for an order (auto-fetched or manually uploaded),
then *sends* the chosen ones to an Evidence Locker keyed by the order number. A drafter later
references that locker. Lockers live under EVIDENCE_DIR/<order-slug>/ with the copied files and
a locker.json manifest. Everything here is confined to EVIDENCE_DIR / the job's research dir
(path-traversal guarded), mirroring jobs.py.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import shutil

from ..config import EVIDENCE_DIR
from . import jobs


def _slug(text: str) -> str:
    """Filesystem-safe, idempotent slug for an order number / locker dir."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", (text or "").strip()).strip("-.")
    return (s or "order")[:80]


def _safe_name(filename: str) -> str:
    base = pathlib.PurePath((filename or "file").replace("\\", "/")).name
    return re.sub(r"[^A-Za-z0-9._ -]+", "_", base)[:120] or "file"


def _locker_dir(order: str) -> pathlib.Path:
    return EVIDENCE_DIR / _slug(order)


def _alloc_order(order: str) -> str:
    """Pick an order key whose locker doesn't exist yet: the base if free, else base-2,
    base-3, … So re-sending the same parcel makes a NEW locker instead of touching the old."""
    base = (order or "order").strip()
    if not _locker_dir(base).exists():
        return base
    i = 2
    while _locker_dir(f"{base}-{i}").exists():
        i += 1
    return f"{base}-{i}"


# ---------------------------------------------------------------------------------
# Per-document upload (attach a manually-downloaded file to a job's doc)
# ---------------------------------------------------------------------------------
def _order_ref(res: dict, job_name: str) -> str:
    """Same locker key the UI uses: explicit order, else Parcel ID, else the job folder."""
    return (res or {}).get("order") or (res or {}).get("parcel_id") or job_name


def save_upload(job_name: str, key: str, filename: str, data: bytes) -> dict | None:
    """Save an uploaded file for a doc step. Only ONE upload per doc: any previous upload for
    that key is replaced (removed from disk, result.json, and the locker). Returns
    {"file": saved, "removed": [old...]}."""
    research = jobs._safe_research_dir(job_name)
    if not research or not data:
        return None
    docs = research / "documents"
    docs.mkdir(parents=True, exist_ok=True)
    prefix = f"Uploaded_{_slug(key)}_"

    # Replace any prior upload for this doc.
    removed = []
    for old in docs.glob(prefix + "*"):
        try:
            old.unlink()
            removed.append(old.name)
        except Exception:  # noqa: BLE001
            pass
    out = docs / (prefix + _safe_name(filename))
    out.write_bytes(data)

    order = ""
    rf = research / "result.json"
    if rf.exists():
        try:
            res = json.loads(rf.read_text())
            order = _order_ref(res, job_name)
            for s in res.get("steps", []):
                if s.get("key") == key:
                    dl = [f for f in (s.get("downloaded") or []) if f not in removed]
                    if out.name not in dl:
                        dl.append(out.name)
                    s["downloaded"] = dl
                    s["uploaded"] = True
                    if s.get("status") != "ok":
                        s["status"] = "ok"
                    break
            rf.write_text(json.dumps(res, indent=2, default=str))
        except Exception:  # noqa: BLE001 — the file is saved regardless
            pass

    # Keep the locker in sync: drop the replaced upload(s) from it.
    for r in removed:
        try:
            delete_item(order, r)
        except Exception:  # noqa: BLE001
            pass
    return {"file": out.name, "removed": removed}


def delete_job_doc(job_name: str, file: str) -> dict | None:
    """Delete one document file from a job (disk + result.json) and remove it from the order's
    Evidence Locker too — so the row and the locker stay in sync."""
    research = jobs._safe_research_dir(job_name)
    if not research or not file or ".." in file or "/" in file or "\\" in file:
        return None
    docs = research / "documents"
    fp = docs / file
    try:
        if fp.is_file() and docs.resolve() in fp.resolve().parents:
            fp.unlink()
    except Exception:  # noqa: BLE001
        pass
    order = ""
    rf = research / "result.json"
    if rf.exists():
        try:
            res = json.loads(rf.read_text())
            order = _order_ref(res, job_name)
            for s in res.get("steps", []):
                dl = s.get("downloaded") or []
                if file in dl:
                    dl2 = [f for f in dl if f != file]
                    s["downloaded"] = dl2
                    if not any(f.startswith("Uploaded_") for f in dl2):
                        s.pop("uploaded", None)
                    if not dl2 and s.get("link"):
                        s["status"] = "link"
            rf.write_text(json.dumps(res, indent=2, default=str))
        except Exception:  # noqa: BLE001
            pass
    try:
        delete_item(order, file)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "file": file}


# ---------------------------------------------------------------------------------
# Evidence Locker
# ---------------------------------------------------------------------------------
def send_to_evidence(order: str, job_name: str, items: list[dict],
                     new_order: bool = False) -> dict | None:
    """Copy the selected job documents into the order's Evidence Locker (append-only).

    When `new_order` is set (the first send of a session), a fresh order key is allocated —
    suffixed if a locker for this parcel already exists — so the old locker is never modified.
    The resolved order/slug is returned so the caller reuses it for the rest of the session."""
    research = jobs._safe_research_dir(job_name)
    if not research:
        return None
    if new_order:
        order = _alloc_order(order)
    docs = research / "documents"
    ld = _locker_dir(order)
    ld.mkdir(parents=True, exist_ok=True)
    lf = ld / "locker.json"

    locker = {"order": order, "items": []}
    if lf.exists():
        try:
            locker = json.loads(lf.read_text())
        except Exception:  # noqa: BLE001
            locker = {"order": order, "items": []}
    existing = {it.get("file") for it in locker.get("items", [])}
    now = datetime.datetime.utcnow().isoformat() + "Z"

    for it in items:
        fn = (it.get("file") or "").strip()
        if not fn or ".." in fn or "/" in fn or "\\" in fn:
            continue
        src = docs / fn
        if not src.is_file():
            continue
        shutil.copy2(src, ld / fn)
        if fn not in existing:
            locker.setdefault("items", []).append({
                "key": it.get("key", ""), "label": it.get("label", ""), "file": fn,
                "source_job": job_name, "source_url": it.get("source_url", ""),
                "sent_utc": now,
            })
            existing.add(fn)

    locker["order"] = order
    locker["updated_utc"] = now
    lf.write_text(json.dumps(locker, indent=2, default=str))

    # Persist the locker link on the source job so its "Sent to Evidence Locker" status stays
    # consistent when the job is reopened later (same idea as the persisted match/verdict).
    rf = research / "result.json"
    if rf.exists():
        try:
            res = json.loads(rf.read_text())
            res["locker_order"] = order
            rf.write_text(json.dumps(res, indent=2, default=str))
        except Exception:  # noqa: BLE001
            pass
    return {**locker, "slug": _slug(order)}


def list_lockers() -> list[dict]:
    out = []
    if EVIDENCE_DIR.is_dir():
        for d in EVIDENCE_DIR.iterdir():
            lf = d / "locker.json"
            if not lf.is_file():
                continue
            try:
                L = json.loads(lf.read_text())
            except Exception:  # noqa: BLE001
                continue
            # An order only exists to hold documents — prune any that are empty so a
            # zero-doc order never lingers in the locker list.
            if not L.get("items"):
                try:
                    shutil.rmtree(d)
                except Exception:  # noqa: BLE001
                    pass
                continue
            out.append({"order": L.get("order", d.name), "slug": d.name,
                        "count": len(L.get("items", [])), "updated": L.get("updated_utc", "")})
    out.sort(key=lambda x: x.get("updated", ""), reverse=True)
    return out


def delete_item(order: str, file: str) -> dict | None:
    """Remove one document from an order's locker (deletes the copied file + its entry)."""
    ld = _locker_dir(order)
    lf = ld / "locker.json"
    if not lf.is_file() or not file or ".." in file or "/" in file or "\\" in file:
        return None
    try:
        locker = json.loads(lf.read_text())
    except Exception:  # noqa: BLE001
        return None
    locker["items"] = [it for it in locker.get("items", []) if it.get("file") != file]
    fp = ld / file
    try:
        if fp.is_file() and ld.resolve() in fp.resolve().parents:
            fp.unlink()
    except Exception:  # noqa: BLE001
        pass
    # An order only exists to hold documents — when the last one is removed, drop the order.
    if not locker.get("items"):
        try:
            shutil.rmtree(ld)
        except Exception:  # noqa: BLE001
            pass
        return {"order": locker.get("order", order), "items": [], "removed": True}
    locker["updated_utc"] = datetime.datetime.utcnow().isoformat() + "Z"
    lf.write_text(json.dumps(locker, indent=2, default=str))
    return locker


def delete_locker(order: str) -> bool:
    """Delete an entire Evidence Locker order (its folder + all copied documents)."""
    ld = _locker_dir(order)
    try:
        if ld.is_dir() and EVIDENCE_DIR.resolve() in ld.resolve().parents:
            shutil.rmtree(ld)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def locker_detail(order: str) -> dict | None:
    lf = _locker_dir(order) / "locker.json"
    if not lf.is_file():
        return None
    try:
        return json.loads(lf.read_text())
    except Exception:  # noqa: BLE001
        return None


def locker_file(order: str, relpath: str):
    ld = _locker_dir(order)
    if not relpath or ".." in relpath or relpath.startswith(("/", "\\")):
        return None
    p = ld / relpath
    try:
        if p.is_file() and ld.resolve() in p.resolve().parents:
            return p
    except Exception:  # noqa: BLE001
        return None
    return None
