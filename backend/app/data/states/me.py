"""ME — statewide parcel service (one module per state; edit here to debug ME).

Maine GeoLibrary publishes a statewide parcel layer ("Maine_Parcels_Organized_Towns") — ~704k
parcels across all 16 counties' organized towns, with parcel id (STATE_ID) + situs (PROP_LOC).
Owner is only in a companion table (layer 9), not on the polygon layer, so owner is left blank.
Coverage is organized towns (Unorganized Territory is a separate dataset); data currency varies
by town (some parcels last updated years ago). Verified 2026-08-12 (Portland + Bangor).
"""
STATE = "ME"
PARCEL = {
    "url": ("https://services1.arcgis.com/RbMX0mRVOFNTdLzd/arcgis/rest/services/"
            "Maine_Parcels_Organized_Towns/FeatureServer/10"),
    "kind": "featureserver",
    "label": "Maine Statewide Parcels (Maine GeoLibrary — organized towns)",
    "id_fields": ["STATE_ID", "MAP_BK_LOT"],
}
COUNTIES = {}
