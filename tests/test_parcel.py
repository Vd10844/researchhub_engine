"""Offline unit tests for parcel-identity validation + lot-area extraction.

No network: we feed the selection/extraction logic synthetic ArcGIS attribute dicts
modeled on real FL DOR records (incl. the 526 vs 505 Hampton neighbor bug) and assert
the right parcel is chosen, mismatches are flagged, and lot area is read correctly.

Run:  ../.venv/Scripts/python.exe -m unittest -v   (from tests/)
      .venv/Scripts/python.exe -m unittest discover tests   (from repo root)
"""
import pathlib
import sys
import unittest

# Make the backend package importable without installing anything.
_BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services import parcel as P  # noqa: E402

# --- Real neighbor parcels from the 526 Hampton Ave, Lakeland FL case ----------
C526 = {"PARCEL_ID": "242821240400006020", "PHY_ADDR1": "526 HAMPTON AVE",
        "LND_SQFOOT": 7800, "OWN_NAME": "SUBJECT OWNER"}
C505 = {"PARCEL_ID": "242821240400005100", "PHY_ADDR1": "505 HAMPTON AVE",
        "LND_SQFOOT": 8124, "OWN_NAME": "DEASE APRIL S"}
SEARCH = "526 HAMPTON AVE, LAKELAND, FL, 33801"


class House(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(P._house("526 HAMPTON AVE"), "526")
        self.assertEqual(P._house("  505 Hampton Ave, Lakeland"), "505")

    def test_unit_and_missing(self):
        self.assertEqual(P._house("526A HAMPTON"), "526")
        self.assertEqual(P._house("HAMPTON AVE"), "")
        self.assertEqual(P._house(""), "")

    def test_trailing_house_number(self):
        # TN layer stores the number last: "N ROYAL ST 214".
        self.assertEqual(P._house("N ROYAL ST 214"), "214")
        self.assertEqual(P._street_tokens("N ROYAL ST 214"), ["ROYAL"])
        # A number-last situs matches a normal number-first search.
        self.assertIs(P._addr_match("214 N ROYAL ST", "N ROYAL ST 214"), True)


class StreetTokens(unittest.TestCase):
    def test_drops_house_suffix_directional(self):
        self.assertEqual(P._street_tokens("526 HAMPTON AVE"), ["HAMPTON"])
        self.assertEqual(P._street_tokens("526 N MAIN ST"), ["MAIN"])
        self.assertEqual(P._street_tokens("526 MAIN ST N"), ["MAIN"])

    def test_keeps_numbered_street(self):
        self.assertEqual(P._street_tokens("526 42ND ST"), ["42ND"])

    def test_ignores_city_state_zip(self):
        self.assertEqual(P._street_tokens("526 HAMPTON AVE, LAKELAND, FL, 33801"),
                         ["HAMPTON"])


class AddrMatch(unittest.TestCase):
    def test_exact(self):
        self.assertIs(P._addr_match(SEARCH, "526 HAMPTON AVE"), True)

    def test_suffix_variation(self):
        self.assertIs(P._addr_match("526 HAMPTON AVE", "526 HAMPTON AVENUE"), True)
        self.assertIs(P._addr_match("526 HAMPTON AVE", "526 HAMPTON"), True)

    def test_wrong_house(self):
        self.assertIs(P._addr_match(SEARCH, "505 HAMPTON AVE"), False)

    def test_right_house_wrong_street(self):
        self.assertIs(P._addr_match("526 HAMPTON AVE", "526 OAK ST"), False)

    def test_not_comparable(self):
        self.assertIsNone(P._addr_match("HAMPTON AVE", "526 HAMPTON AVE"))
        self.assertIsNone(P._addr_match("526 HAMPTON", ""))


class Situs(unittest.TestCase):
    def test_variants(self):
        self.assertEqual(P.situs_of({"PHY_ADDR1": "526 HAMPTON AVE"}), "526 HAMPTON AVE")
        self.assertEqual(P.situs_of({"SITUS_ADDR": "10 OAK ST"}), "10 OAK ST")
        self.assertEqual(P.situs_of({"SITE_ADDR": "10 OAK ST"}), "10 OAK ST")
        self.assertEqual(P.situs_of({"PropLoc": "10 OAK ST"}), "10 OAK ST")
        self.assertEqual(P.situs_of({"OWN_NAME": "SMITH"}), "")

    def test_adress_misspelled_national_standard(self):
        # WI + the national parcel standard use SITEADRESS (one D). situsAdd (CO) via "situs".
        self.assertEqual(P.situs_of({"SITEADRESS": "733 N MILWAUKEE ST"}), "733 N MILWAUKEE ST")
        self.assertEqual(P.situs_of({"situsAdd": "144 W COLFAX AVE", "sitAddZip": "80202"}),
                         "144 W COLFAX AVE")
        # WI national-standard schema: PSTLADRESS (mailing) must NOT win over SITEADRESS (situs),
        # even though it appears first and also contains "adress".
        self.assertEqual(P.situs_of({"PSTLADRESS": "5005 NEWPORT DR STE 501 ROLLING MEADOWS, IL",
                                     "SITEADRESS": "733 N MILWAUKEE ST"}), "733 N MILWAUKEE ST")

    def test_full_field_wins_over_components(self):
        # Chatham/SAGIS: the concatenated field must win over PropAddress_Num/_City, whatever
        # the dict order.
        attrs = {"PropAddress_Num": "143", "PropAddress_City": "SAVANNAH",
                 "PropAddress_Full": "143 W RIVER ST"}
        self.assertEqual(P.situs_of(attrs), "143 W RIVER ST")

    def test_skips_city_state_component(self):
        # Kent MI: PROPERTYADDRESS is the street; PROPADDRESSCITY shares the prefix but is a city.
        attrs = {"PROPADDRESSCITY": "GRAND RAPIDS", "PROPERTYADDRESS": "26 DIVISION AVE N"}
        self.assertEqual(P.situs_of(attrs), "26 DIVISION AVE N")

    def test_collapses_internal_whitespace(self):
        # Cobb GA stores irregular internal whitespace in SITUS_ADDR.
        self.assertEqual(P.situs_of({"SITUS_ADDR": "191   SUMMIT  AVE"}), "191 SUMMIT AVE")

    def test_composes_from_split_components(self):
        # Will County IL Parcels_LY has no single situs field — assemble from components.
        attrs = {"HOUSENUMBE": "70", "PREFIXDIRE": "N", "STREETNAME": "CHICAGO",
                 "SUFFIXTYPE": "ST", "CITY": "JOLIET", "STATE": "IL", "ZIP_CODE": "60432"}
        self.assertEqual(P.situs_of(attrs), "70 N CHICAGO ST")

    def test_compose_prefers_situs_over_owner_mailing(self):
        # Muscogee GA CAMA carries BOTH Property_Street* (situs) and Owner_Street* (mailing);
        # the composed situs must use the property components, not the owner's mailing street.
        attrs = {"Owner_Number": "500", "Owner_StreetName": "VETERANS", "Owner_StreetType": "PKWY",
                 "Property_Number": "824", "Property_StreetName": "3RD", "Property_StreetType": "AVE",
                 "Property_CityCode": "COLUMBUS"}
        self.assertEqual(P.situs_of(attrs), "824 3RD AVE")

    def test_situs_exclude_mailing_field_then_composes(self):
        # Coweta GA: StreetAddress is the owner MAILING address -> exclude it and compose situs.
        attrs = {"StreetAddress": "160 TEMPLE AVENUE", "HouseNumber": "108",
                 "StreetName": "MEADOWVIEW", "StreetType": "LN"}
        self.assertEqual(P.situs_of(attrs, exclude=("StreetAddress",)), "108 MEADOWVIEW LN")

    def test_number_field_is_not_reused_as_street_name(self):
        # Worth GA: ADDRESS_NU (house number) matches the number aliases AND the name pass's
        # "addr" fragment, so before the `taken` guard this composed "201 201".
        attrs = {"ADDRESS_NU": "402", "STREET": "FRANKLIN", "Parcel_No": "SV060077"}
        self.assertEqual(P.situs_of(attrs), "402 FRANKLIN")

    def test_bare_street_field_is_a_street_name(self):
        # A layer whose street-name column is just "STREET" (Worth/Stewart GA).
        self.assertEqual(P.situs_of({"STREET_NUM": "30", "STREET": "GA HWY 27"}),
                         "30 GA HWY 27")

    def test_streetnumb_alias_composes(self):
        # Newton GA uses StreetNumb/StreetDire/StreetName/StreetType.
        attrs = {"StreetNumb": "7211", "StreetDire": " ", "StreetName": "HWY 212",
                 "StreetType": " "}
        self.assertEqual(P.situs_of(attrs), "7211 HWY 212")

    def test_no_number_gives_no_composed_situs(self):
        # Newton GA's published mirror has StreetName but a blank StreetNumb for every row, and
        # Address1 is the owner MAILING address. With Address1 excluded there is no house
        # number, so the situs must stay EMPTY rather than be invented from the street alone
        # (an invented situs would produce a false address match).
        attrs = {"StreetNumb": " ", "StreetName": "STALLING", "StreetType": "ST",
                 "Address1": "1124 CLARK STREET", "City": "LITHONIA"}
        self.assertEqual(P.situs_of(attrs, exclude=("Address1", "City")), "")


class LandArea(unittest.TestCase):
    def test_sqft_gives_acres(self):
        self.assertEqual(P.land_area_of({"LND_SQFOOT": 7800}), (7800.0, 0.179))

    def test_acres_gives_sqft(self):
        self.assertEqual(P.land_area_of({"gisacres": 0.35}), (15246, 0.35))

    def test_both_present_untouched(self):
        self.assertEqual(P.land_area_of({"LND_SQFOOT": 7800, "GISACRES": 0.18}),
                         (7800.0, 0.18))

    def test_none(self):
        self.assertEqual(P.land_area_of({"OWN_NAME": "SMITH"}), (None, None))


class Choose(unittest.TestCase):
    def test_picks_address_match_not_first(self):
        # 505 is first in the list but 526 is the searched address -> must pick 526.
        chosen, matched = P._choose([C505, C526], SEARCH)
        self.assertEqual(chosen["PARCEL_ID"], C526["PARCEL_ID"])
        self.assertTrue(matched)

    def test_flags_when_only_neighbor_present(self):
        chosen, matched = P._choose([C505], SEARCH)
        self.assertEqual(chosen["PARCEL_ID"], C505["PARCEL_ID"])
        self.assertFalse(matched)  # not confident -> gets a verify flag

    def test_street_breaks_house_collision(self):
        oak = {"PARCEL_ID": "OAK", "PHY_ADDR1": "526 OAK ST"}
        ham = {"PARCEL_ID": "HAM", "PHY_ADDR1": "526 HAMPTON AVE"}
        chosen, matched = P._choose([oak, ham], "526 HAMPTON AVE")
        self.assertEqual(chosen["PARCEL_ID"], "HAM")
        self.assertTrue(matched)

    def test_no_address_returns_first(self):
        chosen, matched = P._choose([C505, C526], "")
        self.assertEqual(chosen["PARCEL_ID"], C505["PARCEL_ID"])
        self.assertFalse(matched)

    def test_skips_null_situs_placeholder(self):
        # Cobb GA: a PIN='000' ROW polygon with null situs intersects alongside the real parcel;
        # when nothing address-matches we must still prefer the row that has a situs.
        placeholder = {"PIN": "000", "SITUS_ADDR": ""}
        real = {"PIN": "16128800070", "SITUS_ADDR": "191 SUMMIT AVE"}
        chosen, matched = P._choose([placeholder, real], "999 NOWHERE RD")
        self.assertEqual(chosen["PIN"], "16128800070")
        self.assertFalse(matched)


class Finish(unittest.TestCase):
    def _finish(self, candidates, buffered, address):
        chosen, matched = P._choose(candidates, address)
        return P._finish({"hints": {}}, chosen, candidates, buffered, matched,
                         address, "http://svc")

    def test_correct_parcel_confident(self):
        r = self._finish([C505, C526], False, SEARCH)
        self.assertEqual(r["parcels"][0]["PARCEL_ID"], C526["PARCEL_ID"])
        self.assertEqual(r["situs"], "526 HAMPTON AVE")
        self.assertEqual(r["land_sqft"], 7800.0)
        self.assertEqual(r["land_acres"], 0.179)
        self.assertIs(r["address_match"], True)
        self.assertFalse(r["buffered_match"])

    def test_neighbor_only_is_flagged(self):
        r = self._finish([C505], True, SEARCH)  # buffered hit, wrong parcel
        self.assertIs(r["address_match"], False)
        self.assertTrue(r["buffered_match"])
        self.assertEqual(r["candidate_count"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
