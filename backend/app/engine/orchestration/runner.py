"""The engine research run — the production replacement for the POC's ``run_research``.

Two phases, cleanly separated:

  Phase A — context:   ``resolve_property_context`` (geocode → parcel → references)
  Phase B — documents: ``build_steps`` (per-source adapters, honoring ``include``)

Everything the old monolith did ad-hoc is now either a context-phase concern or a
per-source adapter concern.  The runner itself does not branch per source — it just
wires the two phases, builds the canonical ``ResearchResult``, and writes the audit
artifacts (manifest + result.json) into the run's staging folder.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from app.engine.contracts import JobState, ResearchResult

from . import context as ctx_mod
from .folders import write_manifest, write_result
from .steps import build_steps


def run_research(job_number: str = "", address: str = "",
                 survey_type: str = "Residential Land Survey", include=None,
                 selected_state: str = "", selected_county_fips: str = "",
                 order_number: str = "", search_parcel_id: str = "") -> ResearchResult:
    """Run the full research pipeline for an address or parcel ID.

    ``include``: optional iterable of document-step keys (e.g. ``["deed"]``).
    Only those sources are fetched; the rest are skipped entirely (no work, no
    stale failures).  ``None`` fetches every document in the reference set.

    Returns a canonical ``ResearchResult``; the exact same payload is also
    persisted to ``<folder>/result.json`` and the audit trail to ``manifest.json``.
    """
    ctx = ctx_mod.resolve_property_context(
        job_number=job_number,
        address=address,
        survey_type=survey_type,
        selected_state=selected_state,
        selected_county_fips=selected_county_fips,
        order_number=order_number,
        search_parcel_id=search_parcel_id,
    )

    steps = build_steps(ctx, include=include)

    _q = quote_plus(ctx.matched_address or address)
    map_links = [
        {"label": "Google Maps", "url": f"https://www.google.com/maps/search/?api=1&query={ctx.lat},{ctx.lon}"},
        {"label": "Google Street View", "url":
            f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={ctx.lat},{ctx.lon}"},
        {"label": "Bing Maps (aerial)", "url":
            f"https://www.bing.com/maps?cp={ctx.lat}~{ctx.lon}&lvl=19&style=a"},
        {"label": "County Property Appraiser", "url": ctx.appraiser_url},
        {"label": "Search address on Google", "url": f"https://www.google.com/search?q={_q}"},
    ]

    result = ResearchResult(
        job_number=ctx.job_number,
        order=ctx.order,
        parcel_id=ctx.parcel_id,
        address=ctx.address,
        matched_address=ctx.matched_address,
        county=ctx.county,
        county_fips=ctx.county_fips,
        state=ctx.state,
        lat=ctx.lat,
        lon=ctx.lon,
        name=ctx.name,
        geocoder=ctx.geocoder,
        map_links=map_links,
        folder=str(ctx.folder.parent),        # frozen semantic: job-level folder
        docs_dir=str(ctx.folder),             # additive: research staging dir (has documents/)
        steps=steps,
        warnings=list(ctx.warnings),
        completed_utc=ctx_mod.now_utc(),
        job_state=JobState.completed,
        survey_type=ctx.survey_type,
    )

    meta = {
        "job_number": ctx.job_number, "order": ctx.order, "parcel_id": ctx.parcel_id,
        "address": ctx.address, "survey_type": ctx.survey_type,
        "matched_address": ctx.matched_address, "county": ctx.county,
        "county_fips": ctx.county_fips, "state": ctx.state,
        "lat": ctx.lat, "lon": ctx.lon,
        "warnings": list(ctx.warnings),
    }
    write_manifest(ctx.folder, ctx.manifest, meta)
    write_result(ctx.folder, result.model_dump(mode="json"))
    return result