"""OK — parcel services (one module per state; edit here to debug OK).

Oklahoma's statewide parcels are view-only WMS (no queryable REST), so parcels are wired
county-by-county for the big metros. Oklahoma County (Oklahoma City) is first. Verified
2026-08-12 (parcel id + situs + owner).
"""
STATE = "OK"
PARCEL = None   # statewide OK parcels are WMS-only (not queryable) — county-by-county here

COUNTIES = {
    "40109": {  # Oklahoma County — Oklahoma City, ~800k
        "county": "Oklahoma", "state": "OK",
        # OK County Assessor public parcel view (ArcGIS Online hosted); accountno/pin/location/name1.
        "gis_rest": ("https://services8.arcgis.com/euhkr1dAJeQBIjV0/arcgis/rest/services/"
                     "TaxParcelsPublics_view/FeatureServer/0"),
        "id_fields": ["accountno", "PARCELNB_1", "pin", "propertyid"],
        "clerk_platform": "unknown",
    },
    "40143": {  # Tulsa — ~670k
        "county": "Tulsa", "state": "OK",
        # Tulsa County Assessor via INCOG regional GIS; ParcelNo/PropertyAddress/Owner.
        "gis_rest": ("https://map11.incog.org/arcgis11wa/rest/services/"
                     "Parcels_TulsaCo/FeatureServer/0"),
        "id_fields": ["ParcelNo", "AccountNo", "ACCT_NUM"],
        "clerk_platform": "unknown",
    },
    "40017": {  # Canadian — El Reno/Yukon/Mustang (OKC western suburbs), ~155k
        "county": "Canadian", "state": "OK",
        # County public parcel service, layer 3 "Parcel Data (External)" (~85k parcels). situs +
        # situs_city + owners_name + parcel_id/account; mail_address is owner mailing (skipped by
        # the situs mail-guard). Geometry is OK State Plane — the app's envelope-buffer query in
        # 4326 resolves it (an exact-point query alone misses).
        "gis_rest": ("https://services2.arcgis.com/0NjdXxmJp53hZWPd/arcgis/rest/services/"
                     "ParcelDataService_2_view/FeatureServer/3"),
        "id_fields": ["parcel_id", "account"],
        "clerk_platform": "unknown",
    },
    "40031": {  # Comanche — Lawton, ~120k
        "county": "Comanche", "state": "OK",
        # County assessor parcels: ParcelID/ACCOUNT (id) + NAME (owner). NO situs street field on
        # the layer — delivers Parcel ID + owner; situs via county link.
        "gis_rest": ("https://services6.arcgis.com/eNPJk90aMrXNOKF8/arcgis/rest/services/"
                     "Comanche_Parcels/FeatureServer/0"),
        "id_fields": ["ParcelID", "ACCOUNT"],
        "clerk_platform": "unknown",
    },
    # TODO (follow-up): Cleveland/Norman (40027); Rogers (40131 — the public Parcels layer has
    # situs+owner but its ParcelNo/AccountNo id fields are null throughout, so no Parcel ID to
    # deliver; skip until an id-bearing layer is found).
}
