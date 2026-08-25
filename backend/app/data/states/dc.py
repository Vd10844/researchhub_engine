"""DC — parcel service (one module per state; edit here to debug DC).

Washington DC property basemap (OCTO/DCGIS), the whole District — SSL (Square-Suffix-Lot) id,
owner, ADDRESS1 situs. Verified 2026-08-04.
"""
STATE = "DC"
PARCEL = {
    "url": ("https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/"
            "DC_Property_Basemap_WebMercator/MapServer/2"),
    "kind": "mapserver",
    "label": "DC Property (OCTO / DCGIS)",
    "id_fields": ["SSL"],
}
COUNTIES = {}
