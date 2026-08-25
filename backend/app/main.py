"""FastAPI application - API + static frontend."""
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import APP_NAME, FRONTEND_DIR, JOBS_DIR
from .models import ResearchRequest, FeedbackRequest, EvidenceSendRequest
from concurrent.futures import ThreadPoolExecutor

from .services import orchestrator, jobs, evidence
from .services.http import check_url
from .data import reference, county_platforms, geography
from . import db
# Importing the QuickPlot package registers its ORM models on db.Base, so init_db() below
# creates the qp_* tables in the same pass as the v1 index tables.
from .quickplot import router as quickplot_router

app = FastAPI(title=APP_NAME, version="1.0.0")
app.include_router(quickplot_router)

# Create the index/analytics tables at startup (SQLite in dev, Postgres in prod). Best-effort:
# the filesystem is the source of truth, so a DB problem must never stop the app from serving.
try:
    db.init_db()
except Exception as _e:  # noqa: BLE001
    print(f"[db] init skipped: {_e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def _revalidate_frontend(request, call_next):
    """No-build frontend: tell the browser to REVALIDATE the index + static JS on every load
    (it still gets a fast 304 via ETag when unchanged) so edits show up on a normal reload
    instead of being served from a stale disk cache."""
    resp = await call_next(request)
    path = request.url.path
    if path in ("/", "/quickplot") or path.startswith(("/static/", "/quickplot/")):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


# ------------------------------------------------------------------- API
@app.get("/api/health")
def health():
    return {"status": "ok", "app": APP_NAME, "jobs_dir": str(JOBS_DIR)}


@app.get("/api/stats")
def stats():
    """Index/analytics counts from the database (jobs, searches, evidence)."""
    try:
        return db.stats()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"stats unavailable: {e}")


@app.post("/api/research")
def research(req: ResearchRequest):
    if not req.address.strip() and not req.parcel_id.strip():
        raise HTTPException(400, "provide an address or a parcel_id")
    if req.parcel_id.strip() and not req.address.strip() and not req.state.strip():
        raise HTTPException(400, "parcel_id search needs the state")
    try:
        result = orchestrator.run_research(
            req.job_number.strip(), req.address.strip(),
            req.survey_type, req.include,
            selected_state=req.state.strip(),
            selected_county_fips=req.county_fips.strip(),
            order_number=req.order_number.strip(),
            search_parcel_id=req.parcel_id.strip(),
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Research failed: {e}")
    # Index the job + log the search (best-effort; never fails the request).
    try:
        docs = sum(len(s.get("downloaded") or []) for s in result.get("steps", []))
        db.upsert_job({**result, "docs": docs})
        db.record_event("search", job=result.get("name", ""),
                        address=result.get("matched_address") or req.address.strip(),
                        detail={"county": result.get("county"), "parcel_id": result.get("parcel_id")})
    except Exception as _e:  # noqa: BLE001
        print(f"[db] index skipped: {_e}")
    return result


@app.get("/api/jobs")
def get_jobs():
    return {"jobs": jobs.list_jobs()}


@app.post("/api/feedback")
def post_feedback(req: FeedbackRequest):
    """Record the surveyor's match/mismatch verdict (+ optional note) on a fetched document."""
    data = jobs.save_feedback(req.name, req.model_dump())
    if data is None:
        raise HTTPException(404, "job not found")
    return {"ok": True, "feedback": data}


@app.post("/api/jobs/upload")
def upload_doc(name: str = Form(...), key: str = Form(...), file: UploadFile = File(...)):
    """Attach a manually-downloaded document to a job's doc step (one upload per doc; replaces
    any previous one and syncs the locker). Returns {file, removed:[...]}."""
    saved = evidence.save_upload(name, key, file.filename or "upload", file.file.read())
    if not saved:
        raise HTTPException(404, "job not found")
    return {"ok": True, **saved}


@app.delete("/api/jobs/doc")
def delete_job_doc(name: str = "", file: str = ""):
    """Delete one document file from a job (and remove it from its Evidence Locker)."""
    d = evidence.delete_job_doc(name, file)
    if d is None:
        raise HTTPException(404, "job not found")
    return d


@app.post("/api/evidence/send")
def evidence_send(req: EvidenceSendRequest):
    """Send selected job documents to the order's Evidence Locker."""
    locker = evidence.send_to_evidence(req.order.strip(), req.job_name.strip(),
                                       [i.model_dump() for i in req.items],
                                       new_order=req.new_order)
    if locker is None:
        raise HTTPException(404, "job not found")
    try:
        order = locker.get("order", req.order.strip())
        db.add_evidence(order, [i.model_dump() for i in req.items], source_job=req.job_name.strip())
        db.set_locker_order(req.job_name.strip(), order)
        db.record_event("evidence_send", job=req.job_name.strip(),
                        detail={"order": order, "count": len(req.items)})
    except Exception as _e:  # noqa: BLE001
        print(f"[db] evidence index skipped: {_e}")
    return {"ok": True, "locker": locker}


@app.get("/api/evidence")
def evidence_list():
    return {"orders": evidence.list_lockers()}


@app.get("/api/evidence/detail")
def evidence_detail(order: str = ""):
    d = evidence.locker_detail(order)
    if d is None:
        raise HTTPException(404, "locker not found")
    return d


@app.delete("/api/evidence/item")
def evidence_delete_item(order: str = "", file: str = ""):
    """Remove one document from an order's Evidence Locker."""
    locker = evidence.delete_item(order, file)
    if locker is None:
        raise HTTPException(404, "locker or file not found")
    try:
        db.remove_evidence(order, file)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "locker": locker}


@app.delete("/api/evidence")
def evidence_delete_order(order: str = ""):
    """Delete an entire Evidence Locker order (folder + all its documents)."""
    if not evidence.delete_locker(order):
        raise HTTPException(404, "locker not found")
    try:
        db.remove_evidence(order)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True}


@app.get("/api/evidence/file")
def evidence_file(order: str = "", file: str = "", download: bool = False):
    p = evidence.locker_file(order, file)
    if not p:
        raise HTTPException(404, "file not found")
    disp = "attachment" if download else "inline"
    return FileResponse(str(p), filename=p.name, content_disposition_type=disp)


@app.delete("/api/jobs")
def delete_job(name: str = ""):
    """Delete a saved job/search record (its whole folder)."""
    if not jobs.delete_job(name):
        raise HTTPException(404, "job not found")
    return {"ok": True}


@app.get("/api/jobs/detail")
def get_job_detail(name: str = ""):
    d = jobs.job_detail(name)
    if not d:
        raise HTTPException(404, "job not found")
    return d


@app.get("/api/jobs/file")
def get_job_file(name: str = "", file: str = "", download: bool = False):
    """Serve a job document. Inline by default so PDFs/HTML render in the in-app viewer;
    pass ?download=1 for the download buttons to force a save."""
    p = jobs.job_file(name, file)
    if not p:
        raise HTTPException(404, "file not found")
    disp = "attachment" if download else "inline"
    return FileResponse(str(p), filename=p.name, content_disposition_type=disp)


@app.get("/api/reference/survey-types")
def survey_types():
    return {"survey_types": reference.SURVEY_TYPES}


@app.get("/api/reference/matrix")
def matrix():
    return reference.DOC_MATRIX


@app.get("/api/reference/sources")
def sources():
    return {"sources": reference.SOURCES}


@app.get("/api/reference/states")
def states():
    return {"states": geography.states()}


@app.get("/api/reference/parcel-states")
def parcel_states():
    """States where Parcel-ID search works (a statewide parcel service is wired)."""
    out = [{"abbr": abbr, "label": svc.get("label", abbr)}
           for abbr, svc in county_platforms.STATE_PARCEL.items()]
    return {"states": sorted(out, key=lambda x: x["abbr"])}


@app.get("/api/reference/coverage")
def coverage():
    """Per-state build-out tracker (computed live from the registry, so it never goes stale).

    'Development %' = share of a state's counties whose PARCEL record auto-fetches for free:
    100% where a statewide parcel service is wired, else (counties wired county-by-county /
    total counties). Federal layers (FEMA flood + NGS control) are nationwide/free everywhere
    and are reported separately, not folded into the %.
    """
    raw = geography._counties_raw()
    parcel_states = county_platforms.STATE_PARCEL          # abbr -> service (statewide)
    deed_states = county_platforms.STATE_DEED              # abbr -> statewide deed portal
    appr_states = county_platforms.STATE_APPRAISER         # abbr -> statewide assessment search
    reg = county_platforms.REGISTRY

    # Count county-level wiring per state FIPS prefix (parcel service, clerk link, appraiser link).
    wired_parcel: dict[str, int] = {}
    wired_clerk: dict[str, int] = {}
    wired_appr: dict[str, int] = {}
    for fips, e in reg.items():
        if not (isinstance(fips, str) and len(fips) == 5 and fips.isdigit()):
            continue
        st = fips[:2]
        if e.get("gis_rest"):
            wired_parcel[st] = wired_parcel.get(st, 0) + 1
        if e.get("clerk_url"):
            wired_clerk[st] = wired_clerk.get(st, 0) + 1
        if e.get("appraiser_url"):
            wired_appr[st] = wired_appr.get(st, 0) + 1

    # Count only the 50 states + DC (the app's scope); exclude U.S. territories (AS/GU/MP/PR/VI)
    # so the national total is the standard ~3,144 counties, not 3,235.
    TERRITORIES = {"60", "66", "69", "72", "78"}

    states = []
    tot_counties = tot_parcel = 0
    for st_fips, rows in raw.items():
        if st_fips in TERRITORIES:
            continue
        meta = geography.STATES.get(st_fips)
        if not meta:
            continue
        abbr, name = meta
        n = len(rows)
        svc = parcel_states.get(abbr)
        # An `id_only` statewide layer answers Parcel-ID lookups but carries no situs, so it
        # cannot auto-fetch from an address — the app's actual entry point. Ohio's ODNR layer is
        # one, and counting it as statewide credited OH with all 88 counties when only the 33
        # with their own situs-bearing service can resolve an address. Count those instead.
        statewide = svc is not None and not svc.get("id_only")
        if statewide:
            # A statewide service covers all counties unless it declares partial coverage
            # (counties_covered) — e.g. TN's layer is 86 of 95, CO's ~38 of 64.
            wired = min(int(svc.get("counties_covered", n)), n)
        else:
            wired = min(wired_parcel.get(st_fips, 0), n)
        pct = round(wired / n * 100, 1) if n else 0.0
        mode = "statewide" if statewide else ("county" if wired else "federal")
        tot_counties += n
        tot_parcel += wired
        states.append({
            "abbr": abbr, "name": name, "counties": n,
            "parcel_counties": wired, "parcel_pct": pct, "mode": mode,
            "parcel_label": parcel_states.get(abbr, {}).get("label", "") if statewide else "",
            "deed_statewide": abbr in deed_states,
            "appraiser_statewide": abbr in appr_states,
            # A statewide deed/assessment portal covers EVERY county in that state, so report
            # the effective count (n), not just the per-county overrides in the registry.
            "clerk_counties": (n if abbr in deed_states
                               else min(wired_clerk.get(st_fips, 0), n)),
            "appraiser_counties": (n if abbr in appr_states
                                   else min(wired_appr.get(st_fips, 0), n)),
        })

    # Order: most-developed first, then by county-wiring, then alphabetically.
    states.sort(key=lambda s: (-s["parcel_pct"], -s["parcel_counties"], s["abbr"]))
    order = {"statewide": 0, "county": 1, "federal": 2}
    national = {
        "counties_total": tot_counties,
        "counties_parcel": tot_parcel,
        "parcel_pct": round(tot_parcel / tot_counties * 100, 1) if tot_counties else 0.0,
        "states_statewide": sum(1 for s in states if s["mode"] == "statewide"),
        "states_county": sum(1 for s in states if s["mode"] == "county"),
        "states_federal": sum(1 for s in states if s["mode"] == "federal"),
    }
    counts = {k: sum(1 for s in states if s["mode"] == k) for k in order}

    # ---- Per-document coverage (the whole survey set, not just parcels) --------------------
    # Auto-download of the recorded deed/plat images requires a per-clerk-platform adapter; the
    # set of wired county portals is the source of truth for how many counties auto-fetch those.
    from .services import clerk_scraper as _cs
    clerk_auto = (set(_cs.NEWVISION_PORTALS) | set(_cs.TYLER_PORTALS)
                  | set(_cs.MANATEE_PORTALS) | set(_cs.VOLUSIA_PORTALS))
    T = tot_counties
    county_metro = sum(s["parcel_counties"] for s in states if s["mode"] == "county")
    ga_deed = "GA" in deed_states

    def _pct(n):
        return round(n / T * 100, 1) if T else 0.0

    # VERIFIED-LINK coverage, tracked separately from auto-download. A verified link is a
    # county-specific (or statewide) records portal we have confirmed live — as opposed to the
    # generic NETROnline directory fallback, which exists for every county but is not
    # county-verified. This is the axis most of the build-out work moves.
    tot_clerk = sum(s["clerk_counties"] for s in states)
    tot_appr = sum(s["appraiser_counties"] for s in states)

    documents = [
        {"key": "parcel", "label": "Parcel / Parcel ID", "access": "auto+link",
         "auto_counties": tot_parcel, "auto_pct": national["parcel_pct"],
         "link_counties": T, "link_pct": 100.0,
         "note": (f"Auto in {national['states_statewide']} statewide states + {county_metro} "
                  "metro counties; verified county link everywhere else.")},
        {"key": "appraiser", "label": "Property Appraiser / tax card", "access": "auto+link",
         "auto_counties": tot_parcel, "auto_pct": national["parcel_pct"],
         "link_counties": tot_appr, "link_pct": _pct(tot_appr),
         "note": ("Tax-roll summary auto-generated wherever the parcel resolves; official record "
                  f"card for Polk FL. {tot_appr:,} counties also have a VERIFIED county "
                  "appraiser/assessor portal (rest use the directory link).")},
        {"key": "deed", "label": "Deed (current vesting)", "access": "auto+link",
         "auto_counties": len(clerk_auto), "auto_pct": _pct(len(clerk_auto)),
         "link_counties": tot_clerk, "link_pct": _pct(tot_clerk),
         "note": (f"Auto-download for {len(clerk_auto)} FL clerk platforms"
                  + (" + statewide GSCCCA index for GA" if ga_deed else "")
                  + f". {tot_clerk:,} counties have a VERIFIED clerk/recorder records portal "
                    "(rest use the directory link).")},
        {"key": "plat", "label": "Plat / subdivision map", "access": "auto+link",
         "auto_counties": len(clerk_auto), "auto_pct": _pct(len(clerk_auto)),
         "link_counties": tot_clerk, "link_pct": _pct(tot_clerk),
         "note": (f"Auto when the plat book/page is known (same {len(clerk_auto)} clerk "
                  f"adapters); {tot_clerk:,} counties have a verified clerk portal — plats are "
                  "recorded with the deeds.")},
        {"key": "flood", "label": "FEMA flood map + zone", "access": "auto",
         "auto_counties": T, "auto_pct": 100.0,
         "link_counties": T, "link_pct": 100.0,
         "note": "Nationwide & free — FEMA National Flood Hazard Layer."},
        {"key": "ngs", "label": "Survey control / benchmarks", "access": "auto",
         "auto_counties": T, "auto_pct": 100.0,
         "link_counties": T, "link_pct": 100.0,
         "note": "Nationwide & free — NOAA National Geodetic Survey."},
    ]
    return {"national": national, "mode_counts": counts, "documents": documents, "states": states}


# Core data endpoints the app fetches from — probed by the connection check.
_CORE_ENDPOINTS = [
    ("US Census Geocoder", "https://geocoding.geo.census.gov/geocoder/"),
    ("Census TIGERweb (state/county/city)", "https://tigerweb.geo.census.gov/arcgis/rest/services"),
    ("FEMA NFHL flood API", "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer?f=json"),
    ("FEMA Map Service Center", "https://msc.fema.gov/portal/home"),
    ("NOAA NGS benchmarks", "https://geodesy.noaa.gov/"),
    ("FL Statewide Parcels (DOR)", "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0?f=json"),
]


@app.get("/api/linkcheck")
def linkcheck(county_fips: str = "", portals: bool = False):
    """Probe the data sources from THIS machine so the user can see which URLs their
    own network / antivirus (e.g. K7) is blocking. Runs the checks in parallel.

    - core (always): the federal/statewide APIs the app auto-fetches.
    - one county's clerk+appraiser when `county_fips` is given.
    - every registered clerk+appraiser portal when `portals=true`.
    """
    targets = [(n, u, "core") for n, u in _CORE_ENDPOINTS]
    seen: set[str] = set()

    def add_reg(e):
        cty = e["county"]
        for key, tag in (("clerk_url", "Clerk (deed/plat)"),
                         ("appraiser_url", "Property Appraiser")):
            u = e.get(key)
            if u and u not in seen:
                seen.add(u)
                targets.append((f"{cty} {tag}", u, "portal"))

    if county_fips and (reg := county_platforms.lookup(county_fips)):
        add_reg(reg)
    if portals:
        for e in county_platforms.REGISTRY.values():
            add_reg(e)

    with ThreadPoolExecutor(max_workers=10) as pool:
        verdicts = list(pool.map(
            lambda t: {"name": t[0], "kind": t[2], **check_url(t[1])}, targets))
    return {"results": verdicts}


@app.get("/api/reference/cities")
def cities(county_fips: str = ""):
    """Cities/places inside a county, to populate the address City dropdown."""
    return {"county_fips": county_fips, "cities": list(geography.cities(county_fips))}


@app.get("/api/reference/counties")
def counties(state: str = ""):
    """Counties for the guided-form dropdown.

    Pass ?state=FL (USPS abbr or FIPS) for the full annotated county list of that
    state. With no state, returns just the counties that have a records platform
    registered (the ones with the richest auto-fetch support).
    """
    if state:
        return {"state": state, "counties": geography.counties(state)}
    out = []
    for fips, e in county_platforms.REGISTRY.items():
        out.append({
            "fips": fips, "county": e["county"], "state": e["state"],
            "clerk_platform": e.get("clerk_platform"),
            "clerk_url": e.get("clerk_url"),
            "appraiser_url": e.get("appraiser_url"),
            "has_parcel_api": bool(e.get("gis_rest")),
        })
    return {"counties": sorted(out, key=lambda x: (x["state"], x["county"]))}


# ------------------------------------------------------------------- Frontend
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    idx = FRONTEND_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse({"message": f"{APP_NAME} API running. Frontend not found."})


@app.get("/quickplot")
@app.get("/quickplot/{_path:path}")
def quickplot(_path: str = ""):
    """The Mapperty QuickPlot research hub (order-centric UI on API v2). Served as a
    single page; the client routes on the hash, so every sub-path returns the same shell."""
    idx = FRONTEND_DIR / "quickplot.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse({"message": "QuickPlot frontend not found."}, status_code=404)
