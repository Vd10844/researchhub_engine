"""WV — statewide parcel service (one module per state; edit here to debug WV).

West Virginia statewide parcels (WVU GIS Technical Center) — CleanParcelID + FullOwnerName,
all 55 counties. No situs address on this layer (owner + id). Verified 2026-08-04 (Charleston).
"""
STATE = "WV"
PARCEL = {
    "url": ("https://services.wvgis.wvu.edu/arcgis/rest/services/Planning_Cadastre/"
            "WV_Parcels/MapServer/0"),
    "kind": "mapserver",
    "label": "West Virginia Statewide Parcels (WVU GISTC)",
    "id_fields": ["CleanParcelID"],
}
COUNTIES = {}
