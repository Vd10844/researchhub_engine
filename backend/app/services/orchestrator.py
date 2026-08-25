"""US residential land survey — research pipeline.

Given an address: resolve the parcel (its Parcel ID keys the whole job), then produce the
full FL residential research document set (reference.RESIDENTIAL_DOCS) — each item classified
mandatory / conditional / recommended, auto-fetched where a public API exists (parcel, FEMA,
NGS) or deep-linked to the county Clerk Official Records / BLM GLO otherwise. Everything is
filed under a Parcel-ID job folder with an audit manifest.
"""
import re
from urllib.parse import quote_plus

from . import geocode as geo_svc
from . import fema, ngs, parcel, clerk, jobs, downloader, clerk_scraper, appraiser
from .geocode import STATE_FIPS
from ..data import geography, reference
from ..data.county_platforms import lookup, netronline, STATE_APPRAISER

GLO = "https://glorecords.blm.gov/"


def _attr(attrs: dict, *needles: str) -> str:
    for k, v in (attrs or {}).items():
        kl = k.lower().replace("_", "")
        if any(n in kl for n in needles) and v not in (None, "", " ", 0):
            return str(v).strip()
    return ""


def _field(attrs: dict, name: str) -> str:
    """Exact (case-insensitive) field lookup — for precise DOR columns like OR_BOOK1."""
    for k, v in (attrs or {}).items():
        if k.upper() == name and v not in (None, "", " "):
            return str(v).strip()
    return ""


def _numref(value: str) -> str:
    """A usable recorded-document reference: has a digit and isn't an all-zero placeholder.
    Rejects roll junk like 'UNRE'/'INST' (unrecorded) that would otherwise drive a bad
    clerk search."""
    v = (value or "").strip()
    return v if (any(c.isdigit() for c in v) and v.strip("0 ")) else ""


def _plat_ref(legal: str):
    """Pull (book, page) from a legal description, e.g. '... PB 37 PG 25'.

    Book and page are matched independently — DOR legals frequently give the plat book
    but omit the page (the page is then resolved from the subdivision by the scraper)."""
    legal = legal or ""
    mb = (re.search(r"\bP\.?\s?B\.?\s*(\d+)", legal, re.I)
          or re.search(r"PLAT\s*BOOK\s*(\d+)", legal, re.I))
    mp = re.search(r"\bP(?:G|AGE)\.?\s*(\d+)", legal, re.I)
    return (mb.group(1) if mb else None, mp.group(1) if mp else None)


def _or_ref(legal: str):
    """Pull the deed Official-Records (book, page) that some rolls embed in the legal text,
    e.g. '9-17-30 PER OR 8147 PG 4623 SW'. Requires the 'OR' book marker so it never picks
    up a plat/map book (PB/MB). Returns (book, page) or (None, None)."""
    m = re.search(r"\bO\.?\s?R\.?\s*(?:BOOK\s*)?(\d{2,6})\s*"
                  r"(?:/\s*(\d{1,6})|(?:PG|PAGE|P)\.?\s*(\d{1,6}))", (legal or ""), re.I)
    if not m:
        return (None, None)
    return (m.group(1), m.group(2) or m.group(3))


def _subdivision(legal: str) -> str:
    """Subdivision name + unit (text before the block/lot/plat-book markers)."""
    head = re.split(r"\b(BLK|BLOCK|LOT|LT|PB|P\s?B|PLAT|SEC|BEG)\b",
                    (legal or "").upper())[0]
    return " ".join(head.split()[:6]).strip()


def _find_parcel_id(parcels: list[dict]) -> str:
    """Pull the unique parcel identifier (folio / PIN / strap / APN / parno / SPAN / acct)."""
    keys = ("folio", "parcelid", "parcel_id", "parcelno", "parcel_no", "parno",
            "parcelnum", "pin", "strap", "apn", "altkey", "gid", "span", "acct", "parcel",
            "prop_id", "propid", "property_id", "sbl", "locid", "ssl")   # TX; NY; MA; DC=ssl
    # Don't mistake an ADDRESS field for the ID (e.g. NY "PARCEL_ADDR" contains "parcel").
    bad = ("addr", "street", "situs", "owner", "city", "zip", "mail")
    for rec in parcels or []:
        for k, v in rec.items():
            kl = k.lower().replace(" ", "").replace("-", "")
            if v in (None, "", 0) or any(b in kl for b in bad):
                continue
            if any(t in kl for t in keys):
                return str(v)
    return ""


def run_research(job_number: str = "", address: str = "",
                 survey_type: str = "Residential Land Survey", include=None,
                 selected_state: str = "", selected_county_fips: str = "",
                 order_number: str = "", search_parcel_id: str = "") -> dict:
    steps: list[dict] = []
    manifest: list[dict] = []
    warnings: list[str] = []

    # Entry: by Parcel ID (resolve the parcel directly → its centroid drives the rest) or by
    # address (geocode). Parcel-ID search needs the state so we know which parcel service to hit.
    st = ""
    _preresolved = None
    if search_parcel_id.strip() and not address.strip():
        st = selected_state.strip().upper()
        if not (len(st) == 2 and st.isalpha()):
            st = STATE_FIPS.get(selected_state.strip(), "")
        pr = parcel.resolve_by_id(st, search_parcel_id.strip(), selected_county_fips.strip())
        if not pr or pr.get("lat") is None:
            raise ValueError(f"Parcel ID '{search_parcel_id.strip()}' not found"
                             + (f" in {st}." if st else " — pick the state and try again."))
        cn, cf, sf = geo_svc._county_from_coords(pr["lat"], pr["lon"])
        geo = {"matched_address": pr["parcel"].get("situs") or f"Parcel {search_parcel_id.strip()}",
               "lat": pr["lat"], "lon": pr["lon"], "county_name": cn, "county_fips": cf,
               "state_fips": sf, "provider": "parcel-id"}
        _preresolved = pr["parcel"]
        address = geo["matched_address"]   # downstream (folder, matching) uses the situs
    else:
        geo = geo_svc.geocode(address)
    state_abbr = STATE_FIPS.get(geo["state_fips"], "") or st
    fips = geo["county_fips"]
    cname = geography.county_name(fips) or geo["county_name"]
    lat, lon = geo["lat"], geo["lon"]
    provider = geo.get("provider", "census")
    reg = lookup(fips) or {}
    # Appraiser/tax link: county-specific site → else a STATEWIDE assessment search where one
    # exists (e.g. NJ's MOD-IV search covers all 21 counties) → else the NETROnline directory.
    appraiser_url = (reg.get("appraiser_url") or STATE_APPRAISER.get(state_abbr)
                     or netronline(state_abbr, cname))

    # The Census file missed this address; a fallback geocoder (ArcGIS/OSM) supplied the
    # location. It's usually right, but the user should eyeball it on the map before trusting
    # the parcel — so surface it rather than silently proceed.
    if provider != "census":
        warnings.append(
            f'Address not in the US Census file — matched via {provider.upper()} instead. '
            "Please confirm the pinned location on the map is the correct property."
        )

    # ---- Parcel first (Mandatory): its Parcel ID keys the whole job ----
    try:
        p = _preresolved or parcel.resolve(fips, state_abbr, cname, lat, lon,
                                           address=geo["matched_address"])
    except Exception as e:  # noqa: BLE001
        p = {"method": "error", "error": str(e), "hints": {}}
    parcel_hints = p.get("hints", {})
    pid = _find_parcel_id(p.get("parcels", []))

    # Trust the parcel ONLY on a positive address match, or an exact-polygon hit whose situs
    # doesn't contradict the search. A buffered/neighbor guess is worse than nothing — a wrong
    # Parcel ID also drives a wrong deed/plat/appraiser fetch — so we suppress it entirely and
    # fall back to reference links ("Parcel record not found") instead of showing bad data.
    parcel_ok = (bool(p.get("parcels")) and p.get("address_match") is not False
                 and not p.get("buffered_match"))
    if not parcel_ok:
        pid = ""                 # don't key the job or drive downloads off an unconfirmed parcel
        parcel_hints = {}
        warnings.append(
            "Couldn't confirm a parcel matching this address — showing reference links only. "
            "Parcel ID, lot area, and deed/plat auto-fetch are skipped to avoid wrong data; "
            "use the County Property Appraiser link to look up the parcel.")
    p["parcel_id"] = pid

    # Job folder keyed by Parcel ID (falls back to any passed job number / the address).
    job_id = pid or (job_number or "").strip()
    folder = jobs.job_folder(job_id, address)
    # Evidence-Locker order reference: the given order # (from upstream), else the Parcel ID,
    # else the job folder name — so every job maps to some locker key.
    order = (order_number or "").strip() or pid or job_id or folder.parent.name

    manifest.append({**jobs.save_json(folder, "geocode.json", geo), "source": geo_svc.CENSUS})
    manifest.append({**jobs.save_json(folder, "parcel.json", p),
                     "source": p.get("source", appraiser_url)})

    # Clerk Official Records — one lookup shared by deed/plat/adjoiners/easements/prior/condo.
    clerk_ref = clerk.references(fips, state_abbr, cname, parcel_hints)
    clerk_url = clerk_ref["official_records_search"]
    manifest.append({**jobs.save_json(folder, "clerk_search_refs.json", clerk_ref),
                     "source": clerk_url})
    hint_str = ", ".join(list(parcel_hints)[:4])
    doc_meta = {"parcel_id": pid, "matched_address": geo["matched_address"],
                "county": cname, "state": state_abbr,
                "situs": p.get("situs", "") if parcel_ok else "",
                "land_sqft": p.get("land_sqft") if parcel_ok else None,
                "land_acres": p.get("land_acres") if parcel_ok else None}

    # Auto-fetch deed/plat images from the county Clerk portal where an adapter exists
    # (best-effort, browser-driven — any failure leaves the deep-link fallback in place).
    # Property Appraiser: official Property Record Card PDF + the full (untruncated) legal,
    # which supplies the plat Book/Page when the DOR tax-roll legal cut it off. Best-effort
    # (needs the appraiser host reachable — see appraiser.py).
    appr: dict = {}
    if appraiser.available(fips) and pid:
        try:
            appr = appraiser.fetch(fips, pid, downloader.docs_dir(folder))
        except Exception:  # noqa: BLE001
            appr = {}

    clerk_docs: dict = {}
    if parcel_ok and clerk_scraper.has_adapter(fips) and p.get("parcels"):
        attrs = p["parcels"][0]
        legal = _attr(attrs, "slegal", "legal")
        owner = _attr(attrs, "ownname", "owner")
        pb, pg = _plat_ref(legal)
        # Fall back to the appraiser's untruncated legal for the plat book/page.
        if not pb and appr.get("plat_book"):
            pb, pg = appr["plat_book"], appr.get("plat_page")
        subdiv = _subdivision(legal)
        # Plat needs at least the book; the page is resolved from the subdivision if absent.
        plat_arg = {"book": pb, "page": pg, "subdivision": subdiv} if pb else None
        # Deed: prefer the authoritative OR book/page from the tax roll (SALE_1); the roll
        # leaves it blank for older/estate transfers, so fall back to the owner-name search.
        # Some county rolls put placeholder text in these fields ("UNRE"/"INST" for
        # unrecorded, all-zeros, etc.), so require a real numeric reference — otherwise
        # we'd burn a clerk search on junk and risk matching the wrong document.
        ob, op = _numref(_field(attrs, "OR_BOOK1")), _numref(_field(attrs, "OR_PAGE1"))
        cn = _numref(_field(attrs, "CLERK_NO1"))  # recorded document / instrument number
        # Some rolls (e.g. Volusia) leave those columns blank but embed the reference in the
        # legal text ("... PER OR 8147 PG 4623 ..."). Recover it when the columns are empty.
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
                clerk_docs = clerk_scraper.fetch_documents(
                    fips, downloader.docs_dir(folder), plat=plat_arg, deed=deed_arg)
            except Exception:  # noqa: BLE001 — never let scraping break the pipeline
                clerk_docs = {}

    def fetch_flood():
        f = fema.flood(lat, lon, county_fips=fips)
        manifest.append({**jobs.save_json(folder, "flood_zone.json", f), "source": fema.NFHL})
        return f

    def fetch_bench():
        b = ngs.benchmarks(lat, lon)
        manifest.append({**jobs.save_json(folder, "benchmarks.json", b), "source": ngs.RADIAL})
        return b

    # ---- Build the classified document set in defined order ----
    for d in reference.RESIDENTIAL_DOCS:
        step = {"key": d["key"], "label": d["label"], "requirement": d["requirement"],
                "condition": d.get("condition", ""), "description": d.get("description", ""),
                "summary": d["guidance"],
                "link": "", "link_label": "", "source_url": "", "saved_file": None, "data": None}
        src = d["source"]

        if src == "parcel":
            if parcel_ok and p.get("method") == "arcgis-rest" and p.get("parcels"):
                sqft, acres = p.get("land_sqft"), p.get("land_acres")
                situs = p.get("situs", "")
                area_txt = (f" · Lot {int(sqft):,} sq ft" + (f" ({acres} ac)" if acres else "")
                            if sqft else "")
                step.update({
                    "status": "ok",
                    "summary": (f"Parcel ID: {pid}" if pid else parcel.summarize(p)) + area_txt,
                    "data": p, "source_url": p.get("source") or appraiser_url,
                    "saved_file": "parcel.json", "link": appraiser_url,
                    "link_label": "Open County Property Appraiser",
                    "situs": situs, "land_sqft": sqft, "land_acres": acres, "address_match": True,
                })
                fn = downloader.save_parcel_record(folder, p, doc_meta)
                if fn:
                    manifest.append({"file": f"documents/{fn}", "source": p.get("source", "")})
                    step["downloaded"] = [fn]
            else:
                # No confident parcel match — show links only, never a neighbor's data.
                step.update({
                    "status": "link",
                    "summary": "Parcel record not found for this address — open the County "
                               "Property Appraiser to look it up.",
                    "data": None, "source_url": appraiser_url, "link": appraiser_url,
                    "link_label": "Open County Property Appraiser",
                    "situs": "", "land_sqft": None, "land_acres": None, "address_match": None,
                })
        elif src == "appraiser":
            got = parcel_ok and bool(p.get("parcels"))
            step.update({
                "status": "ok" if got else "link",
                "summary": ("Owner, values & last sale from the county tax roll"
                            if got else "Open the County Property Appraiser"),
                "data": p.get("parcels", [{}])[0] if got else None,
                "source_url": appraiser_url, "link": appraiser_url,
                "link_label": "Open County Property Appraiser",
            })
            files = []
            if appr.get("doc"):  # official Property Record Card PDF
                files.append(appr["doc"])
                manifest.append({"file": f"documents/{appr['doc']}", "source": appraiser_url})
                step["summary"] = "Official Property Record Card (county appraiser)"
            for extra in (appr.get("docs") or []):  # extra appraiser docs (e.g. Mapping Worksheet)
                if extra not in files:
                    files.append(extra)
                    manifest.append({"file": f"documents/{extra}", "source": appraiser_url})
            if got:  # always also keep the DOR tax-roll summary
                fn = downloader.save_appraiser_record(folder, p["parcels"][0], doc_meta, appraiser_url)
                if fn:
                    manifest.append({"file": f"documents/{fn}", "source": appraiser_url})
                    step["saved_file"] = "parcel.json"
                    files.append(fn)
            if files:
                step["downloaded"] = files
        elif src == "clerk":
            # Plats can live in a different index from deeds (see clerk.references); everywhere
            # without a declared plat source this resolves back to clerk_url, i.e. no change.
            doc_url = clerk_ref.get("plat_search", clerk_url) if d["key"] == "plat" else clerk_url
            step.update({
                "status": "link", "data": clerk_ref, "source_url": doc_url,
                "saved_file": "clerk_search_refs.json", "link": doc_url,
                "link_label": f"Open Clerk Official Records — {d['label']}",
            })
            if d["key"] == "deed" and hint_str:
                step["summary"] += f"  ·  hints: {hint_str}"
            # Attach an auto-fetched deed/plat image if the clerk adapter retrieved one.
            fetched = clerk_docs.get(d["key"])
            if fetched:
                step["status"] = "ok"
                step["downloaded"] = [fetched]
                manifest.append({"file": f"documents/{fetched}", "source": clerk_url})
                if d["key"] == "deed":
                    ref = clerk_docs.get("deed_ref", "")
                    step["summary"] = (f"Auto-fetched deed {ref} — verify grantee & legal "
                                       f"match the subject parcel").strip()
                else:
                    step["summary"] = "Auto-fetched the recorded plat / subdivision map"
        elif src == "fema":
            try:
                f = fetch_flood()
                has = bool(f.get("flood_zone"))
                dls = []
                # Build the map first so it can be MERGED into the single FEMA Flood Report
                # (embedded inline). The PNG stays on disk + in the manifest for audit, but it is
                # not exposed as a separate document — the report is the one flood doc.
                mp = downloader.save_flood_map(folder, lat, lon, f, doc_meta)
                if mp:
                    manifest.append({"file": f"documents/{mp}", "source": fema.NFHL})
                if has:
                    fn = downloader.save_flood_report(folder, f, doc_meta, map_file=mp)
                    if fn:
                        manifest.append({"file": f"documents/{fn}", "source": fema.NFHL})
                        dls.append(fn)
                if mp and not dls:
                    dls.append(mp)   # fallback: no zone data → show the map exhibit itself
                if has:
                    summ = fema.summarize(f)
                elif mp:
                    summ = "Not in a mapped SFHA polygon (Zone X) — see flood map excerpt, parcel at center"
                else:
                    summ = "No NFHL polygon here — open the FIRM directly"
                step.update({
                    "status": "ok" if (has or mp) else "link",
                    "summary": summ,
                    "data": f, "source_url": fema.NFHL, "saved_file": "flood_zone.json",
                    "link": fema.MSC_HOME, "link_label": "Open FEMA Map Service Center (FIRMette)",
                    "downloaded": dls,
                })
            except Exception:  # noqa: BLE001
                step.update({"status": "link",
                             "summary": "Couldn't reach FEMA NFHL from this network — open the FIRM directly",
                             "link": fema.MSC_HOME, "link_label": "Open FEMA Map Service Center (FIRMette)"})
        elif src == "ngs":
            try:
                b = fetch_bench()
                dls = downloader.download_ngs_datasheets(folder, b.get("marks"), limit=3)
                for fn in dls:
                    manifest.append({"file": f"documents/{fn}", "source": ngs.RADIAL})
                summ = ngs.summarize(b)
                if dls:
                    summ += f"  ·  downloaded {len(dls)} datasheet(s)"
                step.update({
                    "status": "ok" if b.get("count") else "empty", "summary": summ,
                    "data": b, "source_url": ngs.RADIAL, "saved_file": "benchmarks.json",
                    "downloaded": dls,
                    "link": "https://geodesy.noaa.gov/", "link_label": "Open NGS datasheets",
                })
            except Exception:  # noqa: BLE001
                step.update({"status": "link",
                             "summary": "Couldn't reach NGS — open the datasheets directly",
                             "link": "https://geodesy.noaa.gov/", "link_label": "Open NGS datasheets"})
        elif src == "glo":
            step.update({"status": "link", "source_url": GLO, "link": GLO,
                         "link_label": "Open BLM GLO Records"})

        steps.append(step)

    meta = {
        "job_number": job_id, "order": order, "parcel_id": pid, "address": address,
        "survey_type": survey_type,
        "matched_address": geo["matched_address"], "county": cname, "county_fips": fips,
        "state": state_abbr, "lat": lat, "lon": lon, "warnings": warnings,
    }
    jobs.write_manifest(folder, manifest, meta)

    # Multiple verification links so the user can independently confirm the location/parcel
    # (especially useful when a fallback geocoder was used, or the parcel needs a manual check).
    _q = quote_plus(geo["matched_address"] or address)
    map_links = [
        {"label": "Google Maps", "url": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"},
        {"label": "Google Street View", "url":
            f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}"},
        {"label": "Bing Maps (aerial)", "url": f"https://www.bing.com/maps?cp={lat}~{lon}&lvl=19&style=a"},
        {"label": "County Property Appraiser", "url": appraiser_url},
        {"label": "Search address on Google", "url": f"https://www.google.com/search?q={_q}"},
    ]

    out = {
        "job_number": job_id, "order": order, "parcel_id": pid, "address": address,
        "matched_address": geo["matched_address"], "county": cname, "county_fips": fips,
        "state": state_abbr, "lat": lat, "lon": lon, "name": folder.parent.name,
        "geocoder": provider, "map_links": map_links,
        "folder": str(folder.parent), "steps": steps, "warnings": warnings,
    }
    # persist the full result so the job can be reopened later with all its doc cards.
    jobs.save_json(folder, "result.json", out)
    return out
