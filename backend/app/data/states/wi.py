"""WI — statewide parcel service (one module per state; edit here to debug WI).

Wisconsin publishes a current statewide parcel layer via the WI Dept. of Administration / State
Cartographer's Office ("Wisconsin_Statewide_Parcels_DB", V12/2026) — all 72 counties, ~3.57M
parcels, with parcel id, situs (SITEADRESS — the misspelled national parcel-standard spelling),
and owner. Verified point-queryable 2026-08-12 (Milwaukee + Madison returned parcels).
"""
STATE = "WI"
PARCEL = {
    "url": ("https://services3.arcgis.com/n6uYoouQZW75n5WI/arcgis/rest/services/"
            "Wisconsin_Statewide_Parcels_DB/FeatureServer/0"),
    "kind": "featureserver",
    "label": "Wisconsin Statewide Parcels (WI DOA / State Cartographer)",
    "id_fields": ["PARCELID", "TAXPARCELID", "STATEID"],
}
COUNTIES = {}
