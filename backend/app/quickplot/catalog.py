"""The Source registry catalog — the ordered list of research sources the right-hand rail
renders, and the mapping from each one to the v1 pipeline step that produces it.

Order and labels come from the QuickPlot design. Nine of the eleven entries are produced by
`services/orchestrator.run_research`; `zoning` is link-only (no nationwide queryable source
exists, so we hand the researcher the municipal code search) and `condo` only applies to
condominium units.
"""
from __future__ import annotations

from urllib.parse import quote_plus

#: key -> (label, requirement, v1 orchestrator step key or "" for link-only)
CATALOG: list[dict] = [
    {"key": "parcel", "label": "Parcel record / Parcel ID", "requirement": "mandatory",
     "step": "parcel", "auto": True,
     "blurb": "County and federal sources for parcel"},
    {"key": "appraiser", "label": "Property appraiser / Tax record", "requirement": "mandatory",
     "step": "appraiser", "auto": True,
     "blurb": "County and federal sources for parcel"},
    {"key": "plat", "label": "Recorded plat / Subdivision map", "requirement": "mandatory",
     "step": "plat", "auto": True,
     "blurb": "County and federal sources for parcel"},
    {"key": "deed", "label": "Deed — subject parcel", "requirement": "mandatory",
     "step": "deed", "auto": True,
     "blurb": "County and federal sources for parcel"},
    {"key": "adjoiners", "label": "Deed — adjoining parcel", "requirement": "mandatory",
     "step": "adjoiners", "auto": True,
     "blurb": "County and federal sources for parcel"},
    {"key": "easements", "label": "Easement / ROW / CC&Rs", "requirement": "mandatory",
     "step": "easements", "auto": True,
     "blurb": "County and federal sources for parcel"},
    {"key": "flood", "label": "FEMA flood zone / FIRM", "requirement": "conditional",
     "step": "flood", "auto": True,
     "blurb": "FEMA National Flood Hazard Layer"},
    {"key": "zoning", "label": "Zoning / Setback ordinance", "requirement": "recommended",
     "step": "", "auto": False,
     "blurb": "Municipal code — link only, no queryable source"},
    {"key": "prior_survey", "label": "Prior survey / Field notes", "requirement": "recommended",
     "step": "prior_survey", "auto": True,
     "blurb": "County and federal sources for parcel"},
    {"key": "benchmarks", "label": "Survey control / Benchmarks", "requirement": "recommended",
     "step": "benchmarks", "auto": True,
     "blurb": "NOAA National Geodetic Survey"},
    {"key": "glo", "label": "GLO / PLSS plats & field notes", "requirement": "conditional",
     "step": "glo", "auto": False,
     "blurb": "BLM General Land Office records"},
    {"key": "condo", "label": "Condominium declaration", "requirement": "conditional",
     "step": "condo", "auto": True,
     "blurb": "County and federal sources for parcel"},
]

BY_KEY = {c["key"]: c for c in CATALOG}
STEP_TO_KEY = {c["step"]: c["key"] for c in CATALOG if c["step"]}

#: What the "Document Type" dropdown in the evidence table offers. Same keys as the
#: registry so a document dropped in manually can satisfy a checklist row.
DOC_TYPES = [{"key": c["key"], "label": c["label"]} for c in CATALOG] + [
    {"key": "order_intake", "label": "Order Intake"},
    {"key": "correspondence", "label": "Correspondence"},
    {"key": "other", "label": "Other / Supporting"},
]

#: Rows the Research Checklist drawer scores completion against.
CHECKLIST_KEYS = ["parcel", "appraiser", "plat", "deed", "adjoiners", "easements",
                  "flood", "zoning"]


def zoning_link(city: str, county: str, state: str) -> str:
    """Municipal-code search for the jurisdiction. No nationwide zoning API exists, so the
    honest answer is a targeted search rather than a fabricated endpoint."""
    where = " ".join(x for x in (city, county, state) if x).strip()
    return ("https://www.google.com/search?q="
            + quote_plus(f"{where} zoning ordinance setback requirements municipal code"))
