"""Download actual document files where an automatable, reachable source exists.

Files are saved into  <job>/research/documents/ .

Reachable via plain HTTP (implemented here): NGS datasheets, BLM GLO (where a direct
file URL exists). FEMA FIRMette needs the US-egress VPN. County Clerk records (deed, plat,
easements, adjoiner deeds, prior surveys, condo) sit behind bot-blocked, JavaScript search
portals and need a per-platform browser adapter (Playwright) — see clerk.py `_ADAPTERS`.
"""
import base64
import datetime
import html as _html
import io
import math
import pathlib

from .http import _session
from ..config import HTTP_TIMEOUT

NGS_DATASHEET = "https://geodesy.noaa.gov/cgi-bin/ds_mark.prl"  # ?PidBox=<PID> -> datasheet HTML

# Flood-map exhibit: FEMA NFHL flood layers composited over an Esri topo basemap (no key).
NFHL_EXPORT = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/export"
BASEMAP_EXPORT = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                  "World_Topo_Map/MapServer/export")

# Report-document styling — a clean, print-ready page (renders in the in-app viewer and
# Print -> Save as PDF gives a portable deliverable). No external branding.
_CSS = """<style>
:root{--ink:#1e293b;--muted:#64748b;--line:#e2e8f0;--brand:#33409E;--band:#f4f6fc}
*{box-sizing:border-box}
body{font-family:'Segoe UI',Arial,sans-serif;color:var(--ink);margin:0;background:#f1f5f9;
     line-height:1.5;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.doc{max-width:820px;margin:24px auto;background:#fff;border:1px solid var(--line);
     border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(15,23,42,.06)}
.head{padding:22px 30px;border-bottom:3px solid var(--brand);
      display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--brand)}
.head h1{font-size:22px;margin:4px 0 2px;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13px}
.stamp{text-align:right;font-size:11px;color:var(--muted);line-height:1.7;white-space:nowrap}
.body{padding:8px 30px 26px}
.banner{margin:18px 0 6px;padding:12px 16px;border-radius:9px;font-weight:700;font-size:15px;
        display:flex;align-items:center;gap:10px}
.banner .lbl{font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.06em;opacity:.8}
.banner.ok{background:#ecfdf5;color:#047857;border:1px solid #a7f3d0}
.banner.hi{background:#fef2f2;color:#b91c1c;border:1px solid #fecaca}
.banner.mid{background:#fffbeb;color:#b45309;border:1px solid #fde68a}
.sec{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);
     margin:22px 0 8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
dl.grid{display:grid;grid-template-columns:1fr 1fr;gap:0;margin:0;border:1px solid var(--line);border-radius:9px;overflow:hidden}
dl.grid>div{display:flex;flex-direction:column;gap:2px;padding:11px 15px;border-bottom:1px solid var(--line)}
dl.grid>div:nth-child(odd){border-right:1px solid var(--line)}
dl.grid>div.full{grid-column:1/-1}
dl.grid dt{font-size:10.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
dl.grid dd{margin:0;font-size:14px;font-weight:500;color:var(--ink);word-break:break-word}
.exhibit{margin-top:14px}
.exhibit img{width:100%;border:1px solid var(--line);border-radius:9px;display:block}
.cap{font-size:11px;color:var(--muted);margin-top:6px}
.note{margin-top:18px;padding:12px 15px;background:var(--band);border-radius:9px;font-size:12px;color:#475569}
.note b{color:var(--ink)}
a{color:var(--brand)}
@media print{body{background:#fff}.doc{border:0;box-shadow:none;margin:0;max-width:none}}
</style>"""


def docs_dir(folder: pathlib.Path) -> pathlib.Path:
    d = folder / "documents"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _e(v) -> str:
    return _html.escape("" if v is None else str(v))


def _write_html(folder, filename: str, body: str) -> str:
    (docs_dir(folder) / filename).write_text(
        f"<!doctype html><meta charset='utf-8'>{_CSS}{body}", encoding="utf-8")
    return filename


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _row(label: str, value, full: bool = False) -> str:
    """One dt/dd cell for the definition grid. Skips empties. `full` spans both columns."""
    if value in (None, ""):
        return ""
    return (f"<div class='{'full' if full else ''}'><dt>{_e(label)}</dt>"
            f"<dd>{_e(value)}</dd></div>")


def _shell(eyebrow: str, title: str, subtitle: str, source: str, inner: str) -> str:
    return (f"<div class=doc><div class=head>"
            f"<div><div class=eyebrow>{_e(eyebrow)}</div><h1>{_e(title)}</h1>"
            f"<div class=sub>{subtitle}</div></div>"
            f"<div class=stamp>Generated {_stamp()}<br>{source}</div></div>"
            f"<div class=body>{inner}</div></div>")


# Parcel attributes worth surfacing at the top of the record, in this order, by
# common county/DOR field-name aliases (case-insensitive).
_PARCEL_KEYS = [
    ("Owner", ("own_name", "owner", "ownname", "owner_name")),
    ("Owner mailing", ("own_addr1", "owner_addr", "mailing")),
    ("Subdivision / legal", ("s_legal", "legal", "legal_desc", "slegal")),
    ("Land use", ("dor_uc", "use_code", "landuse", "pa_uc")),
    ("Year built", ("act_yr_blt", "yr_blt", "year_built")),
    ("Living area", ("tot_lvg_ar", "living_area", "heated_area")),
]


def _attr(attrs: dict, aliases) -> str:
    for a in aliases:
        for k, v in attrs.items():
            if str(k).lower() == a and v not in (None, "", 0):
                return v
    return ""


def save_parcel_record(folder, parcel: dict, meta: dict) -> str | None:
    """Render the fetched parcel attributes as a clean Parcel Record document."""
    parcels = parcel.get("parcels") or []
    if not parcels:
        return None
    attrs = parcels[0]
    src = parcel.get("source", "")
    label = parcel.get("parcel_source_label") or "county parcel service"
    sqft, acres = meta.get("land_sqft"), meta.get("land_acres")
    lot = (f"{int(sqft):,} sq ft" + (f" ({acres} ac)" if acres else "")) if sqft else ""

    # Top summary grid (the fields a surveyor checks first).
    summary = [
        _row("Parcel ID", meta.get("parcel_id")),
        _row("Situs address", meta.get("situs")),
        _row("Land area", lot),
        _row("County", f"{meta.get('county')} County, {meta.get('state')}"),
    ]
    for lbl, aliases in _PARCEL_KEYS:
        summary.append(_row(lbl, _attr(attrs, aliases)))
    grid = f"<dl class=grid>{''.join(summary)}</dl>"

    # Full attribute dump (everything the parcel service returned), collapsed below.
    dump = "".join(
        f"<div><dt>{_e(k)}</dt><dd>{_e(v)}</dd></div>"
        for k, v in attrs.items()
        if v not in (None, "", 0) and not str(k).lower().startswith("shape"))
    src_html = f"<a href='{_e(src)}'>{_e(label)}</a>" if src else _e(label)
    subtitle = (f"{_e(meta.get('matched_address') or '')} &middot; "
                f"{_e(meta.get('county'))} County, {_e(meta.get('state'))}")
    inner = (f"<div class=sec>Parcel summary</div>{grid}"
             f"<div class=sec>All recorded attributes</div><dl class=grid>{dump}</dl>"
             f"<div class=note><b>Verify the situs address matches the subject property.</b> "
             f"Values are the county parcel-service figures at fetch time.</div>")
    body = _shell("Survey Research", "Parcel Record", subtitle, src_html, inner)
    return _write_html(folder, "Parcel_Record.html", body)


def _merc(lon: float, lat: float) -> tuple:
    """Lon/lat (EPSG:4326) -> Web Mercator (EPSG:3857) meters."""
    x = lon * 20037508.342789244 / 180.0
    y = math.log(math.tan((90 + lat) * math.pi / 360.0)) / (math.pi / 180.0)
    return x, y * 20037508.342789244 / 180.0


def _font(size: int):
    try:
        from PIL import ImageFont
        return ImageFont.truetype("arial.ttf", size)
    except Exception:  # noqa: BLE001 — fall back to the bitmap default
        from PIL import ImageFont
        return ImageFont.load_default()


def save_flood_map(folder, lat: float, lon: float, flood: dict, meta: dict,
                   half_m: int = 700, size: int = 1000) -> str | None:
    """Save a flood-map exhibit PNG: FEMA NFHL zones over a topo basemap, parcel at center.

    Useful even when the point isn't inside an SFHA polygon (shows the surrounding zones
    and the governing FIRM panel). Returns the filename, or None if the map can't be built.
    """
    try:
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001 — Pillow missing; caller keeps the FIRM deep-link
        return None
    try:
        cx, cy = _merc(lon, lat)
        bbox = f"{cx-half_m},{cy-half_m},{cx+half_m},{cy+half_m}"
        common = {"bbox": bbox, "bboxSR": "3857", "imageSR": "3857",
                  "size": f"{size},{size}", "dpi": "96", "format": "png32", "f": "image"}
        base = _session.get(BASEMAP_EXPORT, params={**common, "transparent": "false"},
                            timeout=HTTP_TIMEOUT)
        nfhl = _session.get(NFHL_EXPORT, params={**common, "transparent": "true"},
                            timeout=HTTP_TIMEOUT)
        base.raise_for_status()
        nfhl.raise_for_status()
        img = Image.open(io.BytesIO(base.content)).convert("RGBA")
        img.alpha_composite(Image.open(io.BytesIO(nfhl.content)).convert("RGBA"))

        d = ImageDraw.Draw(img)
        c = size // 2
        red = (200, 0, 0, 255)
        d.line([(c - 16, c), (c + 16, c)], fill=red, width=3)
        d.line([(c, c - 16), (c, c + 16)], fill=red, width=3)
        d.ellipse([c - 7, c - 7, c + 7, c + 7], outline=red, width=3)

        # caption strip
        zone = flood.get("flood_zone") or "X (not in mapped SFHA)"
        panel = flood.get("firm_panel") or "—"
        cap = (f"{meta.get('matched_address', '')}   |   Zone {zone}   |   "
               f"FIRM panel {panel}   |   red crosshair = parcel   |   FEMA NFHL / Esri topo")
        f = _font(15)
        d.rectangle([0, size - 30, size, size], fill=(255, 255, 255, 235))
        d.text((10, size - 23), cap, fill=(20, 20, 20, 255), font=f)

        out = docs_dir(folder) / "Flood_Map.png"
        img.convert("RGB").save(out)
        return "Flood_Map.png"
    except Exception:  # noqa: BLE001 — best-effort exhibit; a miss just isn't saved
        return None


def _f(attrs: dict, name: str):
    for k, v in attrs.items():
        if k.upper() == name:
            return v
    return None


def _ga(attrs: dict, *needles) -> object:
    """First attribute whose (normalized) name contains one of `needles`, in needle order,
    skipping empties. Works across any state's parcel/assessor schema (not just FL DOR)."""
    for n in needles:
        for k, v in attrs.items():
            kl = str(k).lower().replace(" ", "").replace("-", "").replace("_", "")
            if n in kl and v not in (None, "", " ", 0, "0"):
                return v
    return None


def save_appraiser_record(folder, attrs: dict, meta: dict, appraiser_url: str = "") -> str | None:
    """Render a Property Appraiser / Tax card from whatever the county's parcel/assessor layer
    returned — owner, mailing, situs, legal, use, areas, values, and the last sale. Field names
    vary by state, so this matches generically (FL DOR names included) and shows what's present."""
    if not attrs:
        return None

    def money(v):
        try:
            return f"${int(float(v)):,}"
        except (TypeError, ValueError):
            return None

    own = _ga(attrs, "ownname", "ownername", "ownernm", "primaryowner", "owner1", "owner", "owner")
    mail = _ga(attrs, "mailaddr", "ownaddr", "owneraddr", "mailing", "addmail")
    situs = meta.get("situs") or _ga(attrs, "situsaddr", "siteaddr", "phyaddr", "parceladdr",
                                     "propaddr", "locaddr", "situs")
    legal = _ga(attrs, "slegal", "legaldesc", "legal", "subdiv")
    use = _ga(attrs, "doruc", "usecode", "landuse", "propuse", "classcode", "propertyclass", "luc")
    yr = _ga(attrs, "actyrblt", "yrblt", "yearbuilt", "effyr")
    lvg = _ga(attrs, "totlvgar", "living", "heated", "finsqft", "bldgarea")
    mkt = money(_ga(attrs, "just", "jv", "market", "mktval", "apprval", "totalappr", "totalvalue"))
    assd = money(_ga(attrs, "assess", "avsd", "assdtot", "assd"))
    txbl = money(_ga(attrs, "taxable", "tvsd", "txbl"))
    saleprc = money(_ga(attrs, "saleprc", "saleprice", "saleamt", "lastsale"))
    sqft, acres = meta.get("land_sqft"), meta.get("land_acres")
    land = (f"{int(sqft):,} sq ft" + (f" ({acres} ac)" if acres else "")) if sqft else None

    is_fl = (meta.get("state") == "FL")
    rows = "".join([
        _row("Parcel ID", meta.get("parcel_id")),
        _row("Owner", own),
        _row("Owner mailing", mail),
        _row("Situs address", situs, full=True),
        _row("County", f"{meta.get('county')} County, {meta.get('state')}"),
        _row("Subdivision / legal", legal, full=True),
        _row("Land use", use),
        _row("Land area", land),
        _row("Living area", f"{int(float(lvg)):,} sq ft" if lvg else None),
        _row("Year built", yr),
        _row("Market value", mkt),
        _row("Assessed value", assd),
        _row("Taxable value", txbl),
        _row("Last sale price", saleprc),
    ])
    src_label = ("Florida DOR statewide tax roll (NAL/cadastral)" if is_fl
                 else f"{meta.get('county')} County parcel / assessor data")
    src = (src_label + (f" &middot; <a href='{_e(appraiser_url)}'>open county Property Appraiser</a>"
                        if appraiser_url else ""))
    subtitle = (f"{_e(meta.get('situs') or meta.get('matched_address') or '')} &middot; "
                f"{_e(meta.get('county'))} County, {_e(meta.get('state'))}")
    inner = (f"<div class=sec>Property &amp; tax</div><dl class=grid>{rows}</dl>"
             f"<div class=note>Values (where shown) are the county roll figures. Verify current-year "
             f"assessment, exemptions, and tax due on the county Property Appraiser / Assessor site.</div>")
    body = _shell("Survey Research", "Property Appraiser / Tax Record", subtitle, src, inner)
    return _write_html(folder, "Property_Appraiser.html", body)


# Flood-zone descriptions (FEMA NFHL zone codes) — presentation only, no fabricated data.
_ZONE_DESC = {
    "A": "1% annual-chance (100-year) floodplain — no base flood elevation determined",
    "AE": "1% annual-chance (100-year) floodplain with base flood elevations",
    "AH": "Shallow flooding, 1–3 ft ponding (1% annual-chance)",
    "AO": "Shallow flooding, 1–3 ft sheet flow (1% annual-chance)",
    "AR": "Temporarily increased risk while a flood-control system is restored",
    "A99": "Area protected by a flood-control system under construction",
    "V": "Coastal high-hazard area with wave action (1% annual-chance)",
    "VE": "Coastal high-hazard area with wave action and base flood elevations",
    "X": "Outside the mapped floodplain",
    "D": "Undetermined — no flood-hazard analysis conducted",
}


def _flood_risk(flood: dict) -> tuple:
    """(risk phrase, banner css class) derived from the zone. Presentation, not new data."""
    zone = (flood.get("flood_zone") or "").upper().strip()
    subty = (flood.get("zone_subtype") or "").upper()
    if flood.get("in_sfha") == "T":
        return "HIGH RISK — SPECIAL FLOOD HAZARD AREA", "hi"
    if "0.2" in subty or "500" in subty:
        return "MODERATE RISK — 0.2% ANNUAL-CHANCE (500-YEAR) FLOODPLAIN", "mid"
    if zone.startswith("X"):
        return "MODERATE TO LOW RISK", "ok"
    if zone == "D":
        return "UNDETERMINED RISK", "mid"
    return "SEE FIRM", "mid"


def _img_data_uri(path: pathlib.Path) -> str:
    try:
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
    except Exception:  # noqa: BLE001
        return ""


def save_flood_report(folder, flood: dict, meta: dict, map_file: str | None = None) -> str | None:
    """Render the FEMA NFHL result as a clean Flood Zone Report (MapWise-style layout,
    no third-party branding). Embeds the flood-map exhibit inline when available."""
    if not flood.get("flood_zone"):
        return None
    zone = (flood.get("flood_zone") or "").upper().strip()
    in_sfha = flood.get("in_sfha") == "T"
    risk, cls = _flood_risk(flood)
    sfha_txt = "INSIDE SPECIAL FLOOD HAZARD AREA" if in_sfha else "OUTSIDE SPECIAL FLOOD HAZARD AREA"
    desc = _ZONE_DESC.get(zone, "") or (flood.get("zone_subtype") or "")
    panel = flood.get("firm_panel") or ""
    if panel and flood.get("panel_suffix"):
        panel = f"{panel} {flood.get('panel_suffix')}"
    bfe = flood.get("static_bfe")
    bfe_txt = "N/A" if bfe in (None, "", "-9999", -9999) else f"{bfe} ft"

    rows = "".join([
        _row("Property address", meta.get("matched_address"), full=True),
        _row("FEMA data source", "NFHL — National Flood Hazard Layer (Digital FIRM)"),
        _row("Flood zone", zone),
        _row("Zone description", desc, full=True),
        _row("Risk level", risk.title()),
        _row("Base flood elevation", bfe_txt),
        _row("FIRM panel number", panel),
        _row("Community panel", flood.get("panel")),
        _row("Map panel effective date", flood.get("effective_date")),
        _row("County", f"{meta.get('county')} County"),
        _row("State", meta.get("state")),
        _row("Parcel ID", meta.get("parcel_id")),
    ])
    banner = (f"<div class='banner {cls}'><span class=lbl>Inside SFHA?</span>{_e(sfha_txt)}</div>")

    exhibit = ""
    if map_file:
        uri = _img_data_uri(docs_dir(folder) / map_file)
        if uri:
            exhibit = (f"<div class=sec>Flood map exhibit</div>"
                       f"<div class=exhibit><img src='{uri}' alt='FEMA flood map'>"
                       f"<div class=cap>FEMA NFHL flood zones over topographic basemap; "
                       f"red crosshair marks the parcel.</div></div>")

    subtitle = (f"{_e(meta.get('matched_address') or '')} &middot; "
                f"{_e(meta.get('county'))} County, {_e(meta.get('state'))}")
    src = f"<a href='{_e(flood.get('map_service_center',''))}'>FEMA Map Service Center</a>"
    inner = (f"{banner}<div class=sec>Flood determination</div><dl class=grid>{rows}</dl>"
             f"{exhibit}"
             f"<div class=note><b>Determination is from the effective FEMA NFHL</b> at the "
             f"parcel location. Confirm the panel and any LOMA/LOMR on the FEMA Map Service "
             f"Center before certifying.</div>")
    body = _shell("FEMA · NFHL", "FEMA Flood Report", subtitle, src, inner)
    return _write_html(folder, "FEMA_Flood_Report.html", body)


def _pid(mark: dict) -> str:
    for k in ("pid", "PID", "permanent_identifier", "permanentIdentifier"):
        v = mark.get(k)
        if v:
            return str(v)
    return ""


def download_ngs_datasheets(folder, marks, limit: int = 3) -> list[str]:
    """Save the NGS datasheet for the nearest `limit` control marks. Returns filenames saved."""
    saved: list[str] = []
    dd = docs_dir(folder)
    for m in (marks or [])[:limit]:
        pid = _pid(m)
        if not pid:
            continue
        try:
            r = _session.get(NGS_DATASHEET, params={"PidBox": pid}, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            fn = f"NGS_datasheet_{pid}.html"
            (dd / fn).write_bytes(r.content)
            saved.append(fn)
        except Exception:  # noqa: BLE001 — best-effort; a miss just isn't saved
            continue
    return saved
