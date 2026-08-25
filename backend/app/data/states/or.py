"""OR — parcel services (one module per state; edit here to debug OR).

Oregon's statewide ORMAP taxlot service is render-only (no /query) and the DOR one is
token-secured, so there is no free queryable statewide layer. Parcels are wired for the Portland
metro (~1.9M people): Multnomah County's own service (has owner) + the Oregon Metro RLIS taxlot
layer, which covers the whole 3-county metro (Multnomah/Washington/Clackamas) but without owner.
Verified 2026-08-12.
"""
STATE = "OR"
PARCEL = None   # no free queryable statewide taxlot layer — county/metro-by-metro here

# Oregon Metro RLIS "Taxlots (Public)" — one layer spanning Multnomah + Washington + Clackamas.
_METRO_RLIS = ("https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/"
               "Taxlots_(Public)/FeatureServer/3")

COUNTIES = {
    "41051": {  # Multnomah — Portland; county service exposes owner (NAME)
        "county": "Multnomah", "state": "OR",
        "gis_rest": ("https://services5.arcgis.com/x7DNZL1YqNQVNykA/arcgis/rest/services/"
                     "Multnomah_County_Taxlot_Parcels/FeatureServer/0"),
        "id_fields": ["MAPTAXLOT", "PROPID", "ALTACCTNUM"],
        "clerk_platform": "unknown",
    },
    "41067": {  # Washington — Beaverton/Hillsboro; via Metro RLIS (situs, no owner)
        "county": "Washington", "state": "OR",
        "gis_rest": _METRO_RLIS,
        "id_fields": ["TLID", "PRIMACCNUM", "ORTAXLOT"],
        "clerk_platform": "unknown",
    },
    "41005": {  # Clackamas — Oregon City; via Metro RLIS (situs, no owner)
        "county": "Clackamas", "state": "OR",
        "gis_rest": _METRO_RLIS,
        "id_fields": ["TLID", "PRIMACCNUM", "ORTAXLOT"],
        "clerk_platform": "unknown",
    },
    "41039": {  # Lane — Eugene, ~380k
        "county": "Lane", "state": "OR",
        # Parcel polygon (layer 2) has MAPTAXLOT + OWNNAME (its ADDR* fields are owner mailing);
        # situs (concat_address) is on the Address-Site layer 0, joined on MAPTAXLOT.
        "gis_rest": ("https://lcmaps.lanecounty.org/arcgis/rest/services/LaneCountyMaps/"
                     "AddressParcel/MapServer/2"),
        "id_fields": ["MAPTAXLOT", "TAXLOT", "ACCTNO"],
        "related": {"url": ("https://lcmaps.lanecounty.org/arcgis/rest/services/LaneCountyMaps/"
                            "AddressParcel/MapServer/0"), "key": "MAPTAXLOT"},
        "clerk_platform": "unknown",
    },
    "41047": {  # Marion — Salem (state capital), ~350k
        "county": "Marion", "state": "OR",
        "gis_rest": ("https://services3.arcgis.com/SXXjryU22GsO8OEC/arcgis/rest/services/"
                     "Parcels/FeatureServer/0"),
        "id_fields": ["TAXLOT", "ALT_TAXLOT"],
        "clerk_platform": "unknown",
    },
    "41029": {  # Jackson — Medford, ~225k
        "county": "Jackson", "state": "OR",
        "gis_rest": ("https://services1.arcgis.com/aD4sstpQmlnZu2vq/arcgis/rest/services/"
                     "Taxlots/FeatureServer/0"),
        "id_fields": ["MAPNUMBER", "TAXLOT", "ACCOUNT"],
        "clerk_platform": "unknown",
    },
    "41035": {  # Klamath — Klamath Falls, ~70k
        "county": "Klamath", "state": "OR",
        "gis_rest": ("https://services.arcgis.com/H6Mh1bySxR4oHx6x/arcgis/rest/services/"
                     "KC_Taxlots/FeatureServer/1"),
        "id_fields": ["MAP_TAXLOT", "MapNumber", "ORMapNum"],
        "clerk_platform": "unknown",
    },
    # TODO (follow-up, own-host / not on public AGOL): Deschutes/Bend (41017), Linn (41043),
    # Douglas (41019), Benton (41003), Yamhill (41071).
}
