"""US states + counties reference for the guided form dropdowns.

County list is a bundled offline snapshot of the Census TIGERweb county layer
(all 3,235 counties/equivalents nationwide) so the dropdowns work instantly and
without a network call. Each county is annotated with whatever records-platform
info exists for it in `county_platforms.REGISTRY`.
"""
import functools
import json
import pathlib

from .county_platforms import REGISTRY, netronline, PLATFORM_LABEL, STATE_PARCEL, STATE_DEED
from ..services.http import get_json, post_json

_DATA = pathlib.Path(__file__).with_name("_counties_raw.json")

# TIGERweb layers used to enumerate the cities/places that fall inside a county.
_TIGER_COUNTY = ("https://tigerweb.geo.census.gov/arcgis/rest/services/"
                 "TIGERweb/State_County/MapServer/1/query")
_TIGER_PLACES = ("https://tigerweb.geo.census.gov/arcgis/rest/services/"
                 "TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer")
_PLACE_LAYERS = (4, 5)  # 4 = Incorporated Places, 5 = Census Designated Places

# FIPS state code -> (USPS abbr, full name). 50 states + DC + territories.
STATES: dict[str, tuple[str, str]] = {
    "01": ("AL", "Alabama"), "02": ("AK", "Alaska"), "04": ("AZ", "Arizona"),
    "05": ("AR", "Arkansas"), "06": ("CA", "California"), "08": ("CO", "Colorado"),
    "09": ("CT", "Connecticut"), "10": ("DE", "Delaware"),
    "11": ("DC", "District of Columbia"), "12": ("FL", "Florida"),
    "13": ("GA", "Georgia"), "15": ("HI", "Hawaii"), "16": ("ID", "Idaho"),
    "17": ("IL", "Illinois"), "18": ("IN", "Indiana"), "19": ("IA", "Iowa"),
    "20": ("KS", "Kansas"), "21": ("KY", "Kentucky"), "22": ("LA", "Louisiana"),
    "23": ("ME", "Maine"), "24": ("MD", "Maryland"), "25": ("MA", "Massachusetts"),
    "26": ("MI", "Michigan"), "27": ("MN", "Minnesota"), "28": ("MS", "Mississippi"),
    "29": ("MO", "Missouri"), "30": ("MT", "Montana"), "31": ("NE", "Nebraska"),
    "32": ("NV", "Nevada"), "33": ("NH", "New Hampshire"), "34": ("NJ", "New Jersey"),
    "35": ("NM", "New Mexico"), "36": ("NY", "New York"),
    "37": ("NC", "North Carolina"), "38": ("ND", "North Dakota"), "39": ("OH", "Ohio"),
    "40": ("OK", "Oklahoma"), "41": ("OR", "Oregon"), "42": ("PA", "Pennsylvania"),
    "44": ("RI", "Rhode Island"), "45": ("SC", "South Carolina"),
    "46": ("SD", "South Dakota"), "47": ("TN", "Tennessee"), "48": ("TX", "Texas"),
    "49": ("UT", "Utah"), "50": ("VT", "Vermont"), "51": ("VA", "Virginia"),
    "53": ("WA", "Washington"), "54": ("WV", "West Virginia"), "55": ("WI", "Wisconsin"),
    "56": ("WY", "Wyoming"), "60": ("AS", "American Samoa"), "66": ("GU", "Guam"),
    "69": ("MP", "Northern Mariana Islands"), "72": ("PR", "Puerto Rico"),
    "78": ("VI", "U.S. Virgin Islands"),
}

ABBR_TO_FIPS = {abbr: fips for fips, (abbr, _name) in STATES.items()}


@functools.lru_cache(maxsize=1)
def _counties_raw() -> dict[str, list[dict]]:
    return json.loads(_DATA.read_text())


def state_fips(state: str) -> str:
    """Accept a 2-digit FIPS or a USPS abbreviation and return the FIPS code."""
    s = (state or "").strip().upper()
    if s in STATES:
        return s
    return ABBR_TO_FIPS.get(s, "")


def states() -> list[dict]:
    """All states/territories that have at least one county in the dataset."""
    have = set(_counties_raw().keys())
    out = [{"fips": f, "abbr": a, "name": n}
           for f, (a, n) in STATES.items() if f in have]
    return sorted(out, key=lambda x: x["name"])


def _annotate(fips: str, abbr: str, name: str, basename: str) -> dict:
    reg = REGISTRY.get(fips)
    # Mirror the real resolution order the pipeline uses, so the dropdown never advertises
    # less (or more) than a job will actually produce:
    #   parcels — county gis_rest, else the statewide service (services/parcel.py)
    #   deeds   — county clerk_url, else a statewide index, else NETROnline (services/clerk.py)
    # Without the statewide arms, every FL county but two reported has_parcel_api=False while
    # the DOR layer covers all 67, and 144 GA counties showed a NETROnline link although the
    # job hands them GSCCCA.
    return {
        "fips": fips,
        "name": name,               # e.g. "Pinellas County"
        "basename": basename,       # e.g. "Pinellas"
        # A statewide layer only counts here if it can answer an ADDRESS search; Ohio's ODNR
        # layer carries PIN but no situs (id_only), so its counties need their own gis_rest.
        "has_parcel_api": bool((reg and reg.get("gis_rest"))
                               or not (STATE_PARCEL.get(abbr) or {"id_only": True}).get("id_only")),
        "clerk_platform": (reg or {}).get("clerk_platform"),
        "clerk_url": ((reg or {}).get("clerk_url") or STATE_DEED.get(abbr)
                      or netronline(abbr, basename)),
        "clerk_platform_label": PLATFORM_LABEL.get(
            (reg or {}).get("clerk_platform", "unknown"), "Directory link"),
        "appraiser_url": (reg or {}).get("appraiser_url"),
        "in_registry": bool(reg),
    }


def counties(state: str) -> list[dict]:
    """County list for a state (FIPS or abbr), annotated with portal availability."""
    fips = state_fips(state)
    if not fips:
        return []
    abbr = STATES.get(fips, ("", ""))[0]
    rows = _counties_raw().get(fips, [])
    return [_annotate(c["fips"], abbr, c["name"], c["basename"]) for c in rows]


def county_name(county_fips: str) -> str:
    """BASENAME for a 5-digit county FIPS, or '' if unknown."""
    st = county_fips[:2]
    for c in _counties_raw().get(st, []):
        if c["fips"] == county_fips:
            return c["basename"]
    return ""


@functools.lru_cache(maxsize=512)
def cities(county_fips: str) -> tuple[str, ...]:
    """Cities / places that fall inside a county — used to populate the City
    dropdown so the user can pin the address to a real place the county recognizes.

    Live from Census TIGERweb, works for any county nationwide. Cached per county.
    Returns () if the lookup fails (the UI then accepts a free-typed city).
    """
    fips = (county_fips or "").strip()
    if len(fips) != 5:
        return ()
    try:
        g = get_json(_TIGER_COUNTY, {
            "where": f"GEOID='{fips}'", "outFields": "GEOID",
            "returnGeometry": "true", "outSR": "4326", "f": "json",
        })
        feats = g.get("features", [])
        if not feats:
            return ()
        geom = json.dumps({"rings": feats[0]["geometry"]["rings"],
                           "spatialReference": {"wkid": 4326}})
        names: set[str] = set()
        for layer in _PLACE_LAYERS:
            q = post_json(f"{_TIGER_PLACES}/{layer}/query", {
                "geometry": geom, "geometryType": "esriGeometryPolygon",
                "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
                "outFields": "BASENAME", "returnGeometry": "false", "f": "json",
            })
            for f in q.get("features", []):
                nm = f.get("attributes", {}).get("BASENAME")
                if nm:
                    names.add(nm)
        return tuple(sorted(names))
    except Exception:  # noqa: BLE001 — dropdown falls back to free text
        return ()
