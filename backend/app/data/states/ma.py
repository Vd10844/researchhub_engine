"""MA — statewide parcel service (one module per state; edit here to debug MA).

Massachusetts publishes the MassGIS Level-3 standardized statewide parcel layer (all 351
municipalities) — situs (SITE_ADDR) + LOC_ID. Owner is on a related assessor table, not this
polygon layer. Verified 2026-08-04 (Boston).
"""
STATE = "MA"
PARCEL = {
    "url": ("https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/"
            "Massachusetts_Property_Tax_Parcels/FeatureServer/0"),
    "kind": "featureserver",
    "label": "MassGIS L3 Statewide Property Tax Parcels",
    "id_fields": ["LOC_ID"],
}
COUNTIES = {}
