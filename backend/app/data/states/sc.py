"""SC — parcel services (one module per state; edit here to debug SC).

South Carolina has no free statewide parcel layer (decentralized via qPublic/Beacon), so it needs
per-county wiring. None wired yet — the metros probed each had a blocker:
  - Charleston (45019): parcel polygon `gisccapps.charlestoncounty.org/.../New_Public_Search/
    MapServer/7` has PID + OWNER1 but NO situs; the Address-Points layer (…/MapServer/1, PID +
    WHOLE_ADDRESS) that should supply situs returns 0 features on join/envelope queries — too
    sparse to rely on. Needs a reliable situs source before wiring (else empty-situs "confirmed"
    parcels).
  - Richland (45079, Columbia): GeoServer/UTF-grid only — no queryable ArcGIS REST.
  - Charleston / Richland: see per-county notes above (still blocked).
Greenville (45045) IS wired below (self-hosted GCGIA FeatureServer).
"""
STATE = "SC"
PARCEL = None   # no free statewide parcel layer
COUNTIES = {
    "45091": {  # York — Rock Hill / Fort Mill (Charlotte metro), ~290k
        "county": "York", "state": "SC",
        "gis_rest": ("https://services1.arcgis.com/2AGLxyiJoNiVHKwq/arcgis/rest/services/"
                     "Parcels/FeatureServer/0"),
        "id_fields": ["ParcelID", "ParcelTrackID"],
        "clerk_platform": "unknown",
    },
    "45045": {  # Greenville — largest SC county (~540k), Greenville/Greer
        "county": "Greenville", "state": "SC",
        # Self-hosted GCGIA "Tax Parcel" layer 10 (244k polygons). Situs is SPLIT — STRNUM (site
        # number) + LOCATE (street name, no suffix) — composed by _compose_situs. The STREET /
        # CITY / STATE / ZIP5 fields are the OWNER MAILING address, NOT situs (a trap) — excluded.
        "gis_rest": ("https://www.gcgis.org/arcgis3/rest/services/GCGIA/"
                     "GCGIA_FeatureAccess/FeatureServer/10"),
        "id_fields": ["PIN"],
        "situs_exclude": ["STREET", "CITY", "STATE", "ZIP5"],
        "clerk_platform": "unknown",
    },
    # TODO: Charleston (45019, needs situs source), Spartanburg (45083),
    # Lexington (45063), Horry (45051) — self-hosted, not on public AGOL.
}
