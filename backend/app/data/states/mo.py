"""MO — parcel services (one module per state; edit here to debug MO).

Missouri has no free statewide parcel cadastre (only state-owned parcels). Wired county-by-county
for the big metros: St. Louis County + Jackson County (Kansas City). Jackson's parcel polygon
carries only ids; situs+owner are in a companion CAMA table (layer 2), joined PropertyID ->
property_id (integer key). Verified 2026-08-12.
"""
STATE = "MO"
PARCEL = None   # no free statewide parcel cadastre

_JAX = "https://jcgis.jacksongov.org/arcgis/rest/services/ParcelViewer/ParcelsAscendRelate/MapServer"
COUNTIES = {
    "29189": {  # St. Louis County — ~1M (largest MO county; NOT St. Louis City 29510)
        "county": "St. Louis", "state": "MO",
        "gis_rest": "https://maps.stlouisco.com/hosting/rest/services/Maps/AGS_Parcels/MapServer/0",
        "id_fields": ["LOCATOR"],
        "clerk_platform": "unknown",
    },
    "29095": {  # Jackson — Kansas City, ~700k
        "county": "Jackson", "state": "MO",
        "gis_rest": f"{_JAX}/1",   # polygon: parcel_id + PropertyID (situs/owner via join)
        "id_fields": ["parcel_id", "PropertyID", "Name"],
        # companion CAMA table: situs_address + owner_info, joined on an INTEGER property_id.
        "related": {"url": f"{_JAX}/2", "key": "PropertyID", "where": "property_id", "quote": False},
        "clerk_platform": "unknown",
    },
    "29183": {  # St. Charles — St. Louis suburbs, ~410k
        "county": "St. Charles", "state": "MO",
        # Parcel polygon (layer 2) is self-contained: Parcel_ID/Account + situs + Owner. The prod
        # host WAF-blocks datacenter IPs (403) but works from a normal browser / the app's US
        # residential egress; schema verified via the gis-dev mirror.
        "gis_rest": ("https://gis.sccmo.org/scc_gis/rest/services/open_data/"
                     "Tax_Information_o/FeatureServer/2"),
        "id_fields": ["Parcel_ID", "Account"],
        "clerk_platform": "unknown",
    },
    "29097": {  # Jasper — Joplin, ~123k
        "county": "Jasper", "state": "MO",
        # Address (single situs, populated) + Own_Name (owner). MO State Plane; 4326 reprojects.
        "gis_rest": ("https://services6.arcgis.com/f6278XvXrNz6PmsX/arcgis/rest/services/"
                     "Parcels/FeatureServer/1"),
        "id_fields": ["PIN", "FullPin"],
        "clerk_platform": "unknown",
    },
    "29165": {  # Platte — Kansas City north suburbs, ~150k
        "county": "Platte", "state": "MO",
        # Situs is split HOUSENUM + ADDRESS (street), so force compose (compose_situs) rather than
        # let the direct pass grab ADDRESS alone — an ordinal street like "4TH ST" has a digit and
        # would otherwise be returned without the house number. Compose prepends HOUSENUM +
        # ADDRESS. DEEDHOLDER = owner. Use the attributed Tax_Parcels_2023 layer (the sibling
        # Current_Parcels is geometry+id only).
        "gis_rest": ("https://services.arcgis.com/KP64F8Xif9MkUwD4/arcgis/rest/services/"
                     "Tax_Parcels_2023/FeatureServer/0"),
        "id_fields": ["Parcel_PIN", "PARCELNUM"],
        "compose_situs": True,
        "clerk_platform": "unknown",
    },
    "29019": {  # Boone — Columbia (Univ. of Missouri), ~185k
        "county": "Boone", "state": "MO",
        # "ParcelsForQuery": ASSESSOR (id) + OWNER. NO situs on this layer (only owner mailing) —
        # delivers Parcel ID + owner; situs via county link. MO State Plane, needs the app buffer.
        "gis_rest": "https://gis.showmeboone.com/arcgis/rest/services/CO_TaxEntities/MapServer/0",
        "id_fields": ["ASSESSOR", "ASSESSOR_FORMAT"],
        "clerk_platform": "unknown",
    },
    "29145": {  # Newton — Neosho (Joplin metro), ~58k
        "county": "Newton", "state": "MO",
        # Countywide parcel polygons: PARCEL_PID + legal only (no situs, no owner) — delivers the
        # Parcel ID by location; situs/owner via county link.
        "gis_rest": ("https://services3.arcgis.com/g6eV2CrSSwCZj8Mc/arcgis/rest/services/"
                     "Newton_Parcels/FeatureServer/0"),
        "id_fields": ["PARCEL_PID"],
        "clerk_platform": "unknown",
    },
    # TODO (follow-up): Greene/Springfield (29077), Clay (29047), Jefferson (29099), St. Louis City
    # (29510), Franklin (29071), Cole (29051), Cass (29037) — not verified (agent subagents failed);
    # re-investigate. Cole/Callaway are on token-gated midmogis; SE-MO metros on semogis (503).
}
