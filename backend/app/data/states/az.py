"""AZ — parcel services (one module per state; edit here to debug AZ).

Arizona has NO free statewide parcel layer (state land dept only publishes trust-land parcels;
the all-county set is non-queryable vector tiles). So parcels are wired county-by-county for the
big metros. Maricopa (Phoenix) + Pima (Tucson) together cover ~5.5M of AZ's ~7.4M people.
Verified 2026-08-12 (both return parcel id + situs).
"""
STATE = "AZ"
PARCEL = None   # no free statewide parcel layer

# A shared, public multi-county Arizona parcel service (one layer per county) — covers the rural/
# mid-size counties in a single FeatureServer. Same schema on every layer: APN + PARCEL (id),
# SITE_ADDRESS (situs) + SITE_CITY/SITE_ZIP, OWNER_NAME. Verified 2026-08-17 (whole-county counts,
# e.g. Coconino 78k / Yuma 97k / Cochise 123k). The big metros (Maricopa/Pima/Pinal/Yavapai) keep
# their own dedicated county services below — they're more complete than this shared layer.
_AZ = "https://services.arcgis.com/C34zQ7veRS0V1t04/arcgis/rest/services/Parcels/FeatureServer"


def _azc(county, layer):
    return {"county": county, "state": "AZ", "gis_rest": f"{_AZ}/{layer}",
            "id_fields": ["APN", "PARCEL"], "clerk_platform": "unknown"}


COUNTIES = {
    "04001": _azc("Apache", 0),      # St. Johns (situs sparse on rural/reservation land; id+owner)
    "04003": _azc("Cochise", 1),     # Sierra Vista/Bisbee, ~125k
    "04005": _azc("Coconino", 2),    # Flagstaff, ~145k
    "04007": _azc("Gila", 3),        # Globe/Payson, ~53k
    "04009": _azc("Graham", 4),      # Safford, ~40k
    "04011": _azc("Greenlee", 5),    # Clifton, ~9k
    "04012": _azc("La Paz", 6),      # Parker, ~17k
    "04017": _azc("Navajo", 9),      # Show Low/Holbrook, ~110k
    "04023": _azc("Santa Cruz", 12), # Nogales, ~48k
    "04027": _azc("Yuma", 13),       # Yuma, ~205k
    "04013": {  # Maricopa — Phoenix, ~4.5M (4th-largest US county)
        "county": "Maricopa", "state": "AZ",
        "gis_rest": "https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Parcels/MapServer/0",
        "id_fields": ["APN", "APN_DASH"],
        "clerk_platform": "unknown",
    },
    "04019": {  # Pima — Tucson, ~1M
        "county": "Pima", "state": "AZ",
        # Pima County ITD-GIS open data; layer 12 "Parcels - Regional". OWNER is the mailing name
        # (MAIL1); no dedicated owner-of-record field.
        "gis_rest": ("https://gisdata.pima.gov/arcgis1/rest/services/GISOpenData/"
                     "LandRecords/MapServer/12"),
        "id_fields": ["PARCEL"],
        "clerk_platform": "unknown",
    },
    "04021": {  # Pinal — Casa Grande/Florence, ~460k (Phoenix-Tucson corridor)
        "county": "Pinal", "state": "AZ",
        # County GIS TaxParcels; layer 3. NAP right-of-way rows have null situs — _choose skips
        # them (prefers a candidate with a situs).
        "gis_rest": "https://gis.pinal.gov/mapping/rest/services/TaxParcels/MapServer/3",
        "id_fields": ["PARCELID"],
        "clerk_platform": "unknown",
    },
    "04025": {  # Yavapai — Prescott/Sedona area, ~240k
        "county": "Yavapai", "state": "AZ",
        "gis_rest": ("https://services1.arcgis.com/BajuNXbtZNiBKFkx/arcgis/rest/services/"
                     "Parcels_in_Yavapai_County/FeatureServer/0"),
        "id_fields": ["PARCEL_ID", "ACCOUNTNO"],
        "clerk_platform": "unknown",
    },
    # TODO (follow-up): Mohave (04015) — not on the shared C34 service; needs own-host discovery.
    # (Coconino is now wired via the C34 service above.)
}
