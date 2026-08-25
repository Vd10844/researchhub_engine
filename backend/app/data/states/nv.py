"""NV — statewide parcel service (one module per state; edit here to debug NV).

Nevada Division of State Lands publishes a statewide parcel layer (hosted by NV DOT,
"Statewide_Parcels") — all 17 counties, with parcel id (APN) + situs (SiteAddress) + owner
(OwnerName). Vintage is 2018 (a snapshot, so APNs/owners can lag current county systems); some
commercial/government parcels have null situs/owner. Verified 2026-08-12 (Las Vegas + Reno).
"""
STATE = "NV"
PARCEL = {
    "url": ("https://gis.dot.nv.gov/agsphs/rest/services/Reference/"
            "Statewide_Parcels/MapServer/0"),
    "kind": "mapserver",
    "label": "Nevada Statewide Parcels (NV State Lands — 2018)",
    "id_fields": ["APN"],
}
COUNTIES = {}
