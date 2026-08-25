"""TN — statewide parcel service (one module per state; edit here to debug TN).

Tennessee's Comptroller of the Treasury (Division of Property Assessments) publishes a statewide
parcel layer ("Tennessee_Property_Boundaries_Public_Use") with parcel id (PARCELID), situs
(ADDRESS) and owner (OWNER). It covers 86 of 95 counties — nine metros that run their own
assessment systems are EXCLUDED (Davidson/Nashville, Shelby/Memphis, Knox/Knoxville,
Hamilton/Chattanooga, Rutherford, Williamson, Montgomery, Chester, Hickman); those fall back to
the appraiser/records link until wired county-by-county. Verified 2026-08-12 (Jackson + Johnson
City returned parcels; the excluded metros returned empty, as expected).
"""
STATE = "TN"
PARCEL = {
    "url": ("https://services1.arcgis.com/YuVBSS7Y1of2Qud1/arcgis/rest/services/"
            "Tennessee_Property_Boundaries_Public_Use/FeatureServer/0"),
    "kind": "featureserver",
    "label": "Tennessee Statewide Parcels (TN Comptroller — 86 of 95 counties)",
    "id_fields": ["PARCELID", "GISLINK", "PARCEL"],
    "counties_covered": 86,   # of 95 — the 9 self-assessing metros are not in this layer
}
COUNTIES = {}
