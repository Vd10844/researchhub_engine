"""IL — parcel services (one module per state; edit here to debug IL).

Illinois has NO free statewide parcel layer, so parcels are wired county-by-county
(COUNTIES below), biggest-first. Deeds/plats are recorded at the county level (102 separate
County Recorders, no statewide index like GA's GSCCCA), so the clerk link falls back to the
nationwide NETROnline directory. Probed 2026-08-18 for a statewide equivalent: none exists —
the ISGS clearinghouse is geological data, not land records.

COVERAGE (2026-08-18): 19 of 102 counties have a situs-bearing parcel endpoint.
  * The first 5 (Cook, DuPage, Lake, Will, Kane) were wired by hand 2026-08-11 — the Chicago
    metro, i.e. most of the state's order volume.
  * The next 14 came from the automated sweep, and include real metros: McHenry (150k parcels),
    St. Clair (148k, Metro East/St. Louis), Winnebago (129k, Rockford), McLean (71k,
    Bloomington-Normal), Tazewell + Macon (Peoria, Decatur), Kankakee.
"""
STATE = "IL"
PARCEL = None   # no free statewide parcel layer
DEED_LINK = None

COUNTIES = {
    "17031": {  # Cook — largest IL county (~5.1M), city of Chicago
        "county": "Cook", "state": "IL",
        # Cook County assessor-backed CookViewer parcels (layer 0). Owner name is NOT on this
        # public layer (look up by PIN on cookcountypropertyinfo.com); PIN + situs are present.
        "gis_rest": ("https://gis12.cookcountyil.gov/traditional/rest/services/"
                     "CookViewer3Parcels/MapServer/0"),
        "id_fields": ["PIN14_dash", "PIN14", "PARID"],
        "clerk_platform": "unknown",
    },
    "17043": {  # DuPage — 2nd-largest IL county (~930k), metro Chicago
        "county": "DuPage", "state": "IL",
        # DuPage County IT/GIS + County Clerk parcels-with-real-estate layer (layer 0).
        "gis_rest": ("https://gis.dupageco.org/arcgis/rest/services/DuPage_County_IL/"
                     "ParcelsWithRealEstateCC/MapServer/0"),
        "id_fields": ["PIN"],
        "clerk_platform": "unknown",
    },
    "17097": {  # Lake — 3rd-largest IL county (~700k), metro Chicago (Waukegan)
        "county": "Lake", "state": "IL",
        # County CCAO tax parcels; layer 12 "Tax Parcel Information" (PIN/situs/taxpayer_name +
        # lot area, legal, sales).
        "gis_rest": ("https://maps.lakecountyil.gov/arcgis/rest/services/GISMapping/"
                     "WABParcels/MapServer/12"),
        "id_fields": ["PIN"],
        "clerk_platform": "unknown",
    },
    "17197": {  # Will — 4th-largest IL county (~700k), metro Chicago (Joliet)
        "county": "Will", "state": "IL",
        # County "Levy Year" parcels (PIN + split address components -> composed situs; no owner
        # on this layer). Hosted on Will County's official ArcGIS Online org.
        "gis_rest": ("https://services.arcgis.com/fGsbyIOAuxHnF97m/arcgis/rest/services/"
                     "Parcels_LY/FeatureServer/0"),
        "id_fields": ["PIN"],
        "clerk_platform": "unknown",
    },
    "17089": {  # Kane — Aurora/Geneva (Chicago metro), ~530k
        "county": "Kane", "state": "IL",
        "gis_rest": "https://gistech.countyofkane.org/arcgis/rest/services/KanePINList/MapServer/0",
        "id_fields": ["PIN"],
        "clerk_platform": "unknown",
    },
    # ---- Added 2026-08-18 by the automated sweep (scripts/discover_state_parcels.py ->
    #      audit_parcel_candidates.py -> verify_situs_fields.py). Four gates cleared:
    #      point-queryable with a situs; parcels returned across the WHOLE county, not just
    #      the county seat; feature count consistent with a complete roll vs Census housing
    #      units; and the app's own situs_of() returning real street addresses on sampled
    #      parcels. Provenance is in each comment. ----
    "17005": {  # Bond — 14,477 parcels (2.11x housing units), edited 2026-08-12
        "county": "Bond", "state": "IL",
        "gis_rest": ("https://services.arcgis.com/VbP0KHITyLTMBTy3/arcgis/rest/services/Parcels/"
                     "FeatureServer/0"),
        "id_fields": ["parcel_number", "alternate_parcel_number"],
        # situs 66% clean, e.g. '12243 KEYESPORT RD'
        "clerk_platform": "unknown",
    },
    "17009": {  # Brown — 5,615 parcels (2.41x housing units), edited 2026-07-30
        "county": "Brown", "state": "IL",
        "gis_rest": ("https://services1.arcgis.com/aHxsJXn8GAlRIIIg/arcgis/rest/services/Parcels"
                     "/FeatureServer/2"),
        "id_fields": ["ParcelID", "PIN", "ALTPIN"],
        # situs 100% clean, e.g. '40 1630E ST'
        "clerk_platform": "unknown",
    },
    "17049": {  # Effingham — 23,514 parcels (1.54x housing units), edited 2025-10-17
        "county": "Effingham", "state": "IL",
        "gis_rest": ("https://services5.arcgis.com/4aeqJB5xSs86LgEv/arcgis/rest/services/Effingh"
                     "am_Public_View/FeatureServer/1"),
        "id_fields": ["PinAssesso", "PinFormatt", "PinUnforma"],
        # situs 100% clean, e.g. 'N 1525th St Mason IL 62443'
        "clerk_platform": "unknown",
    },
    "17063": {  # Grundy — 27,540 parcels (1.3x housing units), edited 2026-07-06
        "county": "Grundy", "state": "IL",
        "gis_rest": ("https://services6.arcgis.com/xzQjU5cYdJs9TQI4/arcgis/rest/services/Economi"
                     "cDevelopment_WFL1/FeatureServer/14"),
        "id_fields": ["PIN"],
        # situs 90% clean, e.g. '1100 W LIVINGSTON RD'
        "clerk_platform": "unknown",
    },
    "17073": {  # Henry — 31,932 parcels (1.44x housing units), edited 2026-08-17
        "county": "Henry", "state": "IL",
        "gis_rest": ("https://services.arcgis.com/4YineAQdtmx0tv46/arcgis/rest/services/Parcel_H"
                     "enry/FeatureServer/0"),
        "id_fields": ["PIN", "PIN_J", "ParcelNumber_Formatted"],
        # situs 98% clean, e.g. '410 SW 2ND AVE'
        "clerk_platform": "unknown",
    },
    "17091": {  # Kankakee — 54,929 parcels (1.21x housing units), edited no edit date published
        "county": "Kankakee", "state": "IL",
        "gis_rest": ("https://k3gis.net/arcgis/rest/services/Cadastral/Tax_Parcels_and_Subdivisi"
                     "ons_2025/MapServer/0"),
        "id_fields": ["pin", "parcel_number", "formatted_parcel"],
        # situs 83% clean, e.g. '108 N AMES ST'
        "clerk_platform": "unknown",
    },
    "17109": {  # McDonough — 18,348 parcels (1.35x housing units), edited no edit date published
        "county": "McDonough", "state": "IL",
        "gis_rest": "https://gis.wiu.edu/arcgis/rest/services/mcdonough_highway/MapServer/21",
        "id_fields": ["PARCELID", "FIRST_PIN", "NEW_PIN"],
        # situs 100% clean, e.g. '409 MACOMB ST'
        "clerk_platform": "unknown",
    },
    "17111": {  # McHenry — 150,087 parcels (1.25x housing units), edited 2026-08-14
        "county": "McHenry", "state": "IL",
        "gis_rest": ("https://services1.arcgis.com/6iYC5AXXYapRVNzl/arcgis/rest/services/McHenry"
                     "_County_TaxParcels/FeatureServer/0"),
        "id_fields": ["ParcelNumber", "ParcelArea"],
        # situs 100% clean, e.g. '6008 PLEASANT HILL RD'
        "clerk_platform": "unknown",
    },
    "17113": {  # McLean — 71,425 parcels (0.95x housing units), edited no edit date published
        "county": "McLean", "state": "IL",
        "gis_rest": ("https://www.mcgisweb.org/mcgc/rest/services/Cadastral/Cadastral_Web/MapSer"
                     "ver/0"),
        "id_fields": ["PIN", "Dash_PIN", "parcel_year"],
        # situs 98% clean, e.g. '6 GRAYSTONE CT'
        "clerk_platform": "unknown",
    },
    "17115": {  # Macon — 57,044 parcels (1.15x housing units), edited 2026-08-11
        "county": "Macon", "state": "IL",
        "gis_rest": ("https://services1.arcgis.com/a3k0qIja5SolIRYR/arcgis/rest/services/Parcels"
                     "2021/FeatureServer/0"),
        "id_fields": ["ParcelNumb"],
        # situs 62% clean, e.g. '15232 N KENNY RD~MAROA, IL 61756'
        "clerk_platform": "unknown",
    },
    "17131": {  # Mercer — 14,012 parcels (1.92x housing units), edited 2023-09-22
        "county": "Mercer", "state": "IL",
        "gis_rest": ("https://services1.arcgis.com/p5CKEkDVdYePfy0g/arcgis/rest/services/Parcel/"
                     "FeatureServer/39"),
        "id_fields": ["PIN", "AltPIN", "parcel_number"],
        # situs 100% clean, e.g. '2646 1ST AVE'
        "clerk_platform": "unknown",
    },
    "17163": {  # St. Clair — 147,886 parcels (1.29x housing units), edited no edit date published
        "county": "St. Clair", "state": "IL",
        "gis_rest": ("https://arcgispublicmap.co.st-clair.il.us/server/rest/services/SCC_parcel_"
                     "map_data/MapServer/29"),
        "id_fields": ["parcelid", "parcel_number"],
        # situs 100% clean, e.g. '11329 RANDOLPH COUNTY LINE RD'
        "clerk_platform": "unknown",
    },
    "17179": {  # Tazewell — 68,098 parcels (1.16x housing units), edited no edit date published
        "county": "Tazewell", "state": "IL",
        "gis_rest": ("https://gis.tazewell-il.gov/arcgis/rest/services/WAB/TazCo_Parcels_WithOwn"
                     "er/MapServer/1"),
        "id_fields": ["PIN2", "PIN", "parcel_number"],
        # situs 68% clean, e.g. '103 3RD ST'
        "clerk_platform": "unknown",
    },
    "17201": {  # Winnebago — 128,608 parcels (1.03x housing units), edited 2026-07-30
        "county": "Winnebago", "state": "IL",
        "gis_rest": ("https://services9.arcgis.com/s8vOzt2hgxqrWawQ/arcgis/rest/services/Parcels"
                     "_and_Addresses/FeatureServer/1"),
        "id_fields": ["PrimaryPIN", "PIN", "DashPIN"],
        # situs 100% clean, e.g. '1906 BRUNER ST'
        "clerk_platform": "unknown",
    },
    # TODO (follow-up — no complete, current, situs-bearing layer found): DeKalb (17037),
    #   Madison (17119). McHenry + Winnebago came off this list in the 2026-08-18 sweep.
    # TRIED AND REJECTED 2026-08-18 (re-run the scripts if a county republishes):
    #   Fayette (17051), Greene (17061) — full current rolls, but every address-like field
    #     (TSC_Site_Address1/2, SiteAddress/PrimaryAddress) is blank or non-situs, so the app's
    #     situs_of() yields no street address.
    #   Champaign (17019) — complete roll (0.86x housing units) but last edited 4.3 years ago,
    #     past the freshness cutoff. Worth re-checking; Champaign-Urbana is real order volume.
}
