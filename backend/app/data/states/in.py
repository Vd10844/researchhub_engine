"""IN — statewide parcel service (one module per state; edit here to debug IN).

Indiana publishes a current statewide parcel layer (IndianaMap / DLGF) — state parcel id, situs
(dlgf_prop_address), township, all 92 counties. Verified 2026-08-04 (Indianapolis).
"""
STATE = "IN"
PARCEL = {
    "url": ("https://gisdata.in.gov/server/rest/services/Hosted/"
            "Parcel_Boundaries_of_Indiana_Current/FeatureServer/0"),
    "kind": "featureserver",
    "label": "Indiana Statewide Parcels (IndianaMap / DLGF)",
    "id_fields": ["state_parcel_id", "parcel_id"],
}
COUNTIES = {}
