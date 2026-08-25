"""NY — statewide parcel service (one module per state; edit here to debug NY).

New York publishes a genuine statewide public tax-parcel layer (NYS GIS Program Office), so
parcels auto-fetch for every county — owner, situs (PARCEL_ADDR), and the SBL/print-key id.
Verified point-queryable 2026-08-04 (Manhattan returned owner + address).
"""
STATE = "NY"
PARCEL = {
    "url": ("https://gisservices.its.ny.gov/arcgis/rest/services/"
            "NYS_Tax_Parcels_Public/MapServer/1"),
    "kind": "mapserver",
    "label": "NYS Statewide Tax Parcels (NYS GIS)",
    "id_fields": ["PRINT_KEY", "SWIS_SBL_ID"],   # Parcel-ID (SBL) search columns
}
COUNTIES = {}
