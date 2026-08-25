"""NOAA National Geodetic Survey - nearby geodetic control (benchmarks). Nationwide, free API."""
from .http import get_json

RADIAL = "https://geodesy.noaa.gov/api/nde/radial"
DATASHEET = "https://geodesy.noaa.gov/cgi-bin/ds_mark.prl?PidBox={PID}"


def benchmarks(lat: float, lon: float, radius_m: int = 3000, limit: int = 25) -> dict:
    marks = get_json(RADIAL, {
        "lat": lat, "lon": lon, "radius": radius_m, "units": "METER",
    })
    if not isinstance(marks, list):
        marks = marks.get("marks", []) if isinstance(marks, dict) else []
    trimmed = []
    for m in marks[:limit]:
        pid = m.get("pid", "").strip()
        trimmed.append({
            "pid": pid,
            "name": (m.get("name") or "").strip(),
            "lat": m.get("lat"),
            "lon": m.get("lon"),
            "datum": (m.get("posDatum") or "").strip(),
            "vert_source": (m.get("orthoHt") or m.get("posSource") or "").strip(),
            "datasheet": DATASHEET.format(PID=pid) if pid else "",
        })
    return {"radius_m": radius_m, "count": len(marks), "marks": trimmed}


def summarize(b: dict) -> str:
    return f"{b.get('count', 0)} NGS control marks within {b.get('radius_m')} m"
