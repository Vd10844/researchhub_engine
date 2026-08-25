"""PA — statewide parcel service (one module per state; edit here to debug PA)."""
STATE = "PA"
PARCEL = {'kind': 'mapserver',
 'label': 'Pennsylvania Parcels (PA DEP/PASDA)',
 'url': 'https://gis.dep.pa.gov/depgisprd/rest/services/Parcels/PA_Parcels/MapServer/0'}
# Optional per-county overrides for this state: {"<fips>": {..registry entry..}}
COUNTIES = {}
