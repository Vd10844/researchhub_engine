"""MN — parcel service (one module per state; edit here to debug MN).

Minnesota's discoverable free service is the Twin Cities 7-county METRO parcel layer (MetroGIS:
Hennepin, Ramsey, Dakota, Anoka, Washington, Scott, Carver) — owner + county/state PIN. That
metro is the bulk of MN's order volume; rural MN counties fall back to the records link.
Follow-up: wire the MnGeo statewide aggregate when a stable public endpoint is confirmed.
Verified 2026-08-04 (Minneapolis).
"""
STATE = "MN"
PARCEL = {
    "url": ("https://services.arcgis.com/8df8p0NlLFEShl0r/arcgis/rest/services/"
            "7Counties_Layers/FeatureServer/6"),
    "kind": "featureserver",
    "label": "Minnesota Twin Cities 7-county metro parcels (MetroGIS)",
    "id_fields": ["COUNTY_PIN", "STATE_PIN"],
}
COUNTIES = {}
