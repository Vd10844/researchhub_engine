"""VA — statewide parcel service (one module per state; edit here to debug VA)."""
STATE = "VA"
PARCEL = {'kind': 'mapserver',
 'label': 'Virginia VGIN Statewide Parcels',
 'url': 'https://vginmaps.vdem.virginia.gov/arcgis/rest/services/VA_Base_Layers/VA_Parcels/MapServer/0'}
# Optional per-county overrides for this state: {"<fips>": {..registry entry..}}
COUNTIES = {}
