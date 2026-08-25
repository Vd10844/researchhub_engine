"""Browser regression suite for the QuickPlot UI.

Drives a real Chromium against a real server on a throwaway database, so these catch the
things an API test cannot: a component that fails to render, a control that does nothing,
a dialog that will not close, a validation message that never appears.

Any uncaught JS error or failed console log fails the test that was running at the time —
a blank page is the classic no-build-step failure mode and must never pass silently.

    .venv/Scripts/python.exe -m pytest tests/test_quickplot_ui.py -q

Skipped automatically when Chromium is not installed (`python -m playwright install chromium`).
"""
from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent

playwright = pytest.importorskip("playwright.sync_api",
                                 reason="playwright not installed")
from playwright.sync_api import sync_playwright  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    """A real uvicorn on a scratch database, so the UI exercises the true stack."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="qp_ui_"))
    port = _free_port()
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{(tmp / 'ui.db').as_posix()}",
        "QP_STORAGE_ROOT": str(tmp / "blob"),
        "SURVEY_JOBS_DIR": str(tmp / "jobs"),
        "SURVEY_EVIDENCE_DIR": str(tmp / "evidence"),
        "PYTHONIOENCODING": "utf-8",
    }
    proc = subprocess.Popen(
        [str(_ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "uvicorn",
         "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=str(_ROOT / "backend"), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    base = f"http://127.0.0.1:{port}"
    import urllib.error
    import urllib.request
    for _ in range(120):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            break
        except (urllib.error.URLError, OSError):
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="replace")
                pytest.fail(f"server died on startup:\n{out}")
            time.sleep(0.25)
    else:
        proc.kill()
        pytest.fail("server did not come up")

    yield base
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"chromium unavailable: {e}")
        yield b
        b.close()


@pytest.fixture
def page(browser, server):
    """A page whose JS errors are fatal to the test."""
    pg = browser.new_page(viewport={"width": 1600, "height": 1100})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: errors.append(f"console.error: {m.text}")
          if m.type == "error" else None)
    pg.base = server
    yield pg
    pg.close()
    assert not errors, "JavaScript errors on the page:\n  " + "\n  ".join(errors)


def open_app(page, hash_route="#/orders"):
    page.goto(f"{page.base}/quickplot{hash_route}", wait_until="networkidle")
    page.wait_for_timeout(1200)
    return page


def seed(page):
    """The shared demo order. Idempotent, so it is only safe for read-only tests."""
    import json
    import urllib.request

    req = urllib.request.Request(f"{page.base}/api/v2/demo/seed", method="POST",
                                 headers={"X-Org-Id": "default"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["order"]


def new_order(page, title="UI Test Order"):
    """A private order for one test.

    The `server` fixture is module-scoped (starting uvicorn per test would be far too
    slow) and `seed()` returns the SAME order every time, so any test that uploads or
    locks would otherwise contaminate the next one. Anything that mutates state must use
    this instead.
    """
    import json
    import urllib.request
    import uuid

    body = json.dumps({
        "title": title, "order_no": "UI-" + uuid.uuid4().hex[:6],
        "address": "1015 E Palmetto St, Lakeland, FL 33801",
        "city": "Lakeland", "county": "Polk", "county_fips": "12105", "state": "FL",
    }).encode()
    req = urllib.request.Request(f"{page.base}/api/v2/orders", data=body, method="POST",
                                 headers={"X-Org-Id": "default",
                                          "X-Actor": "UI Test",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ------------------------------------------------------------------- rendering
def test_app_renders_and_is_not_blank(page):
    open_app(page)
    assert page.locator(".qp-app").count() == 1, "shell did not render (blank page?)"
    assert page.locator("text=Orders").first.is_visible()


def test_all_hash_routes_render(page):
    o = seed(page)
    for route, marker in (("#/orders", "Orders"),
                          (f"#/orders/{o['id']}", "Back to Orders"),
                          (f"#/orders/{o['id']}/research", "Gather the research set"),
                          ("#/users", "Users"),
                          ("#/support", "Support"),
                          ("#/quote", "Quote hub")):
        open_app(page, route)
        assert page.locator(f"text={marker}").first.is_visible(), f"{route} did not render"


def test_unknown_route_does_not_crash(page):
    open_app(page, "#/nonsense/deep/path")
    assert page.locator(".qp-app").count() == 1


# ------------------------------------------------- search bar clear (team item 1)
def test_orders_search_has_a_one_click_clear(page):
    seed(page)
    open_app(page)
    box = page.locator(".qp-search input").first
    assert page.locator(".qp-search__clear").count() == 0, \
        "clear button shown while the box is empty"
    box.fill("oakmont")
    page.wait_for_timeout(500)
    clear = page.locator(".qp-search__clear").first
    assert clear.is_visible(), "no clear button once text is typed"
    clear.click()
    page.wait_for_timeout(600)
    assert box.input_value() == "", "clear button did not empty the search box"


def test_escape_clears_the_search_box(page):
    seed(page)
    open_app(page)
    box = page.locator(".qp-search input").first
    box.fill("something")
    page.wait_for_timeout(300)
    box.press("Escape")
    page.wait_for_timeout(300)
    assert box.input_value() == ""


def test_document_search_also_clears(page):
    o = new_order(page)
    open_app(page, f"#/orders/{o['id']}/research")
    page.click("text=Upload Documents")
    page.wait_for_timeout(500)
    with page.expect_file_chooser() as fc:
        page.click(".qp-dropzone")
    fc.value.set_files({"name": "Deed.pdf", "mimeType": "application/pdf",
                        "buffer": b"%PDF-1.4\n1 0 obj<</Type /Page>>endobj\n%%EOF"})
    page.wait_for_timeout(400)
    page.select_option(".qp-uprow select", "deed")
    page.click(".qp-modal__foot button:has-text('Upload')")
    page.wait_for_timeout(1800)

    box = page.locator(".qp-search input").first
    box.fill("zzz-no-match")
    page.wait_for_timeout(400)
    assert page.locator("text=No documents match").count() == 1
    page.locator(".qp-search__clear").first.click()
    page.wait_for_timeout(400)
    assert page.locator("tbody tr").count() >= 1, "clearing did not restore the list"


# ------------------------------------------------ form validation (team item 2)
def test_new_order_form_rejects_a_blank_submission(page):
    open_app(page)
    page.click("text=New Order")
    page.wait_for_timeout(600)
    # The seeded default is only a state code, which is not identifying on its own.
    page.fill("label.qp-field:has-text('Order title') input", "")
    page.click(".qp-modal__foot button:has-text('Create order')")
    page.wait_for_timeout(700)
    assert page.locator(".qp-field__error, .qp-toast--err").count() >= 1, \
        "blank order produced no visible error"
    assert page.locator(".qp-modal").count() == 1, "modal closed despite invalid input"


def test_due_date_before_received_is_flagged_in_the_form(page):
    open_app(page)
    page.click("text=New Order")
    page.wait_for_timeout(600)
    page.fill("label.qp-field:has-text('Order title') input", "Date Order Test")
    page.fill("label.qp-field:has-text('Received') input", "2026-08-20")
    page.fill("label.qp-field:has-text('Due date') input", "2026-08-01")
    page.click(".qp-modal__foot button:has-text('Create order')")
    page.wait_for_timeout(700)
    txt = page.locator(".qp-field__error, .qp-toast").all_inner_texts()
    assert any("before the received" in t.lower() or "due date" in t.lower() for t in txt), \
        f"no due-date error surfaced; saw {txt}"


def test_bad_email_is_flagged_in_the_form(page):
    open_app(page)
    page.click("text=New Order")
    page.wait_for_timeout(600)
    page.fill("label.qp-field:has-text('Order title') input", "Email Test")
    page.fill(".qp-modal >> label.qp-field:has-text('Email') input", "not-an-email")
    page.click(".qp-modal__foot button:has-text('Create order')")
    page.wait_for_timeout(700)
    txt = " ".join(page.locator(".qp-field__error, .qp-toast").all_inner_texts()).lower()
    assert "email" in txt, "invalid email was not flagged"


# ---------------------------------------------------------- the locking flow
def _upload_one(page, order_id, name="Deed.pdf", doc_type="deed"):
    page.click("text=Upload Documents")
    page.wait_for_timeout(500)
    with page.expect_file_chooser() as fc:
        page.click(".qp-dropzone")
    fc.value.set_files({"name": name, "mimeType": "application/pdf",
                        "buffer": b"%PDF-1.4\n1 0 obj<</Type /Page>>endobj\n%%EOF"})
    page.wait_for_timeout(400)
    page.select_option(".qp-uprow select", doc_type)
    page.click(".qp-modal__foot button:has-text('Upload')")
    page.wait_for_timeout(1800)


def test_approve_and_lock_is_gated_on_all_three_checks(page):
    o = new_order(page)
    open_app(page, f"#/orders/{o['id']}/research")
    _upload_one(page, o["id"])
    page.click("tbody button:has-text('Review & lock')")
    page.wait_for_timeout(1200)

    approve = page.locator(".qp-modal__foot button:has-text('Approve & Lock')")
    assert approve.is_disabled(), "Approve & Lock was enabled with nothing confirmed"
    page.click(".qp-confirm:has-text('Legible and complete')")
    page.wait_for_timeout(200)
    assert approve.is_disabled(), "Approve & Lock enabled after only one confirmation"
    page.click(".qp-confirm:has-text('Matches this parcel')")
    page.click(".qp-confirm:has-text('Source is recorded')")
    page.wait_for_timeout(300)
    assert approve.is_enabled(), "Approve & Lock still disabled with all three confirmed"


def test_full_lock_flow_updates_the_row_and_checklist(page):
    o = new_order(page)
    open_app(page, f"#/orders/{o['id']}/research")
    _upload_one(page, o["id"])
    page.click("tbody button:has-text('Review & lock')")
    page.wait_for_timeout(1200)
    for label in ("Legible and complete", "Matches this parcel", "Source is recorded"):
        page.click(f".qp-confirm:has-text('{label}')")
    page.click(".qp-modal__foot button:has-text('Approve & Lock')")
    page.wait_for_timeout(700)
    assert page.locator("text=Confirm Evidence Lock").is_visible()
    page.click(".qp-modal--center .qp-modal__foot button:has-text('Lock')")
    page.wait_for_timeout(2200)

    assert page.locator("tbody >> text=Locked").count() >= 1, "row did not become Locked"
    assert page.locator("tbody >> text=Unlock").count() >= 1, "no Unlock action offered"

    page.click("text=Research Checklist")
    page.wait_for_timeout(1200)
    assert page.locator(".qp-checkrow.is-done").count() >= 1, "checklist did not tick"
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    assert page.locator(".qp-drawer").count() == 0, "drawer did not close on Escape"


def test_review_and_lock_is_disabled_without_a_document_type(page):
    o = new_order(page)
    open_app(page, f"#/orders/{o['id']}/research")
    page.click("text=Upload Documents")
    page.wait_for_timeout(500)
    with page.expect_file_chooser() as fc:
        page.click(".qp-dropzone")
    fc.value.set_files({"name": "Unclassified.pdf", "mimeType": "application/pdf",
                        "buffer": b"%PDF-1.4\n%%EOF"})
    page.wait_for_timeout(400)
    page.click(".qp-modal__foot button:has-text('Upload')")     # no type chosen
    page.wait_for_timeout(1800)
    btn = page.locator("tbody button:has-text('Review & lock')").first
    assert btn.is_disabled(), "Review & lock offered on an unclassified document"


def test_submit_is_refused_with_nothing_locked(page):
    o = new_order(page)
    open_app(page, f"#/orders/{o['id']}/research")
    _upload_one(page, o["id"])
    page.click(".qp-sticky-foot button:has-text('Submit Research')")
    page.wait_for_timeout(1500)
    assert page.locator("text=Lock at least one document").count() >= 1, \
        "submit dialog did not warn about the empty evidence set"
    submit = page.locator(".qp-modal__foot button:has-text('Submit research')")
    assert submit.is_disabled(), "submit was possible with nothing locked"


# ------------------------------------------------------------------ dialogs
def test_every_dialog_closes_on_escape(page):
    o = new_order(page)
    open_app(page, f"#/orders/{o['id']}/research")
    for opener in ("text=Upload Documents", "text=Locker log"):
        page.click(opener)
        page.wait_for_timeout(800)
        assert page.locator(".qp-modal").count() == 1, f"{opener} did not open"
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        assert page.locator(".qp-modal").count() == 0, f"{opener} did not close on Escape"


def test_order_log_shows_the_audit_trail(page):
    o = seed(page)
    open_app(page, f"#/orders/{o['id']}")
    page.click("text=Order Log")
    page.wait_for_timeout(1300)
    assert page.locator("text=Order created").count() >= 1
    assert page.locator("text=Order information — change log").count() == 1
