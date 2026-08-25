"""NC — statewide parcel service (one module per state; edit here to debug NC)."""
STATE = "NC"
PARCEL = {'kind': 'featureserver',
 'label': 'NC OneMap Statewide Parcels',
 'url': 'https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/1'}
# Optional per-county overrides for this state: {"<fips>": {..registry entry..}}
COUNTIES = {}
