"""MT — statewide parcel service (one module per state; edit here to debug MT)."""
STATE = "MT"
PARCEL = {'kind': 'mapserver',
 'label': 'Montana Cadastral (MSL/DOR)',
 'url': 'https://gisservicemt.gov/arcgis/rest/services/MSDI_Framework/Parcels/MapServer/0'}
# Optional per-county overrides for this state: {"<fips>": {..registry entry..}}
COUNTIES = {}
