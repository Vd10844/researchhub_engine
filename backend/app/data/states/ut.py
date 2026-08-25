"""UT — statewide parcel service (one module per state; edit here to debug UT).

Utah UGRC statewide LIR parcels aggregate (all 29 counties) — PARCEL_ID, PARCEL_ADD situs,
owner type. Verified 2026-08-04 (Salt Lake City).
"""
STATE = "UT"
PARCEL = {
    "url": ("https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/"
            "UtahStatewideParcels/FeatureServer/0"),
    "kind": "featureserver",
    "label": "Utah Statewide Parcels (UGRC / LIR)",
    "id_fields": ["PARCEL_ID"],
}
COUNTIES = {}
