"""ID — statewide parcel service (one module per state; edit here to debug ID).

Idaho Dept. of Lands re-publishes a statewide parcel layer ("WhiteStar_Parcels") free/public on
its own ArcGIS host — all 44 counties, ~1.14M parcels, with parcel id (apn) + situs (propfuladd)
+ owner (owner1). Data is WhiteStar-derived (commercial source re-published free by the state);
fine for per-property lookups. Verified 2026-08-12 (Boise + Idaho Falls returned parcels).
"""
STATE = "ID"
PARCEL = {
    "url": ("https://gis1.idl.idaho.gov/arcgis/rest/services/Portal/"
            "WhiteStar_Parcels/FeatureServer/0"),
    "kind": "featureserver",
    "label": "Idaho Statewide Parcels (ID Dept. of Lands / WhiteStar)",
    "id_fields": ["apn"],
}
COUNTIES = {}
