"""Address geocoding + county resolution.

Primary geocoder is the **free US Census geocoder** (nationwide, keyless, and it returns
the county FIPS directly). Its TIGER address file has real coverage gaps, though — plenty of
valid addresses (new construction, some suburban/rural streets) return zero matches. So on a
Census miss we fall back to **ArcGIS**, then **Nominatim (OpenStreetMap)**, for the
coordinates, and resolve the county from those coordinates via the Census *coordinates*
geography endpoint. All three providers are free / keyless.

`provider` in the result says which geocoder matched, so the UI can flag fallback matches for
the user to eyeball.
"""
from .http import get_json

CENSUS_ADDR = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
CENSUS = CENSUS_ADDR  # back-compat alias (manifest "source" reference in the orchestrator)
CENSUS_COORD = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
ARCGIS = ("https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/"
          "findAddressCandidates")
NOMINATIM = "https://nominatim.openstreetmap.org/search"

_GEO = {"benchmark": "Public_AR_Current", "vintage": "Current_Current",
        "layers": "Counties", "format": "json"}


def _census_address(address: str) -> dict | None:
    """Census one-line address match — returns everything (address, lat/lon, county) at once."""
    j = get_json(CENSUS_ADDR, {"address": address, **_GEO})
    matches = j.get("result", {}).get("addressMatches", [])
    if not matches:
        return None
    m = matches[0]
    counties = m.get("geographies", {}).get("Counties", [])
    county = counties[0] if counties else {}
    return {
        "matched_address": m.get("matchedAddress", address),
        "lon": m["coordinates"]["x"],
        "lat": m["coordinates"]["y"],
        "county_name": county.get("BASENAME", ""),
        "county_fips": county.get("GEOID", ""),   # 5-digit state+county
        "state_fips": county.get("STATE", ""),
        "provider": "census",
    }


def _county_from_coords(lat: float, lon: float) -> tuple[str, str, str]:
    """(name, county_fips, state_fips) for a point — used when a fallback geocoder gives us
    only coordinates. Reverse point-in-county always works even where address match fails."""
    try:
        j = get_json(CENSUS_COORD, {"x": lon, "y": lat, **_GEO})
        c = j.get("result", {}).get("geographies", {}).get("Counties", [])
        if c:
            return c[0].get("BASENAME", ""), c[0].get("GEOID", ""), c[0].get("STATE", "")
    except Exception:
        pass
    return "", "", ""


def _arcgis(address: str):
    """ArcGIS World geocoder — free/keyless for single lookups. Returns (lat, lon, matched)."""
    try:
        j = get_json(ARCGIS, {"SingleLine": address, "f": "json", "outFields": "Match_addr",
                              "countryCode": "USA", "maxLocations": 1})
        cands = j.get("candidates", [])
        if cands and cands[0].get("score", 0) >= 80:
            c = cands[0]
            return c["location"]["y"], c["location"]["x"], c.get("address", address)
    except Exception:
        pass
    return None


def _nominatim(address: str):
    """Nominatim (OpenStreetMap) — free/keyless. Returns (lat, lon, matched)."""
    try:
        j = get_json(NOMINATIM, {"q": address, "format": "json", "limit": 1,
                                 "countrycodes": "us"})
        if j:
            return float(j[0]["lat"]), float(j[0]["lon"]), j[0].get("display_name", address)
    except Exception:
        pass
    return None


def geocode(address: str) -> dict:
    """Return matched address, lat/lon, county name + FIPS, state FIPS, and provider.
    Nationwide, no API key. Falls back through ArcGIS and Nominatim when the Census file
    has no match, so real addresses missing from TIGER still resolve."""
    hit = _census_address(address)
    if hit:
        return hit
    for name, fn in (("arcgis", _arcgis), ("nominatim", _nominatim)):
        res = fn(address)
        if not res:
            continue
        lat, lon, matched = res
        cname, cfips, sfips = _county_from_coords(lat, lon)
        return {
            "matched_address": matched, "lat": lat, "lon": lon,
            "county_name": cname, "county_fips": cfips, "state_fips": sfips,
            "provider": name,
        }
    raise ValueError(f"No geocoder match for: {address}")


# FIPS state code -> USPS abbreviation (for building source directory links)
STATE_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}
