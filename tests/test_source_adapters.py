"""Source-adapter recorded-response tests (validation-plan 1.1).

The engine's biggest, most brittle code is the real source scrapers. Where a
pure parse function exists it can be pinned offline with representative payloads
(no network, no browser):

  - ``parcel.situs_of`` / ``parcel.land_area_of``  — extract situs + lot area
    from ArcGIS attribute dicts (the shape the real FeatureServer returns).
  - ``http.check_url``  — classify real-world reachability verdicts
    (ok / blocked / broken / offline), mocked via ``responses``.

These pin the parse/classification behavior the docs freeze, so a refactor of
the 30 KB+ source modules can't silently change what gets extracted.
"""
from __future__ import annotations

import pytest
import requests
import responses
from app.services import http, parcel

# ------------------------------------------------------------------ situs_of


def test_situs_of_full_field_wins():
    attrs = {
        "SITUSADDRESS": "1015 E PALMETTO ST",
        "SITUS_CITY": "Lakeland",       # excluded (city)
        "ZIPCODE": "33801",             # excluded (zip)
    }
    assert parcel.situs_of(attrs) == "1015 E PALMETTO ST"


def test_situs_of_alias_field():
    attrs = {"PROPERTYADDRESS": "  220 W COMMERCIAL ST  ", "PROPERTYADDRESSCITY": "X"}
    assert parcel.situs_of(attrs) == "220 W COMMERCIAL ST"


def test_situs_of_composes_from_components():
    attrs = {
        "HOUSENUMBER": "123",
        "PREFIXDIR": "N",
        "STREETNAME": "MAIN",
        "SUFFIXTYPE": "ST",
        "SUFFIXDIR": "E",
    }
    assert parcel.situs_of(attrs) == "123 N MAIN ST E"


def test_situs_of_owner_mailing_excluded():
    attrs = {
        "PROPERTYADDRESS": "220 W COMMERCIAL ST",
        "OWNERADDRESS": "PO BOX 900",
    }
    # Owner mailing (drop the owner's PO box) must not win over the situs.
    assert parcel.situs_of(attrs) == "220 W COMMERCIAL ST"


def test_situs_of_ignores_bare_number_and_directional():
    # A field that's only a number or only a direction is not a street address.
    attrs = {"ADDRESSNUMBER": "2407", "PROPERTYADDRESS": "2407 OLD CANTON RD"}
    # Pass 1 alias order: "address" alias can catch ADDRESSNUMBER but _has_street
    # requires a letter+digit, so it falls through to the real situs field.
    assert parcel.situs_of(attrs) == "2407 OLD CANTON RD"


def test_situs_of_exclude_tuple_honored():
    attrs = {"STREETADDRESS": "PO BOX 100"}
    # Whitfield GA: StreetAddress is the owner MAILING address; exclude it.
    assert parcel.situs_of(attrs, exclude=("streetaddress",)) == ""


# ------------------------------------------------------------------ land_area_of


def test_land_area_from_sqft():
    sqft, acres = parcel.land_area_of({"LNDSQFOOT": "21780"})
    assert sqft == 21780.0
    assert acres == pytest.approx(0.5, abs=0.01)


def test_land_area_from_acres():
    sqft, acres = parcel.land_area_of({"GISACRES": "1.25"})
    assert sqft == pytest.approx(54450, abs=1)
    assert acres == 1.25


def test_land_area_missing_is_none():
    assert parcel.land_area_of({"OWNER": "X"}) == (None, None)


# ------------------------------------------------------------------ http.check_url


@responses.activate
def test_check_url_ok():
    responses.add(responses.GET, "https://example.test/a", status=200, body="ok")
    verdict = http.check_url("https://example.test/a")
    assert verdict["verdict"] == "ok"
    assert verdict["status"] == 200


@responses.activate
def test_check_url_waf_403_is_blocked():
    responses.add(responses.GET, "https://example.test/waf", status=403)
    verdict = http.check_url("https://example.test/waf")
    assert verdict["verdict"] == "blocked"
    assert verdict["status"] == 403


@responses.activate
def test_check_url_404_is_broken():
    responses.add(responses.GET, "https://example.test/gone", status=404)
    verdict = http.check_url("https://example.test/gone")
    assert verdict["verdict"] == "broken"


@responses.activate
def test_check_url_5xx_is_broken():
    responses.add(responses.GET, "https://example.test/err", status=500)
    verdict = http.check_url("https://example.test/err")
    assert verdict["verdict"] == "broken"


@responses.activate
def test_check_url_timeout_is_offline():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(
            responses.GET,
            "https://example.test/slow",
            body=requests.exceptions.Timeout("timed out"),
        )
        verdict = http.check_url("https://example.test/slow")
    assert verdict["verdict"] == "offline"
    assert verdict["status"] is None


@responses.activate
def test_check_url_connection_error_is_offline():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(
            responses.GET,
            "https://example.test/down",
            body=requests.exceptions.ConnectionError("reset"),
        )
        verdict = http.check_url("https://example.test/down")
    assert verdict["verdict"] == "offline"
