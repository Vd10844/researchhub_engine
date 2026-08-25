"""WA — statewide parcel service (one module per state; edit here to debug WA)."""
STATE = "WA"
PARCEL = {'kind': 'featureserver',
 'label': 'Washington State Parcels',
 'url': 'https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/Current_Parcels/FeatureServer/0'}
# Optional per-county overrides for this state: {"<fips>": {..registry entry..}}
COUNTIES = {}
