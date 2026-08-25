"""DE — parcel services (one module per state; edit here to debug DE).

Delaware has no usable free statewide parcel layer with situs (FirstMap DE_StateParcels is
PIN-only), so it's wired county-by-county. Only 3 counties. Kent is wired (situs + owner).
Verified 2026-08-18.

TODO — the other two counties both hit a hard wall from here:
  - New Castle (10003, Wilmington, DE's largest ~570k): both parcel layers (gis.nccde.org
    Base_Layers/MapServer/0 AND the AGOL Parcels_owners) are stored in DE State Plane (wkid 2235)
    and their servers do NOT reproject an inSR=4326 query geometry — a point query in 4326
    silently returns 0. Needs a reproject-to-native-SR capability (no pyproj installed) before it
    can point-resolve; attribute/by-ID queries would work today. Situs = ADDRESS/LOC_ADDRESS,
    owner = CNTCTLAST, id = PRCLID.
  - Sussex (10005): the reachable public polygon layer is a parcel-fabric PIN layer with null
    situs/owner; the situs+owner FeatureServer 404s from here.
"""
STATE = "DE"
PARCEL = None   # FirstMap statewide is PIN-only (no situs); wired per-county

COUNTIES = {
    "10001": {  # Kent — Dover (state capital), ~185k
        "county": "Kent", "state": "DE",
        # Kent County GIS Parcels (layer 0). Name (id) + LOCATION (situs) + OWNERNAME. inSR=4326 ok.
        "gis_rest": "https://gis.kentcountyde.gov/server/rest/services/Parcels/Parcels/MapServer/0",
        "id_fields": ["Name"],
        "clerk_platform": "unknown",
    },
}
