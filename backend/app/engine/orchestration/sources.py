"""Source adapter framework — one pluggable fetcher per document step.

This replaces the monolithic if/elif chain in the old ``run_research``.  Every
document type (parcel, appraiser, deed, plat, ...) has a ``SourceAdapter``:

  - ``fetch(ctx, docs_dir)``   → ``FetchedSource`` on success (even "nothing found")
  - ``fallback(ctx, ...)``     → what the step shows when ``fetch`` raised

Failures never escape ``steps.build_steps``: the runner catches anything raised,
classifies it (``blocked`` / ``broken`` / ``retryable``), falls back to the
deep-link step, and attaches a structured ``ErrorInfo``.  ``FetchedSource.status``
stays in the frozen vocabulary ``ok / link / empty``; the *why* of a fallback
rides in ``source_outcome`` + ``error`` (engine-additive fields).

The registry (``ADAPTERS``) is the seam for testing and for new sources: register
a fake/no-network adapter during tests, or add a new county source later without
touching the runner.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests

from app.engine.contracts import Confidence, ErrorInfo, SourceOutcome, StepStatus

GLO = "https://glorecords.blm.gov/"


class SourceError(Exception):
    """Raised by an adapter when the source is unreachable/poisoned.

    ``outcome`` classifies *why* (blocked/broken/retryable); the steps builder
    converts it to a fallback link step + structured error.
    """

    def __init__(self, outcome: SourceOutcome, code: str = "", message: str = "",
                 retryable: bool = False):
        super().__init__(message or code or outcome.value)
        self.outcome = outcome
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass
class FetchedSource:
    """Canonical result of one adapter call — the input to step assembly."""

    status: StepStatus = StepStatus.link
    data: object = None
    summary: str = ""
    link: str = ""
    link_label: str = ""
    source_url: str = ""
    downloaded: list[str] = field(default_factory=list)
    saved_file: str | None = None
    records: list[dict] = field(default_factory=list)   # manifest/audit entries
    warnings: list[str] = field(default_factory=list)
    confidence: Confidence | None = None
    # Ambiguous-but-present data that needs human eyeballs (e.g. a parcel matched
    # via a buffered point with no address confirmation). Step assembly maps this
    # to SourceOutcome.manual_review; the frozen status stays as-designed
    # (typically `link`) so old frontends render it without change.
    manual_review: bool = False

    # --- frozen POC parcel-step extras (only the parcel adapter sets these) ---
    situs: str | None = None
    land_sqft: float | None = None
    land_acres: float | None = None
    address_match: bool | None = None


class SourceAdapter:
    """Interface every document-step adapter implements."""

    key: str = ""

    def fetch(self, ctx, docs_dir) -> FetchedSource:  # pragma: no cover - abstract
        raise NotImplementedError

    def fallback(self, ctx, error: ErrorInfo | None = None) -> FetchedSource:
        return FetchedSource(link="", link_label="", summary="")


# --------------------------------------------------------------------------- helpers

def classify_exception(e: Exception) -> tuple[SourceOutcome, str, str, bool]:
    """Map an exception to (outcome, code, message, retryable)."""
    if isinstance(e, SourceError):
        return e.outcome, e.code, e.message, e.retryable
    if isinstance(e, requests.exceptions.HTTPError):
        code = getattr(e.response, "status_code", None)
        if code in (401, 403, 406, 429):
            return (SourceOutcome.blocked, f"HTTP_{code}",
                    f"Source returned HTTP {code} (WAF/bot/geo block — opens in a browser).",
                    False)
        if code in (404, 410):
            return (SourceOutcome.broken, f"HTTP_{code}",
                    f"Source returned HTTP {code} — the URL is wrong or moved.", False)
        return (SourceOutcome.broken, f"HTTP_{code or '?'}",
                f"Source returned HTTP {code} — server error.", True)
    if isinstance(e, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return (SourceOutcome.retryable, "CONNECTION_FAILED",
                "Source timed out or connection was reset (network/firewall?).", True)
    return (SourceOutcome.retryable, "ADAPTER_ERROR", str(e)[:300], True)


# --------------------------------------------------------------- parcel

class ParcelAdapter(SourceAdapter):
    key = "parcel"

    def fetch(self, ctx, docs_dir) -> FetchedSource:
        p = ctx.parcel
        ok = (ctx.parcel_ok and p.get("method") == "arcgis-rest" and bool(p.get("parcels")))
        if not ok:
            fs = self.fallback(ctx, error=ErrorInfo(
                code="PARCEL_NOT_FOUND",
                message="No confident parcel match for this address.",
                retryable=False))
            # A polygon WAS returned but only via a buffered point (geocoder
            # landing on the street centerline) with no address confirmation.
            # The data is present yet ambiguous — flag it for human review
            # instead of hiding it behind a plain reference link.
            if bool(p.get("parcels")) and p.get("buffered_match"):
                fs.manual_review = True
                fs.summary = "Parcel found via a buffered match — review the boundary and ID before using."
                fs.source_url = p.get("source") or ctx.appraiser_url
                fs.warnings.append(
                    "Parcel matched with a 40 m buffer and no address confirmation — "
                    "verify the parcel boundary and ID before relying on this data.")
            return fs

        sqft, acres = p.get("land_sqft"), p.get("land_acres")
        situs = p.get("situs", "")
        area_txt = (f" · Lot {int(sqft):,} sq ft" + (f" ({acres} ac)" if acres else "")
                    if sqft else "")
        records: list[dict] = []
        fn = None
        try:
            from app.services import downloader
            fn = downloader.save_parcel_record(ctx.folder, p, ctx.doc_meta)
        except Exception:
            fn = None
        if fn:
            records.append({"file": f"documents/{fn}",
                            "source": p.get("source", ctx.appraiser_url)})
        from app.services import parcel as parcel_svc
        return FetchedSource(
            status=StepStatus.ok,
            data=p,
            summary=(f"Parcel ID: {ctx.parcel_id}" if ctx.parcel_id
                     else parcel_svc.summarize(p)) + area_txt,
            link=ctx.appraiser_url,
            link_label="Open County Property Appraiser",
            source_url=p.get("source") or ctx.appraiser_url,
            saved_file="parcel.json",
            downloaded=[fn] if fn else [],
            records=records,
            situs=situs,
            land_sqft=sqft,
            land_acres=acres,
            address_match=True,
        )

    def fallback(self, ctx, error: ErrorInfo | None = None) -> FetchedSource:
        return FetchedSource(
            status=StepStatus.link,
            summary="Parcel record not found for this address — open the County "
                    "Property Appraiser to look it up.",
            link=ctx.appraiser_url,
            link_label="Open County Property Appraiser",
            source_url=ctx.appraiser_url,
            saved_file="parcel.json",
        )


# --------------------------------------------------------------- appraiser

class AppraiserAdapter(SourceAdapter):
    key = "appraiser"

    def _fetch(self, ctx, docs_dir) -> dict | None:
        if ctx.appr is None:
            return None
        return ctx.appr

    def fetch(self, ctx, docs_dir) -> FetchedSource:
        got = ctx.parcel_ok and bool(ctx.parcel.get("parcels"))
        appr = ctx.appr or {}
        records: list[dict] = []
        files: list[str] = []
        if appr.get("doc"):
            files.append(appr["doc"])
            records.append({"file": f"documents/{appr['doc']}", "source": ctx.appraiser_url})
        for extra in appr.get("docs") or []:
            if extra not in files:
                files.append(extra)
                records.append({"file": f"documents/{extra}", "source": ctx.appraiser_url})
        if got:
            fn = None
            try:
                from app.services import downloader
                fn = downloader.save_appraiser_record(
                    ctx.folder, ctx.parcel["parcels"][0], ctx.doc_meta, ctx.appraiser_url)
            except Exception:
                fn = None
            if fn:
                records.append({"file": f"documents/{fn}", "source": ctx.appraiser_url})
                files.append(fn)
        summary = ("Owner, values & last sale from the county tax roll"
                   if got else "Open the County Property Appraiser")
        if got and appr.get("doc"):
            summary = "Official Property Record Card (county appraiser)"
        return FetchedSource(
            status=StepStatus.ok if got else StepStatus.link,
            data=ctx.parcel.get("parcels", [{}])[0] if got else None,
            summary=summary,
            link=ctx.appraiser_url,
            link_label="Open County Property Appraiser",
            source_url=ctx.appraiser_url,
            downloaded=files,
            saved_file="parcel.json" if got and files else None,
            records=records,
        )

    def fallback(self, ctx, error: ErrorInfo | None = None) -> FetchedSource:
        return FetchedSource(
            status=StepStatus.link,
            summary="Open the County Property Appraiser",
            link=ctx.appraiser_url,
            link_label="Open County Property Appraiser",
            source_url=ctx.appraiser_url,
        )


# --------------------------------------------------------------- clerk (deed/plat)

# --- helpers ported verbatim from the POC orchestrator (shared by deed/plat) ---

def _attr(attrs: dict, *needles: str) -> str:
    for k, v in (attrs or {}).items():
        kl = k.lower().replace("_", "")
        if any(n in kl for n in needles) and v not in (None, "", " ", 0):
            return str(v).strip()
    return ""


def _field(attrs: dict, name: str) -> str:
    for k, v in (attrs or {}).items():
        if k.upper() == name and v not in (None, "", " "):
            return str(v).strip()
    return ""


def _numref(value: str) -> str:
    v = (value or "").strip()
    return v if (any(c.isdigit() for c in v) and v.strip("0 ")) else ""


def _plat_ref(legal: str):
    legal = legal or ""
    mb = (re.search(r"\bP\.?\s?B\.?\s*(\d+)", legal, re.I)
          or re.search(r"PLAT\s*BOOK\s*(\d+)", legal, re.I))
    mp = re.search(r"\bP(?:G|AGE)\.?\s*(\d+)", legal, re.I)
    return (mb.group(1) if mb else None, mp.group(1) if mp else None)


def _or_ref(legal: str):
    m = re.search(r"\bO\.?\s?R\.?\s*(?:BOOK\s*)?(\d{2,6})\s*"
                  r"(?:/\s*(\d{1,6})|(?:PG|PAGE|P)\.?\s*(\d{1,6}))", (legal or ""), re.I)
    if not m:
        return (None, None)
    return (m.group(1), m.group(2) or m.group(3))


def _subdivision(legal: str) -> str:
    head = re.split(r"\b(BLK|BLOCK|LOT|LT|PB|P\s?B|PLAT|SEC|BEG)\b",
                    (legal or "").upper())[0]
    return " ".join(head.split()[:6]).strip()


def _hint_str(ctx) -> str:
    return ", ".join(list(ctx.parcel_hints)[:4])


def _clerk_url(ctx, doc_key: str) -> str:
    return (ctx.clerk_ref.get("plat_search", ctx.clerk_ref["official_records_search"])
            if doc_key == "plat" else ctx.clerk_ref["official_records_search"])


# --- shared scrape (cached per context so deed + plat fetch exactly once) ------

def _scrape_documents(ctx, docs_dir) -> dict:
    """Run the county clerk browser scrape once per context; cache the result."""
    cached = getattr(ctx, "_clerk_docs", None)
    if cached is not None:
        return cached
    docs: dict = {}
    try:
        from app.services import appraiser as appraiser_svc
        from app.services import clerk_scraper

        if appraiser_svc.available(ctx.county_fips) and ctx.parcel_id and ctx.appr is None:
            try:
                ctx.appr = appraiser_svc.fetch(
                    ctx.county_fips, ctx.parcel_id, docs_dir)
            except Exception:
                ctx.appr = {}

        if (ctx.parcel_ok and clerk_scraper.has_adapter(ctx.county_fips)
                and ctx.parcel.get("parcels")):
            attrs = ctx.parcel["parcels"][0]
            legal = _attr(attrs, "slegal", "legal")
            owner = _attr(attrs, "ownname", "owner")
            pb, pg = _plat_ref(legal)
            appr = ctx.appr or {}
            if not pb and appr.get("plat_book"):
                pb, pg = appr["plat_book"], appr.get("plat_page")
            subdiv = _subdivision(legal)
            plat_arg = {"book": pb, "page": pg, "subdivision": subdiv} if pb else None
            ob, op = _numref(_field(attrs, "OR_BOOK1")), _numref(_field(attrs, "OR_PAGE1"))
            cn = _numref(_field(attrs, "CLERK_NO1"))
            if not (ob and op):
                lb, lp = _or_ref(legal)
                if lb and lp:
                    ob, op = lb, lp
            if cn or (ob and op):
                deed_arg = {"doc_number": cn, "book": ob, "page": op}
            elif owner:
                deed_arg = {"owner": owner, "subdivision": subdiv}
            else:
                deed_arg = None
            if plat_arg or deed_arg:
                try:
                    docs = clerk_scraper.fetch_documents(
                        ctx.county_fips, docs_dir, plat=plat_arg, deed=deed_arg)
                except Exception:
                    docs = {}
    except Exception:
        docs = {}
    ctx._clerk_docs = docs
    return docs


class DeedAdapter(SourceAdapter):
    key = "deed"

    def fetch(self, ctx, docs_dir) -> FetchedSource:
        doc_url = _clerk_url(ctx, "deed")
        fetched = _scrape_documents(ctx, docs_dir).get("deed")
        summary = "Open Clerk Official Records — Deed — subject parcel"
        records: list[dict] = []
        downloaded: list[str] = []
        if ctx.parcel_hints:
            summary += f"  ·  hints: {_hint_str(ctx)}"
        if fetched:
            ref = _scrape_documents(ctx, docs_dir).get("deed_ref", "")
            summary = (f"Auto-fetched deed {ref} — verify grantee & legal "
                       f"match the subject parcel").strip()
            downloaded = [fetched]
            records = [{"file": f"documents/{fetched}", "source": doc_url}]
        return FetchedSource(
            status=StepStatus.ok if fetched else StepStatus.link,
            data=ctx.clerk_ref,
            summary=summary,
            link=doc_url,
            link_label="Open Clerk Official Records — Deed — subject parcel",
            source_url=doc_url,
            saved_file="clerk_search_refs.json",
            downloaded=downloaded,
            records=records,
            confidence=Confidence.medium if fetched else None,
        )

    def fallback(self, ctx, error: ErrorInfo | None = None) -> FetchedSource:
        doc_url = _clerk_url(ctx, "deed")
        summary = "Open Clerk Official Records — Deed — subject parcel"
        if ctx.parcel_hints:
            summary += f"  ·  hints: {_hint_str(ctx)}"
        return FetchedSource(
            status=StepStatus.link,
            data=ctx.clerk_ref,
            summary=summary,
            link=doc_url,
            link_label="Open Clerk Official Records — Deed — subject parcel",
            source_url=doc_url,
            saved_file="clerk_search_refs.json",
        )


class PlatAdapter(SourceAdapter):
    key = "plat"

    def fetch(self, ctx, docs_dir) -> FetchedSource:
        doc_url = _clerk_url(ctx, "plat")
        fetched = _scrape_documents(ctx, docs_dir).get("plat")
        records: list[dict] = []
        downloaded: list[str] = []
        summary = "Open Clerk Official Records — Recorded plat / subdivision map"
        if fetched:
            summary = "Auto-fetched the recorded plat / subdivision map"
            downloaded = [fetched]
            records = [{"file": f"documents/{fetched}", "source": doc_url}]
        return FetchedSource(
            status=StepStatus.ok if fetched else StepStatus.link,
            data=ctx.clerk_ref,
            summary=summary,
            link=doc_url,
            link_label="Open Clerk Official Records — Recorded plat / subdivision map",
            source_url=doc_url,
            saved_file="clerk_search_refs.json",
            downloaded=downloaded,
            records=records,
            confidence=Confidence.medium if fetched else None,
        )

    def fallback(self, ctx, error: ErrorInfo | None = None) -> FetchedSource:
        doc_url = _clerk_url(ctx, "plat")
        return FetchedSource(
            status=StepStatus.link,
            data=ctx.clerk_ref,
            summary="Open Clerk Official Records — Recorded plat / subdivision map",
            link=doc_url,
            link_label="Open Clerk Official Records — Recorded plat / subdivision map",
            source_url=doc_url,
            saved_file="clerk_search_refs.json",
        )


# -------------------------------------------------------- clerk docs (attempt → link)


def _attempt_clerk_adapter(step_key: str, label: str, source_key: str):
    """Clerk-family document: TRY to fetch via the shared clerk scrape, and
    only fall back to the Official Records deep-link if the source can't
    produce a document for this family.

    ``source_key`` is the key the shared ``_scrape_documents`` cache uses for
    this document family (e.g. ``deed`` for the subject deed). Where the county
    has no scraping adapter there is nothing to download → the link fallback is
    the honest, one-click path (which is what most counties will show).
    """
    class _AttemptClerk(SourceAdapter):
        key_name = step_key
        label_text = label

        def fetch(self, ctx, docs_dir) -> FetchedSource:
            doc_url = _clerk_url(ctx, self.key_name)
            fetched = _scrape_documents(ctx, docs_dir).get(source_key)
            summary = (f"Open Clerk Official Records — {self.label_text}"
                       if not fetched else
                       f"Auto-fetched {self.label_text} — verify the match")
            return FetchedSource(
                status=StepStatus.ok if fetched else StepStatus.link,
                data=ctx.clerk_ref,
                summary=summary,
                link=doc_url,
                link_label=f"Open Clerk Official Records — {self.label_text}",
                source_url=doc_url,
                saved_file="clerk_search_refs.json",
            )

        def fallback(self, ctx, error: ErrorInfo | None = None) -> FetchedSource:
            return self.fetch(ctx, None)

    _AttemptClerk.key = step_key
    return _AttemptClerk()


# --------------------------------------------------------------- flood

class FloodAdapter(SourceAdapter):
    key = "flood"

    def fetch(self, ctx, docs_dir) -> FetchedSource:
        from app.services import downloader, fema

        f = fema.flood(ctx.lat, ctx.lon, county_fips=ctx.county_fips)
        has = bool(f.get("flood_zone"))
        records: list[dict] = []
        dls: list[str] = []
        mp = None
        try:
            mp = downloader.save_flood_map(ctx.folder, ctx.lat, ctx.lon, f, ctx.doc_meta)
            if mp:
                records.append({"file": f"documents/{mp}", "source": fema.NFHL})
        except Exception:
            mp = None
        if has:
            fn = None
            try:
                fn = downloader.save_flood_report(ctx.folder, f, ctx.doc_meta, map_file=mp)
            except Exception:
                fn = None
            if fn:
                records.append({"file": f"documents/{fn}", "source": fema.NFHL})
                dls.append(fn)
        if mp and not dls:
            dls.append(mp)   # fallback: no zone data → show the map exhibit itself
        if has:
            summ = fema.summarize(f)
        elif mp:
            summ = "Not in a mapped SFHA polygon (Zone X) — see flood map excerpt, parcel at center"
        else:
            summ = "No NFHL polygon here — open the FIRM directly"
        return FetchedSource(
            status=StepStatus.ok if (has or mp) else StepStatus.link,
            data=f,
            summary=summ,
            link=fema.MSC_HOME,
            link_label="Open FEMA Map Service Center (FIRMette)",
            source_url=fema.NFHL,
            saved_file="flood_zone.json",
            downloaded=dls,
            records=records,
        )

    def fallback(self, ctx, error: ErrorInfo | None = None) -> FetchedSource:
        from app.services import fema
        return FetchedSource(
            status=StepStatus.link,
            summary="Couldn't reach FEMA NFHL from this network — open the FIRM directly",
            link=fema.MSC_HOME,
            link_label="Open FEMA Map Service Center (FIRMette)",
            source_url=fema.NFHL,
            saved_file="flood_zone.json",
        )


# --------------------------------------------------------------- ngs

class NgsAdapter(SourceAdapter):
    key = "benchmarks"   # RESIDENTIAL_DOCS calls this step "benchmarks"

    def fetch(self, ctx, docs_dir) -> FetchedSource:
        from app.services import downloader, ngs

        b = ngs.benchmarks(ctx.lat, ctx.lon)
        dls = []
        records: list[dict] = []
        try:
            dls = downloader.download_ngs_datasheets(ctx.folder, b.get("marks"), limit=3)
            for fn in dls:
                records.append({"file": f"documents/{fn}", "source": ngs.RADIAL})
        except Exception:
            dls = []
        summ = ngs.summarize(b)
        if dls:
            summ += f"  ·  downloaded {len(dls)} datasheet(s)"
        return FetchedSource(
            status=StepStatus.ok if b.get("count") else StepStatus.empty,
            data=b,
            summary=summ,
            link="https://geodesy.noaa.gov/",
            link_label="Open NGS datasheets",
            source_url=ngs.RADIAL,
            saved_file="benchmarks.json",
            downloaded=dls,
            records=records,
        )

    def fallback(self, ctx, error: ErrorInfo | None = None) -> FetchedSource:
        return FetchedSource(
            status=StepStatus.link,
            summary="Couldn't reach NGS — open the datasheets directly",
            link="https://geodesy.noaa.gov/",
            link_label="Open NGS datasheets",
            source_url="https://geodesy.noaa.gov/api/nde/radial",
            saved_file="benchmarks.json",
        )


# --------------------------------------------------------------- glo (link-only)

class GloAdapter(SourceAdapter):
    key = "glo"

    def fetch(self, ctx, docs_dir) -> FetchedSource:
        return FetchedSource(
            status=StepStatus.link,
            link=GLO,
            link_label="Open BLM GLO Records",
            source_url=GLO,
        )

    def fallback(self, ctx, error: ErrorInfo | None = None) -> FetchedSource:
        return self.fetch(ctx, None)


# --------------------------------------------------------------- zoning (link-only)

class ZoningAdapter(SourceAdapter):
    """Zoning / setback ordinance — link-only.

    Zoning maps and setback ordinances live on county/municipal GIS or
    permitting portals, not in a single auto-fetchable instrument, so today
    we deep-link to the county appraiser/GIS portal (which carries the zoning
    parcel search). ``source_url`` stays explicit so a future adapter can
    replace the link with an auto-fetch without touching the reference set.
    """
    key = "zoning"

    def fetch(self, ctx, docs_dir) -> FetchedSource:
        doc_url = ctx.appraiser_url or ctx.clerk_ref.get("appraiser_url") or ctx.clerk_ref.get("directory_url", "")
        label = doc_url or "County zoning / GIS portal"
        return FetchedSource(
            status=StepStatus.link,
            summary="Zoning / setback ordinance — search the county zoning/GIS portal",
            link=doc_url,
            link_label="Open County Zoning / GIS Portal",
            source_url=label,
        )

    def fallback(self, ctx, error: ErrorInfo | None = None) -> FetchedSource:
        return self.fetch(ctx, None)


# ------------------------------------------------------------------- registry

ADAPTERS: dict[str, SourceAdapter] = {
    a.key: a for a in (
        ParcelAdapter(),
        AppraiserAdapter(),
        DeedAdapter(),
        PlatAdapter(),
        _attempt_clerk_adapter("adjoiners", "Deeds — adjoining parcels", "deed"),
        _attempt_clerk_adapter("easements", "Easements / ROW / covenants (CC&Rs)", "deed"),
        _attempt_clerk_adapter("prior_survey", "Prior recorded surveys", "deed"),
        _attempt_clerk_adapter("condo", "Condominium declaration & exhibits", "plat"),
        FloodAdapter(),
        NgsAdapter(),
        GloAdapter(),
        ZoningAdapter(),
    )
}


def register_source(key: str, adapter: SourceAdapter) -> None:
    """Register/replace an adapter (extension point + test seam)."""
    ADAPTERS[key] = adapter
