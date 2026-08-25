"""IA — parcel services (one module per state; edit here to debug IA).

Iowa's only free statewide layer is a 2017 snapshot with no situs (not wired). Big counties that
publish current parcels with situs on ArcGIS Online are wired here. Verified 2026-08-14.
"""
STATE = "IA"
PARCEL = None   # no usable free statewide layer (2017 snapshot has no situs)

_POLK = "https://gis4.polkcountyiowa.gov/server/rest/services/Public/Polk_County_Parcels/FeatureServer"
COUNTIES = {
    "19153": {  # Polk — Des Moines, IA's largest county (~500k)
        "county": "Polk", "state": "IA",
        # Normalized schema: the polygon (layer 1) carries only Parcel_Number + HouseNo. Full situs
        # (StreetNumber/PreDirection/StreetName/StreetType/PostDirection, composed) is in related
        # table 3 "Situs Address"; owner (Name) is in related table 5 "Owners Mail". Both join on
        # ParcelNumber = the polygon's Parcel_Number.
        "gis_rest": f"{_POLK}/1",
        "id_fields": ["Parcel_Number"],
        "related": [
            {"url": f"{_POLK}/3", "key": "Parcel_Number", "where": "ParcelNumber", "quote": True},
            {"url": f"{_POLK}/5", "key": "Parcel_Number", "where": "ParcelNumber", "quote": True},
        ],
        "clerk_platform": "unknown",
    },
    "19163": {  # Scott — Davenport / Quad Cities, ~175k
        "county": "Scott", "state": "IA",
        # Scott County GIS hosted Cadastral, layer 3 "Parcel" (polygon). PIN + PropertyAddress
        # (single full situs) + DeedHold (owner); mailing is separate (MailAddr1/MailName).
        "gis_rest": ("https://services.arcgis.com/ovln19YRWV44nBqV/arcgis/rest/services/"
                     "Cadastral/FeatureServer/3"),
        "id_fields": ["PIN"],
        "clerk_platform": "unknown",
    },
    "19103": {  # Johnson — Iowa City, ~155k
        "county": "Johnson", "state": "IA",
        # County LandRecords service, layer 9 "Parcels" (polygon). PPN + SiteAddress (single full
        # situs) + DeedHolder1 (owner). NOTE this host 403s any non-browser User-Agent — the app
        # sends a browser UA globally (config.USER_AGENT), which this depends on.
        "gis_rest": ("https://gis.johnsoncountyiowa.gov/arcgis/rest/services/LandRecords/"
                     "Land_Records/MapServer/9"),
        "id_fields": ["PPN"],
        "clerk_platform": "unknown",
    },
    "19113": {  # Linn — Cedar Rapids, ~230k
        "county": "Linn", "state": "IA",
        "gis_rest": ("https://services.arcgis.com/i14SLLmXo7Hn9vNc/arcgis/rest/services/"
                     "RealEstateParcel/FeatureServer/0"),
        "id_fields": ["GPN"],
        "clerk_platform": "unknown",
    },
    "19193": {  # Woodbury — Sioux City, ~105k
        "county": "Woodbury", "state": "IA",
        # Situs is split: addr_num + addr_stname (+addr_city, excluded), composed by _compose_situs.
        "gis_rest": ("https://services.arcgis.com/kd1jFI4TM5bZHeP8/arcgis/rest/services/"
                     "Woodbury_County_IA_Parcel_Data_Feature/FeatureServer/0"),
        "id_fields": ["PIN"],
        "situs_exclude": ["addr_city"],
        "clerk_platform": "unknown",
    },
    "19169": {  # Story — Ames (Iowa State Univ.), ~100k
        "county": "Story", "state": "IA",
        "gis_rest": "https://apps.storycounty.com/arcgis/rest/services/parcels/MapServer/0",
        "id_fields": ["PARCELID", "GEOCODE"],
        "clerk_platform": "unknown",
    },
    "19155": {  # Pottawattamie — Council Bluffs (Omaha metro), ~93k
        "county": "Pottawattamie", "state": "IA",
        # ADDRESS = situs; TaxAddress = owner mailing (excluded).
        "gis_rest": ("https://gis.pottcounty-ia.gov/arcgis/rest/services/PublicDataEnterprise/"
                     "PublicData_Parcels/FeatureServer/0"),
        "id_fields": ["PIN", "TAXPIN"],
        "situs_exclude": ["TaxAddress"],
        "clerk_platform": "unknown",
    },
    "19033": {  # Cerro Gordo — Mason City, ~43k
        "county": "Cerro Gordo", "state": "IA",
        "gis_rest": ("https://services7.arcgis.com/qyyoWTywHfayX67L/arcgis/rest/services/"
                     "Tax_Parcels_Feature_Service/FeatureServer/0"),
        "id_fields": ["PARCELID", "Tyler_ParcelNumber"],
        "clerk_platform": "unknown",
    },
    "19127": {  # Marshall — Marshalltown, ~40k
        "county": "Marshall", "state": "IA",
        "gis_rest": "https://gis.marshallcountyia.gov/arcgis/rest/services/WebParcels/MapServer/0",
        "id_fields": ["PIN", "parcel_number"],
        "clerk_platform": "unknown",
    },
    "19013": {  # Black Hawk — Waterloo/Cedar Falls, ~130k
        "county": "Black Hawk", "state": "IA",
        # Parcel-fabric attributed polygon (layer 15). Carries PIN + owner (deedholder) but NO
        # situs street address on this layer — delivers Parcel ID + owner; situs via county link.
        "gis_rest": ("https://services5.arcgis.com/ya62ECiavqTkK0wv/arcgis/rest/services/"
                     "ParcelFabricPublished_gdb/FeatureServer/15"),
        "id_fields": ["PIN", "ParcelID"],
        "clerk_platform": "unknown",
    },
    "19061": {  # Dubuque — ~100k
        "county": "Dubuque", "state": "IA",
        # County Land Records, layer 26. PIN + FullSitus + OwnerName. NOTE the host
        # gis.dubuquecounty.us dropped .NET/PowerShell TLS in testing but serves browser-class
        # clients; the app's requests stack (browser UA) is verified to reach it.
        "gis_rest": ("https://gis.dubuquecounty.us/server/rest/services/Maps/Land_Records/"
                     "MapServer/26"),
        "id_fields": ["PIN"],
        "clerk_platform": "unknown",
    },
    # TODO (follow-up): Dallas (19049), Muscatine (19139), Clinton (19045), Webster (19187),
    # Marion (19125), Wapello (19179) — all Beacon/Schneider (qPublic) HTML, no public REST.
}
