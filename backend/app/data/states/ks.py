"""KS — parcel services (one module per state; edit here to debug KS).

Kansas has no free statewide parcel POLYGON layer (DASC only has NG911 address points). Wired
county-by-county for the big metros.

NOTE on Sedgwick: its GIS host (gismaps.sedgwickcounty.org) WAF-blocks non-residential IPs — the
REST directory lists fine, but /query and layer-info are "Request Rejected" from CI (curl,
WebFetch, and headless Chromium all blocked). It works from a normal browser / the app's US
residential egress, so it resolves in the deployed app. Field names are auto-detected (no explicit
id_fields) since they can't be read from here; if it ever fails to resolve, the app falls back to
the appraiser/records link (never shows wrong data).
"""
STATE = "KS"
PARCEL = None   # no free statewide parcel polygon layer

COUNTIES = {
    "20173": {  # Sedgwick — Wichita, ~525k
        "county": "Sedgwick", "state": "KS",
        # County Appraiser parcel MapServer (official; layer 0). See module note re: WAF.
        "gis_rest": ("https://gismaps.sedgwickcounty.org/arcgis/rest/services/Appraiser/"
                     "ParcelsTrim_Dynamic_SP/MapServer/0"),
        "clerk_platform": "unknown",
    },
    "20177": {  # Shawnee — Topeka (state capital), ~180k
        "county": "Shawnee", "state": "KS",
        # County/City "Parcels" (ArcGIS Online hosted). PADDRESS = situs street; PADDRESS2 is the
        # city/state/zip line (excluded so it's never mistaken for the street). No owner on layer.
        "gis_rest": ("https://services2.arcgis.com/2XE514jeVQMWNKHX/arcgis/rest/services/"
                     "Parcels/FeatureServer/0"),
        "id_fields": ["PIN", "QUICKREFID"],
        "situs_exclude": ["PADDRESS2"],
        "clerk_platform": "unknown",
    },
    "20161": {  # Riley — Manhattan (Kansas State Univ.), ~75k
        "county": "Riley", "state": "KS",
        # County parcels (ArcGIS Online). Property_A = full situs; PID/QuickRefID ids; no owner.
        "gis_rest": ("https://services.arcgis.com/6WmEmDp2YlKJjhJt/arcgis/rest/services/"
                     "Parcels/FeatureServer/0"),
        "id_fields": ["PID", "QuickRefID", "PARCELNUM"],
        "clerk_platform": "unknown",
    },
    "20045": {  # Douglas — Lawrence (Univ. of Kansas), ~120k
        "county": "Douglas", "state": "KS",
        # County GIS Tax_Parcel (official). Host WAF-403s datacenter IPs (like Sedgwick) but serves
        # a normal browser / the app's US residential egress; fields auto-detected there.
        "gis_rest": "https://gis.dgcoks.gov/server/rest/services/Tax_Parcel/MapServer/0",
        "clerk_platform": "unknown",
    },
    # TODO (follow-up): Johnson (20091, gated/DDR — no public service), Wyandotte/KCK (20209 —
    # the public parcel_py layer is id-only, no situs).
}
