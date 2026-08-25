"""NM — per-county parcel layers (one module per state; edit here to debug NM).

New Mexico's Office of the State Engineer publishes a statewide parcel dataset (tax year 2025,
CAMA-derived) but SPLIT into 33 per-county layers in one MapServer (ids 0-32, alphabetical) —
each layer has UPC (Universal Parcel Code) + SitusAddressAll + OwnerAll. There is no single merged
statewide layer, so we map each county FIPS to its layer id and wire it as a county service.
Verified 2026-08-12 (Bernalillo layer 0 + Doña Ana layer 7 returned parcels with situs + owner).
"""
STATE = "NM"
PARCEL = None   # not one merged statewide layer — per-county layers (COUNTIES below)

_BASE = "https://gis.ose.nm.gov/server_s/rest/services/Parcels/County_Parcels_2025/MapServer"

# (layer_id, county_fips, county_name) — the MapServer's 33 layers, alphabetical (ids 0-32).
_LAYERS = [
    (0, "35001", "Bernalillo"), (1, "35003", "Catron"), (2, "35005", "Chaves"),
    (3, "35006", "Cibola"), (4, "35007", "Colfax"), (5, "35009", "Curry"),
    (6, "35011", "De Baca"), (7, "35013", "Doña Ana"), (8, "35015", "Eddy"),
    (9, "35017", "Grant"), (10, "35019", "Guadalupe"), (11, "35021", "Harding"),
    (12, "35023", "Hidalgo"), (13, "35025", "Lea"), (14, "35027", "Lincoln"),
    (15, "35028", "Los Alamos"), (16, "35029", "Luna"), (17, "35031", "McKinley"),
    (18, "35033", "Mora"), (19, "35035", "Otero"), (20, "35037", "Quay"),
    (21, "35039", "Rio Arriba"), (22, "35041", "Roosevelt"), (23, "35043", "Sandoval"),
    (24, "35045", "San Juan"), (25, "35047", "San Miguel"), (26, "35049", "Santa Fe"),
    (27, "35051", "Sierra"), (28, "35053", "Socorro"), (29, "35055", "Taos"),
    (30, "35057", "Torrance"), (31, "35059", "Union"), (32, "35061", "Valencia"),
]
COUNTIES = {
    fips: {
        "county": name, "state": "NM",
        "gis_rest": f"{_BASE}/{lid}",
        "id_fields": ["UPC", "StateParcelId", "LocalParcelId", "AccountNumber"],
        "clerk_platform": "unknown",
    }
    for lid, fips, name in _LAYERS
}
