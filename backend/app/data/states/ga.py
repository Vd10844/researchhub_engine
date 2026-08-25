"""GA — parcel services (one module per state; edit here to debug GA).

Georgia is the hardest Tier-C state: 159 counties (most in the US) and NO free statewide parcel
layer. So parcels are wired county-by-county (COUNTIES below), biggest-first. For DEEDS, Georgia
has a genuine statewide resource — GSCCCA (Georgia Superior Court Clerks' Cooperative Authority)
real-estate index — used as the clerk link.

COVERAGE (2026-08-18): GA is ~34% of order volume.
  * Parcels — 35 of 159 counties. The first 15 (Gwinnett -> Coweta) were wired by hand,
    biggest-first; the next 20 came from the automated sweep (see the header on that block for
    the four gates each had to clear). The rural long tail is still the gap, and a paid parcel
    API (Regrid/ReportAll) remains the only efficient route to all 159 at once.
  * Deeds — all 159, via the statewide GSCCCA index below. No per-county work needed.
  * Plats — all 159, via GSCCCA's SEPARATE plat index (PLAT_LINK). Before 2026-08-18 the plat
    step reused the deed URL, so every GA plat lookup opened the wrong search screen.
  * Property Appraiser — 159 of 159 (2026-08-18), but only 149 are VERIFIED: each was fetched
    and confirmed to serve a page naming its own county. The remaining 10 sit behind
    Schneider's Cloudflare and cannot be checked from here at all — see the warning above
    APPRAISER. Confirm those in a browser before trusting them.
Every GA county still gets a records link via the nationwide fallback.
Coverage note: GA is ~34% of order volume (2nd behind FL), so it gets the most county-by-county
work. Every GA county still gets a records link via the nationwide fallback.

Wired: 90 / 159 counties (2026-08-20). Order-weighted this is the large majority of GA volume —
all of metro Atlanta plus every secondary city (Augusta, Columbus, Macon, Savannah, Athens,
Albany, Valdosta, Rome, Dalton, Brunswick, Warner Robins, LaGrange, Griffin, Statesboro …).

How counties get added here (the method that found the last 30): enumerate the GDIT
"Parcels - GA - *" AGOL catalog plus the GMASS (ISpzx3B5ZsVA6e1Z), MGRC (Ug5xGQbHsD8zuZzM) and
GA-GIO (Za9Nk6CPIPbvR1t7) org service directories, then VERIFY each candidate layer with a grid
of point queries inside the county polygon. A candidate is only wired if >=60% of interior grid
points return a parcel, the layer has >=400 features, and it exposes a parcel-id field. That
coverage gate matters: these orgs publish many look-alike layers that are actually city-only or
study-area subsets (Walton's reachable "Parcels" copy covers 8% of the county), and a bbox or
single-point check would happily accept them.

Verified 2026-08-04: Gwinnett County parcel service point-queryable (PIN + address).
"""
STATE = "GA"
PARCEL = None   # no free statewide parcel layer

GSCCCA = "https://search.gsccca.org/RealEstate/"   # statewide GA deed/lien index
DEED_LINK = GSCCCA   # used as the clerk/deed link for EVERY GA county (all 159), even link-only

# GSCCCA keeps PLATS in a separate index from deeds — /RealEstate/ is "Search Real Estate
# Records", /Plat/ is "Plat Index" (both verified live 2026-08-18). Without this the plat step
# reused the deed URL and sent surveyors to the wrong search screen in all 159 counties.
GSCCCA_PLAT = "https://search.gsccca.org/Plat/"    # statewide GA plat index
PLAT_LINK = GSCCCA_PLAT

COUNTIES = {
    "13135": {  # Gwinnett — ~1M residents (2nd-largest GA county, metro Atlanta)
        "county": "Gwinnett", "state": "GA",
        "gis_rest": ("https://services3.arcgis.com/RfpmnkSAQleRbndX/arcgis/rest/services/"
                     "Property_and_Tax/FeatureServer"),
        "clerk_url": GSCCCA,
        "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13121": {  # Fulton — largest GA county (~1.07M), city of Atlanta
        "county": "Fulton", "state": "GA",
        # County Property Map Viewer backend; layer 11 "Tax Parcel" (ParcelID/Address/Owner).
        "gis_rest": ("https://gismaps.fultoncountyga.gov/arcgispub2/rest/services/"
                     "PropertyMapViewer/PropertyMapViewer/MapServer/11"),
        "id_fields": ["ParcelID"],
        "clerk_url": GSCCCA,
        "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13089": {  # DeKalb — ~3rd-largest GA county (~760k), metro Atlanta
        "county": "DeKalb", "state": "GA",
        # County Property Appraisal (IASWorld/CAMA) FeatureServer, layer 0.
        "gis_rest": ("https://dcgis.dekalbcountyga.gov/hosted/rest/services/"
                     "PropertyAppraisal/Parcels_IASWorld/FeatureServer/0"),
        "id_fields": ["PARCELID"],
        "clerk_url": GSCCCA,
        "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13067": {  # Cobb — ~770k, metro Atlanta (Marietta)
        "county": "Cobb", "state": "GA",
        # County GIS "cobbpublic" parcels; layer 3 "Parcels" (PIN/SITUS_ADDR/OWNER_NAM1).
        "gis_rest": ("https://gis.cobbcounty.gov/gisserver/rest/services/cobbpublic/"
                     "cobbparcelsmapwm_public/MapServer/3"),
        "id_fields": ["PIN", "PARID"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13063": {  # Clayton — ~300k, metro Atlanta (Jonesboro)
        "county": "Clayton", "state": "GA",
        "gis_rest": ("https://gis.claytoncountyga.gov/server/rest/services/TaxAssessor/"
                     "Parcels/MapServer/0"),
        "id_fields": ["PARCELID"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13051": {  # Chatham — ~300k, city of Savannah (SAGIS Board of Assessors digest)
        "county": "Chatham", "state": "GA",
        # SAGIS Parcel Digest (PIN/PropAddress_Full/Owner); digest snapshot may lag current roll.
        "gis_rest": ("https://pub.sagis.org/arcgis/rest/services/Pictometry/"
                     "ParcelDigest/MapServer/0"),
        "id_fields": ["PIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13057": {  # Cherokee — ~280k, metro Atlanta (Canton)
        "county": "Cherokee", "state": "GA",
        # County GIS MainLayers; layer 1 = Parcels (PIN/Property_Address/OWNER + deed book/page).
        "gis_rest": ("https://gis.cherokeecountyga.gov/arcgis/rest/services/"
                     "MainLayers/MapServer/1"),
        "id_fields": ["PIN", "TINNoSpace"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13151": {  # Henry — ~250k, metro Atlanta (McDonough)
        "county": "Henry", "state": "GA",
        "gis_rest": ("https://arcgis.co.henry.ga.us/server/rest/services/"
                     "Parcels/MapServer/12"),
        "id_fields": ["PARCEL_NO"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13117": {  # Forsyth — ~270k, metro Atlanta (Cumming)
        "county": "Forsyth", "state": "GA",
        "gis_rest": ("https://geo.forsythco.com/gis/rest/services/Public/"
                     "Tax_Parcel/FeatureServer/0"),
        "id_fields": ["PARCELID"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13139": {  # Hall — ~210k, Gainesville
        "county": "Hall", "state": "GA",
        "gis_rest": ("https://hallgis.hallcounty.org/arcgis/rest/services/"
                     "GHCGIS_WebData/MapServer/1"),
        "id_fields": ["PIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13021": {  # Bibb — ~155k, consolidated Macon-Bibb (city of Macon)
        "county": "Bibb", "state": "GA",
        # Macon-Bibb County's own ArcGIS Online TaxParcels (SITEADDRESS/OWNERNME1); ~2018 data.
        "gis_rest": ("https://services2.arcgis.com/zPFLSOZ5HzUzzTQb/arcgis/rest/services/"
                     "TaxParcels/FeatureServer/0"),
        "id_fields": ["PARCELID", "LOWPARCELID"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13245": {  # Richmond — ~210k, consolidated Augusta-Richmond (city of Augusta)
        "county": "Richmond", "state": "GA",
        # Augusta-Richmond consolidated gov't ArcGIS; layer 32 joins ParcelWeb tax attrs
        # (parcel_no/siteaddress/own1 + deed/plat page).
        "gis_rest": ("https://gismap.augustaga.gov/arcgis/rest/services/AGOL/"
                     "AGSGeneralFeatures/MapServer/32"),
        "id_fields": ["parcel_no", "pin"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13215": {  # Muscogee — ~205k, consolidated Columbus-Muscogee (city of Columbus)
        "county": "Muscogee", "state": "GA",
        # Columbus Consolidated Gov't CAMA parcels; situs is split across Property_* components
        # (no single field) -> composed by the resolver. Owner_Name + deed/plat book-page present.
        "gis_rest": ("https://ccggisprod.columbusga.org/server/rest/services/TaxAssessors/"
                     "CurrentYearCAMA_Internal/MapServer/1"),
        "id_fields": ["TaxPIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13097": {  # Douglas — ~145k, metro Atlanta (Douglasville)
        "county": "Douglas", "state": "GA",
        "gis_rest": ("https://maps.douglascountyga.gov/arcgis/rest/services/LandRecords/"
                     "LandRecords/MapServer/0"),
        "id_fields": ["PIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13095": {  # Dougherty — ~85k, city of Albany
        "county": "Dougherty", "state": "GA",
        # County "Parcels_Public_View" (ArcGIS Online). Address = situs + Name (owner) + ParcelNum;
        # MailAddress2 is owner mailing (skipped by the situs mail-guard).
        "gis_rest": ("https://services6.arcgis.com/VKHi8CC6pMIyYUIs/arcgis/rest/services/"
                     "Parcels_Public_View/FeatureServer/0"),
        "id_fields": ["ParcelNum"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13073": {  # Columbia — ~160k, Augusta metro (Evans/Grovetown)
        "county": "Columbia", "state": "GA",
        # Self-hosted "Parcels_Snapshot" (layer 1003). Tax_Physical_Address = situs (Tax_Mailing_
        # Address1 is owner mailing, skipped) + Tax_OwnerName1. BONUS: Tax_Deed_Book/Page +
        # Tax_Plat_Book/Page on the layer.
        "gis_rest": ("https://gis.columbiacountyga.gov/host/rest/services/MapsOnline/"
                     "Parcels_Snapshot/MapServer/1003"),
        "id_fields": ["ParcelNum"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13313": {  # Whitfield — ~105k, city of Dalton
        "county": "Whitfield", "state": "GA",
        # Self-hosted TaxAssessMapping (layer 11). Situs is split house_no + stdirect + street_nam
        # + sttype (composed). `address1` (+ city/state/zip) is the owner MAILING PO box — excluded
        # (also from compose). Owner = lastname; id = PARCEL_FUL.
        "gis_rest": ("https://gis.whitfieldcountyga.com/server/rest/services/TaxAssessMapping/"
                     "MapServer/11"),
        "id_fields": ["PARCEL_FUL"],
        "situs_exclude": ["address1", "city", "state", "zip"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13127": {  # Glynn — ~85k, city of Brunswick (St. Simons/Golden Isles)
        "county": "Glynn", "state": "GA",
        # Glynn County AGOL CAMA layer. PHYSICAL_A = situs (OWNER_MAIL is mailing, skipped) + NAME
        # owner. NOTE: the layer name is date-stamped (a periodic CAMA snapshot) so this URL may
        # change when the county republishes — re-point if it 404s (the county self-host exposes no
        # current tax-parcel polygon).
        "gis_rest": ("https://services.arcgis.com/5iWzb1srkjPDXmpL/arcgis/rest/services/"
                     "GlynnCounty_Cama_05212026/FeatureServer/0"),
        "id_fields": ["PARCEL_ID", "PARCELID"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13179": {  # Liberty — ~65k, city of Hinesville (Fort Stewart)
        "county": "Liberty", "state": "GA",
        # Self-hosted ParcelsService (layer 15 = TaxParcel). Property_Address = situs + Owner_Name;
        # id = Parcel_Number.
        "gis_rest": ("https://gis.libertycountyga.gov/arcgis/rest/services/ParcelsService/"
                     "MapServer/15"),
        "id_fields": ["Parcel_Number", "PIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    # ---- 4th-pass batch (GDITAdmin catalog / GMASS / sgrcmaps / valorgis) ----
    "13113": {  # Fayette — ~120k, Fayetteville/Peachtree City (Atlanta metro)
        "county": "Fayette", "state": "GA",
        "gis_rest": ("https://services5.arcgis.com/Hg5aLg4LtSINzVWa/arcgis/rest/services/"
                     "TaxParcels_public/FeatureServer/0"),
        "id_fields": ["PARCELID"],  # SITEADDRESS situs; PSTL* mailing auto-skipped
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13015": {  # Bartow — ~110k, Cartersville (Atlanta NW metro)
        "county": "Bartow", "state": "GA",
        # Situs split HOUSE_NO + STREET_NAM; Mailing_* excluded. Owner1.
        "gis_rest": ("https://www.bartowgis.org/arcgis/rest/services/AGOServices/BartowLand/"
                     "FeatureServer/2"),
        "id_fields": ["PARCELID"],
        "situs_exclude": ["Mailing_Address_1", "Mailing_Address_2", "Mailing_City",
                          "Mailing_State", "Mailing_Zip"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13115": {  # Floyd — ~100k, Rome
        "county": "Floyd", "state": "GA",
        # PROP_ADDR single situs; NAME owner; ADDRESS/CITY/STATE/ZIP = mailing (excluded).
        "gis_rest": ("https://services2.arcgis.com/nV67H1IJR8GS6SAA/ArcGIS/rest/services/"
                     "Current_Parcels/FeatureServer/5"),
        "id_fields": ["PARCEL"],
        "situs_exclude": ["ADDRESS", "CITY", "STATE", "ZIP"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13045": {  # Carroll — ~120k, Carrollton (Atlanta W metro)
        "county": "Carroll", "state": "GA",
        # GMASS House_No + Road + Rd_Type + Owner (public ExportFeatures copy; the catalog's
        # Carroll_Parcels is token-required).
        "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                     "Carroll_Parcels_20240923_ExportFeatures/FeatureServer/0"),
        "id_fields": ["PIN", "Parcel_no"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13247": {  # Rockdale — ~95k, Conyers (Atlanta E metro)
        "county": "Rockdale", "state": "GA",
        # Situs Address + Road_name + St_Type (composed); no owner on layer.
        "gis_rest": ("https://services.arcgis.com/Tbke9ca9DhtF4VIx/ArcGIS/rest/services/"
                     "Parcel_Polygons_working/FeatureServer/0"),
        "id_fields": ["PARCEL_NO"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13185": {  # Lowndes — ~120k, Valdosta
        "county": "Lowndes", "state": "GA",
        # valorgis; split HOUSE_NO + STDIRECT + STTYPE + STREET_NAM; LASTNAME/FIRSTNAME; mailing
        # ADDRESS1/2/3 + CITY/STATE/ZIP excluded.
        "gis_rest": "https://www.valorgis.com/arcgis/rest/services/Valor/Parcels/MapServer/0",
        "id_fields": ["PARCEL_NO"],
        "situs_exclude": ["ADDRESS1", "ADDRESS2", "ADDRESS3", "CITY", "STATE", "ZIP"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13275": {  # Thomas — ~45k, Thomasville
        "county": "Thomas", "state": "GA",
        "gis_rest": ("https://www.thomascountymaps.org/arcgis/rest/services/parcels_addresses/"
                     "MapServer/4"),
        "id_fields": ["PARCEL_NO"],
        "situs_exclude": ["ADDRESS1", "ADDRESS2", "ADDRESS3", "CITY", "STATE", "ZIP_1"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13029": {  # Bryan — ~45k, Pembroke/Richmond Hill (Savannah metro)
        "county": "Bryan", "state": "GA",
        # split HOUSE_NO + STDIRECT + STTYPE + STREET_NAM; LASTNAME; mailing excluded. (Server
        # rejects pagination — the app never sends resultRecordCount, so this is fine.)
        "gis_rest": ("https://bryangis.bryan-county.org/arcgis/rest/services/PropertyDetails/"
                     "MapServer/0"),
        "id_fields": ["PARCEL_NO"],
        "situs_exclude": ["ADDRESS1", "ADDRESS2", "ADDRESS3", "CITY", "STATE", "ZIP_1"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13303": {  # Washington — ~20k, Sandersville
        "county": "Washington", "state": "GA",
        # split HOUSE_NO + STDIRECT + STTYPE + STREET_NAM; no owner on layer.
        "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                     "Washington_Parcels/FeatureServer/0"),
        "id_fields": ["Parcel_ID", "PARCEL_NO"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13193": {  # Macon — ~12k, Oglethorpe/Montezuma
        "county": "Macon", "state": "GA",
        "gis_rest": ("https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/ArcGIS/rest/services/"
                     "Parcels12_2018/FeatureServer/0"),
        "id_fields": ["Parcel_Num"],  # Address single situs + Owner
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    # GMASS House_No + Road + Rd_Type + Owner (services.arcgis.com/ISpzx3B5ZsVA6e1Z):
    "13221": {"county": "Oglethorpe", "state": "GA", "id_fields": ["PIN", "Parcel_No"],
              "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                           "Oglethorpe_Parcels/FeatureServer/0"),
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13161": {"county": "Jeff Davis", "state": "GA", "id_fields": ["PIN"],
              "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                           "JeffDParcels_ExportFeatures/FeatureServer/0"),
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13291": {"county": "Union", "state": "GA", "id_fields": ["PIN"],
              "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                           "Union_Parcels/FeatureServer/0"),
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13263": {"county": "Talbot", "state": "GA", "id_fields": ["PIN", "Parcel_No"],
              "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                           "Talbot_Parcels/FeatureServer/0"),
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13251": {"county": "Screven", "state": "GA", "id_fields": ["PIN", "parcel_no"],
              "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                           "Screven_2020_Webmap/FeatureServer/0"),
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13081": {"county": "Crisp", "state": "GA", "id_fields": ["PIN", "Parcel_No"],
              "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                           "Crisp_Parcels/FeatureServer/0"),
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13109": {"county": "Evans", "state": "GA", "id_fields": ["PARCEL_NO", "PIN"],
              "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                           "Parcels_ExportFeaturesEvans/FeatureServer/0"),
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13125": {"county": "Glascock", "state": "GA", "id_fields": ["PIN"],
              "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                           "Glascock_Web_Map_2026_WFL1/FeatureServer/1"),
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13013": {"county": "Barrow", "state": "GA", "id_fields": ["Parcel_no", "Realkey"],
              "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/ArcGIS/rest/services/"
                           "Barrow_Web_Map_2026_WFL1/FeatureServer/3"),
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13049": {"county": "Charlton", "state": "GA", "id_fields": ["PARCEL_NO", "PIN"],
              "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/ArcGIS/rest/services/"
                           "Charlton_Webmap/FeatureServer/0"),
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13271": {"county": "Telfair", "state": "GA", "id_fields": ["PIN"],  # use 2025_WFL1 (has CAMA);
              # the separate Telfair_Parcels service is id-only
              "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/ArcGIS/rest/services/"
                           "Telfair_2025_WFL1/FeatureServer/0"),
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    # WinGAP split (house_no+stdirect+sttype+street_nam) — mailing excluded:
    "13093": {"county": "Dooly", "state": "GA", "id_fields": ["Parcel_No"],
              "gis_rest": ("https://services9.arcgis.com/x9uoDq5JB3OouaRv/arcgis/rest/services/"
                           "Parcel_Regions_w_WinGAP/FeatureServer/0"),
              "situs_exclude": ["address1", "address2", "address3", "city", "state", "zip_code"],
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    # Southern GA Regional Commission (sgrcmaps.com/alma) — State Plane, app buffer resolves:
    "13277": {"county": "Tift", "state": "GA", "id_fields": ["ParcelNum"],  # single Situs + OwnerName
              "gis_rest": "https://www.sgrcmaps.com/alma/rest/services/Tift/Tift_Parcels/MapServer/0",
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13155": {"county": "Irwin", "state": "GA", "id_fields": ["PARCEL_NO"],
              "gis_rest": ("https://www.sgrcmaps.com/alma/rest/services/Irwin/ParcelInformation/"
                           "MapServer/5"),
              "situs_exclude": ["ADDRESS1", "ADDRESS2", "ADDRESS3", "CITY", "STATE", "ZIP_1"],
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13287": {"county": "Turner", "state": "GA", "id_fields": ["Parcel_No"],
              "gis_rest": ("https://www.sgrcmaps.com/alma/rest/services/Turner/TurnerParcels/"
                           "MapServer/0"),
              "situs_exclude": ["address1", "address2", "address3"],
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13003": {"county": "Atkinson", "state": "GA", "id_fields": ["PARCEL_NO", "PARCELNUM"],
              "gis_rest": ("https://www.sgrcmaps.com/alma/rest/services/Atkinson/"
                           "PropertyInformation/MapServer/1"),
              "situs_exclude": ["ADDRESS1", "ADDRESS2", "ADDRESS3", "CITY", "STATE", "ZIP_1"],
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13069": {"county": "Coffee", "state": "GA", "id_fields": ["Parcel_No"],  # split situs, no owner
              "gis_rest": ("https://www.sgrcmaps.com/alma/rest/services/Coffee/"
                           "CoffeeBackgroundLayers/MapServer/2"),
              "clerk_url": GSCCCA, "clerk_platform": "unknown"},
    "13233": {  # Polk — ~43k, Cedartown/Rockmart
        "county": "Polk", "state": "GA",
        # GMASS mass-appraisal host. Situs split House_No + Road + Rd_Type (composed) + Owner.
        "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/ArcGIS/rest/services/"
                     "Parcels/FeatureServer/0"),
        "id_fields": ["PID", "PIN", "Parcel_Num"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13225": {  # Peach — ~28k, Fort Valley/Byron
        "county": "Peach", "state": "GA",
        # ADDRESS single situs field; no owner on the layer. PARCEL_NO id.
        "gis_rest": ("https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/"
                     "Peach_County_Parcels/FeatureServer/0"),
        "id_fields": ["PARCEL_NO"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13199": {  # Meriwether — ~21k, Greenville
        "county": "Meriwether", "state": "GA",
        # WinGAP: situs split house_no + stdirect + street_nam + sttype (composed). address1/2/3 +
        # city/state/zip_code = owner mailing (excluded). lastname owner.
        "gis_rest": ("https://services9.arcgis.com/Xv8vRekQ4FVHSSIe/arcgis/rest/services/"
                     "MeriwetherParcels/FeatureServer/0"),
        "id_fields": ["Parcel_No"],
        "situs_exclude": ["address1", "address2", "address3", "city", "state", "zip_code"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13055": {  # Chattooga — ~25k, Summerville
        "county": "Chattooga", "state": "GA",
        # GMASS 2025 webmap layer 3. Situs split House_No + Road + Rd_Type + Owner. State Plane SR
        # (exact point 0) — app envelope-buffer resolves it.
        "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/ArcGIS/rest/services/"
                     "Chattooga_Webmap_2025_WFL1/FeatureServer/3"),
        "id_fields": ["PIN", "MAP_PAR"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13027": {  # Brooks — ~16k, Quitman
        "county": "Brooks", "state": "GA",
        # Southern GA Regional Commission host. Situs split HOUSE_NO + STDIRECT + STTYPE +
        # STREET_NAM (composed). ADDRESS1/2/3 + CITY/STATE/ZIP_1 = owner mailing (excluded).
        "gis_rest": "https://www.sgrcmaps.com/alma/rest/services/Brooks/Boundaries/MapServer/0",
        "id_fields": ["PARCEL_NO"],
        "situs_exclude": ["ADDRESS1", "ADDRESS2", "ADDRESS3", "CITY", "STATE", "ZIP_1"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13075": {  # Cook — ~17k, Adel
        "county": "Cook", "state": "GA",
        "gis_rest": "https://www.sgrcmaps.com/alma/rest/services/Cook/Cook_Parcels/MapServer/0",
        "id_fields": ["Parcel_No"],
        "situs_exclude": ["address1", "address2", "address3", "city", "state"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13163": {  # Jefferson — ~15k, Louisville
        "county": "Jefferson", "state": "GA",
        # GMASS 2024 webmap layer 3. Situs split House_No + Road + Rd_Type + Owner. NOTE the layer
        # includes a null-attribute "mask" polygon over the whole extent; _choose skips the
        # situs-less candidate and picks the real parcel.
        "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/ArcGIS/rest/services/"
                     "Jefferson_Web_Map_2024_WFL1/FeatureServer/3"),
        "id_fields": ["PIN", "PARCEL_NO"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13107": {  # Emanuel — ~22k, Swainsboro
        "county": "Emanuel", "state": "GA",
        # WinGAP view. Situs split house_no + stdirect + street_nam + sttype. Mailing excluded.
        "gis_rest": ("https://services8.arcgis.com/oi3j4zWzPc3hzTpc/arcgis/rest/services/"
                     "Emanuel_Parcels_view/FeatureServer/0"),
        "id_fields": ["Parcel_No"],
        "situs_exclude": ["address1", "address2", "address3", "city", "state", "zip_code"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13229": {  # Pierce — ~19k, Blackshear
        "county": "Pierce", "state": "GA",
        "gis_rest": ("https://www.sgrcmaps.com/alma/rest/services/Pierce/ParcelInformation/"
                     "MapServer/0"),
        "id_fields": ["PARCEL_NO", "PAR_ID"],
        "situs_exclude": ["ADDRESS1", "ADDRESS2", "ADDRESS3", "CITY", "STATE", "ZIP_1"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13157": {  # Jackson — ~80k, Jefferson/Braselton (Atlanta NE exurb)
        "county": "Jackson", "state": "GA",
        # Esri-hosted Tax_Parcels, layer 9 (layer 0 is sparse — use 9). Situs split HOUSE_NO +
        # STREET_NAM (composed). ADDRESS1/2/3 + CITY/STATE are owner MAILING (excluded). LASTNAME
        # owner; PARCEL_NO id.
        "gis_rest": ("https://services8.arcgis.com/bcbi4lYRFOsss0F5/arcgis/rest/services/"
                     "Tax_Parcels/FeatureServer/9"),
        "id_fields": ["PARCEL_NO", "PIN", "tax_id"],
        "situs_exclude": ["ADDRESS1", "ADDRESS2", "ADDRESS3", "CITY", "STATE"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13133": {  # Greene — ~19k, Greensboro (Lake Oconee resort area)
        "county": "Greene", "state": "GA",
        # WinGAP CAMA view. Situs split house_no + stdirect + street_nam + sttype (composed).
        # address1/2/3 + city/state/zip_code are owner MAILING (excluded). lastname owner.
        "gis_rest": ("https://services7.arcgis.com/QbbsWI5nIfBp4cMB/arcgis/rest/services/"
                     "Parcel_Regions_w_WinGAP_view/FeatureServer/0"),
        "id_fields": ["Parcel_No"],
        "situs_exclude": ["address1", "address2", "address3", "city", "state", "zip_code"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13211": {  # Morgan — ~20k, Madison
        "county": "Morgan", "state": "GA",
        # WinGAP parcels. Situs split HOUSE_NO + STDIRECT + STTYPE + STREET_NAM (composed). No owner
        # on the layer (only a qPublic link). Custom GA-West State Plane SR — an exact-point query
        # in 4326 returns 0, but the app's envelope-buffer widening resolves it.
        "gis_rest": ("https://services9.arcgis.com/mr2xH531NAL4tt7e/arcgis/rest/services/"
                     "Parcels/FeatureServer/0"),
        "id_fields": ["Parcel_No"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13059": {  # Clarke — ~130k, consolidated Athens-Clarke (Univ. of Georgia)
        "county": "Clarke", "state": "GA",
        # Athens-Clarke Unified Gov't parcels. PAR_ADD = situs + OWNER_NAME + PARCEL_NO; OWNER_ADD
        # is owner mailing. (HOUSE/STNAM_TYP split components also present.)
        "gis_rest": "https://enigma.accgov.com/server/rest/services/ACC_Parcels/FeatureServer/0",
        "id_fields": ["PARCEL_NO"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13077": {  # Coweta — ~150k, metro Atlanta (Newnan)
        "county": "Coweta", "state": "GA",
        # WinGAP CAMA parcels. IMPORTANT: this layer's `StreetAddress` field is the owner MAILING
        # address, so it is excluded and the situs is composed from the Street* components.
        "gis_rest": ("https://coweta-gis-web.coweta.ga.us/arcgis/rest/services/"
                     "WinGapParcels/MapServer/0"),
        "id_fields": ["PID", "ParcelNumber"],
        "situs_exclude": ["StreetAddress"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    # ---- Batch added 2026-08-20 (30 counties) ----
    # Found by enumerating the GDIT "Parcels - GA - *" catalog + the GMASS (ISpzx3B5ZsVA6e1Z),
    # MGRC (Ug5xGQbHsD8zuZzM) and GA-GIO AGOL orgs, then VERIFYING each layer with a grid of
    # point queries inside the county polygon (>=60% of interior grid points must return a
    # parcel, count >= 400, and an id field must exist). That coverage gate is what rejects the
    # city-only / study-area subsets these orgs are full of — e.g. Walton and Effingham each
    # have a public "Parcels" layer that covers <10% of the county, so they stay link-only.
    "13153": {  # Houston — ~168k, Warner Robins (was previously believed qPublic-only)
        "county": "Houston", "state": "GA",
        # Middle Georgia Regional Commission publishes the full county digest with owner+situs.
        "gis_rest": ("https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/"
                     "HoustonCoParcels_withOwner/FeatureServer/0"),
        "id_fields": ["PARCEL_NO", "PIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13223": {  # Paulding — ~180k, metro Atlanta NW (Dallas/Hiram)
        "county": "Paulding", "state": "GA",
        # County's own AGOL webmap layer. Parcel-ID + acreage + owner KEY only (no situs string),
        # so the address-match step can't confirm; the app flags it and the link stays available.
        "gis_rest": ("https://services8.arcgis.com/7YXQzPPGs9Uc4qKl/arcgis/rest/services/"
                     "Paulding_Map_Auto_Updated_WFL1/FeatureServer/25"),
        "id_fields": ["APIN", "GPIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13217": {  # Newton — ~115k, metro Atlanta E (Covington)
        "county": "Newton", "state": "GA",
        # Newton's OWN server (gis.ncboc.com) now requires a token, so this is the public mirror
        # of the county PARCEL_VIEW digest. Verified 2026-08-20 over all 45,755 rows:
        #   POPULATED - PARCEL_NO/PARCELNO, StreetName (45,608), TotalAcres,
        #               DeedBook/DeedPage (44,421) and PlatBook/PlatPage (13,762)  <- the deed
        #               and plat book/page are exactly what the deed/plat steps need.
        #   EMPTY     - StreetNumb, ParcelAddr, OwnersName (all 0 rows) in this mirror.
        # So there is NO full situs: the app gets the street NAME but no house number, and
        # _compose_situs correctly returns "" rather than inventing one, which means the
        # address-match step can't confirm and the result is flagged for verification.
        # Address1/Address2 are owner MAILING, not situs - confirmed by sampling (values like
        # "PO BOX 1366", and mailing City is Lithonia/Madison/Conyers while ParcelCity is
        # always Covington) - hence the exclude, so they can't leak into a composed situs.
        "gis_rest": ("https://services1.arcgis.com/qTQ6qYkHpxlu0G82/arcgis/rest/services/"
                     "Newton_Parcels/FeatureServer/0"),
        "id_fields": ["PARCEL_NO", "PARCELNO"],
        "situs_exclude": ["Address1", "Address2", "City", "State", "ZipCode"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13285": {  # Troup — ~70k, LaGrange
        "county": "Troup", "state": "GA",
        # Regrid-schema extract published by the county's GIS vendor: `address` is the situs,
        # the mail_* / mailadd fields are owner mailing (auto-skipped as "mail").
        "gis_rest": ("https://services6.arcgis.com/WjqAE1SlQxuk7dsk/arcgis/rest/services/"
                     "Troup_County_GA_Parcel_Feature_Layer/FeatureServer/0"),
        "id_fields": ["parcelnumb", "account_nu"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13255": {  # Spalding — ~68k, Griffin
        "county": "Spalding", "state": "GA",
        "gis_rest": ("https://services5.arcgis.com/IBG8fFojdkoiHAvQ/arcgis/rest/services/"
                     "Parcels_Public_View/FeatureServer/1"),
        "id_fields": ["PARCEL_ID"],   # county "public view" carries id + jurisdiction only
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13031": {  # Bulloch — ~83k, Statesboro (Georgia Southern)
        "county": "Bulloch", "state": "GA",
        "gis_rest": ("https://services6.arcgis.com/XxfLDid4CNOqpdhy/arcgis/rest/services/"
                     "Mobile_Map/FeatureServer/1"),
        "id_fields": ["PROP_PIN"],   # parcel id + acreage only
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13175": {  # Laurens — ~49k, Dublin
        "county": "Laurens", "state": "GA",
        # GMASS webmap; situs composed from House_No + Road + Rd_Type (GMASS schema).
        "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                     "Laurens_Web_Map_WFL1/FeatureServer/5"),
        "id_fields": ["Parcel_No", "PIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13219": {  # Oconee — ~43k, Watkinsville (Athens metro)
        "county": "Oconee", "state": "GA",
        # MGRC "Greater Athens" composite; layer 32 is the Oconee digest (also has PLAT_BOOK
        # + DEED_BOOK, useful for the plat/deed steps).
        "gis_rest": ("https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/"
                     "Greater_Athens_All_WFL1/FeatureServer/32"),
        "id_fields": ["PARCELID", "RealKey"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13137": {  # Habersham — ~47k, Clarkesville/Cornelia
        "county": "Habersham", "state": "GA",
        "gis_rest": ("https://arcgis5.roktech.net/arcgis/rest/services/habersham/"
                     "habersham_rokmaps/MapServer/8"),
        "id_fields": ["PARNO", "PIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13187": {  # Lumpkin — ~35k, Dahlonega
        "county": "Lumpkin", "state": "GA",
        # WinGAP CAMA: ADDRESS1-3/CITY/STATE/ZIP are the owner MAILING address, so the situs
        # must be composed from HOUSE_NO + STREET_NAM.
        "gis_rest": ("https://services6.arcgis.com/gVx1YCdWTpppaijl/arcgis/rest/services/"
                     "Base_Map/FeatureServer/3"),
        "id_fields": ["PARCEL_NO", "REALKEY"],
        "situs_exclude": ["ADDRESS1", "ADDRESS2", "ADDRESS3", "CITY", "STATE", "ZIP"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13009": {  # Baldwin — ~43k, Milledgeville
        "county": "Baldwin", "state": "GA",
        "gis_rest": ("https://services7.arcgis.com/Da8HZMsU25Hzzob3/arcgis/rest/services/"
                     "Baldwin_County_Zoning_WFL1/FeatureServer/1"),
        "id_fields": ["PARID"],   # parcel id + acreage only
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13039": {  # Camden — ~55k, Kingsland/St. Marys
        "county": "Camden", "state": "GA",
        "gis_rest": ("https://services3.arcgis.com/feUM6sTOP0Mfde8s/arcgis/rest/services/"
                     "CamdenParcel_12132021_view/FeatureServer/122"),
        "id_fields": ["RealKey"],   # RealKey + owner Name + stated area (no situs string)
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13299": {  # Ware — ~36k, Waycross
        "county": "Ware", "state": "GA",
        # NOTE layer 38 = the plain Parcels layer. Layers 23/37 are parcels INTERSECTED with
        # soils (~60k rows = fragments per soil polygon) and must not be used for lookup.
        "gis_rest": ("https://services9.arcgis.com/XAyIBOsw3fLfDjTY/arcgis/rest/services/"
                     "WareCounty_Base_gdb/FeatureServer/38"),
        "id_fields": ["PARCEL_NO", "REALKEY"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13261": {  # Sumter — ~29k, Americus
        "county": "Sumter", "state": "GA",
        "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                     "Sumter_Lake_Subrecords_2026_WFL1/FeatureServer/1"),
        "id_fields": ["PARCELID", "PIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13207": {  # Monroe — ~28k, Forsyth
        "county": "Monroe", "state": "GA",
        "gis_rest": ("https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/"
                     "MonroeCountyParcels_Jan2026/FeatureServer/15"),
        "id_fields": ["PARCELID", "PARCEL"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13085": {  # Dawson — ~30k, Dawsonville
        "county": "Dawson", "state": "GA",
        "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                     "Dawson_Webmap_WFL1/FeatureServer/1"),
        "id_fields": ["Parcel_No", "Realkey"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13083": {  # Dade — ~16k, Trenton (Chattanooga metro)
        "county": "Dade", "state": "GA",
        # WinGAP CAMA (has a real SITUS field as well as the split components).
        "gis_rest": ("https://services2.arcgis.com/9rZSWj5rVGcJbHoU/arcgis/rest/services/"
                     "EPL_Map/FeatureServer/4"),
        "id_fields": ["PARCEL_NO", "REALKEY"],
        "situs_exclude": ["ADDRESS1", "ADDRESS2", "ADDRESS3", "CITY", "STATE", "ZIP"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13079": {  # Crawford — ~12k, Roberta
        "county": "Crawford", "state": "GA",
        "gis_rest": ("https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/"
                     "CrawfordCountyParcels_Jan2026/FeatureServer/0"),
        "id_fields": ["PARCELNO", "PID"],   # also carries DeedRef + PLATREF
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13321": {  # Worth — ~20k, Sylvester
        "county": "Worth", "state": "GA",
        # Situs composed from ADDRESS_NU + STREET.
        "gis_rest": ("https://services2.arcgis.com/PYn6bWCjT6bhw1z3/arcgis/rest/services/"
                     "Worth_Heirs_Concentration_Census_Block_WFL1/FeatureServer/4"),
        "id_fields": ["Parcel_No", "PIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13279": {  # Toombs — ~27k, Vidalia
        "county": "Toombs", "state": "GA",
        "gis_rest": ("https://services5.arcgis.com/HHvUPZ2XuLOAJxjR/arcgis/rest/services/"
                     "MontgomeryToombsBoundary/FeatureServer/16"),
        "id_fields": ["Parcel_No", "Realkey"],
        "situs_exclude": ["address1", "address2", "address3", "city", "state", "zip",
                          "zip_code"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13025": {  # Brantley — ~19k, Nahunta
        "county": "Brantley", "state": "GA",
        "gis_rest": ("https://services3.arcgis.com/86pyA5PND5NdokIc/arcgis/rest/services/"
                     "Brantley_Parcels_view/FeatureServer/0"),
        "id_fields": ["Parcel_No", "Realkey"],
        "situs_exclude": ["address1", "address2", "address3", "city", "state", "zip",
                          "zip_code"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13191": {  # McIntosh — ~11k, Darien
        "county": "McIntosh", "state": "GA",
        "gis_rest": ("https://services1.arcgis.com/PITZGI6S0DUdRaq5/arcgis/rest/services/"
                     "McIntosh_Parcels_20220811/FeatureServer/0"),
        "id_fields": ["PARCEL_NO", "PIN", "REALKEY"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13289": {  # Twiggs — ~8k, Jeffersonville
        "county": "Twiggs", "state": "GA",
        # CAVEAT (measured 2026-08-20): this layer holds 6,828 parcels county-wide but ZERO
        # inside the Jeffersonville (county seat) town limits — the incorporated area is not in
        # the published extract. Rural Twiggs addresses resolve; in-town addresses return no
        # parcel and fall through to the GSCCCA/NETROnline link, same as being unwired. Kept
        # because the rural coverage is real and the fallback keeps in-town jobs one click away.
        "gis_rest": ("https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/"
                     "Twiggs_County_Parcels/FeatureServer/0"),
        "id_fields": ["PARCEL_NO"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13269": {  # Taylor — ~8k, Butler
        "county": "Taylor", "state": "GA",
        "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/arcgis/rest/services/"
                     "Taylor_Web_Map_2025_WFL1/FeatureServer/6"),
        "id_fields": ["PARCEL_NO", "PIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13317": {  # Wilkes — ~10k, Washington
        "county": "Wilkes", "state": "GA",
        "gis_rest": ("https://services.arcgis.com/ISpzx3B5ZsVA6e1Z/ArcGIS/rest/services/"
                     "Wilkes_Parcels/FeatureServer/0"),
        "id_fields": ["QPID", "REALKEY"],   # owner + acreage; MAIL1-3 are owner mailing
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13131": {  # Grady — ~26k, Cairo
        "county": "Grady", "state": "GA",
        # County AGOL 2017 digest — parcel id + acreage only (no situs/owner).
        "gis_rest": ("https://services7.arcgis.com/Pf7RRv4QttHB3VbR/arcgis/rest/services/"
                     "WebParcels/FeatureServer/0"),
        "id_fields": ["PARCELNO", "PIN"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13173": {  # Lanier — ~10k, Lakeland
        "county": "Lanier", "state": "GA",
        "gis_rest": "https://www.sgrcmaps.com/alma/rest/services/Lanier/Parcels/MapServer/2",
        "id_fields": ["PARCEL_NO"],   # owner + legal desc; no situs string
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13259": {  # Stewart — ~5k, Lumpkin
        "county": "Stewart", "state": "GA",
        "gis_rest": ("https://services2.arcgis.com/PYn6bWCjT6bhw1z3/arcgis/rest/services/"
                     "Stewart_County_WFL1/FeatureServer/5"),
        "id_fields": ["PARCEL_ID", "REALKEY"],
        "situs_exclude": ["ADDRESS1", "ADDRESS2", "ADDRESS3", "CITY", "STATE", "ZIP"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13101": {  # Echols — ~4k, Statenville
        "county": "Echols", "state": "GA",
        "gis_rest": ("https://services5.arcgis.com/HA2thkMWRBDb77XN/arcgis/rest/services/"
                     "Echols_Tax_Parcels/FeatureServer/11"),
        "id_fields": ["PARCEL_NO", "REALKEY"],
        "situs_exclude": ["ADDRESS1", "ADDRESS2", "ADDRESS3", "CITY", "STATE", "ZIP"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    "13061": {  # Clay — ~3k, Fort Gaines
        "county": "Clay", "state": "GA",
        "gis_rest": ("https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/"
                     "Clay_County_Parcels_10_23/FeatureServer/0"),
        "id_fields": ["Parcel_No", "Realkey"],
        "situs_exclude": ["address1", "address2", "address3", "city", "state", "zip",
                          "zip_code"],
        "clerk_url": GSCCCA, "clerk_platform": "unknown",
        "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
    },
    # STILL LINK-ONLY (verified 2026-08-20 — a public layer exists but FAILS the coverage gate,
    # so wiring it would return wrong/no parcels for most of the county):
    #   Walton (13297)  - waltongis `walton_parcels_view` needs a token; the reachable
    #                     "Walton Parcels" copy covers 8% of the county (2,286 of ~45k parcels).
    #   Effingham (13103) - the public "Effingham_County_Parcels" service holds only BOE/BOC/IDA
    #                     owned-property subsets (41-253 features).
    #   Walker (13295)  - only a third-party 2021/2026 "LLLT" study layer, 55% coverage, 7,811
    #                     features vs ~30k expected.
    #   Bleckley (13023) - City of Cochran dilapidated-structures subset only (79 features).
    # TOKEN-WALLED (service exists on the county/vendor host but returns "Token Required"):
    #   Fannin (13111), McDuffie (13189), Wilcox (13315), Newton's own gis.ncboc.com.
    # RENAMED/GONE from the GDIT catalog (re-enumerate the host if revisiting):
    #   Colquitt (13071), Decatur (13087), Gilmer (13123), Haralson (13143), Harris (13145),
    #   Lee (13177), Long (13183), Schley (13249), Ben Hill (13017).
    # For the remaining rural long tail, a paid API (Regrid/ReportAll) is still the only
    # efficient path to all 159 counties.
}

# ---------------------------------------------------------------------------------------
# APPRAISER / TAX links — all 159 counties (verified 2026-08-20)
# ---------------------------------------------------------------------------------------
# Georgia's assessors are overwhelmingly on qPublic (Schneider Geospatial), and the LEGACY
# per-county path is uniform and stable: https://qpublic.net/ga/<slug>/  where <slug> is the
# county basename lowercased with non-alphanumerics stripped ("Ben Hill" -> benhill).
# Swept all 159: 152 answer on that pattern (149 with a 200 naming the county in the title,
# plus Bryan/Camden/Whitfield which sit behind a Cloudflare challenge -> 403, i.e. "opens in a
# browser"; the URL is correct by construction because the county is IN the path). The 7 below
# genuinely run their own site or the modern qPublic app instead, so they are overridden.
_QPUBLIC = "https://qpublic.net/ga/{}/"
_APPRAISER_OVERRIDE = {
    "13135": ("https://www.gwinnettcounty.com/government/departments/"
              "county-administrator/assessor"),                     # Gwinnett
    "13051": "https://boa.chathamcountyga.gov/",                     # Chatham (Savannah)
    "13063": "https://claytoncountypropertyappraiser.org/",          # Clayton
    "13097": "https://www.celebratedouglascounty.com/TaxAssessor/",  # Douglas
    "13113": "https://fayettecountyga.gov/departments/assessor/online_services.php",  # Fayette
    # modern qPublic app (the legacy /ga/<slug>/ path 404s for these two)
    "13073": ("https://qpublic.schneidercorp.com/Application.aspx?"
              "App=ColumbiaCountyGA&PageType=Search"),               # Columbia
    "13011": ("https://qpublic.schneidercorp.com/Application.aspx?"
              "App=BanksCountyGA&PageType=Search"),                  # Banks
}


def _fill_all_counties() -> None:
    """Give every GA county an appraiser link + the statewide GSCCCA deed link.

    Counties with no free parcel service get a LINK-ONLY registry entry (no `gis_rest`), which
    is exactly what the app needs to show the appraiser/deed cards. coverage() counts parcels
    by the presence of `gis_rest`, so these entries do NOT inflate the parcel number.
    """
    import json
    import pathlib
    import re
    raw = json.loads(
        (pathlib.Path(__file__).resolve().parent.parent / "_counties_raw.json")
        .read_text(encoding="utf-8"))
    for c in raw["13"]:
        fips = c["fips"]
        slug = re.sub(r"[^a-z0-9]", "", c["basename"].lower())
        entry = COUNTIES.setdefault(fips, {
            "county": c["basename"], "state": "GA",
            "clerk_url": GSCCCA, "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        })
        entry.setdefault("appraiser_url",
                         _APPRAISER_OVERRIDE.get(fips, _QPUBLIC.format(slug)))

    COUNTIES.update({
        # ---- Added 2026-08-17 by the automated sweep (scripts/discover_state_parcels.py ->
        #      audit_parcel_candidates.py -> verify_situs_fields.py). Every entry below cleared
        #      all four gates: point-queryable with a situs, parcels found across the WHOLE
        #      county (not just the county seat), feature count consistent with a complete roll
        #      vs Census housing units, and the app's own situs_of() returning real street
        #      addresses on sampled parcels. Provenance is in each comment. ----
        "13013": {  # Barrow — 38,071 parcels (1.27x housing units), edited 2024-09-24
            "county": "Barrow", "state": "GA",
            "gis_rest": ("https://services5.arcgis.com/OVFGXfRTCVcPwl55/arcgis/rest/services/Barrow_"
                         "Parcels_w_Owner/FeatureServer/0"),
            "id_fields": ["Map_no", "Parcel_no", "PARCEL_NO_1"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13017": {  # Ben Hill — 11,619 parcels (1.43x housing units), edited 2025-03-17
            "county": "Ben Hill", "state": "GA",
            "gis_rest": ("https://services5.arcgis.com/HA2thkMWRBDb77XN/arcgis/rest/services/BH_Prop"
                         "erty/FeatureServer/2"),
            "id_fields": ["PARCEL_NO", "ACCTSTATUS_1"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13055": {  # Chattooga — 14,451 parcels (1.33x housing units), edited 2025-08-12
            "county": "Chattooga", "state": "GA",
            "gis_rest": ("https://services9.arcgis.com/eXIsbyIncFwEzqul/arcgis/rest/services/parcels"
                         "_historic/FeatureServer/2"),
            "id_fields": ["parcel_address"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13061": {  # Clay — 3,063 parcels (1.56x housing units), edited 2024-05-09
            "county": "Clay", "state": "GA",
            "gis_rest": ("https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/Clay_Co"
                         "unty_Parcels_10_23/FeatureServer/0"),
            "id_fields": ["Parcel_No", "acctstatus", "Parcel"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
            "situs_exclude": ["address1", "address2", "address3", "city", "state", "zip", "zip_code"],
        },
        "13083": {  # Dade — 7,811 parcels (1.06x housing units), edited 2026-07-23
            "county": "Dade", "state": "GA",
            "gis_rest": ("https://services.arcgis.com/UnTXoPXBYERF0OH6/arcgis/rest/services/Dade_Par"
                         "cels_2020LLLT/FeatureServer/5"),
            "id_fields": ["PARCEL_NO", "parcelAddress"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13095": {  # Dougherty — 38,005 parcels (0.94x housing units), edited 2026-08-07
            "county": "Dougherty", "state": "GA",
            "gis_rest": ("https://services6.arcgis.com/VKHi8CC6pMIyYUIs/arcgis/rest/services/Parcels"
                         "_Public_View/FeatureServer/0"),
            "id_fields": ["ParcelNum", "Parcels"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13101": {  # Echols — 2,206 parcels (1.44x housing units), edited 2026-06-23
            "county": "Echols", "state": "GA",
            "gis_rest": ("https://services5.arcgis.com/HA2thkMWRBDb77XN/arcgis/rest/services/Echols_"
                         "Tax_Parcels/FeatureServer/11"),
            "id_fields": ["PARCELNO", "PARCEL_NO", "PARCEL_NO2"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13103": {  # Effingham — 32,941 parcels (1.35x housing units), edited 2024-10-31
            "county": "Effingham", "state": "GA",
            "gis_rest": ("https://services5.arcgis.com/9Z9r3rLUCq0SjsRb/arcgis/rest/services/Effingh"
                         "am_County_GA_Parcels/FeatureServer/0"),
            "id_fields": ["PIN400", "PIN", "WPIN"],
            "situs_exclude": ["address1"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13107": {  # Emanuel — 14,974 parcels (1.5x housing units), edited 2025-09-16
            "county": "Emanuel", "state": "GA",
            "gis_rest": ("https://services5.arcgis.com/HHvUPZ2XuLOAJxjR/arcgis/rest/services/Emanuel"
                         "_CountyWide_GeoData_View/FeatureServer/20"),
            "id_fields": ["Parcel_No", "acctstatus", "Parcel"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13109": {  # Evans — 6,635 parcels (1.43x housing units), edited 2024-04-10
            "county": "Evans", "state": "GA",
            "gis_rest": ("https://services6.arcgis.com/vgwS5Le2XfU2EPjI/arcgis/rest/services/Evans_A"
                         "ddress_WithParcel_info/FeatureServer/1"),
            "id_fields": ["PARCEL_NO"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13113": {  # Fayette — 49,074 parcels (1.09x housing units), edited 2026-08-16
            "county": "Fayette", "state": "GA",
            "gis_rest": ("https://services5.arcgis.com/Hg5aLg4LtSINzVWa/arcgis/rest/services/Parcels"
                         "_Data_SAGES/FeatureServer/0"),
            "id_fields": ["PARCEL_NO", "PARCEL_KEY", "PARCEL"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13115": {  # Floyd — 49,316 parcels (1.22x housing units), edited 2023-05-24
            "county": "Floyd", "state": "GA",
            "gis_rest": ("https://services2.arcgis.com/nV67H1IJR8GS6SAA/arcgis/rest/services/Current"
                         "_Parcels/FeatureServer/5"),
            "id_fields": ["PARCEL", "PARCEL_1"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13133": {  # Greene — 17,735 parcels (1.76x housing units), edited 2025-09-04
            "county": "Greene", "state": "GA",
            "gis_rest": ("https://services7.arcgis.com/QbbsWI5nIfBp4cMB/arcgis/rest/services/Parcel_"
                         "Regions_w_WinGAP_view/FeatureServer/0"),
            "id_fields": ["Parcel_No", "acctstatus", "Parcel"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13185": {  # Lowndes — 52,543 parcels (1.08x housing units), edited 2026-08-13
            "county": "Lowndes", "state": "GA",
            "gis_rest": ("https://services3.arcgis.com/fYt1jp3hqamxgSvI/arcgis/rest/services/TaxParc"
                         "els_OwnerName/FeatureServer/0"),
            "id_fields": ["PARCEL_NO", "PARCEL"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13187": {  # Lumpkin — 17,741 parcels (1.36x housing units), edited 2025-02-05
            "county": "Lumpkin", "state": "GA",
            "gis_rest": ("https://services6.arcgis.com/BAJNi3EgCdtQ1BCG/arcgis/rest/services/Lumpkin"
                         "_2025Parcels/FeatureServer/0"),
            "id_fields": ["PARCEL_NO", "PARCEL_N_1", "parcel_n_2"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13199": {  # Meriwether — 16,511 parcels (1.75x housing units), edited 2023-06-11
            "county": "Meriwether", "state": "GA",
            "gis_rest": ("https://services9.arcgis.com/Xv8vRekQ4FVHSSIe/arcgis/rest/services/Meriwet"
                         "herParcels/FeatureServer/0"),
            "id_fields": ["Parcel_No", "acctstatus", "Parcel"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13225": {  # Peach — 14,150 parcels (1.18x housing units), edited 2024-04-30
            "county": "Peach", "state": "GA",
            "gis_rest": ("https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/Peach_C"
                         "ounty_Parcels/FeatureServer/0"),
            "id_fields": ["PARCEL_NO"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13287": {  # Turner — 5,714 parcels (1.46x housing units), edited 2026-01-21
            "county": "Turner", "state": "GA",
            "gis_rest": ("https://services5.arcgis.com/HA2thkMWRBDb77XN/arcgis/rest/services/TunerPa"
                         "rcels/FeatureServer/4"),
            "id_fields": ["Parcel_No", "acctstatus", "Parcel"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13289": {  # Twiggs — 7,069 parcels (1.75x housing units), edited 2025-03-20
            "county": "Twiggs", "state": "GA",
            "gis_rest": ("https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/Twiggs_"
                         "County_Parcels/FeatureServer/0"),
            "id_fields": ["PARCEL_NO"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        "13313": {  # Whitfield — 45,924 parcels (1.18x housing units), edited 2026-01-16
            "county": "Whitfield", "state": "GA",
            "gis_rest": ("https://services7.arcgis.com/POtw9JZ8E63Yf33x/arcgis/rest/services/City_of"
                         "_Dalton_WFL1/FeatureServer/7"),
            "id_fields": ["PARCEL_FUL"],
            "clerk_url": GSCCCA,
            "clerk_platform": "unknown",
            "clerk_note": "Georgia statewide GSCCCA real-estate index (all counties).",
        },
        # TODO (follow-up — the sweep found no complete, current, situs-bearing layer for these):
        #   Bartow (13015), Carroll (13045), Columbia (13073), Newton (13217), Walton (13297).
        # TRIED AND REJECTED 2026-08-17 (re-run the scripts if a county republishes):
        #   Rockdale (13247), Decatur (13087), McIntosh (13191), Walker (13295) — a full, current
        #     roll exists but every address-like field holds the owner name / PO box / a bare house
        #     number, so situs_of() cannot produce a street address (see verify_situs_fields.py).
        #   Dooly (13093) — complete roll, but served from a 2020 university course project.
        #   Crisp (13081) — layer last edited 2022-03; past the 4-year freshness cutoff.
        #   Glynn (13127) — "County_Owned_Parcels", 1% of the roll. Jasper (13159) — historic
        #     building survey, 10%. Dawson (13085) — Dawsonville city only, 36%.
        # HARD WALLS (no free situs-bearing public REST — stay on the qPublic/NETROnline link):
        #   Houston (13153, qPublic/Schneider only); Paulding (13223, public layer is parcel-ID-only,
        #   no situs/owner). For the rural 100+ county long tail, a paid API (Regrid/ReportAll) is
        #   the only efficient path to full 159-county coverage.
    })

# ---------------------------------------------------------------------------------------
# Property Appraiser / Tax Assessor site per county — {fips: (county, url)}.
#
# GA had NO appraiser links at all, so "Open County Property Appraiser" (shown on both the
# parcel and appraiser document cards) fell back to the generic NETROnline directory for all
# 159 counties. Most of Georgia publishes its digest through qPublic (Schneider), which is
# per-county, so this closes the gap for 149 of 159.
#
# EVERY url here was fetched and confirmed to return a property-search page that names its own
# county (scripts/verify_appraiser_links.py) — none are pattern-generated. That matters: the
# obvious qpublic.net/ga/<slug>/ guess is wrong often enough to be dangerous (Gwinnett 404s,
# Fulton redirects to its own domain), and probing Ohio's plausible-looking recorder portals
# found landaccess.com now 301ing to a click-tracker spam domain.
#
# A few entries are marked as 403 — those hosts WAF-block datacenter/VPN IPs but open fine in
# a browser, which CLAUDE.md treats as reachable, so they are kept.
# ---------------------------------------------------------------------------------------
#  UNVERIFIED — CONFIRM IN A BROWSER BEFORE RELYING ON THESE !!
# The 10 counties added 2026-08-18 (Banks, Clayton, Columbia, Coweta, DeKalb, Dougherty,
# Douglas, Henry, Lumpkin, Union) run qPublic under Schneider's Application.aspx?App=<County>
# form, NOT the qpublic.net/ga/<slug>/ form the other 149 use — which is exactly why the
# pattern sweep returned 0/10 for them.
#
# These were originally annotated "verified 2026-08-18" on the theory that a real App= slug
# returns 403 while a bogus one returns 500. THAT TEST IS UNSOUND and the claim was withdrawn
# on re-check: qpublic.schneidercorp.com sits behind Cloudflare, and App=BanksCountyGA and
# App=NotARealCountyGA both return an identical 403 "Just a moment..." challenge page. The
# request never reaches Schneider, so NOTHING about slug validity can be inferred from it —
# unlike the other 149, which were each fetched and confirmed to name their own county.
#
# They are kept because the App=<County>CountyGA form is Schneider's documented convention and
# each was attributed to its county by search, but they rest on that alone. Open each in a
# browser (where Cloudflare passes) and confirm the page names the right county; if one is
# wrong, delete the line — the county then falls back to the NETROnline directory, which is
# where it sat before.
APPRAISER: dict[str, tuple[str, str]] = {
    "13001": ("Appling", "https://qpublic.net/ga/appling/"),
    "13003": ("Atkinson", "https://qpublic.net/ga/atkinson/"),
    "13005": ("Bacon", "https://qpublic.net/ga/bacon/"),
    "13007": ("Baker", "https://qpublic.net/ga/baker/"),
    "13009": ("Baldwin", "https://qpublic.net/ga/baldwin/"),
    "13011": ("Banks", "https://qpublic.schneidercorp.com/Application.aspx?App=BanksCountyGA&Layer=Parcels&PageType=Search"),  # UNVERIFIED — Cloudflare; check in a browser
    "13013": ("Barrow", "https://barrowassessor.org/"),
    "13015": ("Bartow", "https://qpublic.net/ga/bartow/"),
    "13017": ("Ben Hill", "https://qpublic.net/ga/benhill/"),
    "13019": ("Berrien", "https://qpublic.net/ga/berrien/"),
    "13021": ("Bibb", "https://qpublic.net/ga/bibb/"),
    "13023": ("Bleckley", "https://qpublic.net/ga/bleckley/"),
    "13025": ("Brantley", "https://qpublic.net/ga/brantley/"),
    "13027": ("Brooks", "https://qpublic.net/ga/brooks/"),
    "13029": ("Bryan", "https://beacon.schneidercorp.com/Application.aspx?AppID=639&LayerID=11303&PageTypeID=2&PageID=4634"),
    "13031": ("Bulloch", "https://qpublic.net/ga/bulloch/"),
    "13033": ("Burke", "https://qpublic.net/ga/burke/"),
    "13035": ("Butts", "https://qpublic.net/ga/butts/"),
    "13037": ("Calhoun", "https://qpublic.net/ga/calhoun/"),
    "13039": ("Camden", "https://camdencountymaps.com/"),
    "13043": ("Candler", "https://qpublic.net/ga/candler/"),
    "13045": ("Carroll", "https://qpublic.net/ga/carroll/"),
    "13047": ("Catoosa", "https://catoosaassessor.com/"),
    "13049": ("Charlton", "https://qpublic.net/ga/charlton/"),
    "13051": ("Chatham", "https://www.chathamcountyga.gov/"),
    "13053": ("Chattahoochee", "https://qpublic.net/ga/chattahoochee/"),
    "13055": ("Chattooga", "https://qpublic.net/ga/chattooga/"),
    "13057": ("Cherokee", "https://qpublic.net/ga/cherokee/"),
    "13059": ("Clarke", "https://qpublic.net/ga/clarke/"),
    "13061": ("Clay", "https://qpublic.net/ga/clay/"),
    "13063": ("Clayton", "https://qpublic.schneidercorp.com/Application.aspx?App=ClaytonCountyGA&Layer=Parcels&PageType=Search"),  # UNVERIFIED — Cloudflare; check in a browser
    "13065": ("Clinch", "https://qpublic.net/ga/clinch/"),
    "13067": ("Cobb", "https://www.cobbcounty.gov"),
    "13069": ("Coffee", "https://www.coffeecounty-ga.gov/departments/assessor/index.php"),
    "13071": ("Colquitt", "https://qpublic.net/ga/colquitt/"),
    "13073": ("Columbia", "https://qpublic.schneidercorp.com/Application.aspx?App=ColumbiaCountyGA&Layer=Parcels&PageType=Search"),  # UNVERIFIED — Cloudflare; check in a browser
    "13075": ("Cook", "https://qpublic.net/ga/cook/"),
    "13077": ("Coweta", "https://qpublic.schneidercorp.com/Application.aspx?App=CowetaCountyGA&Layer=Parcels&PageType=Search"),  # UNVERIFIED — Cloudflare; check in a browser
    "13079": ("Crawford", "https://qpublic.net/ga/crawford/"),
    "13081": ("Crisp", "https://qpublic.net/ga/crisp/"),
    "13083": ("Dade", "https://qpublic.net/ga/dade/"),
    "13085": ("Dawson", "https://dawsonassessors.com/"),
    "13087": ("Decatur", "https://qpublic.net/ga/decatur/"),
    "13089": ("DeKalb", "https://qpublic.schneidercorp.com/Application.aspx?App=DekalbCountyGA&Layer=Parcels&PageType=Search"),  # UNVERIFIED — Cloudflare; check in a browser
    "13091": ("Dodge", "https://qpublic.net/ga/dodge/"),
    "13093": ("Dooly", "https://qpublic.net/ga/dooly/"),
    "13095": ("Dougherty", "https://qpublic.schneidercorp.com/Application.aspx?App=DoughertyCountyGA&Layer=Parcels&PageType=Search"),  # UNVERIFIED — Cloudflare; check in a browser
    "13097": ("Douglas", "https://qpublic.schneidercorp.com/Application.aspx?App=DouglasCountyGA&Layer=Parcels&PageType=Search"),  # UNVERIFIED — Cloudflare; check in a browser
    "13099": ("Early", "https://qpublic.net/ga/early/"),
    "13101": ("Echols", "https://qpublic.net/ga/echols/"),
    "13103": ("Effingham", "https://qpublic.net/ga/effingham/"),
    "13105": ("Elbert", "https://qpublic.net/ga/elbert/"),
    "13107": ("Emanuel", "https://qpublic.net/ga/emanuel/"),
    "13109": ("Evans", "https://qpublic.net/ga/evans/"),
    "13111": ("Fannin", "https://qpublic.net/ga/fannin/"),
    "13113": ("Fayette", "https://www.fayettecountyga.gov/"),
    "13115": ("Floyd", "https://qpublic.net/ga/floyd/"),
    "13117": ("Forsyth", "https://qpublic.net/ga/forsyth/"),
    "13119": ("Franklin", "https://qpublic.net/ga/franklin/"),
    "13121": ("Fulton", "https://www.fultoncountyga.gov/"),
    "13123": ("Gilmer", "https://gilmerassessors.com/"),
    "13125": ("Glascock", "https://qpublic.net/ga/glascock/"),
    "13127": ("Glynn", "https://qpublic.net/ga/glynn/"),
    "13129": ("Gordon", "https://gordonassessors.com/"),
    "13131": ("Grady", "https://qpublic.net/ga/grady/"),
    "13133": ("Greene", "https://qpublic.net/ga/greene/"),
    "13135": ("Gwinnett", "https://www.gwinnettcounty.com/home"),
    "13137": ("Habersham", "https://qpublic.net/ga/habersham/"),
    "13139": ("Hall", "https://qpublic.net/ga/hall/"),
    "13141": ("Hancock", "https://qpublic.net/ga/hancock/"),
    "13143": ("Haralson", "https://qpublic.net/ga/haralson/"),
    "13145": ("Harris", "https://qpublic.net/ga/harris/"),
    "13147": ("Hart", "https://qpublic.net/ga/hart/"),
    "13149": ("Heard", "https://qpublic.net/ga/heard/"),
    "13151": ("Henry", "https://qpublic.schneidercorp.com/Application.aspx?App=HenryCountyGA&Layer=Parcels&PageType=Search"),  # UNVERIFIED — Cloudflare; check in a browser
    "13153": ("Houston", "https://qpublic.net/ga/houston/"),
    "13155": ("Irwin", "https://qpublic.net/ga/irwin/"),
    "13157": ("Jackson", "https://qpublic.net/ga/jackson/"),
    "13159": ("Jasper", "https://qpublic.net/ga/jasper/"),
    "13161": ("Jeff Davis", "https://qpublic.net/ga/jeffdavis/"),
    "13163": ("Jefferson", "https://qpublic.net/ga/jefferson/"),
    "13165": ("Jenkins", "https://qpublic.net/ga/jenkins/"),
    "13167": ("Johnson", "https://qpublic.net/ga/johnson/"),
    "13169": ("Jones", "https://jonescountygataxassessor.com/"),
    "13171": ("Lamar", "https://qpublic.net/ga/lamar/"),
    "13173": ("Lanier", "https://qpublic.net/ga/lanier/"),
    "13175": ("Laurens", "https://qpublic.net/ga/laurens/"),
    "13177": ("Lee", "https://qpublic.net/ga/lee/"),
    "13179": ("Liberty", "https://qpublic.net/ga/liberty/"),
    "13181": ("Lincoln", "https://qpublic.net/ga/lincoln/"),
    "13183": ("Long", "https://qpublic.net/ga/long/"),
    "13185": ("Lowndes", "https://qpublic.net/ga/lowndes/"),
    "13187": ("Lumpkin", "https://qpublic.schneidercorp.com/Application.aspx?App=LumpkinCountyGA&Layer=Parcels&PageType=Search"),  # UNVERIFIED — Cloudflare; check in a browser
    "13189": ("McDuffie", "https://qpublic.net/ga/mcduffie/"),
    "13191": ("McIntosh", "https://mcintoshassessor.com/"),
    "13193": ("Macon", "https://qpublic.net/ga/macon/"),
    "13195": ("Madison", "https://qpublic.net/ga/madison/"),
    "13197": ("Marion", "https://qpublic.net/ga/marion/"),
    "13199": ("Meriwether", "https://qpublic.net/ga/meriwether/"),
    "13201": ("Miller", "https://qpublic.net/ga/miller/"),
    "13205": ("Mitchell", "https://qpublic.net/ga/mitchell/"),
    "13207": ("Monroe", "https://qpublic.net/ga/monroe/"),
    "13209": ("Montgomery", "https://qpublic.net/ga/montgomery/"),
    "13211": ("Morgan", "https://qpublic.net/ga/morgan/"),
    "13213": ("Murray", "https://qpublic.net/ga/murray/"),
    "13215": ("Muscogee", "https://qpublic.schneidercorp.com/Application.aspx?App=MuscogeeCountyGA&PageType=Search"),
    "13217": ("Newton", "https://qpublic.net/ga/newton/"),
    "13219": ("Oconee", "https://qpublic.net/ga/oconee/"),
    "13221": ("Oglethorpe", "https://qpublic.net/ga/oglethorpe/"),
    "13223": ("Paulding", "https://www.paulding.gov/252/Board-of-Assessors/"),
    "13225": ("Peach", "https://qpublic.net/ga/peach/"),
    "13227": ("Pickens", "https://qpublic.net/ga/pickens/"),
    "13229": ("Pierce", "https://qpublic.net/ga/pierce/"),
    "13231": ("Pike", "https://qpublic.net/ga/pike/"),
    "13233": ("Polk", "https://qpublic.net/ga/polk/"),
    "13235": ("Pulaski", "https://qpublic.net/ga/pulaski/"),
    "13237": ("Putnam", "https://qpublic.net/ga/putnam/"),
    "13239": ("Quitman", "https://qpublic.net/ga/quitman/"),
    "13241": ("Rabun", "https://qpublic.net/ga/rabun/"),
    "13243": ("Randolph", "https://qpublic.net/ga/randolph/"),
    "13245": ("Richmond", "https://augustarichmondtaxassessor.com/"),
    "13247": ("Rockdale", "https://qpublic.net/ga/rockdale/"),
    "13249": ("Schley", "https://qpublic.net/ga/schley/"),
    "13251": ("Screven", "https://qpublic.net/ga/screven/"),
    "13253": ("Seminole", "https://qpublic.net/ga/seminole/"),
    "13255": ("Spalding", "https://qpublic.net/ga/spalding/"),
    "13257": ("Stephens", "https://qpublic.net/ga/stephens/"),
    "13259": ("Stewart", "https://qpublic.net/ga/stewart/"),
    "13261": ("Sumter", "https://sumterassessors.com/"),
    "13263": ("Talbot", "https://qpublic.net/ga/talbot/"),
    "13265": ("Taliaferro", "https://qpublic.net/ga/taliaferro/"),
    "13267": ("Tattnall", "https://qpublic.net/ga/tattnall/"),
    "13269": ("Taylor", "https://qpublic.net/ga/taylor/"),
    "13271": ("Telfair", "https://qpublic.net/ga/telfair/"),
    "13273": ("Terrell", "https://qpublic.net/ga/terrell/"),
    "13275": ("Thomas", "https://qpublic.net/ga/thomas/"),
    "13277": ("Tift", "https://qpublic.net/ga/tift/"),
    "13279": ("Toombs", "https://qpublic.net/ga/toombs/"),
    "13281": ("Towns", "https://qpublic.net/ga/towns/"),
    "13283": ("Treutlen", "https://qpublic.net/ga/treutlen/"),
    "13285": ("Troup", "https://qpublic.net/ga/troup/"),
    "13287": ("Turner", "https://qpublic.net/ga/turner/"),
    "13289": ("Twiggs", "https://qpublic.net/ga/twiggs/"),
    "13291": ("Union", "https://qpublic.schneidercorp.com/Application.aspx?App=UnionCountyGA&Layer=Parcels&PageType=Search"),  # UNVERIFIED — Cloudflare; check in a browser
    "13293": ("Upson", "https://qpublic.net/ga/upson/"),
    "13295": ("Walker", "https://qpublic.net/ga/walker/"),
    "13297": ("Walton", "https://qpublic.net/ga/walton/"),
    "13299": ("Ware", "https://qpublic.net/ga/ware/"),
    "13301": ("Warren", "https://qpublic.net/ga/warren/"),
    "13303": ("Washington", "https://qpublic.net/ga/washington/"),
    "13305": ("Wayne", "https://qpublic.net/ga/wayne/"),
    "13307": ("Webster", "https://qpublic.net/ga/webster/"),
    "13309": ("Wheeler", "https://qpublic.net/ga/wheeler/"),
    "13311": ("White", "https://qpublic.net/ga/white/"),
    "13313": ("Whitfield", "https://qpublic.net/ga/whitfield/"),
    "13315": ("Wilcox", "https://qpublic.net/ga/wilcox/"),
    "13317": ("Wilkes", "https://qpublic.net/ga/wilkes/"),
    "13319": ("Wilkinson", "https://qpublic.net/ga/wilkinson/"),
    "13321": ("Worth", "https://qpublic.net/ga/worth/"),
}

# Fold the appraiser links into COUNTIES so they reach REGISTRY. Counties with no parcel entry
# get an appraiser-only one — enough for the link, and `county`/`state` keep it debuggable.
for _fips, (_name, _url) in APPRAISER.items():
    COUNTIES.setdefault(_fips, {"county": _name, "state": "GA",
                                "clerk_platform": "unknown"})["appraiser_url"] = _url




_fill_all_counties()