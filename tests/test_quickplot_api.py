"""Regression suite for the QuickPlot v2 API.

Covers the four things that actually make this defensible as a product:
  1. the locking rules cannot be talked around,
  2. one tenant cannot see or touch another's data,
  3. nonsense input is rejected rather than stored,
  4. the audit trail records what really happened.

Run:  .venv/Scripts/python.exe -m pytest tests -q
"""
from __future__ import annotations

import uuid

import pytest

from conftest import ALL_CHECKS, MINIMAL_ORDER, PDF_BYTES


# ---------------------------------------------------------------- meta / smoke
def test_meta_reports_providers(api):
    d = api.get("/meta").json()
    assert d["org_id"] == "default"
    assert d["locker_provider"] in ("local", "remote")
    assert d["storage_backend"] in ("local", "s3")
    assert len(d["stages"]) == 6
    assert any(s["key"] == "parcel" for s in d["sources"])


def test_doc_types_are_stable_keys(api):
    keys = [t["key"] for t in api.get("/doc-types").json()["doc_types"]]
    for required in ("parcel", "appraiser", "deed", "plat", "flood"):
        assert required in keys


# ------------------------------------------------------------------- CRUD
def test_create_and_read_order(api):
    body = {**MINIMAL_ORDER, "order_no": "T-" + uuid.uuid4().hex[:6]}
    r = api.post("/orders", json=body)
    assert r.status_code == 201
    o = r.json()
    assert o["title"] == "Test Order"
    assert o["counts"] == {"documents": 0, "locked": 0, "review_needed": 0}
    assert api.get(f"/orders/{o['id']}").status_code == 200


def test_unknown_order_is_404(api):
    assert api.get("/orders/does-not-exist").status_code == 404


def test_patch_updates_only_supplied_fields(api, order):
    r = api.patch(f"/orders/{order['id']}", json={"lender": "Chase"})
    assert r.status_code == 200
    o = r.json()
    assert o["lender"] == "Chase"
    assert o["title"] == order["title"]          # untouched
    assert o["address"] == order["address"]


# --------------------------------------------------------------- validation
# "Common sense without special inputs" — the app must refuse states a human would
# never intend, at the API, not just in the form.
def test_order_requires_something_identifying(api):
    """A completely blank order is not a real order and must not be creatable."""
    r = api.post("/orders", json={})
    assert r.status_code == 422, "blank order was accepted"


def test_due_date_cannot_precede_received_date(api):
    r = api.post("/orders", json={**MINIMAL_ORDER, "order_no": "T-" + uuid.uuid4().hex[:6],
                                  "received_at": "2026-08-20", "due_at": "2026-08-10"})
    assert r.status_code == 422, "due date before received date was accepted"


def test_due_date_cannot_precede_received_date_on_patch(api, order):
    api.patch(f"/orders/{order['id']}", json={"received_at": "2026-08-20"})
    r = api.patch(f"/orders/{order['id']}", json={"due_at": "2026-08-01"})
    assert r.status_code == 422, "PATCH bypassed the date ordering rule"


def test_equal_dates_are_allowed(api):
    """Received and due on the same day is a rush job, not an error."""
    r = api.post("/orders", json={**MINIMAL_ORDER, "order_no": "T-" + uuid.uuid4().hex[:6],
                                  "received_at": "2026-08-20", "due_at": "2026-08-20"})
    assert r.status_code == 201


def test_malformed_date_is_rejected_not_silently_dropped(api):
    r = api.post("/orders", json={**MINIMAL_ORDER, "order_no": "T-" + uuid.uuid4().hex[:6],
                                  "due_at": "not-a-date"})
    assert r.status_code == 422, "garbage date was silently discarded"


def test_stage_must_be_a_known_stage(api, order):
    r = api.patch(f"/orders/{order['id']}", json={"stage": "banana"})
    assert r.status_code == 422, "unknown stage was accepted"


def test_state_code_is_validated(api):
    r = api.post("/orders", json={**MINIMAL_ORDER, "order_no": "T-" + uuid.uuid4().hex[:6],
                                  "state": "ZZ"})
    assert r.status_code == 422, "non-existent state code was accepted"


def test_email_is_validated_when_supplied(api):
    r = api.post("/orders", json={**MINIMAL_ORDER, "order_no": "T-" + uuid.uuid4().hex[:6],
                                  "client": {"name": "A", "email": "not-an-email"}})
    assert r.status_code == 422, "malformed client email was accepted"


def test_doc_type_must_come_from_the_catalog(api, order):
    r = api.post(f"/orders/{order['id']}/documents",
                 files={"files": ("x.pdf", PDF_BYTES, "application/pdf")},
                 data={"doc_type": "totally-made-up"})
    assert r.status_code == 422, "arbitrary doc_type was accepted"


def test_duplicate_order_number_is_rejected(api):
    no = "T-DUP-" + uuid.uuid4().hex[:4]
    assert api.post("/orders", json={**MINIMAL_ORDER, "order_no": no}).status_code == 201
    r = api.post("/orders", json={**MINIMAL_ORDER, "order_no": no})
    assert r.status_code == 409, "duplicate order number was accepted"


# --------------------------------------------------------------- documents
def test_upload_then_list(api, order):
    r = api.post(f"/orders/{order['id']}/documents",
                 files={"files": ("Deed.pdf", PDF_BYTES, "application/pdf")},
                 data={"doc_type": "deed"})
    assert r.status_code == 201
    d = r.json()["documents"][0]
    assert d["status"] == "review_needed"
    assert d["origin"] == "manual_upload"
    assert d["sha256"]
    assert d["pages"] == 2
    listed = api.get(f"/orders/{order['id']}/documents").json()["documents"]
    assert [x["id"] for x in listed] == [d["id"]]


def test_empty_upload_is_rejected(api, order):
    r = api.post(f"/orders/{order['id']}/documents",
                 files={"files": ("empty.pdf", b"", "application/pdf")})
    assert r.status_code == 422, "a zero-byte upload was silently accepted"


def test_oversize_upload_is_rejected(api, order):
    big = b"%PDF-1.4\n" + b"0" * (60 * 1024 * 1024)
    r = api.post(f"/orders/{order['id']}/documents",
                 files={"files": ("huge.pdf", big, "application/pdf")})
    assert r.status_code == 413, "no upload size limit"


def test_document_file_roundtrips(api, order, doc):
    r = api.get(f"/orders/{order['id']}/documents/{doc['id']}/file")
    assert r.status_code == 200
    assert r.content == PDF_BYTES


def test_document_counts_track_reality(api, order, doc):
    o = api.get(f"/orders/{order['id']}").json()
    assert o["counts"] == {"documents": 1, "locked": 0, "review_needed": 1}
    api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=ALL_CHECKS)
    o = api.get(f"/orders/{order['id']}").json()
    assert o["counts"] == {"documents": 1, "locked": 1, "review_needed": 0}


# ------------------------------------------------------------ locking rules
def test_lock_requires_all_three_confirmations(api, order, doc):
    for partial in ({"legible": True},
                    {"legible": True, "matches_parcel": True},
                    {"matches_parcel": True, "source_recorded": True}):
        r = api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=partial)
        assert r.status_code == 400, f"locked with only {partial}"


def test_lock_requires_a_doc_type(api, order):
    r = api.post(f"/orders/{order['id']}/documents",
                 files={"files": ("Unknown.pdf", PDF_BYTES, "application/pdf")})
    did = r.json()["documents"][0]["id"]
    r = api.post(f"/orders/{order['id']}/documents/{did}/lock", json=ALL_CHECKS)
    assert r.status_code == 400, "locked an unclassified document"


def test_locked_document_cannot_be_retyped(api, order, doc):
    api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=ALL_CHECKS)
    r = api.patch(f"/orders/{order['id']}/documents/{doc['id']}", json={"doc_type": "plat"})
    assert r.status_code == 409


def test_locked_document_cannot_be_deleted(api, order, doc):
    api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=ALL_CHECKS)
    r = api.delete(f"/orders/{order['id']}/documents/{doc['id']}?reason=x")
    assert r.status_code == 409


def test_lock_is_idempotent(api, order, doc):
    a = api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=ALL_CHECKS)
    b = api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=ALL_CHECKS)
    assert a.status_code == b.status_code == 200
    assert a.json()["lock_seal"] == b.json()["lock_seal"]


def test_lock_seal_matches_content_digest(api, order, doc):
    d = api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock",
                 json=ALL_CHECKS).json()
    assert d["lock_seal"] == d["sha256"][:6]


def test_unlock_then_delete_works(api, order, doc):
    api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=ALL_CHECKS)
    api.post(f"/orders/{order['id']}/documents/{doc['id']}/unlock", json={"reason": "wrong"})
    r = api.delete(f"/orders/{order['id']}/documents/{doc['id']}?reason=superseded")
    assert r.status_code == 200


def test_deleted_document_disappears_but_audit_remains(api, order, doc):
    api.delete(f"/orders/{order['id']}/documents/{doc['id']}?reason=duplicate")
    assert api.get(f"/orders/{order['id']}/documents").json()["documents"] == []
    log = api.get(f"/orders/{order['id']}/locker/log").json()["events"]
    assert any(e["action"] == "deleted" and e["reason"] == "duplicate" for e in log)


def test_deleted_document_file_is_not_served(api, order, doc):
    api.delete(f"/orders/{order['id']}/documents/{doc['id']}?reason=x")
    r = api.get(f"/orders/{order['id']}/documents/{doc['id']}/file")
    assert r.status_code == 404


# ------------------------------------------------------------- research flow
def test_checklist_ticks_on_locked_not_fetched(api, order, doc):
    before = api.get(f"/orders/{order['id']}/checklist").json()
    assert before["done"] == 0, "checklist ticked for an unlocked document"
    api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=ALL_CHECKS)
    after = api.get(f"/orders/{order['id']}/checklist").json()
    assert after["done"] == 1
    assert 0 < after["percent"] <= 100


def test_cannot_submit_with_nothing_locked(api, order, doc):
    r = api.post(f"/orders/{order['id']}/research/submit", json={"note": "n"})
    assert r.status_code == 409


def test_submit_moves_stage_and_records_note(api, order, doc):
    api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=ALL_CHECKS)
    r = api.post(f"/orders/{order['id']}/research/submit", json={"note": "check easement"})
    assert r.status_code == 200
    o = r.json()["order"]
    assert o["stage"] == "field_survey"
    assert o["research_state"] == "submitted"
    assert o["researcher_note"] == "check easement"
    assert o["stage_dates"].get("field_survey")


def test_double_submit_is_refused(api, order, doc):
    api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=ALL_CHECKS)
    api.post(f"/orders/{order['id']}/research/submit", json={"note": "first"})
    r = api.post(f"/orders/{order['id']}/research/submit", json={"note": "second"})
    assert r.status_code == 409, "research was submitted twice"


def test_sources_have_links_before_any_fetch(api, order):
    srcs = api.get(f"/orders/{order['id']}/sources").json()["sources"]
    assert len(srcs) >= 10
    by = {s["key"]: s for s in srcs}
    # Polk County FL is fully wired, so every county-backed source must offer a link.
    for key in ("parcel", "appraiser", "deed", "plat", "flood"):
        assert by[key]["open_url"], f"{key} has no Open source link"


def test_unknown_source_key_is_404(api, order):
    assert api.post(f"/orders/{order['id']}/sources/nonsense/fetch").status_code == 404


def test_research_summary_shape(api, order, doc):
    d = api.get(f"/orders/{order['id']}/research/summary").json()
    assert set(d["counts"]) == {"documents", "locked", "review_needed"}


# ------------------------------------------------------------------ tenancy
def test_other_tenant_cannot_read_order(api, order):
    other = api.as_org("intruder")
    assert other.get(f"/orders/{order['id']}").status_code == 404


def test_other_tenant_cannot_list_your_orders(api, order):
    other = api.as_org("intruder")
    ids = [o["id"] for o in other.get("/orders").json()["orders"]]
    assert order["id"] not in ids


def test_other_tenant_cannot_read_your_document(api, order, doc):
    other = api.as_org("intruder")
    assert other.get(f"/orders/{order['id']}/documents/{doc['id']}/file").status_code == 404


def test_other_tenant_cannot_lock_your_document(api, order, doc):
    other = api.as_org("intruder")
    r = other.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=ALL_CHECKS)
    assert r.status_code == 404


def test_other_tenant_cannot_delete_your_order(api, order):
    other = api.as_org("intruder")
    assert other.delete(f"/orders/{order['id']}").status_code == 404


# -------------------------------------------------------------------- audit
def test_order_creation_is_logged(api, order):
    log = api.get(f"/orders/{order['id']}/log?scope=order").json()["events"]
    actions = {e["action"] for e in log}
    assert "order_created" in actions
    assert all(e["actor"] for e in log), "an audit entry has no actor"


def test_lock_and_unlock_are_logged_with_actor(api, order, doc):
    api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=ALL_CHECKS)
    api.post(f"/orders/{order['id']}/documents/{doc['id']}/unlock", json={"reason": "redo"})
    log = api.get(f"/orders/{order['id']}/locker/log").json()["events"]
    actions = {e["action"] for e in log}
    assert {"uploaded", "locked", "unlocked"} <= actions
    unlocked = next(e for e in log if e["action"] == "unlocked")
    assert unlocked["reason"] == "redo"
    assert unlocked["actor"] == "QA Bot"


def test_log_scopes_are_separate(api, order, doc):
    order_log = api.get(f"/orders/{order['id']}/log?scope=order").json()["events"]
    locker_log = api.get(f"/orders/{order['id']}/log?scope=locker").json()["events"]
    assert all(e["scope"] == "order" for e in order_log)
    assert all(e["scope"] == "locker" for e in locker_log)


# --------------------------------------------------------------- data hygiene
def test_deleting_order_removes_its_blobs(api, order, doc):
    """An order delete must not leave orphaned files in the blob store."""
    from app.services.storage import store
    from app.db import SessionLocal
    from app.quickplot.models import EvidenceDocument

    with SessionLocal() as s:
        key = s.get(EvidenceDocument, doc["id"]).storage_key
    assert store.exists(key)
    api.delete(f"/orders/{order['id']}")
    assert not store.exists(key), "blob left behind after the order was deleted"


def test_filenames_with_path_separators_are_neutralised(api, order):
    r = api.post(f"/orders/{order['id']}/documents",
                 files={"files": ("../../etc/passwd.pdf", PDF_BYTES, "application/pdf")},
                 data={"doc_type": "deed"})
    assert r.status_code == 201
    name = r.json()["documents"][0]["filename"]
    assert "/" not in name and "\\" not in name and ".." not in name


# ------------------------------------------------- integrity + state machine
def test_each_document_gets_its_own_blob(api, order):
    """Two files in one order must never share a storage key — otherwise the second
    upload silently overwrites the first and the wrong bytes are served back."""
    from app.db import SessionLocal
    from app.quickplot.models import EvidenceDocument

    a = api.post(f"/orders/{order['id']}/documents",
                 files={"files": ("A.pdf", b"%PDF-1.4 AAA\n%%EOF", "application/pdf")},
                 data={"doc_type": "deed"}).json()["documents"][0]
    b = api.post(f"/orders/{order['id']}/documents",
                 files={"files": ("B.pdf", b"%PDF-1.4 BBB\n%%EOF", "application/pdf")},
                 data={"doc_type": "plat"}).json()["documents"][0]
    with SessionLocal() as s:
        ka = s.get(EvidenceDocument, a["id"]).storage_key
        kb = s.get(EvidenceDocument, b["id"]).storage_key
    assert "None" not in ka, f"storage key has no document id: {ka}"
    assert ka != kb, "two documents share one storage key"


def test_served_bytes_match_the_recorded_digest(api, order):
    """The bytes we serve must still hash to the digest recorded at upload — this is what
    makes a lock seal meaningful."""
    import hashlib

    api.post(f"/orders/{order['id']}/documents",
             files={"files": ("First.pdf", b"%PDF-1.4 FIRST\n%%EOF", "application/pdf")},
             data={"doc_type": "deed"})
    first = api.get(f"/orders/{order['id']}/documents").json()["documents"][0]
    api.post(f"/orders/{order['id']}/documents/{first['id']}/lock", json=ALL_CHECKS)
    # A later upload of the same type must not disturb the locked one.
    api.post(f"/orders/{order['id']}/documents",
             files={"files": ("Second.pdf", b"%PDF-1.4 SECOND\n%%EOF", "application/pdf")},
             data={"doc_type": "plat"})
    served = api.get(f"/orders/{order['id']}/documents/{first['id']}/file").content
    assert hashlib.sha256(served).hexdigest() == first["sha256"], \
        "a locked document's stored bytes changed after a later upload"


def test_cannot_restart_research_after_submission(api, order, doc):
    api.post(f"/orders/{order['id']}/documents/{doc['id']}/lock", json=ALL_CHECKS)
    api.post(f"/orders/{order['id']}/research/submit", json={"note": "done"})
    r = api.post(f"/orders/{order['id']}/research/start")
    assert r.status_code == 409, "research restarted on an already-submitted order"


def test_source_does_not_stick_in_fetching_when_a_run_is_already_live(api, order):
    """A per-source fetch that arrives while a run is already in flight must not park that
    row in 'Fetching…'. Asserted without touching the network: the run registry is primed
    to look busy, so start_run short-circuits before it would submit any work."""
    from app.quickplot import research

    api.get(f"/orders/{order['id']}/sources")          # materialise the rows
    research._set_run(order["id"], state="running", percent=20)
    try:
        r = api.post(f"/orders/{order['id']}/sources/deed/fetch")
        assert r.status_code == 200
        srcs = {s["key"]: s for s in api.get(f"/orders/{order['id']}/sources").json()["sources"]}
        assert srcs["deed"]["state"] != "fetching", "source stuck in 'fetching'"
    finally:
        research._set_run(order["id"], state="idle", percent=0)


def test_finished_run_never_leaves_a_source_spinning(api, order):
    """Whatever the outcome, the cleanup pass must clear any row still marked fetching."""
    from app.db import SessionLocal
    from app.quickplot import research
    from app.quickplot.models import OrderSource
    from sqlalchemy import select

    api.get(f"/orders/{order['id']}/sources")
    with SessionLocal() as s:
        row = s.execute(select(OrderSource).where(
            OrderSource.order_id == order["id"], OrderSource.key == "deed")).scalars().first()
        row.state = "fetching"
        s.commit()

    research._clear_stuck_fetching(order["id"])

    srcs = {s["key"]: s for s in api.get(f"/orders/{order['id']}/sources").json()["sources"]}
    assert srcs["deed"]["state"] == "failed"
    assert srcs["deed"]["message"]


# ------------------------------------------------------------ re-fetch hygiene
def _fake_step(key, label, files):
    return {"key": key, "label": label, "status": "ok", "downloaded": list(files),
            "summary": "", "source_url": "https://example.gov/x"}


def _seed_job(tmp_name, files: dict[str, bytes]):
    """Write a fake completed research job on disk so the ingest path has something real
    to read, without going anywhere near the network."""
    from app.config import JOBS_DIR

    docs = JOBS_DIR / tmp_name / "research" / "documents"
    docs.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (docs / name).write_bytes(data)
    return tmp_name


def test_refetch_refreshes_instead_of_duplicating(api, order):
    """Running auto-fetch twice must leave one document per source file, updated —
    not two rows with the same name. The generated reports embed a fetch timestamp, so
    content hashing alone never catches this."""
    from app.db import SessionLocal
    from app.quickplot import research
    from app.quickplot.locker import get_provider
    from app.quickplot.models import Order

    job = _seed_job("qp-test-refetch", {"Parcel_Record.html": b"<html>v1</html>"})
    with SessionLocal() as s:
        s.get(Order, order["id"]).job_name = job
        s.commit()
        o = s.get(Order, order["id"])

    step = _fake_step("parcel", "Parcel record", ["Parcel_Record.html"])
    research._ingest_step(get_provider(), o, step, "QA Bot")

    # second run: same filename, different bytes (as a timestamped report would be)
    (research.jobs_svc.job_file(job, "documents/Parcel_Record.html")).write_bytes(b"<html>v2</html>")
    research._ingest_step(get_provider(), o, step, "QA Bot")

    docs = api.get(f"/orders/{order['id']}/documents").json()["documents"]
    named = [d for d in docs if d["filename"] == "Parcel_Record.html"]
    assert len(named) == 1, f"re-fetch duplicated the document ({len(named)} copies)"
    served = api.get(f"/orders/{order['id']}/documents/{named[0]['id']}/file").content
    assert served == b"<html>v2</html>", "re-fetch did not refresh the content"


def test_refetch_never_replaces_locked_evidence(api, order):
    """A locked document is sealed. A later auto-fetch must leave it alone."""
    from app.db import SessionLocal
    from app.quickplot import research
    from app.quickplot.locker import get_provider
    from app.quickplot.models import Order

    job = _seed_job("qp-test-locked", {"Plat.html": b"<html>sealed</html>"})
    with SessionLocal() as s:
        s.get(Order, order["id"]).job_name = job
        s.commit()
        o = s.get(Order, order["id"])

    step = _fake_step("plat", "Recorded plat", ["Plat.html"])
    research._ingest_step(get_provider(), o, step, "QA Bot")
    d = api.get(f"/orders/{order['id']}/documents").json()["documents"][0]
    api.post(f"/orders/{order['id']}/documents/{d['id']}/lock", json=ALL_CHECKS)

    research.jobs_svc.job_file(job, "documents/Plat.html").write_bytes(b"<html>TAMPERED</html>")
    research._ingest_step(get_provider(), o, step, "QA Bot")

    served = api.get(f"/orders/{order['id']}/documents/{d['id']}/file").content
    assert served == b"<html>sealed</html>", "auto-fetch overwrote locked evidence"
    still = api.get(f"/orders/{order['id']}/documents/{d['id']}/file")
    assert still.status_code == 200
