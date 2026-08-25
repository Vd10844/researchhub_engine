"""VT — statewide parcel service (one module per state; edit here to debug VT)."""
STATE = "VT"
PARCEL = {'kind': 'featureserver',
 'label': 'Vermont VCGI Statewide Parcels',
 'url': 'https://services1.arcgis.com/BkFxaEFNwHqX3tAw/arcgis/rest/services/FS_VCGI_VTPARCELS_WM_NOCACHE_v2/FeatureServer/1'}
# Optional per-county overrides for this state: {"<fips>": {..registry entry..}}
COUNTIES = {}
