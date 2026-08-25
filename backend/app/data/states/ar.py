"""AR — statewide parcel service (one module per state; edit here to debug AR).

Arkansas GeoStor statewide cadastre (all 75 counties) — parcelid, legal, owner. Verified
2026-08-04 (Little Rock). No situs address on this layer (owner + id + legal).
"""
STATE = "AR"
PARCEL = {
    "url": ("https://gis.arkansas.gov/arcgis/rest/services/AGFC/"
            "AGFC_Cadastre_Viewer/FeatureServer/1"),
    "kind": "featureserver",
    "label": "Arkansas Statewide Parcels (GeoStor)",
    "id_fields": ["parcelid"],
}
COUNTIES = {}
