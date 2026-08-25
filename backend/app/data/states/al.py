"""AL — parcel services (one module per state; edit here to debug AL).

Alabama has NO free statewide parcel layer (per-county via Flagship GIS / county servers). Wired
county-by-county for the big metros: Jefferson (Birmingham), Mobile, Madison (Huntsville).
Verified 2026-08-12.
"""
STATE = "AL"
PARCEL = None   # no free statewide parcel layer

COUNTIES = {
    "01073": {  # Jefferson — Birmingham, ~660k (largest AL county)
        "county": "Jefferson", "state": "AL",
        # Parcel polygon has no single situs field (ADDR_PSPR); situs is composed from the
        # Bldg_Number/Street_* components. Owner = OWNERNAME.
        "gis_rest": "https://jccgis.jccal.org/server/rest/services/Basemap/Parcels/MapServer/0",
        "id_fields": ["PARCELID", "PID", "APP_PID", "ParcelNo"],
        "clerk_platform": "unknown",
    },
    "01097": {  # Mobile — ~415k
        "county": "Mobile", "state": "AL",
        "gis_rest": ("https://services8.arcgis.com/HND1NcQt6vgOGn1z/arcgis/rest/services/"
                     "MCRC_Public_Parcels/FeatureServer/0"),
        "id_fields": ["Parcel_Number", "ParcelNo", "Account_Number", "KeyNum"],
        "clerk_platform": "unknown",
    },
    "01089": {  # Madison — Huntsville, ~400k
        "county": "Madison", "state": "AL",
        # Run by KCS GIS (vendor host) for Madison County; layer 141 = Parcel View.
        "gis_rest": ("https://web3.kcsgis.com/kcsgis/rest/services/Madison/"
                     "AL47_GAMAWeb/MapServer/141"),
        "id_fields": ["ParcelNum", "PIN"],
        "clerk_platform": "unknown",
    },
    # TODO (follow-up): Shelby (01117), Tuscaloosa (01125), Baldwin (01003), Montgomery (01101).
}
