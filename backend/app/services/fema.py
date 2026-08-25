"""FEMA National Flood Hazard Layer (NFHL) - flood zone + FIRM panel. Nationwide, free, no key."""
import datetime

from .http import get_json

NFHL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
MSC_HOME = "https://msc.fema.gov/portal/home"


def _fmt_date(v) -> str:
    """FEMA returns EFF_DATE as epoch milliseconds (ArcGIS f=json). Render as YYYY-MM-DD."""
    if v in (None, "", 0):
        return ""
    try:
        return datetime.datetime.utcfromtimestamp(int(v) / 1000).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return str(v)


def _query(layer: int, lat: float, lon: float, fields: str) -> list[dict]:
    j = get_json(f"{NFHL}/{layer}/query", {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": fields,
        "returnGeometry": "false",
        "f": "json",
    })
    return [f.get("attributes", {}) for f in j.get("features", [])]


def _pick_by_prefix(items: list[dict], key: str, prefix: str) -> dict:
    """First item whose `key` starts with `prefix`, else the first item.

    At county lines the point query returns adjacent panels/zones from neighbouring
    counties; the correct one is the panel whose number matches this county's prefix."""
    if prefix:
        for it in items:
            if str(it.get(key) or "").startswith(prefix):
                return it
    return items[0] if items else {}


def flood(lat: float, lon: float, county_fips: str = "") -> dict:
    zones = _query(28, lat, lon, "FLD_ZONE,ZONE_SUBTY,STATIC_BFE,SFHA_TF,DFIRM_ID")
    panels = _query(3, lat, lon, "FIRM_PAN,PANEL,SUFFIX,EFF_DATE")
    # County/community prefix, e.g. "12105" (Polk). Prefer the passed FIPS; else derive
    # it from the zone's DFIRM_ID. Used to keep the panel/zone in the right county.
    prefix = (county_fips or "")[:5] or str((zones[0] if zones else {}).get("DFIRM_ID") or "")[:5]
    z0 = _pick_by_prefix(zones, "DFIRM_ID", prefix) if zones else {}
    p0 = _pick_by_prefix(panels, "FIRM_PAN", prefix)
    bfe = z0.get("STATIC_BFE")
    bfe_txt = "N/A" if bfe in (None, -9999) else str(bfe)
    return {
        "flood_zone": z0.get("FLD_ZONE"),
        "zone_subtype": z0.get("ZONE_SUBTY"),
        "in_sfha": z0.get("SFHA_TF"),           # "T" = Special Flood Hazard Area
        "static_bfe": bfe_txt,
        "firm_panel": p0.get("FIRM_PAN"),
        "panel_suffix": p0.get("SUFFIX"),
        "panel": p0.get("PANEL"),
        "effective_date": _fmt_date(p0.get("EFF_DATE")),
        "map_service_center": MSC_HOME,
        "raw_zones": zones,
        "raw_panels": panels,
    }


def summarize(f: dict) -> str:
    z = f.get("flood_zone") or "unknown"
    sfha = "SFHA" if f.get("in_sfha") == "T" else "not in SFHA"
    panel = f.get("firm_panel") or "?"
    return f"Zone {z} ({sfha}), FIRM panel {panel}, BFE {f.get('static_bfe')}"
