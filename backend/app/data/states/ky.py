"""KY — parcel services (one module per state; edit here to debug KY).

Kentucky has NO free statewide parcel layer (confirmed 2026-08-17: the state DGI —
kygisserver.ky.gov / kygeonet, org "Kentucky_DGI" — publishes only ONE county as a service,
Webster; the other 119 are per-county PVA). So KY is wired county-by-county for the big metros.
Verified 2026-08-12 / 2026-08-17.
"""
STATE = "KY"
PARCEL = None   # no free statewide parcel layer (only Webster Co is on the state DGI org)

COUNTIES = {
    "21111": {  # Jefferson — Louisville (largest KY county, ~780k pop / ~290k parcels)
        "county": "Jefferson", "state": "KY",
        # Jefferson County PVA-hosted "New_AllParcels" (289,963 features, all parcels incl.
        # residential). ParcelID + single complete situs field `Address`; no owner on this public
        # layer. NOTE: the LOJIC open-data URL (gis.lojic.org/.../OpenDataPVA) is Drupal-proxied
        # and returns HTML, not ArcGIS JSON — do NOT use it; this PVA org service is the queryable
        # one.
        "gis_rest": ("https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/"
                     "New_AllParcels/FeatureServer/0"),
        "id_fields": ["ParcelID"],
        "clerk_platform": "unknown",
    },
    "21067": {  # Fayette — Lexington (LFUCG), ~320k
        "county": "Fayette", "state": "KY",
        "gis_rest": "https://maps.lexingtonky.gov/lfucggis/rest/services/property/MapServer/1",
        "id_fields": ["PVANUM"],
        "clerk_platform": "unknown",
    },
    # TODO (follow-up): Kenton (21117), Boone (21015), Warren/Bowling Green (21227) — separate
    # self-hosted services, no single layer covers them.
}
