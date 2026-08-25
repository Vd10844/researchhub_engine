"""MS — statewide parcel service (one module per state; edit here to debug MS).

Mississippi's MARIS/MDEQ publishes statewide parcels, but split into TWO half-state layers
(West = layer 1, East = layer 2) in one MapServer — together they cover all 82 counties. The
resolver tries both (url is a list). Fields: PARNO + SITEADD + OWNNAME. Data quality is uneven by
county (SITEADD is best-effort — sometimes just a house number); Issaquena + Sunflower counties
have no public digital parcels. Verified 2026-08-12 (Jackson=West, Gulfport=East).
"""
STATE = "MS"
_SVC = "https://gis.mississippi.edu/server/rest/services/Cadastral/MS_Parcels_August_2024/MapServer"
PARCEL = {
    "url": [f"{_SVC}/1", f"{_SVC}/2"],   # West + East halves — together all 82 counties
    "kind": "mapserver",
    "label": "Mississippi Statewide Parcels (MARIS/MDEQ)",
    "id_fields": ["PARNO"],
}
COUNTIES = {}
