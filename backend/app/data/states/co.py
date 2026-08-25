"""CO — statewide parcel service (one module per state; edit here to debug CO).

Colorado's Governor's Office of Information Technology (OIT) GIS aggregates a public parcel
composite ("Colorado_Public_Parcels") with parcel id (parcel_id), situs (situsAdd) and owner
(owner). Coverage is PARTIAL: ~44 of 64 counties have parcels loaded and ~38 populate the situs
address (Denver is full; some like El Paso/Colorado Springs carry geometry + id only). Counties
without a situs resolve a parcel id but no address, so they fall back to the appraiser link.
Verified 2026-08-12 (Denver returned parcel_id + situs + owner).
"""
STATE = "CO"
PARCEL = {
    "url": ("https://gis.colorado.gov/public/rest/services/Address_and_Parcel/"
            "Colorado_Public_Parcels/FeatureServer/0"),
    "kind": "featureserver",
    "label": "Colorado Public Parcel Composite (CO OIT — partial statewide)",
    "id_fields": ["parcel_id", "account"],
    "counties_covered": 38,   # of 64 — counties that populate a situs address
}
COUNTIES = {}
