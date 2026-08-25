
"""Per-state implementation package — one module per state (STATE, PARCEL, COUNTIES, DEED_LINK,
APPRAISER_LINK).

Keeping each state separate makes coverage easy to debug and track. The loader below
aggregates every module into STATE_PARCEL (statewide parcel services), STATE_COUNTIES
(per-county registry overrides), STATE_DEED (a statewide deed/records portal used as the
clerk-link fallback for every county in that state) and STATE_APPRAISER (the same idea for the
assessor/tax card — e.g. NJ's statewide MOD-IV assessment search covers all 21 counties) —
which county_platforms.py merges in.
"""
import importlib, pkgutil

STATE_PARCEL = {}
STATE_COUNTIES = {}
STATE_DEED = {}
STATE_PLAT = {}
STATE_APPRAISER = {}

for _m in pkgutil.iter_modules(__path__):
    _mod = importlib.import_module(f"{__name__}.{_m.name}")
    if getattr(_mod, "PARCEL", None) and getattr(_mod, "STATE", None):
        STATE_PARCEL[_mod.STATE] = _mod.PARCEL
    if getattr(_mod, "DEED_LINK", None) and getattr(_mod, "STATE", None):
        STATE_DEED[_mod.STATE] = _mod.DEED_LINK
    if getattr(_mod, "PLAT_LINK", None) and getattr(_mod, "STATE", None):
        STATE_PLAT[_mod.STATE] = _mod.PLAT_LINK
    if getattr(_mod, "APPRAISER_LINK", None) and getattr(_mod, "STATE", None):
        STATE_APPRAISER[_mod.STATE] = _mod.APPRAISER_LINK
    for _fips, _entry in (getattr(_mod, "COUNTIES", {}) or {}).items():
        STATE_COUNTIES[_fips] = _entry
