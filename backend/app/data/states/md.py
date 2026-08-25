"""MD — statewide parcel service (one module per state; edit here to debug MD)."""
STATE = "MD"
PARCEL = {'kind': 'mapserver-points',
 'label': 'Maryland MDP/SDAT Property Data',
 'url': 'https://mdgeodata.md.gov/imap/rest/services/PlanningCadastre/MD_PropertyData/MapServer/0'}
# Optional per-county overrides for this state: {"<fips>": {..registry entry..}}
COUNTIES = {}
