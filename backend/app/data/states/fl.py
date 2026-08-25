"""FL — statewide parcel service (one module per state; edit here to debug FL)."""
STATE = "FL"
PARCEL = {'kind': 'featureserver',
 'label': 'FL DOR Statewide Cadastral (FGIO)',
 'url': 'https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0',
 # Pin the Parcel-ID search to the two indexed, canonical columns (same value). Auto-detect
 # would also include ALT_KEY / PARCEL_ID_, which are unindexed and make the query full-scan
 # ~12M rows and time out — a valid parcel then looks "not found".
 'id_fields': ['PARCEL_ID', 'PARCELNO']}
# Optional per-county overrides for this state: {"<fips>": {..registry entry..}}
COUNTIES = {}
