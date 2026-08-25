"""MI — parcel services (one module per state; edit here to debug MI).

Michigan has NO free statewide parcel layer, so parcels are wired county-by-county
(COUNTIES below), biggest-first. Deeds/plats are recorded at the county level (83 separate
Registers of Deeds, no statewide index), so the clerk link falls back to the nationwide
NETROnline directory. Probed 2026-08-18 for a statewide equivalent: the Office of Land Survey
plat site (egle.state.mi.us/opla/) is dead (404), and michigan.gov/registerofdeeds is WAF-
blocked so it could not be confirmed as a search portal rather than a directory page.

COVERAGE (2026-08-18): 18 of 83 counties have a situs-bearing parcel endpoint.
  * The first 5 (Wayne, Oakland, Macomb, Kent, Ottawa) were wired by hand 2026-08-11 — metro
    Detroit plus Grand Rapids, i.e. most of the state's order volume.
  * The next 13 came from the automated sweep: Muskegon (86k parcels), St. Clair (77k, Port
    Huron), Van Buren, Eaton (Lansing metro), Montcalm, Newaygo, Midland, Calhoun (Battle
    Creek), Ionia, Branch, St. Joseph, Charlevoix, Leelanau.
"""
STATE = "MI"
PARCEL = None   # no free statewide parcel layer
DEED_LINK = None

COUNTIES = {
    "26163": {  # Wayne — largest MI county (~1.8M), city of Detroit
        "county": "Wayne", "state": "MI",
        # Two complementary layers (tried in order): (1) the official City of Detroit parcel layer
        # — carries owner (taxpayer_1), authoritative for the city core; (2) the countywide Wayne
        # County GIS ParcelViewer — situs only (no owner) but covers the suburbs. A Detroit address
        # resolves on (1) with owner; a suburban address returns nothing on (1) and falls to (2).
        "gis_rest": [
            ("https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/"
             "parcel_file_current/FeatureServer/0"),
            ("https://www.waynecounty.com/gisserver/rest/services/ParcelViewer/"
             "prcls_fullAdd_parsed_FINAL/MapServer/0"),
        ],
        "id_fields": ["parcel_id", "packedParc", "PID_All"],
        "clerk_platform": "unknown",
    },
    "26125": {  # Oakland — 2nd-largest MI county (~1.27M), metro Detroit
        "county": "Oakland", "state": "MI",
        # Oakland County enterprise open parcel service, layer 1 "Tax Parcel Plus". Owner name
        # (NAME1/NAME2) is redacted to null on this open layer; parcel id + situs are present.
        "gis_rest": ("https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/"
                     "EnterpriseOpenParcelDataMapService/MapServer/1"),
        "id_fields": ["PIN", "KEYPIN"],
        "clerk_platform": "unknown",
    },
    "26099": {  # Macomb — 3rd-largest MI county (~875k), metro Detroit (Mount Clemens)
        "county": "Macomb", "state": "MI",
        # County enterprise GIS FLEX2 parcels; layer 4 "Property Area Boundaries"
        # (TAX_ID/ADDRESS/ownername1 + legal). NOTE the host path is /arcgis1/ (not /arcgis/).
        "gis_rest": ("https://gis.macombgov.org/arcgis1/rest/services/FLEX2/"
                     "Parcel_Layers/MapServer/4"),
        "id_fields": ["TAX_ID"],
        "clerk_platform": "unknown",
    },
    "26081": {  # Kent — 4th-largest MI county (~660k), city of Grand Rapids
        "county": "Kent", "state": "MI",
        # County GIS ParcelsWithCondos; layer 0 (PNUM/PROPERTYADDRESS/OWNERNAME1). Countywide
        # tax parcel layer (string fields are space-padded; the resolver trims).
        "gis_rest": ("https://gis.kentcountymi.gov/agisprod/rest/services/"
                     "ParcelsWithCondos/MapServer/0"),
        "id_fields": ["PNUM", "PPN"],
        "clerk_platform": "unknown",
    },
    "26139": {  # Ottawa — Holland/Grand Haven (Grand Rapids metro), ~300k
        "county": "Ottawa", "state": "MI",
        # County GIS ParcelsPublic; PropertyAddress/OwnerName (AddressNumber is a bare number,
        # skipped by the situs letter-guard).
        "gis_rest": ("https://gis.miottawa.org/arcgis/rest/services/HostedServices/"
                     "ParcelsPublic/MapServer/0"),
        "id_fields": ["FinalPIN", "ParentPIN", "CondoPIN"],
        "clerk_platform": "unknown",
    },
    # ---- Added 2026-08-18 by the automated sweep (scripts/discover_state_parcels.py ->
    #      audit_parcel_candidates.py -> verify_situs_fields.py). Four gates cleared:
    #      point-queryable with a situs; parcels returned across the WHOLE county, not just
    #      the county seat; feature count consistent with a complete roll vs Census housing
    #      units; and the app's own situs_of() returning real street addresses on sampled
    #      parcels. Provenance is in each comment. ----
    "26023": {  # Branch — 26,860 parcels (1.29x housing units), edited 2025-12-03
        "county": "Branch", "state": "MI",
        "gis_rest": ("https://services2.arcgis.com/OHynDFZ1SVDsGFwm/arcgis/rest/services/BranchC"
                     "ountyParcels/FeatureServer/191"),
        "id_fields": ["PARCELID", "PARCEL_ADD"],
        # situs 100% clean, e.g. '20 N HANCHETT ST'
        "clerk_platform": "unknown",
    },
    "26025": {  # Calhoun — 42,310 parcels (0.71x housing units), edited 2024-08-09
        "county": "Calhoun", "state": "MI",
        "gis_rest": ("https://services6.arcgis.com/cuKwt0IKP5B84jop/arcgis/rest/services/City_Cr"
                     "ew_Televising/FeatureServer/5"),
        "id_fields": ["PARCEL_ID"],
        # situs 86% clean, e.g. "34026 ANNA'S WAY SUITE 1"
        "clerk_platform": "unknown",
    },
    "26029": {  # Charlevoix — 31,247 parcels (1.79x housing units), edited 2024-08-29
        "county": "Charlevoix", "state": "MI",
        "gis_rest": ("https://services8.arcgis.com/iOTGKDZaCCAubV8c/arcgis/rest/services/charlev"
                     "oix_parcels_shp/FeatureServer/0"),
        "id_fields": ["pin", "pin_1", "last5pin"],
        # situs 81% clean, e.g. '911 E MAIN ST'
        "clerk_platform": "unknown",
    },
    "26045": {  # Eaton — 46,447 parcels (0.98x housing units), edited 2026-07-21
        "county": "Eaton", "state": "MI",
        "gis_rest": ("https://services2.arcgis.com/c9l1e4fKpsCnqD7H/arcgis/rest/services/Parcels"
                     "_AGO/FeatureServer/0"),
        "id_fields": ["LOWPARCELID", "PARCELID", "LPARCEL"],
        # situs 100% clean, e.g. '504 BURGENSTOCK DR, LANSING, MI 48917'
        "clerk_platform": "unknown",
    },
    "26067": {  # Ionia — 31,667 parcels (1.29x housing units), edited 2026-08-14
        "county": "Ionia", "state": "MI",
        "gis_rest": ("https://services9.arcgis.com/i2awudUyJK8gxxEe/arcgis/rest/services/Ionia_C"
                     "ounty_Tax_Parcels_Public/FeatureServer/0"),
        "id_fields": ["CountyParcels_PIN", "Parcel_Data_OWNERNAME", "Parcel_Data_OWNERADDRESS"],
        # situs 100% clean, e.g. '5973 W RIVERSIDE DR SARANAC MI 48881'
        "clerk_platform": "unknown",
    },
    "26089": {  # Leelanau — 25,053 parcels (1.62x housing units), edited 2024-09-05
        "county": "Leelanau", "state": "MI",
        "gis_rest": ("https://services7.arcgis.com/fxYnXhgYKUlZqDAy/arcgis/rest/services/Leelana"
                     "u_Parcels_2024/FeatureServer/0"),
        "id_fields": ["PARCEL"],
        # situs 100% clean, e.g. '11625 E SMITH RD'
        "clerk_platform": "unknown",
    },
    "26111": {  # Midland — 25,142 parcels (0.68x housing units), edited 2025-01-11
        "county": "Midland", "state": "MI",
        "gis_rest": ("https://services8.arcgis.com/oPzYIHLHP6C6pRlh/arcgis/rest/services/TaxParc"
                     "els/FeatureServer/18"),
        "id_fields": ["ParcelNumber"],
        # situs 100% clean, e.g. '300 S THIRD ST'
        "clerk_platform": "unknown",
    },
    "26117": {  # Montcalm — 44,024 parcels (1.58x housing units), edited 2026-07-24
        "county": "Montcalm", "state": "MI",
        "gis_rest": ("https://services6.arcgis.com/GJ2uZAPsEvtmqpe1/ArcGIS/rest/services/Tax_Par"
                     "cels/FeatureServer/0"),
        "id_fields": ["TaxParcel_PARCELID"],
        # situs 97% clean, e.g. '6448 N WEST COUNTY LINE RD'
        "clerk_platform": "unknown",
    },
    "26121": {  # Muskegon — 85,735 parcels (1.15x housing units), edited 2023-04-12
        "county": "Muskegon", "state": "MI",
        "gis_rest": ("https://services5.arcgis.com/X42k956XlfnIoN3d/arcgis/rest/services/Kent_Ot"
                     "tawa_Muskegon_Parcels/FeatureServer/1"),
        "id_fields": ["PIN"],
        # situs 100% clean, e.g. '588 3 MILE RD NW STE 203'
        "clerk_platform": "unknown",
    },
    "26123": {  # Newaygo — 40,047 parcels (1.63x housing units), edited 2026-07-22
        "county": "Newaygo", "state": "MI",
        "gis_rest": ("https://services6.arcgis.com/pcT1Mx8rlQHDmzpy/arcgis/rest/services/PivotPo"
                     "intParcelsNewaygo/FeatureServer/0"),
        "id_fields": ["PIN", "PACKEDPIN", "PARCEL"],
        # situs 100% clean, e.g. '5244 E 18 MILE RD'
        "clerk_platform": "unknown",
    },
    "26147": {  # St. Clair — 77,123 parcels (1.07x housing units), edited 2025-10-31
        "county": "St. Clair", "state": "MI",
        "gis_rest": ("https://services7.arcgis.com/uns3DkaXlVtg1Y2Q/arcgis/rest/services/Sanilac"
                     "___St__Clair_Drain_WFL1/FeatureServer/9"),
        "id_fields": ["PIN", "PARCEL_NUM"],
        # situs 100% clean, e.g. '6111 OLD COUNTRY LANE'
        "clerk_platform": "unknown",
    },
    "26149": {  # St. Joseph — 28,346 parcels (1.05x housing units), edited 2026-06-01
        "county": "St. Joseph", "state": "MI",
        "gis_rest": ("https://services5.arcgis.com/jvZ2ldpSLd1kK0tx/arcgis/rest/services/StJoeCo"
                     "ParcelsAGOWM/FeatureServer/0"),
        "id_fields": ["PIN", "PARCELNUM"],
        # situs 100% clean, e.g. '3742 W KALAMO HWY'
        "clerk_platform": "unknown",
    },
    "26159": {  # Van Buren — 51,318 parcels (1.39x housing units), edited 2026-06-16
        "county": "Van Buren", "state": "MI",
        "gis_rest": ("https://services3.arcgis.com/fOViEAUKl91t9cT6/arcgis/rest/services/Parcels"
                     "/FeatureServer/0"),
        "id_fields": ["PARCEL_NO"],
        # situs 100% clean, e.g. '22ND ST'
        "clerk_platform": "unknown",
    },
    # TODO (follow-up — the 2026-08-18 sweep surfaced no usable layer for these):
    #   Genesee (26049, Flint), Washtenaw (26161, Ann Arbor), Ingham (26065, Lansing).
    # TRIED AND REJECTED 2026-08-18 (re-run the scripts if a county republishes):
    #   Kalamazoo (26077) — only match held 1% of the roll (a subset layer), 8 years stale.
    #   Arenac (26011) — complete roll, but every candidate last edited 7.8-8.2 years ago.
    # NOTE on the four Lake Michigan counties below (Charlevoix, Leelanau, Muskegon, Van Buren):
    #   each scored only 0.5-0.75 on the sweep's county-wide coverage test. That is a WATER
    #   artifact, not a coverage gap — TIGER county polygons include lake area, so the sampled
    #   test points fell offshore (Muskegon's missed point was at lon -86.92; its shoreline is
    #   ~-86.35). Each was confirmed by hand to return a parcel at its county seat.
}
