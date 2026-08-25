"""Clerk / Recorder official-records references for deed & plat.

Clerk portals expose NO public API. Full auto-download requires a per-platform browser
adapter (Acclaim / Landmark / Eagle) - stubbed here with a clear extension point. For v1
the app returns the correct official-records search URL plus the book/page/legal hints
pulled from parcel data, so a human (or a future adapter) can retrieve the images in one click.
"""
from . import clerk_scraper
from ..data.county_platforms import lookup, netronline, PLATFORM_LABEL, STATE_DEED, STATE_PLAT


def references(county_fips: str, state_abbr: str, county_name: str,
               parcel_hints: dict | None = None) -> dict:
    reg = lookup(county_fips)
    platform = (reg or {}).get("clerk_platform", "unknown")
    # Clerk/deed link: county-specific portal → else a statewide deed index (e.g. GA GSCCCA,
    # applied to every county in that state) → else the NETROnline county directory.
    state_deed = STATE_DEED.get(state_abbr)
    clerk_url = ((reg or {}).get("clerk_url") or state_deed
                 or netronline(state_abbr, county_name))
    # Plat link: some recorders index plats SEPARATELY from deeds (GA's GSCCCA runs a distinct
    # "Plat Index"), so the plat step needs its own URL. County plat portal → statewide plat
    # index → the deed/clerk URL. That last fallback keeps every state without a declared plat
    # source behaving exactly as before.
    plat_url = ((reg or {}).get("plat_url") or STATE_PLAT.get(state_abbr) or clerk_url)
    return {
        "county": county_name,
        "platform": platform,
        "platform_label": PLATFORM_LABEL.get(platform, platform),
        "official_records_search": clerk_url,
        "plat_search": plat_url,
        "appraiser_url": (reg or {}).get("appraiser_url"),
        "directory_url": netronline(state_abbr, county_name),
        "note": (reg or {}).get("clerk_note", ""),
        "search_hints": parcel_hints or {},
        "targets": ["deed", "plat"],
        "automation_status": (
            "auto-download available (deed + plat)"
            if clerk_scraper.has_adapter(county_fips) or platform in _ADAPTERS else
            "deep-link only (adapter not yet built for this platform)"
        ),
    }


# ---- extension point: browser adapters per platform -------------------------------
# Each adapter, when implemented, takes (clerk_url, search_hints) and downloads deed/plat
# PDFs using Playwright (accept disclaimer -> search by book/page or name -> save image).
# Register implemented adapters here so `references()` reports them as automated.
_ADAPTERS: dict[str, object] = {
    # "acclaim": AcclaimAdapter,
    # "landmark": LandmarkAdapter,
    # "eagle": EagleAdapter,
}


def summarize(r: dict) -> str:
    return f"{r['platform_label']} - {r['automation_status']}"
