"""NH — statewide parcel service (one module per state; edit here to debug NH).

NH GRANIT (UNH) publishes a statewide parcel mosaic ("CAD_ParcelMosaic", NH Dept. of Revenue
Administration) — all 10 counties, with parcel id (pid) + situs (streetaddress). Owner name is
not on this layer. Verified 2026-08-12 (Manchester + Concord returned parcels). Use the open
/hosting/ FeatureServer; the department's /nhgeodata/.../MapServer requires a token.
"""
STATE = "NH"
PARCEL = {
    "url": ("https://nhgeodata.unh.edu/hosting/rest/services/Hosted/"
            "CAD_ParcelMosaic/FeatureServer/1"),
    "kind": "featureserver",
    "label": "New Hampshire Statewide Parcels (NH GRANIT / DRA)",
    "id_fields": ["pid", "displayid"],
}
COUNTIES = {}
