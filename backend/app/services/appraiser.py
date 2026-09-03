"""County Property Appraiser retrieval.

Downloads the official Property Record Card (PRC) PDF and reads the parcel's full legal —
including the plat Book/Page that the FL DOR statewide legal truncates (~30 chars) for
long subdivision names. That plat Book/Page is what lets the plat auto-download when the
tax-roll legal alone can't.

Appraiser sites bot-block datacenter/VPN IPs, so this only works when the host is reachable
from the machine (e.g. a per-domain split-tunnel route). Everything is best-effort: if the
site isn't reachable we return {} and the caller keeps the DOR-derived summary + deep-link.

Currently wired: Polk (NewVision CAMA at polkflpa.gov).
"""
from __future__ import annotations

import pathlib
import re

import requests

# Per-county appraiser base URL. Extend as other counties are split-tunnelled / added.
APPRAISER_SITES: dict[str, str] = {
    "12105": "https://www.polkflpa.gov",
}
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125 Safari/537.36")
_LAUNCH_ARGS = ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                "--ignore-certificate-errors"]


def available(county_fips: str) -> bool:
    return county_fips in APPRAISER_SITES


def _cama_url(base: str, strap: str) -> str:
    return f"{base}/CamaDisplay.aspx?OutputMode=Display&SearchType=RealEstate&ParcelID={strap}"


def _prc_pdf_url(base: str, strap: str) -> str:
    return f"{base}/PRCReport/viewPRC.aspx?strap={strap}&pdf=true"


def _worksheet_pdf_url(base: str, strap: str) -> str:
    # Parcel Mapping Worksheet — a survey-relevant PDF (parcel map, dimensions, adjoiners).
    return f"{base}/MappingWorksheetPDF.aspx?strap={strap}"


def _plat_ref_from_html(html: str):
    """Pull the plat Book/Page from the appraiser's legal text, e.g. '... PB 89 PG 6 ...'."""
    m = re.search(r"\bP\.?\s?B\.?\s*(\d+)\s*[,/]?\s*P(?:G|AGE)?\.?\s*(\d+)", html or "", re.I)
    return (m.group(1), m.group(2)) if m else (None, None)


def fetch(county_fips: str, strap: str, out_dir: pathlib.Path) -> dict:
    """Return {'doc': filename|None, 'plat_book', 'plat_page'} for the parcel.

    'doc' is the saved official Property Record Card PDF; plat_book/page come from the
    appraiser's full (untruncated) legal. Best-effort — returns {} if unreachable.
    """
    result: dict = {"doc": None, "docs": [], "plat_book": None, "plat_page": None}
    base = APPRAISER_SITES.get(county_fips)
    if not base or not strap:
        return result
    try:
        s = requests.Session()
        s.headers.update({"User-Agent": _UA})
        s.get(f"{base}/", timeout=12)  # establish cookies; also a reachability probe
        html = s.get(_cama_url(base, strap), timeout=25).text
        result["plat_book"], result["plat_page"] = _plat_ref_from_html(html)
        # Parcel Mapping Worksheet — a direct PDF by parcel ID (no browser needed).
        try:
            r = s.get(_worksheet_pdf_url(base, strap), timeout=30)
            if r.ok and r.content[:4] == b"%PDF" and len(r.content) > 2000:
                (out_dir / "Property_MappingWorksheet.pdf").write_bytes(r.content)
                result["docs"].append("Property_MappingWorksheet.pdf")
        except Exception:
            pass
    except Exception:
        return result

    # Official Property Record Card PDF (the report exports a PDF via a browser download).
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return result
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(headless=True, args=_LAUNCH_ARGS)
            ctx = br.new_context(ignore_https_errors=True, accept_downloads=True)
            pg = ctx.new_page()
            pg.set_default_timeout(40000)
            try:
                with pg.expect_download(timeout=30000) as di:
                    pg.goto(_prc_pdf_url(base, strap), wait_until="commit")
                out = out_dir / "Property_Appraiser.pdf"
                di.value.save_as(str(out))
                if out.stat().st_size > 2000 and out.read_bytes()[:4] == b"%PDF":
                    result["doc"] = out.name
            finally:
                br.close()
    except Exception:
        pass
    return result
