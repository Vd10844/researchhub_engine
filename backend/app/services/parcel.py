"""Parcel data resolution + parcel-identity validation.

Point-in-polygon against a county MapServer or the statewide FeatureServer. Geocoders
return a street-centerline point that can land in the road ROW or on a NEIGHBORING
parcel, so:
  - we gather all candidate parcels at the point (and a small buffer if the point misses),
  - pick the candidate whose situs address matches the searched house number,
  - and flag the result when we can't confirm the address matches.
Also extracts the situs address and lot area (sq ft / acres) for verification + costing.
"""
import functools
import json
import math
import re

from .http import get_json
from ..data.county_platforms import lookup, netronline, STATE_PARCEL


def _norm(k: str) -> str:
    return k.lower().replace(" ", "").replace("-", "").replace("_", "")


def _attr(attrs: dict, keys: tuple) -> object:
    for k, v in attrs.items():
        nk = _norm(k)
        if any(key in nk for key in keys) and v not in (None, "", " ", 0, "0"):
            return v
    return None


def _isblank(v) -> bool:
    """True for empty / whitespace / literal null-string values ('NULL', 'None', 'N/A') that some
    layers store instead of real nulls — so they don't get concatenated into a composed situs."""
    return v is None or str(v).strip().upper() in ("", "NULL", "NONE", "N/A", "<NULL>")


def _compose_situs(attrs: dict, exclude: tuple = ()) -> str:
    """Assemble a street situs from split component fields when a layer has NO single situs
    field — house number + directional + street name + type (e.g. Will County IL Parcels_LY:
    HOUSENUMBE + PREFIXDIRE + STREETNAME + SUFFIXTYPE). `exclude` (per-county situs_exclude) is
    honored here too, so a mailing field the layer also carries (e.g. Whitfield GA address1 = a
    PO box) can't leak into the composed street via the generic "addr" token."""
    excl = tuple(_norm(e) for e in exclude)
    # Skip owner-mailing component fields — a CAMA layer often carries BOTH Property_Street* (the
    # situs) AND Owner_Street* (the owner's mailing address); we must compose from the situs set.
    def _mail(kl):
        return "owner" in kl or "mail" in kl
    taken = set()   # normalized keys already consumed by a component, so the street-name pass
                    # can't re-use the house-number field as the street name (Worth GA
                    # ADDRESS_NU matches both "addressnu" and the name pass's "addr" -> "201 201")
    def find(*frags):
        for k, v in attrs.items():
            kl = _norm(k)
            if kl not in excl and kl not in taken and not _mail(kl) \
                    and any(f in kl for f in frags) and not _isblank(v):
                taken.add(kl)
                return str(v).strip()
        return ""
    num = find("housenumb", "houseno", "housenum", "stnumber", "stnum", "strnum", "addrnum",
               "addressnu", "situsnum", "addno", "propnum", "propertynum", "bldgnum", "locations",
               "streetnum")
    # propertynum=Muscogee; bldgnum=Jefferson AL Bldg_Number; strnum=Greenville SC STRNUM;
    # housenum=Platte MO HOUSENUM; locations=Ascension LA LOCATION_S (site number);
    # streetnum=Newton GA StreetNumb + Stewart GA STREET_NUM; addressnu=Worth GA ADDRESS_NU
    # (matches ADDRESS_NUM too, since "addressnu" is a prefix of it)
    if num.endswith(".0"):   # float house-number field (e.g. GA sgrcmaps HOUSE_NO=2407.0) -> "2407"
        num = num[:-2]
    predir = find("predir", "prefixdir", "streetdir", "stdir", "direction1",  # direction1=Muscogee
                  "situsdir")   # situsdir=Orleans LA SITUS_DIR
    name = ""
    for k, v in attrs.items():
        kl = _norm(k)
        if kl not in excl and kl not in taken and not _mail(kl) \
                and ("streetname" in kl or "strname" in kl or "stname" in kl or "streetnam" in kl
                     or "locate" in kl or "location1" in kl or "situsstr" in kl or "road" in kl
                     or "addr" in kl or "street" in kl or ("str" in kl and "name" in kl)) \
                and "type" not in kl and "dir" not in kl and "num" not in kl \
                and "city" not in kl and "zip" not in kl \
                and not _isblank(v):
            name = str(v).strip()
            taken.add(kl)
            break
    suftype = find("suffixtype", "streettype", "sttype", "posttype", "strtype",
                   "situstype", "rdtype")   # situstype=Orleans LA SITUS_TYPE; situsstr=Orleans
    # SITUS_STREET; road/rdtype=GMASS GA schema Road + Rd_Type (Polk/Chattooga/Jefferson)
    sufdir = find("suffixdir", "postdir", "direction2")   # direction2=Muscogee Property_Direction2
    if num and name:
        return " ".join(p for p in (num, predir, name, suftype, sufdir) if p)
    return ""


def _has_street(v) -> bool:
    """A usable situs value: contains BOTH a letter (street name) and a digit (house number). Stops
    component fields that also match an 'address' alias — a bare number (Ottawa MI AddressNumber=62.0)
    or a lone directional (AddressDir='W') — from being mistaken for the full site address."""
    s = str(v)
    return v not in (None, "", " ", 0, "0") and any(c.isalpha() for c in s) and any(c.isdigit() for c in s)


def situs_of(attrs: dict, exclude: tuple = (), compose: bool = False) -> str:
    """The parcel's situs (site) street address.

    `exclude` is a per-county tuple of field names to ignore (normalized) — needed when a layer
    has a same-named field that is NOT the situs (e.g. Coweta GA WinGAP `StreetAddress` is the
    owner MAILING address). `compose=True` forces assembly from split components (skips the
    direct-field passes) for layers with no real single situs field.
    """
    if compose:
        return _compose_situs(attrs, exclude)
    excl = tuple(_norm(e) for e in exclude)
    # Prefer a FULL situs/site address field. Skip owner-mailing / component-only fields — zip,
    # city, state (IN has dlgf_prop_address AND ..._zip; Kent MI has PROPERTYADDRESS AND
    # PROPADDRESSCITY — both share the "propaddr" prefix, so the city field must be excluded).
    # pstl/postal: the national parcel standard pairs SITEADRESS (situs) with PSTLADRESS (owner
    # mailing) — both contain "adress", so the postal one must be excluded.
    # billing/taxpayer: rolls that name the owner's mailing address Billing_Address_1 or
    # PPTaxPayerAddress — neither is caught by "mail". Evans County GA's parcel layer carries no
    # other address field at all, so taking it as the situs would match the address to wherever
    # the tax bill is posted.
    # type/desc: classification fields (e.g. RI E911_Type='C1', E911Desc='Commercial') can match an
    # address alias and pass the letter+digit guard — they are never a street address, so skip them.
    skip = ("zip", "mail", "billing", "owner", "city", "state", "pstl", "postal", "taxpayer",
            "type", "desc")
    # Pass 0: a field explicitly named like a COMPLETE street address (…full…/…situs…) wins, so
    # component fields sharing the same prefix (PropAddress_Num/_City) can't shadow the street.
    for k, v in attrs.items():
        kl = _norm(k)
        if kl not in excl and "addr" in kl and ("full" in kl or "complete" in kl or "situs" in kl) \
                and not any(s in kl for s in skip) and _has_street(v):
            return " ".join(str(v).split())
    # Pass 1: first field whose name contains a known situs alias (alias order = priority).
    aliases = ("situsaddress", "situsaddr", "siteaddress", "siteaddr", "siteadd", "phyaddr",
               "physaddr", "physicala", "propaddr", "propadd", "propertya", "proploc", "locaddr",
               "e911", "fulladdr", "fuladd", "parceladd", "paradd", "boaaddr", "location",
               "address", "adress", "situs", "site")
    # physicala=Glynn GA PHYSICAL_A (truncated PHYSICAL_ADDRESS); boaaddr=Rockdale GA BOA_Addres
    # (full "1620 WALNUT ST SE")
    # propertya=Riley KS Property_A (truncated Property_Address); won't match property_class/_use/
    # _id. paradd=Athens-Clarke GA PAR_ADD (parcel/site address)
    # parceladd=UT PARCEL_ADD; address=DC ADDRESS1; adress=WI SITEADRESS (misspelled national std,
    # one D); fuladd=ID propfuladd (one L); siteadd=MS SITEADD / propadd=StL MO PROP_ADD (no "r")
    for a in aliases:
        for k, v in attrs.items():
            kl = _norm(k)
            if kl not in excl and a in kl and not any(s in kl for s in skip) \
                    and _has_street(v):
                return " ".join(str(v).split())
    # Pass 2: assemble from split components (this layer has no single situs field).
    return _compose_situs(attrs, exclude)


def _situs_fn(reg):
    """A situs extractor honoring a county's situs_exclude / compose_situs overrides (or default)."""
    if not reg:
        return situs_of
    exclude = tuple(reg.get("situs_exclude", ()) or ())
    compose = bool(reg.get("compose_situs", False))
    if not exclude and not compose:
        return situs_of
    return lambda a: situs_of(a, exclude=exclude, compose=compose)


def land_area_of(attrs: dict):
    """Return (sq_ft, acres) for the parcel's LAND (not building) area, if present."""
    sqft = _attr(attrs, ("lndsqfoot", "landsqft", "landsquare", "sqfoot"))
    acres = _attr(attrs, ("gisacres", "acres", "acreage"))
    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    sqft, acres = num(sqft), num(acres)
    if sqft and not acres:
        acres = round(sqft / 43560.0, 3)
    if acres and not sqft:
        sqft = round(acres * 43560.0)
    return sqft, acres


def _house(addr: str) -> str:
    a = (addr or "").split(",")[0].strip()
    m = re.match(r"\s*(\d+)", a)
    if m:
        return m.group(1)
    # Some layers store the house number LAST (e.g. TN "N ROYAL ST 214"); fall back to a
    # trailing number when there's no leading one.
    m2 = re.search(r"(\d+)\s*$", a)
    return m2.group(1) if m2 else ""


# Street suffixes / directionals dropped before comparing street *names* so that
# "526 HAMPTON AVE" and "526 HAMPTON AVENUE" (or a situs with no suffix) still match.
_SUFFIX = {"AVE", "AVENUE", "ST", "STREET", "RD", "ROAD", "DR", "DRIVE", "LN", "LANE",
           "BLVD", "BOULEVARD", "CT", "COURT", "CIR", "CIRCLE", "PL", "PLACE", "WAY",
           "TER", "TERRACE", "HWY", "HIGHWAY", "PKWY", "PARKWAY", "TRL", "TRAIL",
           "LOOP", "RUN", "PASS", "PT", "POINT", "SQ", "SQUARE", "PATH", "XING",
           "CV", "COVE", "BND", "BEND", "ROW", "WALK", "PLZ", "PLAZA"}
_DIR = {"N", "S", "E", "W", "NE", "NW", "SE", "SW",
        "NORTH", "SOUTH", "EAST", "WEST"}


def _street_tokens(addr: str) -> list:
    """Significant street-name tokens: drop the house number, unit, suffix and directional."""
    first = (addr or "").split(",")[0].strip()
    toks = first.split()
    if toks and re.match(r"^\d+[A-Za-z]?$", toks[0]):  # leading house-number token
        toks = toks[1:]
    if toks and re.match(r"^\d+$", toks[-1]):          # trailing house number (TN-style)
        toks = toks[:-1]
    toks = [re.sub(r"[^A-Za-z0-9]", "", t).upper() for t in toks]
    return [t for t in toks if t and t not in _SUFFIX and t not in _DIR]


def _addr_match(search: str, situs: str):
    """True/False/None — does a parcel's situs match the searched address?

    Compares house number and (when both sides carry a street name) the street.
    Returns None when there isn't enough to compare (e.g. no house number on either).
    """
    sh, ch = _house(search), _house(situs)
    if not sh or not ch:
        return None
    if sh != ch:
        return False
    st, ct = set(_street_tokens(search)), set(_street_tokens(situs))
    if st and ct:
        return bool(st & ct)  # share at least one street-name token
    return True  # house matches; street not comparable on one side


# Field-name fragments the app actually reads (situs, owner, parcel id, hints, lot area). Used to
# build an explicit, SHORT outFields list — because outFields='*' silently returns 0 features on
# some layers (a field literally named GEOMETRY, e.g. East Baton Rouge LA), and some ArcGIS
# servers also return 0 when too many fields are requested at once.
_KEEP_FIELDS = ("addr", "adress", "situs", "site", "location", "loc", "phy", "prop", "e911",
                "full", "street", "owner", "name", "parcel", "pin", "apn", "folio", "strap",
                "acct", "account", "assess", "prono", "legal", "book", "page", "plat", "instr",
                "deed", "subdiv", "lot", "block", "acre", "sqf", "geoid", "upc", "tms", "gpin",
                "gpn", "span", "altkey", "locator", "taxlot", "maptax", "ppin", "sbl", "id",
                "num", "hous", "taxpayer", "tmk", "link", "par_ad", "road", "dir", "type")
                # road/dir/type: split-situs component fields (GA GMASS Road/Rd_Type, WinGAP
                # STDIRECT/STTYPE) needed by _compose_situs — else the composed situs loses its
                # street name/suffix/direction. situs_of already skips type/desc so keeping them
                # here can't produce a false single-field situs. par_ad=Athens-Clarke GA
                # PAR_ADD situs (kept-list matches raw lowercase, so the underscore is literal).
                # tmk=Hawaii Tax Map Key (the parcel
                # id); link=per-parcel portal/deed links (qpub_link, DeedLink). num/hous: the
                # house-number fields needed to compose a
                                 # split situs (e.g. Greenville SC STRNUM) — else _compose_situs
                                 # gets no number. taxpayer: owner-name field on some layers
                                 # (e.g. City of Detroit taxpayer_1) that "owner" doesn't match.


# Field-importance order for _out_fields ranking: situs/address components first, then owner,
# parcel id, doc hints, lot area. A field's rank = index of the first token it contains.
_FIELD_PRIORITY = ("situs", "site", "adress", "addr", "par_ad", "location", "e911", "phy", "prop",
                   "full",
                   "street", "road", "hous", "num", "dir", "type", "owner", "taxpayer", "name",
                   "parcel", "pin",
                   "apn", "folio", "strap", "acct", "account", "prono", "locator", "geoid", "gpin",
                   "tmk", "span", "altkey", "legal", "book", "page", "plat", "instr", "deed",
                   "subdiv", "lot", "block", "acre", "sqf", "assess", "link")


def _field_rank(name: str) -> int:
    nl = name.lower()
    return next((i for i, t in enumerate(_FIELD_PRIORITY) if t in nl), len(_FIELD_PRIORITY))


@functools.lru_cache(maxsize=512)
def _out_fields(layer_url: str) -> str:
    """Explicit, short list of the app-relevant fields for a layer — situs, owner, parcel id,
    hints, lot area. Avoids outFields='*' (returns 0 features on layers with a GEOMETRY/SHAPE
    field, e.g. East Baton Rouge LA) and keeps the request small (some servers return 0 for a
    too-wide field set). Falls back to '*' when metadata is unavailable."""
    try:
        meta = get_json(layer_url, {"f": "json"})
        names = [f["name"] for f in meta.get("fields", [])
                 if f.get("type") != "esriFieldTypeGeometry"
                 and f["name"].lower() not in ("shape", "geometry")
                 and not f["name"].lower().startswith("shape")
                 and "(shape)" not in f["name"].lower()]
        if not names:
            return "*"
        kept = [n for n in names if any(k in n.lower() for k in _KEEP_FIELDS)]
        # Rank by app-importance BEFORE capping, so a rich schema (Johnson Co IA has >25
        # keep-matching fields, with SiteAddress/PropertyAddress trailing after mailing+value
        # fields) can't push situs/id/owner past the cap. situs_of is alias-driven (order-
        # independent), so reordering the field list never changes which field it picks.
        kept.sort(key=_field_rank)
        return ",".join(kept[:40]) if kept else "*"
    except Exception:  # noqa: BLE001
        return "*"


def _point_query(url: str, lat: float, lon: float, distance: int = 0) -> list[dict]:
    """Intersect a layer at a point, or within a `distance`-metre box; return candidates.

    Two hosted-FeatureServer quirks defeated the original implementation (both fail SLOW —
    ~56 s — with HTTP 400 "Invalid query parameters"):
      * geometry must be ArcGIS JSON, not the `x,y` shorthand;
      * `distance`/`units` buffering and `resultRecordCount` are NOT supported here.
    So we buffer with an explicit envelope (bbox) and cap the candidate list in Python.
    """
    if distance:
        dlat = distance / 111_320.0
        dlon = distance / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
        geom = json.dumps({"xmin": lon - dlon, "ymin": lat - dlat,
                           "xmax": lon + dlon, "ymax": lat + dlat,
                           "spatialReference": {"wkid": 4326}})
        gtype = "esriGeometryEnvelope"
    else:
        geom = json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}})
        gtype = "esriGeometryPoint"
    q = get_json(url, {
        "geometry": geom,
        "geometryType": gtype,
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": _out_fields(url.rsplit("/query", 1)[0]),
        "returnGeometry": "false",
        "f": "json",
    })
    # Return ALL features in the box (a few hundred at most for these radii). Do NOT
    # truncate here: the target parcel is often not among the first N by OBJECTID, and
    # slicing before the address match silently drops it (that was a real bug).
    return [f.get("attributes", {}) for f in q.get("features", [])][:400]


def _candidates(url: str, lat: float, lon: float, address: str = "", situs_fn=situs_of):
    """Find candidate parcels at the point. Returns (candidates, buffered?).

    Geocoders can miss the true parcel by ~100-200 m (observed: Census put "526 Hampton"
    92 m off, and "51 Seminole Dr" ~185 m off — right onto the NEIGHBORING parcel). So we
    trust the exact point hit only when there's no address to check, or one of the hit parcels
    actually matches the searched address; otherwise we widen the box in steps and STOP at the
    first radius whose candidates contain an address match. That way a mis-geocode that lands on
    a neighbor still resolves the correct parcel instead of being suppressed as "not confirmed".
    If no radius yields a match, return the widest set so `_choose` can flag a nearest guess.
    """
    def has_match(feats):
        return bool(address) and any(_addr_match(address, situs_fn(c)) is True for c in feats)

    direct = _point_query(url, lat, lon)
    if direct and (not address or has_match(direct)):
        return direct, False
    widest: list[dict] = direct
    for dist in (75, 150, 300):
        feats = _point_query(url, lat, lon, distance=dist)
        if feats:
            widest = feats
            if has_match(feats):
                return feats, True
    return widest, bool(widest)


def _arcgis_layer_url(service: str, layer_hint: str) -> tuple:
    """Discover the parcel layer in a MapServer. Returns (layer_query_url, layer_name).

    If `service` already points at a specific layer (ends in /<id>, e.g. a county whose exact
    verified layer is known), use it directly instead of scanning — this avoids picking the
    wrong layer in a multi-layer viewer service where several names contain 'parcel'/'property'.
    """
    if re.search(r"/\d+/?$", service):
        svc = service.rstrip("/")
        try:
            name = get_json(svc, {"f": "json"}).get("name")
        except Exception:  # noqa: BLE001
            name = None
        return f"{svc}/query", name
    meta = get_json(service, {"f": "json"})
    layers = meta.get("layers", [])
    cands = [l for l in layers
             if layer_hint in l.get("name", "").lower()
             or "parcel" in l.get("name", "").lower()
             or "property" in l.get("name", "").lower()]
    if not cands:
        return None, None
    return f"{service}/{cands[0]['id']}/query", cands[0].get("name")


def _choose(candidates: list[dict], address: str, situs_fn=situs_of):
    """Pick the candidate whose situs matches the searched address.

    Returns (chosen, matched). `matched` is True only on a positive address match
    (house + street where both are available); a house-only hit on a mismatched or
    unknown street is returned but NOT treated as confident, so it gets flagged.
    """
    # 1) positive identification: address (house + street) matches
    for c in candidates:
        if _addr_match(address, situs_fn(c)) is True:
            return c, True
    # 2) weaker fallback: same house number but street didn't confirm
    house = _house(address)
    if house:
        for c in candidates:
            if _house(situs_fn(c)) == house:
                return c, False
    # 3) last resort: prefer any candidate that actually carries a situs, so we don't return a
    #    null/placeholder ROW polygon (e.g. Cobb GA returns PIN='000' rows with a null situs that
    #    also intersect the query point) when a real attributed parcel is in the set.
    for c in candidates:
        if situs_fn(c):
            return c, False
    return candidates[0], False


def _extract_hints(parcels: list[dict]) -> dict:
    hints = {}
    for p in parcels:
        for k, v in p.items():
            kl = k.lower()
            if v in (None, "", 0):
                continue
            if any(t in kl for t in ("book", "page", "plat", "instrument", "legal",
                                     "subdiv", "owner", "taxpayer", "deed", "folio", "parcel")):
                hints.setdefault(k, v)
    return hints


def _finish(result: dict, chosen: dict, candidates: list, buffered: bool,
            matched: bool, address: str, src: str, layer_name=None, situs_fn=situs_of) -> dict:
    situs = situs_fn(chosen)
    sqft, acres = land_area_of(chosen)
    result.update({
        "method": "arcgis-rest", "source": src, "service": src,
        "layer_name": layer_name, "parcels": [chosen],
        "candidate_count": len(candidates),
        "situs": situs, "land_sqft": sqft, "land_acres": acres,
        # confident when we matched by address; "verify" when buffered and unmatched
        "buffered_match": buffered and not matched,
        "address_match": _addr_match(address, situs),
        "hints": _extract_hints([chosen]),
    })
    return result


def _enrich_related(attrs: dict, cfg) -> None:
    """Merge situs/owner from RELATED table(s)/layer(s) into the parcel attrs, in place. For layers
    whose polygon carries only ids/geometry with situs+owner in a joined table/layer (ND, Charleston
    SC, Lane OR, Jackson MO). Only fills fields the polygon doesn't already have.

    cfg: {url, key: <attr field to read the join value from>, where: <table field to filter on;
    default = key>, quote: <wrap value in quotes; default True — set False for integer keys>}.
    cfg may also be a LIST of such dicts — each is joined in turn (e.g. Polk IA: a situs table AND a
    separate owner table, both keyed on the parcel number).
    """
    for c in (cfg if isinstance(cfg, list) else [cfg]):
        _enrich_one(attrs, c)


def _enrich_one(attrs: dict, cfg: dict) -> None:
    key, url = cfg.get("key"), cfg.get("url")
    val = attrs.get(key) if key else None
    if not (url and val not in (None, "", " ")):
        return
    where_field = cfg.get("where", key)
    try:
        v = str(val).strip().replace("'", "''")
        where = f"{where_field}='{v}'" if cfg.get("quote", True) else f"{where_field}={v}"
        q = get_json(f"{url}/query", {"where": where, "outFields": "*",
                                      "returnGeometry": "false", "f": "json"})
        feats = q.get("features", [])
        if feats:
            for k, fv in feats[0].get("attributes", {}).items():
                if attrs.get(k) in (None, "", " "):
                    attrs[k] = fv
    except Exception:  # noqa: BLE001
        pass


def resolve(county_fips: str, state_abbr: str, county_name: str,
            lat: float, lon: float, address: str = "") -> dict:
    reg = lookup(county_fips)
    result = {"county_fips": county_fips, "hints": {}}
    sfn = _situs_fn(reg)   # per-county situs extractor (exclude/compose overrides)

    # 1) county-specific MapServer -----------------------------------------------
    # gis_rest may be a LIST of layers that together cover the county (e.g. Wayne MI: the official
    # Detroit city layer first, then a whole-county layer for the suburbs). Try each; use the first
    # that returns a parcel at this point.
    grest = reg.get("gis_rest") if reg else None
    for one in (grest if isinstance(grest, list) else [grest]) if grest else []:
        try:
            url, layer_name = _arcgis_layer_url(one, reg.get("parcel_layer_hint", "parcel"))
            if url:
                cands, buffered = _candidates(url, lat, lon, address, situs_fn=sfn)
                if cands:
                    chosen, matched = _choose(cands, address, situs_fn=sfn)
                    if reg.get("related"):   # join situs/owner from a related table
                        _enrich_related(chosen, reg["related"])
                        matched = _addr_match(address, sfn(chosen)) is True
                    return _finish(result, chosen, cands, buffered, matched, address,
                                   url.rsplit("/query", 1)[0], layer_name, situs_fn=sfn)
        except Exception as e:  # noqa: BLE001
            result["arcgis_error"] = str(e)

    # 2) statewide FeatureServer (covers every county in the state) ---------------
    svc = STATE_PARCEL.get(state_abbr)
    if svc:
        # url may be a LIST of layers that together tile the state (e.g. MS East/West halves) —
        # try each and use the first that returns a parcel at this point.
        urls = svc["url"] if isinstance(svc["url"], list) else [svc["url"]]
        for u in urls:
            try:
                cands, buffered = _candidates(f"{u}/query", lat, lon, address)
                if cands:
                    chosen, matched = _choose(cands, address)
                    if svc.get("related"):   # join situs/owner from a related table (e.g. ND)
                        _enrich_related(chosen, svc["related"])
                        matched = _addr_match(address, situs_of(chosen)) is True
                    result["parcel_source_label"] = svc.get("label", "")
                    return _finish(result, chosen, cands, buffered, matched, address, u)
            except Exception as e:  # noqa: BLE001
                result["statewide_error"] = str(e)

    # 3) fallback: appraiser / directory link ------------------------------------
    result["method"] = "directory"
    result["appraiser_url"] = (reg or {}).get("appraiser_url")
    result["directory_url"] = netronline(state_abbr, county_name)
    result["note"] = ("No verified parcel API for this county yet — open the appraiser/"
                      "directory link, or add an ArcGIS REST endpoint to the registry.")
    return result


# ------------------------------------------------------------------ search by Parcel ID
# Candidate ID field-name fragments (matched against the layer's real fields, _norm'd).
_ID_CANDIDATES = ("parcelid", "propid", "apn", "folio", "pin", "strap", "parno",
                  "parcelnumb", "parcelnum", "parcelno", "geoid", "altkey", "span",
                  "acct", "parcel", "propertyid")


def _id_fields(layer_url: str, override) -> list:
    """The layer's fields that look like a parcel identifier (or a per-state override).

    Auto-detected fields are ordered by candidate strength (parcelid/apn/folio/pin before
    altkey/span/acct...) so the strongest, usually-indexed field is queried first.
    """
    if override:
        return list(override)
    try:
        meta = get_json(layer_url, {"f": "json"})
        names = [f["name"] for f in meta.get("fields", [])
                 if any(c in _norm(f.get("name", "")) for c in _ID_CANDIDATES)]

        def rank(n: str) -> int:
            nn = _norm(n)
            return next((i for i, c in enumerate(_ID_CANDIDATES) if c in nn), len(_ID_CANDIDATES))
        return sorted(names, key=rank)
    except Exception:  # noqa: BLE001
        return []


def _centroid(geom: dict):
    """(lat, lon) from an ArcGIS geometry (point, centroid, or first polygon ring)."""
    if not geom:
        return None
    if "y" in geom and "x" in geom:
        return geom["y"], geom["x"]
    c = geom.get("centroid")
    if c:
        return c["y"], c["x"]
    rings = geom.get("rings") or []
    pts = rings[0] if rings else []
    if not pts:
        return None
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


def _query_by_id(layer_url: str, parcel_id: str, override) -> dict | None:
    fields = _id_fields(layer_url, override)
    if not fields:
        return None
    variants = [parcel_id]
    if re.search(r"[-\s]", parcel_id):
        variants.append(re.sub(r"[-\s]", "", parcel_id))   # dash/space-insensitive retry
    # Query ONE field at a time and return on the first hit — do NOT OR every candidate field
    # into a single WHERE. ORing an unindexed id field (e.g. FL DOR ALT_KEY) forces a full-table
    # scan on large statewide layers (~12M rows) and times out, so a valid parcel looks "not
    # found". Per-field exact matches stay index-fast, and fields are tried strongest-first.
    for f in fields:
        for val in variants:
            v = val.replace("'", "''")
            # Predicates to try: quoted (string columns) and — when the value is all digits —
            # unquoted (integer columns, e.g. Orleans LA GEOPIN, reject a quoted numeric literal).
            wheres = [f"{f}='{v}'"]
            if val.isdigit():
                wheres.append(f"{f}={val}")
            # Exact equality only — no UPPER()/functions on the column: hosted parcel layers
            # reject function predicates ("Invalid query parameters") and a scan is far slower.
            for where in wheres:
                try:
                    # No resultRecordCount: some MapServers (e.g. MS MARIS) reject it with
                    # "Pagination is not supported". An exact-id match returns ~1 row, so take [0].
                    q = get_json(f"{layer_url}/query", {
                        "where": where, "outFields": _out_fields(layer_url),
                        "returnGeometry": "true", "outSR": "4326", "f": "json"})
                except Exception:  # noqa: BLE001
                    continue
                feats = q.get("features", [])
                if feats:
                    return feats[0]
    return None


def resolve_by_id(state_abbr: str, parcel_id: str, county_fips: str = "") -> dict:
    """Resolve a parcel by its Parcel ID / APN (no address). Queries the county service (if
    known) then the statewide layer. Returns {'parcel': <same shape as resolve()>, 'lat', 'lon'}
    or {} if not found. Each state module can set PARCEL['id_fields'] to pin the ID column."""
    pid = (parcel_id or "").strip()
    if not pid:
        return {}
    services: list[tuple] = []   # (layer_url, label, id_fields_override, situs_fn, related)
    reg = lookup(county_fips) if county_fips else None
    grest = reg.get("gis_rest") if reg else None
    for one in (grest if isinstance(grest, list) else [grest]) if grest else []:
        try:
            u, name = _arcgis_layer_url(one, reg.get("parcel_layer_hint", "parcel"))
            if u:
                services.append((u.rsplit("/query", 1)[0], name or reg.get("county", ""),
                                 reg.get("id_fields"), _situs_fn(reg), reg.get("related")))
        except Exception:  # noqa: BLE001
            pass
    svc = STATE_PARCEL.get(state_abbr)
    if svc:
        for u in (svc["url"] if isinstance(svc["url"], list) else [svc["url"]]):
            services.append((u, svc.get("label", ""), svc.get("id_fields"), situs_of,
                             svc.get("related")))

    for layer_url, label, override, sfn, related in services:
        feat = _query_by_id(layer_url, pid, override)
        if not feat:
            continue
        attrs = feat.get("attributes", {})
        if related:   # join situs/owner from a related table (e.g. ND)
            _enrich_related(attrs, related)
        cen = _centroid(feat.get("geometry"))
        sqft, acres = land_area_of(attrs)
        parcel = {
            "method": "arcgis-rest", "source": layer_url, "service": layer_url,
            "layer_name": label, "parcels": [attrs], "candidate_count": 1,
            "situs": sfn(attrs), "land_sqft": sqft, "land_acres": acres,
            "buffered_match": False, "address_match": True,   # exact ID match = confident
            "hints": _extract_hints([attrs]), "parcel_source_label": label,
        }
        return {"parcel": parcel, "lat": cen[0] if cen else None,
                "lon": cen[1] if cen else None}
    return {}


def summarize(p: dict) -> str:
    if p.get("method") == "arcgis-rest":
        return f"parcel record via {p.get('layer_name') or 'ArcGIS'}"
    return "No parcel API - directory link provided"
