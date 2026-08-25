"""NE — statewide parcel service (one module per state; edit here to debug NE).

Nebraska OCIO / GIS Council publishes a statewide parcel layer ("StatewideParcelsExternal",
NebraskaMAP-fed, compiled from county assessors) — ~1.15M parcels across all 93 counties, with
parcel id (Parcel_ID; State_PID is the statewide-unique key) + situs (Situs_Address). Owner name
is not exposed. Verified 2026-08-12 (Omaha + Lincoln returned parcels).
"""
STATE = "NE"
PARCEL = {
    "url": ("https://giscat.ne.gov/enterprise/rest/services/"
            "StatewideParcelsExternal/FeatureServer/0"),
    "kind": "featureserver",
    "label": "Nebraska Statewide Parcels (NE OCIO / NebraskaMAP)",
    "id_fields": ["Parcel_ID", "State_PID"],
}
COUNTIES = {}
