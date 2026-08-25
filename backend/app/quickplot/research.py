"""Auto-fetch runner — bridges the v1 research pipeline to a QuickPlot order.

`run_research()` (services/orchestrator) is synchronous and can take a minute against slow
county portals, so it runs on a worker thread and reports phase progress through an in-memory
registry that the UI polls. Results are then *ingested*: every file the pipeline downloaded
becomes an Evidence Locker document, and every step updates its Source registry row.

Scaling note for the SaaS build-out: the in-memory `_RUNS` registry is single-process. Behind
more than one uvicorn worker this needs a shared queue (Celery/RQ + Redis) — the seam is
`start_run()` / `run_status()`, nothing else changes. Documented in docs/INTEGRATION.md.
"""
from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from ..db import SessionLocal
from ..services import jobs as jobs_svc
from ..services import orchestrator
from . import catalog
from .locker import audit, get_provider
from .models import EvidenceDocument, Order, OrderSource, _now

_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="qp-research")
_RUNS: dict[str, dict] = {}
_LOCK = threading.Lock()

#: What the progress panel lists while the pipeline works.
PHASES = [
    ("locate", "Locating the parcel"),
    ("clerk", "Fetching the deed & plat from the county"),
    ("federal", "Pulling the FEMA flood map & NGS control"),
    ("compose", "Composing & filing the job"),
]


def _set_run(order_id: str, **fields) -> dict:
    with _LOCK:
        run = _RUNS.setdefault(order_id, {"order_id": order_id, "state": "idle",
                                          "phase": "", "percent": 0, "error": "",
                                          "only": ""})
        run.update(fields)
        return dict(run)


def run_status(order_id: str) -> dict:
    with _LOCK:
        return dict(_RUNS.get(order_id) or {"order_id": order_id, "state": "idle",
                                            "phase": "", "percent": 0, "error": "",
                                            "only": ""})


# --------------------------------------------------------------------------- sources
def default_links(order: Order) -> dict[str, str]:
    """Resolve the "Open source" URL for every registry row *before* anything is fetched,
    so the researcher can always go to the county portal by hand. Uses the same resolution
    order as the pipeline: county-specific portal -> statewide portal -> NETROnline
    directory, which exists for every county in the country."""
    from ..data.county_platforms import (STATE_APPRAISER, STATE_DEED, lookup, netronline)
    from ..services.fema import MSC_HOME

    reg = lookup(order.county_fips) or {}
    directory = (netronline(order.state, order.county)
                 if order.state and order.county else "")
    clerk = reg.get("clerk_url") or STATE_DEED.get(order.state) or directory
    appraiser = reg.get("appraiser_url") or STATE_APPRAISER.get(order.state) or directory
    return {
        "parcel": appraiser,
        "appraiser": appraiser,
        "plat": clerk,
        "deed": clerk,
        "adjoiners": clerk,
        "easements": clerk,
        "prior_survey": clerk,
        "condo": clerk,
        "flood": MSC_HOME,
        "benchmarks": "https://geodesy.noaa.gov/NGSDataExplorer/",
        "glo": "https://glorecords.blm.gov/search/default.aspx",
        "zoning": catalog.zoning_link(order.city, order.county, order.state),
    }


def ensure_sources(session, order: Order) -> list[OrderSource]:
    """Create the per-order Source registry rows on first use, in catalog order.
    Also (re)fills any missing "Open source" link — the county is often only known after
    the first geocode, so rows created at intake would otherwise stay link-less."""
    have = {r.key: r for r in session.execute(
        select(OrderSource).where(OrderSource.order_id == order.id)).scalars().all()}
    links = default_links(order)
    rows = []
    for c in catalog.CATALOG:
        row = have.get(c["key"])
        if not row:
            row = OrderSource(org_id=order.org_id, order_id=order.id, key=c["key"],
                              label=c["label"], requirement=c["requirement"],
                              state="idle", message=c["blurb"])
            session.add(row)
        if not row.open_url and links.get(c["key"]):
            row.open_url = links[c["key"]]
        rows.append(row)
    return rows


def _ingest_step(provider, order: Order, step: dict, actor: str) -> int:
    """Copy the files one pipeline step downloaded into the order's Evidence Locker.
    Returns how many new documents were added (already-ingested files are skipped by hash)."""
    key = catalog.STEP_TO_KEY.get(step.get("key", ""))
    if not key:
        return 0
    added = 0
    for fname in step.get("downloaded") or []:
        path = jobs_svc.job_file(order.job_name, f"documents/{fname}")
        if not path:
            continue
        try:
            data = path.read_bytes()
        except Exception:  # noqa: BLE001
            continue

        # Re-fetching a source must REFRESH its document, not stack another copy beside it.
        # Identity is (source, filename), not the content hash: several of the generated
        # reports embed the fetch timestamp, so a byte-comparison never matches and every
        # re-run would add a duplicate row.
        with SessionLocal() as s:
            prior = s.execute(select(EvidenceDocument).where(
                EvidenceDocument.order_id == order.id,
                EvidenceDocument.source_key == key,
                EvidenceDocument.filename == fname,
                EvidenceDocument.deleted.is_(False))).scalars().first()
            prior_id = prior.id if prior else None
            prior_locked = bool(prior and prior.status == "locked")

        if prior_locked:
            # Locked evidence is never replaced behind the reviewer's back. They must
            # unlock deliberately if they want a fresher copy.
            continue
        if prior_id:
            provider.delete_document(order.org_id, order.id, prior_id,
                                     "replaced by a newer auto-fetch", actor)

        provider.add_document(
            order.org_id, order.id, filename=fname, data=data,
            doc_type=key, source_key=key, origin="auto_fetch",
            source_label=step.get("label", ""), source_url=step.get("source_url", "")
            or step.get("link", ""), actor=actor)
        added += 1
    return added


def _apply_result(order_id: str, result: dict, actor: str, only: str = "") -> None:
    """Fold a finished pipeline result into the order: property facts, source states,
    and the documents themselves."""
    provider = get_provider()
    with SessionLocal() as s:
        order = s.get(Order, order_id)
        if not order:
            return
        order.job_name = result.get("name") or order.job_name
        order.matched_address = result.get("matched_address") or order.matched_address
        order.county = result.get("county") or order.county
        order.county_fips = result.get("county_fips") or order.county_fips
        order.state = result.get("state") or order.state
        order.parcel_id = result.get("parcel_id") or order.parcel_id
        order.lat = result.get("lat") if result.get("lat") is not None else order.lat
        order.lon = result.get("lon") if result.get("lon") is not None else order.lon
        ensure_sources(s, order)
        s.commit()

    steps = {st.get("key"): st for st in (result.get("steps") or [])}

    # Lot area comes off the parcel step's data payload when the county service returned it.
    with SessionLocal() as s:
        order = s.get(Order, order_id)
        pstep = steps.get("parcel") or {}
        pdata = pstep.get("data") or {}
        if isinstance(pdata, dict):
            if pdata.get("land_sqft"):
                order.lot_area_sqft = float(pdata["land_sqft"])
            if pdata.get("land_acres"):
                order.lot_area_acres = float(pdata["land_acres"])
        s.commit()

    for c in catalog.CATALOG:
        if only and c["key"] != only:
            continue
        step = steps.get(c["step"]) if c["step"] else None
        with SessionLocal() as s:
            order = s.get(Order, order_id)
            row = s.execute(select(OrderSource).where(
                OrderSource.order_id == order_id, OrderSource.key == c["key"])
            ).scalars().first()
            if not row:
                continue
            if step is None:
                s.commit()
                continue
            row.open_url = step.get("link") or step.get("source_url") or row.open_url
            row.message = step.get("summary", "") or row.message
            row.last_run_at = _now()
            status = step.get("status", "")
            downloaded = step.get("downloaded") or []
            if downloaded:
                row.state = "fetched"
            elif status in ("link", "manual"):
                row.state = "failed" if c["auto"] else "unavailable"
                row.message = step.get("summary") or "No downloadable copy — open the source"
            elif status == "ok":
                row.state = "fetched"
            elif status in ("empty", "skipped"):
                row.state = "unavailable"
            elif not c["auto"]:
                # Link-only by design (GLO, zoning) — "no download" is the expected
                # resting state here, not a failure.
                row.state = "unavailable"
            else:
                row.state = "failed"
            s.commit()

        if step is not None:
            n = _ingest_step(provider, order, step, actor)
            if n:
                with SessionLocal() as s:
                    row = s.execute(select(OrderSource).where(
                        OrderSource.order_id == order_id, OrderSource.key == c["key"])
                    ).scalars().first()
                    if row:
                        row.doc_count = (row.doc_count or 0) + n
                    s.commit()


# ------------------------------------------------------------------------------ run
def _worker(order_id: str, actor: str, only: str) -> None:
    try:
        with SessionLocal() as s:
            order = s.get(Order, order_id)
            if not order:
                return
            snapshot = {"job_number": order.order_no, "order": order.order_no or order.id,
                        "address": order.address or order.matched_address,
                        "parcel_id": order.parcel_id, "state": order.state,
                        "county_fips": order.county_fips,
                        "survey_type": order.survey_type}

        _set_run(order_id, state="running", phase=PHASES[0][1], percent=8, only=only)
        result = orchestrator.run_research(
            snapshot["job_number"], snapshot["address"], snapshot["survey_type"], [],
            selected_state=snapshot["state"], selected_county_fips=snapshot["county_fips"],
            order_number=snapshot["order"],
            search_parcel_id="" if snapshot["address"] else snapshot["parcel_id"],
        )
        _set_run(order_id, phase=PHASES[3][1], percent=85)
        _apply_result(order_id, result, actor, only=only)
        _set_run(order_id, state="done", phase="", percent=100, error="")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _set_run(order_id, state="error", percent=0, error=str(e))
    finally:
        _clear_stuck_fetching(order_id)
        with SessionLocal() as s:
            order = s.get(Order, order_id)
            if order:
                audit(s, org_id=order.org_id, order_id=order_id, scope="locker",
                      action="auto_fetch",
                      title=("Auto-fetch — " + (catalog.BY_KEY[only]["label"] if only
                                                else "all sources")),
                      subtitle="Research hub", actor=actor,
                      detail={"state": run_status(order_id).get("state")})
                s.commit()


def _clear_stuck_fetching(order_id: str) -> None:
    """Whatever happened to the run, no row may be left spinning. A source still marked
    'fetching' once the worker has exited would show "Fetching…" in the UI forever."""
    with SessionLocal() as s:
        rows = s.execute(select(OrderSource).where(
            OrderSource.order_id == order_id,
            OrderSource.state == "fetching")).scalars().all()
        for r in rows:
            r.state = "failed"
            r.message = r.message or "Auto-fetch did not complete — open the source"
        if rows:
            s.commit()


def start_run(order_id: str, actor: str = "", only: str = "") -> dict:
    """Kick off an auto-fetch. `only` restricts the registry update to one source key
    (the per-source "Auto fetch" button); the pipeline itself always runs whole, because
    the county lookups share the parcel resolution."""
    cur = run_status(order_id)
    if cur.get("state") == "running":
        return cur
    if only:
        with SessionLocal() as s:
            row = s.execute(select(OrderSource).where(
                OrderSource.order_id == order_id, OrderSource.key == only)).scalars().first()
            if row:
                row.state = "fetching"
                s.commit()
    # NOTE: this only runs when no other run is in flight (guarded above), so a row can
    # never be left "fetching" by a request that did not actually start work.
    _set_run(order_id, state="running", phase=PHASES[0][1], percent=3, error="", only=only)
    _POOL.submit(_worker, order_id, actor, only)
    return run_status(order_id)
