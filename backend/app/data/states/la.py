"""LA — parcel services (one module per state; edit here to debug LA).

Louisiana has no free statewide parcel layer (parcels are per-parish). Wired parish-by-parish for
the big metros. Verified 2026-08-14.
"""
STATE = "LA"
PARCEL = None   # no free statewide parcel layer

COUNTIES = {
    "22033": {  # East Baton Rouge Parish — Baton Rouge (state capital), ~455k
        "county": "East Baton Rouge", "state": "LA",
        # City-Parish EBRGIS Tax Parcel layer; PHYSICAL_ADDRESS (situs) + OWNER + ASSESSMENT_NUM.
        "gis_rest": "https://maps.brla.gov/gis/rest/services/Cadastral/Tax_Parcel/MapServer/0",
        "id_fields": ["ASSESSMENT_NUM", "ID", "PRONO"],
        "clerk_platform": "unknown",
    },
    "22005": {  # Ascension Parish — Gonzales/Donaldsonville (Baton Rouge metro), ~130k
        "county": "Ascension", "state": "LA",
        # Situs is split LOCATION_S (site number) + LOCATION_1 (street, incl. its own directional),
        # composed. OWNERNAME_ = owner; LOCATION_C = city. STREET_DIR is excluded from compose
        # because LOCATION_1 already carries the directional (avoids a doubled "W W ...").
        "gis_rest": ("https://services6.arcgis.com/1fGAZVgZnPx4zcNH/arcgis/rest/services/"
                     "Ascension_Parish_Tax_Parcels/FeatureServer/0"),
        "id_fields": ["PARCEL_NO"],
        "situs_exclude": ["STREET_DIR"],
        "clerk_platform": "unknown",
    },
    "22071": {  # Orleans Parish — New Orleans (coterminous with the city), ~380k
        "county": "Orleans", "state": "LA",
        # Official City of New Orleans assessor landbase (layer 0). Situs is split:
        # SITUS_NUMBER + SITUS_DIR + SITUS_STREET + SITUS_TYPE (composed). No owner on this layer.
        "gis_rest": "https://maps.nola.gov/server/rest/services/Assessor/Landbase_Layers/MapServer/0",
        "id_fields": ["GEOPIN"],
        "clerk_platform": "unknown",
    },
    "22055": {  # Lafayette Parish — Lafayette, ~245k
        "county": "Lafayette", "state": "LA",
        # Parish parcel layer (Regrid/Loveland-derived, publicly hosted). NOTE the layer is
        # MULTI-parish (also holds Vermilion) — a point query naturally returns the right parish,
        # but see situs_exclude for the owner-mailing (mail_*) trap. situs = `address` (full);
        # owner = `owner`.
        "gis_rest": ("https://services1.arcgis.com/Brg1qbmzmFn7JtpX/arcgis/rest/services/"
                     "Parish_Parcels__All_/FeatureServer/0"),
        "id_fields": ["parcelnumb", "parcel_id", "geoid"],
        "clerk_platform": "unknown",
    },
    "22103": {  # St. Tammany Parish — Slidell/Covington/Mandeville (New Orleans north shore), ~265k
        "county": "St. Tammany", "state": "LA",
        # Parish Assessor (STPAO) ASSESSOR_PARCELS layer: prop_addr (situs) + Name (owner) +
        # assmnt_num (id). MAIL_ADDR is owner mailing (skipped by the situs mail-guard). NOTE the
        # STPAO stpao_parcel_data layer is id-only — this ASSESSOR_PARCELS layer is the rich one.
        "gis_rest": ("https://services8.arcgis.com/25X4t4tff35goFar/arcgis/rest/services/"
                     "ASSESSOR_PARCELS/FeatureServer/0"),
        "id_fields": ["assmnt_num", "PIN"],
        "clerk_platform": "unknown",
    },
    # TODO (follow-up): Jefferson (22051 — parcel polygon is geometry-only; situs needs a join to
    # the eweb JPFeatures2025/FeatureServer/46 Addresses layer via LOCATION_ID), Caddo/Shreveport
    # (22017 — only anonymous layer is the NLCOG usrsvcs proxy, id-only, no situs).
}
