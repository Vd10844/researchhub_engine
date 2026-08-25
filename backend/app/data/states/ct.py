"""CT — statewide parcel service (one module per state; edit here to debug CT).

Connecticut publishes a statewide CAMA + parcel layer (CT GIS Office / OPM) — owner, situs
(Location), town, and Parcel_ID for all 169 towns. Verified 2026-08-04 (West Hartford, New Haven).
"""
STATE = "CT"
PARCEL = {
    "url": ("https://services3.arcgis.com/3FL1kr7L4LvwA2Kb/arcgis/rest/services/"
            "Connecticut_CAMA_and_Parcel_Layer/FeatureServer/0"),
    "kind": "featureserver",
    "label": "Connecticut CAMA & Parcel Layer (CT GIS Office)",
    "id_fields": ["Parcel_ID"],
}
COUNTIES = {}
