"""ND — statewide parcel service (one module per state; edit here to debug ND).

North Dakota's GIS Hub publishes a statewide parcel layer ("NDGISHUB_Parcels") — all 53 counties,
~742k parcels. The polygon layer (0) carries the parcel id (UniqueGISID) + legal description but
NOT situs/owner; those live in a related TaxRoll TABLE (layer 1), joined on UniqueGISID. The
resolver joins them via PARCEL['related']. Verified 2026-08-12 (Fargo/Cass + Bismarck/Burleigh).
"""
STATE = "ND"
_SVC = "https://services1.arcgis.com/GOcSXpzwBHyk2nog/arcgis/rest/services/NDGISHUB_Parcels/FeatureServer"
PARCEL = {
    "url": f"{_SVC}/0",
    "kind": "featureserver",
    "label": "North Dakota Statewide Parcels (ND GIS Hub)",
    "id_fields": ["UniqueGISID", "GISID"],
    # situs (PropertyAddress) + owner (OwnerName) are in the related TaxRoll table, joined on key.
    "related": {"url": f"{_SVC}/1", "key": "UniqueGISID"},
}
COUNTIES = {}
