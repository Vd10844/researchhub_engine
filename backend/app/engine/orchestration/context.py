"""Property context — the canonical, fully-resolved state a research run operates on.

This is the phase-separated entry of the pipeline:

  Phase 1 -- geocode (or parcel-ID pre-resolve)        → location, county, state, FIPS
  Phase 2 -- parcel resolution (parcel ID keys the job) → parcel record + hints + situs
  Phase 3 -- clerk/appraiser reference assembly        → clerk URLs + search hints
  Phase 4 -- per-document fetch                        → see ``steps.py``

Phases 1-3 produce a ``PropertyContext``; the doc adapters (``sources.py``) only
consume it — they never re-resolve context on their own.  That is the seam that
lets a retry re-fetch *one document* without re-running the whole monolith.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from app.data import geography
from app.data.county_platforms import STATE_APPRAISER, lookup, netronline
from app.services import geocode as geo_svc
from app.services import parcel as parcel_svc

from .folders import job_folder, save_json


class WarningBag:
    """Deduplicated, ordered warning collector shared by the whole run."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        if message and message not in self.items:
            self.items.append(message)

    def __iter__(self):
        return iter(self.items)


@dataclass
class PropertyContext:
    """Canonical resolved-property state consumed by all document adapters."""

    # --- location / geo ------------------------------------------------
    address: str                # the search address (post parcel-id rewrite = situs)
    matched_address: str
    lat: float
    lon: float
    state: str                  # 2-letter abbr
    state_fips: str
    county: str                 # county name
    county_fips: str
    geocoder: str               # census | arcgis | nominatim | parcel-id

    # --- parcel ----------------------------------------------------------
    parcel: dict = field(default_factory=dict)          # raw parcel.resolve() output
    parcel_ok: bool = False
    parcel_id: str = ""
    parcel_hints: dict = field(default_factory=dict)
    parcel_error: str = ""                              # set when parcel.resolve raised

    # --- links / references ----------------------------------------------
    appraiser_url: str = ""
    clerk_ref: dict = field(default_factory=dict)       # clerk.references() output

    # --- run identity -----------------------------------------------------
    job_number: str = ""
    order: str = ""
    name: str = ""                                      # job-level folder name
    folder: Path = None                                 # research staging dir
    survey_type: str = "Residential Land Survey"

    # --- shared cross-document artifacts (cached, best-effort) --------------
    appr: dict = field(default_factory=dict)            # appraiser.fetch() output

    # --- run bookkeeping -----------------------------------------------------
    warnings: WarningBag = field(default_factory=WarningBag)
    manifest: list = field(default_factory=list)

    @property
    def situs(self) -> str:
        return self.parcel.get("situs", "") if self.parcel_ok else ""

    @property
    def land_sqft(self):
        return self.parcel.get("land_sqft") if self.parcel_ok else None

    @property
    def land_acres(self):
        return self.parcel.get("land_acres") if self.parcel_ok else None

    @property
    def doc_meta(self) -> dict:
        """Roster handed to the downloader's save_* helpers for report headers."""
        return {
            "parcel_id": self.parcel_id,
            "matched_address": self.matched_address,
            "county": self.county,
            "state": self.state,
            "situs": self.situs,
            "land_sqft": self.land_sqft,
            "land_acres": self.land_acres,
        }

    # ------------------------------------------------------------------ staging

    def log(self, entry: dict) -> None:
        """Append a manifest entry (file + source + digest)."""
        self.manifest.append(entry)

    def log_json(self, filename: str, data: dict, source: str) -> None:
        self.log({**save_json(self.folder, filename, data), "source": source})

    def log_file(self, filename: str, source: str) -> None:
        """Record a downloaded document in documents/ (audit trail)."""
        self.log({"file": f"documents/{filename}", "source": source})


def _state_abbr(state_fips: str, selected_state: str) -> str:
    return geo_svc.STATE_FIPS.get(state_fips, "") or selected_state.upper()


def resolve_property_context(
    *,
    job_number: str = "",
    address: str = "",
    survey_type: str = "Residential Land Survey",
    selected_state: str = "",
    selected_county_fips: str = "",
    order_number: str = "",
    search_parcel_id: str = "",
) -> PropertyContext:
    """Phases 1-3: build the canonical context for the given address / parcel ID.

    Raises ``ValueError`` when the parcel-ID pre-resolve finds nothing — the
    worker treats that as a failed job (nothing can be researched).  Address
    geocoding that returns no county also raises (no research without a count y).
    """
    warnings = WarningBag()

    # ---- Phase 1a: parcel-ID search (skips geocoding) ---------------------
    st = ""
    preresolved = None
    if search_parcel_id.strip() and not address.strip():
        st = selected_state.strip().upper()
        if not (len(st) == 2 and st.isalpha()):
            st = geo_svc.STATE_FIPS.get(selected_state.strip(), "")
        pr = parcel_svc.resolve_by_id(st, search_parcel_id.strip(), selected_county_fips.strip())
        if not pr or pr.get("lat") is None:
            raise ValueError(
                f"Parcel ID '{search_parcel_id.strip()}' not found"
                + (f" in {st}." if st else " — pick the state and try again.")
            )
        cn, cf, sf = geo_svc._county_from_coords(pr["lat"], pr["lon"])
        geo = {"matched_address": pr["parcel"].get("situs") or f"Parcel {search_parcel_id.strip()}",
               "lat": pr["lat"], "lon": pr["lon"], "county_name": cn, "county_fips": cf,
               "state_fips": sf, "provider": "parcel-id"}
        preresolved = pr["parcel"]
        address = geo["matched_address"]   # downstream (folder, matching) uses the situs
    else:
        geo = geo_svc.geocode(address)

    # ---- Phase 1b: normalize geo + county/fips -----------------------------
    state_abbr = geo_svc.STATE_FIPS.get(geo.get("state_fips", ""), "") or st
    fips = geo.get("county_fips", "")
    cname = geography.county_name(fips) or geo.get("county_name", "")
    lat, lon = geo.get("lat"), geo.get("lon")
    provider = geo.get("provider", "census")

    reg = lookup(fips) or {}
    appraiser_url = (reg.get("appraiser_url") or STATE_APPRAISER.get(state_abbr)
                     or netronline(state_abbr, cname))

    if provider != "census":
        warnings.add(
            f'Address not in the US Census file — matched via {provider.upper()} instead. '
            "Please confirm the pinned location on the map is the correct property."
        )

    ctx = PropertyContext(
        address=address,
        matched_address=geo.get("matched_address", address),
        lat=lat,
        lon=lon,
        state=state_abbr,
        state_fips=geo.get("state_fips", ""),
        county=cname,
        county_fips=fips,
        geocoder=provider,
        appraiser_url=appraiser_url,
        survey_type=survey_type,
        warnings=warnings,
    )

    # ---- Phase 2: parcel resolution (parcel ID keys the whole job) ---------
    try:
        p = preresolved or parcel_svc.resolve(
            fips, state_abbr, cname, lat, lon, address=ctx.matched_address
        )
    except Exception as e:  # noqa: BLE001
        p = {"method": "error", "error": str(e), "hints": {}}

    ctx.parcel_hints = p.get("hints", {})
    pid = _find_parcel_id(p.get("parcels", []))

    # Trust the parcel ONLY on a positive address match, or an exact-polygon hit whose situs
    # doesn't contradict the search. A buffered/neighbor guess is worse than nothing — a wrong
    # Parcel ID also drives a wrong deed/plat/appraiser fetch — so suppress it entirely and
    # fall back to reference links ("Parcel record not found") instead of showing bad data.
    parcel_ok = (bool(p.get("parcels")) and p.get("address_match") is not False
                 and not p.get("buffered_match"))
    if not parcel_ok:
        pid = ""
        ctx.parcel_hints = {}
        warnings.add(
            "Couldn't confirm a parcel matching this address — showing reference links only. "
            "Parcel ID, lot area, and deed/plat auto-fetch are skipped to avoid wrong data; "
            "use the County Property Appraiser link to look up the parcel.")
    p["parcel_id"] = pid

    ctx.parcel = p
    ctx.parcel_ok = parcel_ok
    ctx.parcel_id = pid

    # ---- Phase 3: run identity + shared reference assembly ------------------
    job_id = pid or (job_number or "").strip()
    folder = job_folder(job_id, address)
    order = (order_number or "").strip() or pid or job_id or folder.parent.name

    ctx.job_number = job_id
    ctx.order = order
    ctx.name = folder.parent.name
    ctx.folder = folder

    ctx.log_json("geocode.json", geo, geo_svc.CENSUS)
    ctx.log_json("parcel.json", p, p.get("source", appraiser_url))

    from app.services import clerk

    clerk_ref = clerk.references(fips, state_abbr, cname, ctx.parcel_hints)
    ctx.clerk_ref = clerk_ref
    ctx.log_json("clerk_search_refs.json", clerk_ref,
                 clerk_ref["official_records_search"])

    return ctx


def _find_parcel_id(parcels: list[dict]) -> str:
    """Pull the unique parcel identifier (folio / PIN / strap / APN / parno / SPAN / acct)."""
    keys = ("folio", "parcelid", "parcel_id", "parcelno", "parcel_no", "parno",
            "parcelnum", "pin", "strap", "apn", "altkey", "gid", "span", "acct", "parcel",
            "prop_id", "propid", "property_id", "sbl", "locid", "ssl")   # TX; NY; MA; DC=ssl
    bad = ("addr", "street", "situs", "owner", "city", "zip", "mail")
    for rec in parcels or []:
        for k, v in rec.items():
            kl = k.lower().replace(" ", "").replace("-", "")
            if v in (None, "", 0) or any(b in kl for b in bad):
                continue
            if any(t in kl for t in keys):
                return str(v)
    return ""


def now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()