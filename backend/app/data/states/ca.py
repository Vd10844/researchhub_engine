"""CA — parcel services (one module per state; edit here to debug CA).

California has NO free comprehensive statewide parcel layer (Tier-C): parcels live in 58 county
assessors, and owner names are largely withheld for privacy. So we wire the big counties'
public parcel services one at a time (COUNTIES below), tried before the statewide fallback.

The statewide FeatureServer here is only a PARTIAL layer (earthquake-hazard-zone parcels: APN +
situs, no owner) — it covers some parcels statewide but returns nothing for most addresses, so
it's a last-resort fallback after the county services. Every CA county still gets a verified
appraiser/records link via the nationwide fallback.
Verified 2026-08-04: LA County parcel service point-queryable (APN + situs).
"""
STATE = "CA"
PARCEL = {
    "url": ("https://services2.arcgis.com/zr3KAIbsRSUyARHG/arcgis/rest/services/"
            "CA_State_Parcels/FeatureServer/0"),
    "kind": "featureserver",
    "label": "CA earthquake-zone parcels (partial — county service preferred)",
    "id_fields": ["PARCEL_APN"],
}

# Big counties first (highest order volume). Each is its own public parcel MapServer/FeatureServer;
# parcel.resolve tries the county service before the partial statewide layer.
COUNTIES = {
    "06037": {  # Los Angeles — ~2.4M parcels (largest county in the US)
        "county": "Los Angeles", "state": "CA",
        "gis_rest": ("https://public.gis.lacounty.gov/public/rest/services/"
                     "LACounty_Cache/LACounty_Parcel/MapServer"),
        "appraiser_url": "https://assessor.lacounty.gov/",
        "clerk_url": "https://www.lavote.gov/home/recorder/document-recording",
        "clerk_platform": "unknown",
    },
    # TODO (follow-up PRs, one county per PR): San Diego (06073), Orange (06059),
    # Santa Clara (06085), Riverside (06065), San Bernardino (06071), Sacramento (06067),
    # Alameda (06001) — add each county's verified public parcel gis_rest here.
}
