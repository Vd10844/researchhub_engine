"""HI — statewide parcel service (one module per state; edit here to debug HI).

Hawaii's State GIS (geodata.hawaii.gov) publishes a single statewide "Statewide TMKs" layer
covering all counties (Honolulu/Hawaii/Maui/Kauai), ~384k parcels. It is TMK-centric: it carries
the Tax Map Key (the Hawaii parcel id) + a per-parcel qPublic link, but NO situs address or owner
on the public layer (those live behind the county qPublic/assessor portals the qpub_link points
to). So the app delivers the Parcel ID (TMK) statewide + the portal link; situs/owner are a
follow-up (no public statewide source found). This still flips HI from zero parcel coverage to
statewide. Verified 2026-08-17 (Honolulu + Maui points returned the correct TMK).
"""
STATE = "HI"
PARCEL = {
    'kind': 'mapserver',
    'label': 'Hawaii Statewide TMK Parcels (State GIS)',
    'url': 'https://geodata.hawaii.gov/arcgis/rest/services/ParcelsZoning/MapServer/25',
    'id_fields': ['tmk_txt', 'cty_tmk', 'tmk'],
}
COUNTIES = {}
