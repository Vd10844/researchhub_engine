"""WY — statewide parcel service (one module per state; edit here to debug WY).

Wyoming's Property Tax Division publishes an official statewide parcel FeatureServer (the layer
behind the state "Wyoming Statewide Parcel Viewer"), ~374k parcels across all 23 counties, with a
single situs field (locationad) + owner (ownername1) + county (jurisdicti). ~83% of parcels carry
a situs address; the blanks are ROW/exempt/rural parcels. inSR=4326 point queries work directly.
Verified 2026-08-18 (Cheyenne "1847 E PERSHING BLVD" / Casper "4000 E 2ND ST" with owners).
"""
STATE = "WY"
PARCEL = {
    'kind': 'featureserver',
    'label': 'Wyoming Statewide Parcels (Property Tax Division)',
    'url': ('https://services3.arcgis.com/r0iJ85SKZ4zAzz3P/arcgis/rest/services/'
            'Wyoming_Parcels_for_2026/FeatureServer/0'),
    'id_fields': ['parcelnb', 'accountno'],
}
COUNTIES = {}
