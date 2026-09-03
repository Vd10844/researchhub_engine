"""Data-registry integrity tests (validation-plan 1.3).

``backend/app/data/county_platforms.py`` and the per-state modules under
``backend/app/data/states/`` are the load-bearing, hand/maintenance-curated
"source of truth" for county portals, appraisers, clerks and statewide parcel
services. A typo (bad URL, wrong FIPS, missing key) ships silently and breaks
production lookups. This sweep imports everything and asserts structural
well-formedness so registry rot is caught by CI rather than by a user.

NOTE on URLs: many real county / CAD sites only serve ``http://`` (no TLS), so
we do NOT require https — we only require a well-formed scheme+host and catch
typos (no scheme, empty host, whitespace). Unwired counties intentionally carry
no URL and fall back to the nationwide NETROnline directory by design.
"""
from __future__ import annotations

import importlib
import pkgutil
import re
from urllib.parse import urlparse

import pytest
from app.data import county_platforms as cp
from app.data import states as states_pkg

_FIPS_RE = re.compile(r"^\d{5}$")


def _collect_urls(entry: dict) -> list[str]:
    """Collect every URL-ish string in a registry entry (handles str/list/None/nested)."""
    urls: list[str] = []
    for key, value in entry.items():
        if key == "related":
            for rel in value if isinstance(value, list) else [value]:
                if isinstance(rel, dict) and rel.get("url"):
                    urls.append(rel["url"])
            continue
        if isinstance(value, str):
            if value.startswith("http://") or value.startswith("https://"):
                urls.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and (
                    item.startswith("http://") or item.startswith("https://")
                ):
                    urls.append(item)
    return urls


def _well_formed(url: str) -> bool:
    try:
        u = urlparse(url)
        return u.scheme in ("http", "https") and bool(u.netloc)
    except Exception:
        return False


# ------------------------------------------------------------------ registry


def test_registry_has_entries():
    assert isinstance(cp.REGISTRY, dict)
    assert len(cp.REGISTRY) >= 1, "county registry is empty"


def test_registry_keys_are_5_digit_fips():
    bad = [k for k in cp.REGISTRY if not _FIPS_RE.match(k)]
    assert not bad, f"registry keys must be 5-digit FIPS, got: {bad}"


def test_registry_entries_have_required_fields():
    required = ("county", "state")
    for fips, entry in cp.REGISTRY.items():
        missing = [f for f in required if f not in entry]
        assert not missing, f"county {fips} ({entry.get('county')}) missing: {missing}"


def test_registry_state_abbr_is_upper_2_letter():
    bad = [
        (fips, entry.get("state"))
        for fips, entry in cp.REGISTRY.items()
        if not (isinstance(entry.get("state"), str) and len(entry["state"]) == 2
                and entry["state"].isupper() and entry["state"].isalpha())
    ]
    assert not bad, f"state abbrs must be 2 uppercase letters, got: {bad}"


def test_registry_urls_are_well_formed():
    offenders = []
    for fips, entry in cp.REGISTRY.items():
        for url in _collect_urls(entry):
            if not _well_formed(url):
                offenders.append((fips, url))
    assert not offenders, f"malformed URLs in registry: {offenders}"


def test_registry_urls_have_no_whitespace():
    offenders = []
    for fips, entry in cp.REGISTRY.items():
        for url in _collect_urls(entry):
            if url != url.strip() or " " in url:
                offenders.append((fips, url))
    assert not offenders, f"URLs with whitespace in registry: {offenders}"


_GIS_TYPES = (str, list, type(None))


@pytest.mark.parametrize("fips", list(cp.REGISTRY.keys()))
def test_gis_rest_is_str_list_or_none(fips):
    """gis_rest may be a URL, a list of URLs, or None (not verified)."""
    gis = cp.REGISTRY[fips].get("gis_rest", None)
    assert isinstance(gis, _GIS_TYPES), f"county {fips} gis_rest must be str/list/None"
    if isinstance(gis, str) and gis:
        assert _well_formed(gis), f"county {fips} gis_rest malformed: {gis}"
    if isinstance(gis, list):
        assert gis, f"county {fips} gis_rest list is empty"
        for u in gis:
            assert _well_formed(u), f"county {fips} gis_rest list malformed: {u}"


# ------------------------------------------------------------------ state modules


def _state_modules():
    return [m.name for m in pkgutil.iter_modules(states_pkg.__path__)]


def test_every_state_module_imports_and_is_well_formed():
    errors = []
    for mod_name in _state_modules():
        try:
            mod = importlib.import_module(f"app.data.states.{mod_name}")
        except Exception:
            errors.append(f"{mod_name}: import failed")
            continue
        state = getattr(mod, "STATE", None)
        if state is None:
            errors.append(f"{mod_name}: missing STATE")
            continue
        if not (isinstance(state, str) and len(state) == 2
                and state.isupper() and state.isalpha()):
            errors.append(f"{mod_name}: STATE must be 2 uppercase letters, got {state!r}")
        parcel = getattr(mod, "PARCEL", None)
        if parcel:
            _check_state_parcel(mod_name, parcel, errors)
        for fips, entry in (getattr(mod, "COUNTIES", {}) or {}).items():
            _check_state_county(mod_name, fips, entry, errors)
    assert not errors, "registry integrity errors:\n  " + "\n  ".join(errors)


def _check_state_parcel(mod_name, parcel: dict, errors: list[str]):
    if "url" not in parcel:
        errors.append(f"{mod_name}: PARCEL missing 'url'")
        return
    urls = parcel["url"] if isinstance(parcel["url"], list) else [parcel["url"]]
    for u in urls:
        if not _well_formed(u):
            errors.append(f"{mod_name}: PARCEL url malformed: {u}")
    if "kind" not in parcel:
        errors.append(f"{mod_name}: PARCEL missing 'kind'")


def _check_state_county(mod_name, fips: str, entry: dict, errors: list[str]):
    if not _FIPS_RE.match(fips):
        errors.append(f"{mod_name}: COUNTIES key not 5-digit FIPS: {fips}")
    for required in ("county", "state"):
        if required not in entry:
            errors.append(f"{mod_name}: county {fips} missing '{required}'")
    for url in _collect_urls(entry):
        if not _well_formed(url):
            errors.append(f"{mod_name}: county {fips} malformed url: {url}")


def test_state_parcel_aggregates_have_unique_keys():
    assert len(states_pkg.STATE_PARCEL) == len(set(states_pkg.STATE_PARCEL)), (
        "STATE_PARCEL has duplicate state keys"
    )
    assert len(states_pkg.STATE_COUNTIES) == len(set(states_pkg.STATE_COUNTIES)), (
        "STATE_COUNTIES has duplicate fips"
    )


def test_state_abbrs_are_unique():
    seen = {}
    for m in _state_modules():
        st = getattr(importlib.import_module(f"app.data.states.{m}"), "STATE", None)
        if st:
            if st in seen:
                raise AssertionError(f"duplicate STATE {st!r} in {seen[st]} and {m}")
            seen[st] = m
