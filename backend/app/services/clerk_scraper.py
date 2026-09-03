"""Browser-driven document retrieval from county Clerk Official-Records portals.

Some clerk portals expose no API and encrypt their per-session document IDs (Polk's
NewVision "BrowserView" RSA-encrypts the ID/Page in each request), so the only reliable
way to pull the actual deed / plat image is to drive the real search UI with Playwright,
capture the image the viewer requests, and save it.

Currently implemented:
  * NewVision BrowserView (Polk 12105) — plat by Plat-Book/Page (deterministic) and deed
    by owner-name Party search disambiguated on the subdivision in the Legal column.

Everything here is best-effort: any failure returns [] and the caller keeps the one-click
deep-link fallback. Playwright + a Chromium build must be installed
(`pip install playwright && python -m playwright install chromium`); if not, this module
degrades to a no-op.
"""
from __future__ import annotations

import base64
import contextlib
import io
import pathlib
import re

# NewVision BrowserView base URLs, keyed by county FIPS. (Polk's registry platform is
# labelled "inhouse"; it is in fact NewVision — this map is the source of truth here.)
NEWVISION_PORTALS: dict[str, str] = {
    "12105": "https://apps.polkcountyclerk.net/browserviewor/",   # Polk
    "12083": "https://nvweb.marioncountyclerk.org/BrowserView/",  # Marion (same NewVision app)
}

# Tyler "Official Records Self-Service" (Eagle Recorder) portals, keyed by county FIPS.
# These serve the actual document as a free PDF at /web/document-image-pdf/... (no cart /
# purchase gate). Many US counties run this exact platform, so the adapter generalises.
TYLER_PORTALS: dict[str, str] = {
    "12091": "https://okaloosacountyfl-web.tylerhost.net/web/",  # Okaloosa
}

# Manatee (Tyler "Public Records Hub"). Unlike the others this needs NO browser: its search
# routes are plain server-rendered GETs and the document pages are free JPEGs from
# InstrumentResultJpgAsync — so the adapter is pure `requests` + Pillow. Keyed by county FIPS.
MANATEE_PORTALS: dict[str, str] = {
    "12081": "https://records.manateeclerk.com",  # Manatee
}

# Volusia's in-house Official Records viewer. It serves the document as a free PDF from
# load_Redact.aspx (no cart / purchase / captcha), but renders it inside Chromium's PDF
# plugin, so the bytes are captured via a CDP Fetch interception rather than a normal
# response handler. Keyed by county FIPS.
VOLUSIA_PORTALS: dict[str, str] = {
    "12127": "https://app02.clerk.org/or_m/",  # Volusia
}

_LAUNCH_ARGS = ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                "--ignore-certificate-errors"]


def available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False


def has_adapter(county_fips: str) -> bool:
    # Manatee is pure requests (no Playwright) — available even if Chromium isn't installed.
    if county_fips in MANATEE_PORTALS:
        return True
    return (county_fips in NEWVISION_PORTALS or county_fips in TYLER_PORTALS
            or county_fips in VOLUSIA_PORTALS) and available()


# ---------------------------------------------------------------------------------
# NewVision BrowserView driver
# ---------------------------------------------------------------------------------
class _NewVision:
    """One headless browsing session against a NewVision BrowserView OR portal."""

    def __init__(self, page, timeout_ms: int = 45000):
        self.pg = page
        self.captured: list[tuple[int, bytes]] = []  # (page_number, image_bytes)
        self.search_results: list[dict] = []          # last /api/search rows
        self.doc_pages: int = 0                        # page count of the open document
        page.set_default_timeout(timeout_ms)
        page.on("response", self._on_response)

    def _on_response(self, r):
        try:
            url = r.url.rstrip("/")
            if url.endswith("/api/search") and r.request.method == "POST":
                j = r.json()
                if isinstance(j, list):
                    self.search_results = j
                return
            if not (url.endswith("/api/document") and r.request.method == "POST"):
                return
            body = r.json()
            if not isinstance(body, dict):
                return
            # Metadata response carries the page count; image responses carry hi_res.
            # Identify images by the hi_res KEY, not size — index/cover pages can be tiny
            # (a 20 KB page 1 was being dropped by the old 50 KB gate).
            if body.get("doc_pages"):
                with contextlib.suppress(TypeError, ValueError):
                    self.doc_pages = int(body["doc_pages"])
            b64 = body.get("hi_res") or body.get("largeimage") or ""
            if isinstance(b64, str) and len(b64) > 1000:
                self.captured.append((int(body.get("pg_num") or 0),
                                      base64.b64decode(b64)))
        except Exception:
            pass

    def open(self, url: str):
        self.pg.goto(url, wait_until="load")
        self.pg.wait_for_timeout(2500)

    # -- search entry points -------------------------------------------------------
    def search_book_page(self, book: str, page: str, book_type: str = "O"):
        """book_type: 'P' = Plat, 'O' = Official Records (deeds/mortgages)."""
        # Target the nav tab precisely — plain text=Book/Page also matches results columns.
        self.pg.get_by_role("link", name="Book/Page", exact=True).first.click()
        self.pg.wait_for_timeout(900)
        self.pg.locator("select:visible").first.select_option(book_type)
        self.pg.locator("input[placeholder='Book']:visible").first.fill(str(book))
        self.pg.locator("input[placeholder='Page']:visible").first.fill(str(page))
        self.pg.locator("button:has-text('Search'):visible").first.click()
        self.pg.wait_for_timeout(3000)

    def search_plat(self, book: str, page: str):
        self.search_book_page(book, page, "P")

    def search_party(self, party_name: str) -> list[dict]:
        """Owner-name search. Returns the /api/search result rows (from JSON, not DOM)."""
        self.search_results = []
        self.pg.click("text=Party")
        self.pg.wait_for_timeout(800)
        self.pg.locator("input[placeholder='Party Name']:visible").first.fill(party_name)
        self.pg.locator("button:has-text('Search'):visible").first.click()
        self.pg.wait_for_timeout(3500)
        return self.search_results

    # -- results + document capture ------------------------------------------------
    def open_first_result(self) -> bool:
        views = self.pg.locator("a:has-text('View'):visible, button:has-text('View'):visible")
        if views.count() == 0:
            return False
        views.first.click()
        self.pg.wait_for_timeout(3500)
        return True

    def capture_pages(self, wait_ms: int = 20000) -> list[bytes]:
        """Collect ALL page images of the open document.

        Opening a result auto-loads page 1 via the api/document XHR (the listener stores
        it). Multi-sheet plats/deeds have more pages behind the viewer's next-page control,
        so after page 1 lands we step through with `changePage(true)` until every page
        (`doc_pages`) is captured or the viewer stops advancing."""
        waited = 0
        while not self.captured and waited < wait_ms:
            self.pg.wait_for_timeout(500)
            waited += 500
        nxt = self.pg.locator("[ng-click='changePage(true)']")
        target = self.doc_pages or 1
        guard = 0
        while len({pn for pn, _ in self.captured}) < target and guard < target + 3:
            guard += 1
            if not nxt.count():
                break
            before = len(self.captured)
            try:
                nxt.first.click()
            except Exception:
                break
            w = 0
            while len(self.captured) == before and w < 10000:
                self.pg.wait_for_timeout(400)
                w += 400
            if len(self.captured) == before:
                break  # viewer didn't advance / no new image → stop
        # de-dup by page number, keep first bytes seen per page, ordered by page
        seen, out = set(), []
        for pg_num, data in sorted(self.captured, key=lambda t: t[0]):
            if pg_num not in seen:
                seen.add(pg_num)
                out.append(data)
        return out


_DEED_TYPES = {"DEED", "D", "WD", "WARRANTY DEED", "QCD", "QUIT CLAIM DEED",
               "SPECIAL WARRANTY DEED", "SWD", "TD", "PR DEED", "GD"}


# Legal-description noise words (incl. DOR's "SUB"/"SUBDIVISION" abbreviation, which does
# NOT appear in recorded deed legals — matching on it made the subdivision check fail).
_LEGAL_STOP = {"HTS", "HEIGHTS", "UNIT", "NO", "PB", "PG", "BLK", "BLOCK", "LOT", "LT",
               "LTS", "PLAT", "SUB", "SUBD", "SUBDIV", "SUBDIVISION", "OF", "THE",
               "ADD", "ADDITION", "PH", "PHASE", "SEC", "REP", "REPLAT"}


def _subdiv_name(s: str) -> list:
    return [t for t in re.sub(r"[^A-Z0-9 ]", " ", (s or "").upper()).split()
            if t not in _LEGAL_STOP and not t.isdigit()][:2]


def _pick_deed(rows: list[dict], subdivision: str) -> dict | None:
    """Pick the subject parcel's vesting deed from an owner-name search.

    A survey uses the *seller's* vesting deed — the deed that gave the currently-listed
    owner their title. In the NewVision index that's the row where the searched owner is
    the GRANTEE (party_code 'R'), as opposed to a later deed where they convey the property
    away ('D'). So: keep only DEED rows whose legal matches the parcel's subdivision (name
    + unit), then prefer the most recent grantee ('R') deed.

    Crucially, if NOTHING matches the subdivision we return None (keep the deep-link)
    rather than a most-recent-by-name guess — for common owner names that guess returned a
    completely different property's deed (observed: a "LAKESIDE" deed for an "IDLEWILD"
    parcel)."""
    deeds = [r for r in rows if str(r.get("doc_type", "")).upper() in _DEED_TYPES]
    name = _subdiv_name(subdivision)
    if not deeds or not name:
        return None
    unit = re.search(r"UNIT\s*(?:NO\.?\s*)?(\d+)", (subdivision or "").upper())

    def matches(r):
        toks = re.sub(r"[^A-Z0-9 ]", " ", str(r.get("legal_1", "")).upper()).split()
        if not all(w in toks for w in name):
            return False
        return not (unit and unit.group(1) not in toks)

    cand = [r for r in deeds if matches(r)]
    if not cand:
        return None
    def recent(rs: list[dict]) -> dict:
        return max(rs, key=lambda r: str(r.get("rec_date") or ""))
    grantee = [r for r in cand if str(r.get("party_code", "")).upper() == "R"]
    return recent(grantee) if grantee else recent(cand)


def _pick_plat_page(rows: list[dict], subdivision: str) -> str | None:
    """Resolve a plat page from a book-only plat search by matching the subdivision
    (name + unit number). Uses the shared _subdiv_name (which strips DOR's "SUB"
    abbreviation — matching on it made recorded legals like "IDLEWILD UNIT NO 2" fail)."""
    name = _subdiv_name(subdivision)
    if not name:
        return None
    unit = re.search(r"UNIT\s*(?:NO\.?\s*)?(\d+)", (subdivision or "").upper())
    for r in rows:
        toks = re.sub(r"[^A-Z0-9 ]", " ", str(r.get("legal_1", "")).upper()).split()
        if all(w in toks for w in name) and not (unit and unit.group(1) not in toks):
            return str(r.get("page"))
    return None


def _save_pdf(images: list[bytes], out_path: pathlib.Path) -> str | None:
    """Combine captured PNG page images into a single multi-page PDF."""
    try:
        from PIL import Image
    except Exception:
        return None
    pages = []
    for raw in images:
        try:
            pages.append(Image.open(io.BytesIO(raw)).convert("RGB"))
        except Exception:
            continue
    if not pages:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(out_path, "PDF", save_all=True, append_images=pages[1:])
    return out_path.name


# ---------------------------------------------------------------------------------
# Tyler "Official Records Self-Service" (Eagle Recorder) driver
# ---------------------------------------------------------------------------------
class _Tyler:
    """One headless session against a Tyler Self-Service Official-Records portal.

    Flow: land -> accept disclaimer -> Document Search -> fill Book/Page (deed) or
    Platted-Legal Subdivision (plat) -> #searchButton -> results carry
    /web/document/<id>?search=<sid> -> the doc detail exposes a free
    /web/document-image-pdf/<id>/<guid>/<name>.pdf which we fetch with the session cookies.
    """

    def __init__(self, page, base: str, timeout_ms: int = 60000):
        from urllib.parse import urlsplit
        self.pg = page
        self.base = base.rstrip("/") + "/"
        s = urlsplit(self.base)
        self.host = f"{s.scheme}://{s.netloc}"
        self.sid = ""
        page.set_default_timeout(timeout_ms)

    def open_search(self):
        pg = self.pg
        pg.goto(self.base, wait_until="domcontentloaded")
        pg.wait_for_timeout(3000)
        b = pg.locator("a:has-text('I accept'), button:has-text('I accept'), "
                       "a:has-text('Accept'), input[value*='ccept']")
        if b.count() and b.first.is_visible():
            b.first.click()
            pg.wait_for_timeout(2500)
        link = pg.locator("a:has-text('Document Search and Copies'), "
                          "a:has-text('Document Search')")
        if link.count() and link.first.is_visible():
            link.first.click()
            pg.wait_for_timeout(3500)
        m = re.search(r"/web/search/(\w+)", pg.url)
        if not m:
            raise RuntimeError(f"tyler: search page not reached ({pg.url})")
        self.sid = m.group(1)

    def _fill(self, field_id: str, value: str):
        el = self.pg.query_selector("#" + field_id)
        if el:
            el.fill(str(value))

    def _run_search(self):
        self.pg.wait_for_selector("#searchButton", timeout=30000)
        self.pg.query_selector("#searchButton").click(force=True)
        self.pg.wait_for_timeout(6500)

    def search_document_number(self, doc_number: str):
        self._fill("field_DocumentNumberID", doc_number)
        self._run_search()

    def search_book_page(self, book: str, page: str):
        self._fill("field_BookPageID_DOT_Book", book)
        self._fill("field_BookPageID_DOT_Page", page)
        self._run_search()

    def search_subdivision(self, subdivision: str, lot: str = "", block: str = ""):
        self._fill("field_PlattedLegalID_DOT_Subdivision", subdivision)
        if lot:
            self._fill("field_PlattedLegalID_DOT_Lot", lot)
        if block:
            self._fill("field_PlattedLegalID_DOT_Block", block)
        self._run_search()

    def first_pdf(self) -> bytes | None:
        """From the current results page, open the first document and fetch its PDF."""
        m = re.search(r"/web/document/(DOC\w+)\?search=" + re.escape(self.sid),
                      self.pg.content())
        if not m:
            return None
        docid = m.group(1)
        self.pg.goto(f"{self.host}/web/document/{docid}?search={self.sid}",
                     wait_until="domcontentloaded")
        self.pg.wait_for_timeout(3000)
        html = self.pg.content()
        pm = (re.search(r"/web/document-image-pdf/[^\"'?\s]+\.pdf\?[^\"'\s]*", html)
              or re.search(r"/web/document/servepdf/[^\"'?\s]+", html))
        if not pm:
            return None
        r = self.pg.context.request.get(self.host + pm.group(0).replace("&amp;", "&"))
        body = r.body()
        return body if body[:4] == b"%PDF" else None


def _fetch_tyler(url, out_dir, plat, deed, headless, result):
    from playwright.sync_api import sync_playwright
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=_LAUNCH_ARGS)
        ctx = browser.new_context(ignore_https_errors=True)
        try:
            # DEED. Modern FL clerks index by recorded DOCUMENT / instrument number
            # (DOR CLERK_NO1); older records use an OR Book/Page (DOR OR_BOOK1/OR_PAGE1).
            # Prefer the document number, fall back to book/page.
            docno = str((deed or {}).get("doc_number") or "").strip()
            if not docno.strip("0"):   # all-zero / blank instrument number is not a real ref
                docno = ""
            book = str((deed or {}).get("book") or "").strip()
            page = str((deed or {}).get("page") or "").strip()
            if docno:
                result["deed_ref"] = f"Doc# {docno} (county tax roll sale)"
                drv = _Tyler(ctx.new_page(), url)
                drv.open_search()
                drv.search_document_number(docno)
                pdf = drv.first_pdf()
                if pdf:
                    out = out_dir / f"Deed_DOC{docno}.pdf"
                    out.write_bytes(pdf)
                    result["deed"] = out.name
            if not result["deed"] and book and page:
                result["deed_ref"] = f"OR {book}/{page} (county tax roll sale)"
                drv = _Tyler(ctx.new_page(), url)
                drv.open_search()
                drv.search_book_page(book, page)
                pdf = drv.first_pdf()
                if pdf:
                    out = out_dir / f"Deed_OR{book}_{page}.pdf"
                    out.write_bytes(pdf)
                    result["deed"] = out.name

            # PLAT — only via a deterministic Plat Book/Page. A bare subdivision search
            # returns every document that references the subdivision (deeds, mortgages, …),
            # and blindly saving the first hit risks filing a non-plat as "the plat" (the
            # same wrong-document trap we fixed for deeds). If there is no plat book/page,
            # leave the one-click clerk link as the fallback rather than guess.
            if plat and plat.get("book") and plat.get("page"):
                drv = _Tyler(ctx.new_page(), url)
                drv.open_search()
                drv.search_book_page(str(plat["book"]), str(plat["page"]))
                pdf = drv.first_pdf()
                if pdf:
                    out = out_dir / f"Plat_PB{plat['book']}_PG{plat['page']}.pdf"
                    out.write_bytes(pdf)
                    result["plat"] = out.name
        finally:
            browser.close()


# ---------------------------------------------------------------------------------
# Manatee "Public Records Hub" — pure HTTP (no browser)
# ---------------------------------------------------------------------------------
_MANATEE_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def _fetch_manatee(base, out_dir, plat, deed, result):
    """Manatee serves search results as server-rendered HTML (DisplayInstrument/<id> links)
    and each document page as a free JPEG (InstrumentResultJpgAsync). Fetch the pages for the
    matching instrument and combine them into a PDF. No Playwright required."""
    import io as _io

    import requests
    from PIL import Image
    requests.packages.urllib3.disable_warnings()  # county cert chain is often incomplete
    s = requests.Session()
    s.headers.update(_MANATEE_UA)
    s.verify = False
    base = base.rstrip("/")
    out_dir.mkdir(parents=True, exist_ok=True)

    def _pages_to_pdf(iid, out_path):
        dh = s.get(f"{base}/OfficialRecords/DisplayInstrument/{iid}", timeout=30).text
        nums = sorted(set(int(x) for x in re.findall(
            r"InstrumentResultJpgAsync\?instrumentId=" + re.escape(iid) + r"&(?:amp;)?page=(\d+)", dh)))
        imgs = []
        for n in nums:
            r = s.get(f"{base}/OfficialRecords/DisplayInstrument/InstrumentResultJpgAsync"
                      f"?instrumentId={iid}&page={n}", timeout=30)
            body = r.content
            if r.headers.get("content-type", "").lower().startswith("image") and body[:2] == b"\xff\xd8":
                imgs.append(Image.open(_io.BytesIO(body)).convert("RGB"))
        if not imgs:
            return None
        imgs[0].save(out_path, "PDF", save_all=True, append_images=imgs[1:])
        return out_path.name

    def _id_by_instrument(num):
        h = s.get(f"{base}/OfficialRecords/Search/InstrumentNumber"
                  f"?instrumentNumber={num}&page=1&pageSize=50", timeout=30).text
        ids = re.findall(r"/OfficialRecords/DisplayInstrument/(\d+)", h)
        return ids[0] if ids else None

    def _id_by_book_page(book, page):
        # The book/page route filters by book+page; use it only when it resolves to a single
        # unambiguous document — never guess among several (avoids filing a wrong instrument).
        h = s.get(f"{base}/OfficialRecords/Search/InstrumentBookPage/{book}/{page}/1/50",
                  timeout=30).text
        ids = list(dict.fromkeys(re.findall(r"/OfficialRecords/DisplayInstrument/(\d+)", h)))
        return ids[0] if len(ids) == 1 else None

    # DEED — instrument number (DOR CLERK_NO1) first, then OR book/page.
    docno = str((deed or {}).get("doc_number") or "").strip()
    if not docno.strip("0"):
        docno = ""
    book = str((deed or {}).get("book") or "").strip()
    page = str((deed or {}).get("page") or "").strip()
    iid = None
    if docno:
        result["deed_ref"] = f"Instrument {docno} (county tax roll sale)"
        iid = _id_by_instrument(docno)
    if not iid and book and page:
        result["deed_ref"] = f"OR {book}/{page} (county tax roll sale)"
        iid = _id_by_book_page(book, page)
    if iid:
        fname = f"Deed_INSTR{docno}.pdf" if docno else f"Deed_OR{book}_{page}.pdf"
        name = _pages_to_pdf(iid, out_dir / fname)
        if name:
            result["deed"] = name

    # PLAT — deterministic Plat Book/Page only.
    if plat and plat.get("book") and plat.get("page"):
        pid = _id_by_book_page(str(plat["book"]), str(plat["page"]))
        if pid:
            name = _pages_to_pdf(pid, out_dir / f"Plat_PB{plat['book']}_PG{plat['page']}.pdf")
            if name:
                result["plat"] = name


# ---------------------------------------------------------------------------------
# Volusia in-house Official Records viewer (CDP-captured PDF)
# ---------------------------------------------------------------------------------
class _Volusia:
    """Search Volusia OR by instrument number or book/page, then capture the free PDF
    that its viewer loads (load_Redact.aspx) via a CDP Fetch interception — Chromium's
    PDF plugin swallows the response, so a normal handler can't read the bytes."""

    def __init__(self, ctx, base: str, timeout_ms: int = 45000):
        self.ctx = ctx
        self.base = base.rstrip("/") + "/"
        self.timeout = timeout_ms
        self.captured: dict = {}
        ctx.on("page", self._wire)          # wire the viewer tab the moment it opens
        self.pg = ctx.new_page()
        self._wire(self.pg)
        self.pg.set_default_timeout(timeout_ms)

    def _wire(self, page):
        try:
            c = self.ctx.new_cdp_session(page)
        except Exception:
            return
        c.send("Fetch.enable",
               {"patterns": [{"urlPattern": "*load_Redact*", "requestStage": "Response"}]})

        def on_paused(ev):
            rid = ev["requestId"]
            try:
                r = c.send("Fetch.getResponseBody", {"requestId": rid})
                body = base64.b64decode(r["body"]) if r.get("base64Encoded") else r["body"].encode()
                if body[:4] == b"%PDF":
                    self.captured["body"] = body
            except Exception:
                pass
            finally:
                with contextlib.suppress(Exception):
                    c.send("Fetch.continueRequest", {"requestId": rid})

        c.on("Fetch.requestPaused", on_paused)

    def open(self):
        self.pg.goto(self.base, wait_until="domcontentloaded")
        self.pg.wait_for_timeout(2000)
        b = self.pg.locator("#accept, input[value*='ccept']")
        if b.count() and b.first.is_visible():
            b.first.click()
        self.pg.wait_for_load_state("networkidle")
        self.pg.wait_for_timeout(1500)

    def _reset(self):
        # a fresh search form (the session's disclaimer flag is already set)
        self.pg.goto(self.base + "inquiry.aspx", wait_until="domcontentloaded")
        self.pg.wait_for_timeout(1200)

    def _capture(self, anchor):
        """Click a results-grid PDF icon and capture the PDF the viewer loads. The viewer
        only requests the document (load_Redact.aspx) once its tab is focused — a background
        headless tab never initialises the PDF embed — so bring it to front and then poll."""
        self.captured.clear()
        with self.ctx.expect_page() as newp:
            anchor.click()
        vp = newp.value
        try:
            vp.bring_to_front()
            vp.wait_for_load_state("networkidle")
        except Exception:
            pass
        for _ in range(20):
            if self.captured.get("body"):
                break
            vp.wait_for_timeout(1000)
        with contextlib.suppress(Exception):
            vp.close()
        return self.captured.get("body")

    def _submit(self):
        self.pg.click("#search")
        self.pg.wait_for_load_state("networkidle")
        self.pg.wait_for_timeout(2500)

    def by_instrument(self, instrument: str):
        """An instrument number is unique — the result rows all point to the one document."""
        self._reset()
        self.pg.fill("#instrument", instrument)
        self._submit()
        a = self.pg.query_selector("a:has(img[src*='pdficon'])")
        return self._capture(a) if a else None

    def by_book_page(self, book: str, page: str):
        """A book/page search returns that book starting AT the page and continuing, so we
        must click the icon on the row whose Book/Page column is EXACTLY book/page — clicking
        the first row blindly would grab a later, unrelated document."""
        self._reset()
        self.pg.fill("#book", book)
        self.pg.fill("#tb_page", page)
        self._submit()
        want = f"{book}/{page}".replace(" ", "")
        for tr in self.pg.query_selector_all("tr"):
            cells = tr.query_selector_all("td")
            if len(cells) < 4:
                continue
            bp = (cells[3].inner_text() or "").strip().replace(" ", "")  # Book/Page column
            if bp == want:
                a = tr.query_selector("a:has(img[src*='pdficon'])")
                if a:
                    return self._capture(a)
        return None


def _fetch_volusia(url, out_dir, plat, deed, headless, result):
    from playwright.sync_api import sync_playwright
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=_LAUNCH_ARGS)
        ctx = browser.new_context(ignore_https_errors=True)
        try:
            drv = _Volusia(ctx, url)
            drv.open()
            # DEED — instrument number (DOR CLERK_NO1) first, then OR book/page.
            docno = str((deed or {}).get("doc_number") or "").strip()
            if not docno.strip("0"):
                docno = ""
            book = str((deed or {}).get("book") or "").strip()
            page = str((deed or {}).get("page") or "").strip()
            if docno:
                result["deed_ref"] = f"Instrument {docno} (county tax roll sale)"
                pdf = drv.by_instrument(docno)
                if pdf:
                    out = out_dir / f"Deed_INSTR{docno}.pdf"
                    out.write_bytes(pdf)
                    result["deed"] = out.name
            if not result["deed"] and book and page:
                result["deed_ref"] = f"OR {book}/{page} (county tax roll sale)"
                pdf = drv.by_book_page(book, page)
                if pdf:
                    out = out_dir / f"Deed_OR{book}_{page}.pdf"
                    out.write_bytes(pdf)
                    result["deed"] = out.name
            # PLAT — deterministic Plat Book/Page only (never guess from a name search).
            if plat and plat.get("book") and plat.get("page"):
                pdf = drv.by_book_page(str(plat["book"]), str(plat["page"]))
                if pdf:
                    out = out_dir / f"Plat_PB{plat['book']}_PG{plat['page']}.pdf"
                    out.write_bytes(pdf)
                    result["plat"] = out.name
        finally:
            browser.close()


# ---------------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------------
def _fetch_once(url, out_dir, plat, deed, headless, result):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=_LAUNCH_ARGS)
        ctx = browser.new_context(ignore_https_errors=True)
        try:
            # PLAT — by Plat Book/Page. If the page is unknown (DOR legal often omits it),
            # search the book alone and resolve the page from the subdivision.
            if plat and plat.get("book"):
                drv = _NewVision(ctx.new_page())
                drv.open(url)
                book, page = str(plat["book"]), plat.get("page")
                if not page and plat.get("subdivision"):
                    drv.search_book_page(book, "", "P")
                    page = _pick_plat_page(drv.search_results, plat["subdivision"])
                    drv.open(url)  # reload to a clean landing before the exact search
                if page:
                    drv.search_plat(book, page)
                    if drv.open_first_result():
                        imgs = drv.capture_pages()
                        if imgs:
                            result["plat"] = _save_pdf(
                                imgs, out_dir / f"Plat_PB{book}_PG{page}.pdf")

            # DEED. Preferred: an authoritative OR Book/Page from the county tax roll
            # (parcel SALE_1). Fallback: owner-name search + vesting-deed pick from JSON.
            if deed:
                drv = _NewVision(ctx.new_page())
                drv.open(url)
                book = str(deed.get("book") or "").strip()
                page = str(deed.get("page") or "").strip()
                if book and page:
                    result["deed_ref"] = f"OR {book}/{page} (county tax roll sale)"
                elif deed.get("owner"):
                    rows = drv.search_party(deed["owner"])
                    row = _pick_deed(rows, deed.get("subdivision", ""))
                    if row and row.get("book") and row.get("page"):
                        book, page = str(row["book"]), str(row["page"])
                        result["deed_ref"] = (f"OR {book}/{page} "
                                              f"{row.get('rec_date', '')[:10]} "
                                              f"{row.get('doc_type', '')}").strip()
                    drv.open(url)  # reload to a clean landing before the Book/Page search
                if book and page:
                    drv.search_book_page(book, page, "O")
                    if drv.open_first_result():
                        imgs = drv.capture_pages()
                        if imgs:
                            result["deed"] = _save_pdf(
                                imgs, out_dir / f"Deed_OR{book}_{page}.pdf")
        finally:
            browser.close()


def fetch_documents(county_fips: str, out_dir: pathlib.Path,
                    plat: dict | None = None, deed: dict | None = None,
                    headless: bool = True) -> dict:
    """Retrieve plat and/or deed images for a Polk (NewVision) parcel.

    plat: {"book","page"}   deed: {"owner","subdivision"}
    Returns {"plat": filename|None, "deed": filename|None, "deed_ref": str, "error": str}.
    """
    result = {"plat": None, "deed": None, "deed_ref": "", "error": ""}
    # Manatee needs no browser — handle it before the Playwright gate.
    ma_url = MANATEE_PORTALS.get(county_fips)
    if ma_url:
        try:
            _fetch_manatee(ma_url, out_dir, plat, deed, result)
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"[:200]
        return result
    if not available():
        result["error"] = "no adapter / playwright unavailable"
        return result
    nv_url = NEWVISION_PORTALS.get(county_fips)
    ty_url = TYLER_PORTALS.get(county_fips)
    vo_url = VOLUSIA_PORTALS.get(county_fips)
    if not nv_url and not ty_url and not vo_url:
        result["error"] = "no adapter / playwright unavailable"
        return result
    # Headless Chromium occasionally dies mid-navigation; retry ONLY that (a deterministic
    # failure won't fix itself and would just double the runtime).
    last = ""
    for _ in range(2):
        try:
            if ty_url:
                _fetch_tyler(ty_url, out_dir, plat, deed, headless, result)
            elif vo_url:
                _fetch_volusia(vo_url, out_dir, plat, deed, headless, result)
            else:
                _fetch_once(nv_url, out_dir, plat, deed, headless, result)
            return result
        except Exception as e:
            last = f"{type(e).__name__}: {e}"[:200]
            if "TargetClosed" not in type(e).__name__ and "closed" not in str(e).lower():
                break
    result["error"] = last
    return result
