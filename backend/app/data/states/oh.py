"""OH — parcel services (one module per state; edit here to debug OH).

Ohio has a genuine statewide parcel layer (ODNR, all 88 counties) used as the default PARCEL
below — but it carries only parcel PIN + (patchy) owner, with NO situs address. So address->parcel
search for the metros needs county layers that DO carry a situs; those are wired in COUNTIES,
biggest-first. A county with no entry still resolves parcels via the statewide ODNR layer (by PIN)
and gets a records link via the nationwide NETROnline fallback.

DEEDS: Ohio records deeds county-by-county through 88 separate County Recorders — there is NO
statewide index like Georgia's GSCCCA — so there is deliberately no STATE-level DEED_LINK here.
Verified per-county Recorder links live in RECORDER at the bottom of this file (20 of 88 so
far); the rest still fall back to the NETROnline directory. AUDITOR does the same for property
(55 of 88) — in Ohio the Auditor is the Property Appraiser equivalent.

COVERAGE (2026-08-18): 33 of 88 counties have a situs-bearing parcel endpoint.
  * The first 8 (Franklin -> Lake) were verified 2026-08-13 via scripts/verify_oh_endpoints.py.
  * The next 25 came from the automated sweep — see the header on that block for the four
    gates each had to clear.
A county with no entry still resolves parcels by PIN via the statewide ODNR layer; only
address->parcel search needs the county layer, because ODNR carries no situs.

Re-run the scripts to refresh or extend: they are additive (already-wired counties are skipped)
and every rejection is recorded at the bottom of COUNTIES with the reason.
"""
STATE = "OH"
PARCEL = {
    "url": ("https://utility.arcgis.com/usrsvcs/servers/213022e8a0644d62a1f03031202039ff/"
            "rest/services/Hosted/Statewide_Parcels_ODNR_WebMerc/FeatureServer/10"),
    "kind": "featureserver",
    "label": "Ohio Statewide Parcels (ODNR)",
    "id_fields": ["statewide_pin", "pin"],
    # No situs on this layer, so it answers Parcel-ID lookups but NOT address->parcel search.
    # geography._annotate reads this so the county dropdown doesn't advertise address search
    # for the counties that only have the statewide fallback.
    "id_only": True,
}
# No statewide deed index in Ohio (88 county Recorders). DEED_LINK intentionally omitted so the
# loader leaves OH counties on the NETROnline records fallback until per-county Recorder links
# are verified and added.

COUNTIES = {
    "39049": {  # Franklin — largest OH county (~1.32M), city of Columbus
        "county": "Franklin", "state": "OH",
        # Official Franklin County GIS "Tax Parcel" MapServer layer (SITEADDRESS + parcel id).
        "gis_rest": ("https://gis.franklincountyohio.gov/hosting/rest/services/"
                     "ParcelFeatures/Parcel_Features/MapServer/0"),
        "id_fields": ["PARCELID", "LOWPARCELID"],
        "clerk_platform": "unknown",
    },
    "39061": {  # Hamilton — ~830k, city of Cincinnati
        "county": "Hamilton", "state": "OH",
        # Hamilton County Board-of-Revision parcel polygons (Property_Address + PARCELID). NOTE:
        # this is a dated snapshot service (…_BOR_20241022); if it is replaced, re-run the verify
        # script to pick up the current CAGIS/auditor parcel service.
        "gis_rest": ("https://services8.arcgis.com/YU1yCuZZBuqsMM2h/arcgis/rest/services/"
                     "Parcel_Poly_BOR_20241022/FeatureServer/0"),
        "id_fields": ["PARCELID", "PARCEL", "Auditor_Property_ID"],
        "clerk_platform": "unknown",
    },
    "39153": {  # Summit — ~540k, city of Akron
        "county": "Summit", "state": "OH",
        # Summit County GIS AGOL public TaxParcels (SITEADDRESS + parcel id). Chose the "_public"
        # service over the dashboard/viewer/dated-snapshot mirrors on the same org.
        "gis_rest": ("https://services3.arcgis.com/3Ukh5HzAdI6WZ3KP/arcgis/rest/services/"
                     "TaxParcels_public/FeatureServer/0"),
        "id_fields": ["LOWPARCELID", "PARCELID"],
        "clerk_platform": "unknown",
    },
    "39095": {  # Lucas — ~430k, city of Toledo
        "county": "Lucas", "state": "OH",
        # Lucas County AREIS parcels (property_address full "###, TOLEDO OH #####" + parcel_code).
        "gis_rest": ("https://services3.arcgis.com/T8dczfwPixv79EgZ/arcgis/rest/services/"
                     "Parcels_General_Land_Use_Classification_view/FeatureServer/0"),
        "id_fields": ["parcel_code"],
        "clerk_platform": "unknown",
    },
    "39151": {  # Stark — ~375k, city of Canton
        "county": "Stark", "state": "OH",
        # Stark County Auditor parcels (SITE_ADDRESS + PIN). Federated/proxied endpoint
        # (utility.arcgis.com/usrsvcs/...) like ODNR; if the proxy id rotates, re-verify.
        "gis_rest": ("https://utility.arcgis.com/usrsvcs/servers/"
                     "067a37ee416e4d11bc23dd1446ad30ba/rest/services/Auditor/"
                     "StarkCountyParcels/FeatureServer/0"),
        "id_fields": ["PIN"],
        "clerk_platform": "unknown",
    },
    "39017": {  # Butler — ~390k, Cincinnati metro (Hamilton, OH)
        "county": "Butler", "state": "OH",
        # Butler County parcels (LOCATION situs + Butler PIN/OPINOLD schema). NOTE: currently served
        # from a "Draft Map" web feature layer; re-point to Butler's canonical auditor service when
        # confirmed. Resolver falls back to statewide ODNR if this ever 404s.
        "gis_rest": ("https://services3.arcgis.com/RFsrKHehR4N08ybb/arcgis/rest/services/"
                     "LSD_Draft_Map_WFL1/FeatureServer/3"),
        "id_fields": ["PIN", "OPINOLD", "RID_PARCEL"],
        "clerk_platform": "unknown",
    },
    "39093": {  # Lorain — ~315k, Elyria / Lorain (Cleveland metro)
        "county": "Lorain", "state": "OH",
        # Lorain County 2025 Ownership Parcels public view (SITEADDRESS full + PARCELID/IMAGEPIN).
        "gis_rest": ("https://services1.arcgis.com/vGBb7WYV10mOJRNM/arcgis/rest/services/"
                     "OwnershipParcels_2025_Public_View/FeatureServer/1"),
        "id_fields": ["PARCELID", "IMAGEPIN"],
        "clerk_platform": "unknown",
    },
    "39085": {  # Lake — ~230k, Painesville / Mentor (Cleveland metro)
        "county": "Lake", "state": "OH",
        # Official Lake County GIS shared parcels (G_FULLADDRESS + PIN).
        "gis_rest": ("https://gis.lakecountyohio.gov/arcgis/rest/services/Sharing/"
                     "LCGIS_SHARE_2023/FeatureServer/0"),
        "id_fields": ["PIN", "PIN_NODASH"],
        "clerk_platform": "unknown",
    },
    # ---- Added 2026-08-17 by the automated sweep (scripts/discover_state_parcels.py ->
    #      audit_parcel_candidates.py -> verify_situs_fields.py). Four gates cleared:
    #      point-queryable with a situs; parcels returned across the WHOLE county, not just
    #      the county seat (this is what rejects city-only layers like Columbus's); feature
    #      count consistent with a complete roll vs Census housing units; and the app's own
    #      situs_of() returning real street addresses on sampled parcels. ----
    "39007": {  # Ashtabula — 74,565 parcels (1.61x housing units), edited 2025-03-19
        "county": "Ashtabula", "state": "OH",
        "gis_rest": ("https://services3.arcgis.com/LbREO35fKGJZptlq/arcgis/rest/services/Integri"
                     "ty_Parcels/FeatureServer/9"),
        "id_fields": ["PIN", "PIN_NO_DASHES"],
        # situs 98% clean, e.g. '120 GARDEN ST'
        "clerk_platform": "unknown",
    },
    "39019": {  # Carroll — 28,656 parcels (2.14x housing units), edited 2026-08-15
        "county": "Carroll", "state": "OH",
        "gis_rest": ("https://services8.arcgis.com/dZSJY7MSQPhysZUz/arcgis/rest/services/Carroll"
                     "_Parcels/FeatureServer/0"),
        "id_fields": ["PIN", "Parcel_Number", "Property_ID"],
        # situs 100% clean, e.g. '3211 ARBOR RD NE'
        "clerk_platform": "unknown",
    },
    "39025": {  # Clermont — 90,188 parcels (1.04x housing units), edited no edit date published
        "county": "Clermont", "state": "OH",
        "gis_rest": ("https://services1.arcgis.com/hwQMmmEzVzbTfv5U/arcgis/rest/services/Clermon"
                     "t_Parcels/FeatureServer/0"),
        "id_fields": ["PIN"],
        # situs 81% clean, e.g. 'RAILROAD AV'
        "clerk_platform": "unknown",
    },
    "39027": {  # Clinton — 26,997 parcels (1.51x housing units), edited 2024-06-03
        "county": "Clinton", "state": "OH",
        "gis_rest": ("https://services1.arcgis.com/tAhcHWpOD9ygNPbJ/arcgis/rest/services/Site_Pl"
                     "an_Parcels_2022/FeatureServer/3"),
        "id_fields": ["PARCELID", "ParcelID_1", "PIN"],
        # situs 100% clean, e.g. 'SR 380'
        "clerk_platform": "unknown",
    },
    "39029": {  # Columbiana — 74,920 parcels (1.63x housing units), edited 2026-08-14
        "county": "Columbiana", "state": "OH",
        "gis_rest": ("https://services8.arcgis.com/234WKrCI77bh5yOY/arcgis/rest/services/Parcels"
                     "_Public/FeatureServer/0"),
        "id_fields": ["ParcelNumber"],
        # situs 95% clean, e.g. '136 SECOND ST'
        "clerk_platform": "unknown",
    },
    "39043": {  # Erie — 46,797 parcels (1.22x housing units), edited no edit date published
        "county": "Erie", "state": "OH",
        "gis_rest": ("https://arcgis.eriecounty.oh.gov/arcgisdev/rest/services/WMAS/Parcels/MapS"
                     "erver/0"),
        "id_fields": ["Map_Number", "Parcel_Number", "Parcel_Number_No_Dash"],
        # situs 86% clean, e.g. '12902 COLLINS BERLIN HEIGHTS OH 44814'
        "clerk_platform": "unknown",
    },
    "39047": {  # Fayette — 18,531 parcels (1.46x housing units), edited 2026-08-13
        "county": "Fayette", "state": "OH",
        "gis_rest": ("https://services8.arcgis.com/CJpiu5T88EYxY793/arcgis/rest/services/Fayette"
                     "_County_Ohio_GIS_Tax_Parcels/FeatureServer/0"),
        "id_fields": ["Parcel_ID", "Parcel_No1", "Parcel_N_1"],
        # situs 100% clean, e.g. 'ANDERSON RD SW'
        "clerk_platform": "unknown",
    },
    "39055": {  # Geauga — 51,006 parcels (1.36x housing units), edited no edit date published
        "county": "Geauga", "state": "OH",
        "gis_rest": ("https://gcgis.geauga.oh.gov/arcgis/rest/services/2030___2026/FeatureServer"
                     "/0"),
        "id_fields": ["PARCEL_ID2", "NumParcels"],
        # situs 100% clean, e.g. '9809 WASHINGTON ST'
        "clerk_platform": "unknown",
    },
    "39059": {  # Guernsey — 40,653 parcels (2.14x housing units), edited 2024-08-06
        "county": "Guernsey", "state": "OH",
        "gis_rest": ("https://services8.arcgis.com/EtYD1cRq8Hkljjf7/arcgis/rest/services/Guernse"
                     "y_County_WFL1/FeatureServer/12"),
        "id_fields": ["Parcel", "Parcel2"],
        # situs 100% clean, e.g. '64900 REDBUD RD CAMBRIDGE OH 43725'
        "clerk_platform": "unknown",
    },
    "39063": {  # Hancock — 38,740 parcels (1.15x housing units), edited 2026-02-23
        "county": "Hancock", "state": "OH",
        "gis_rest": ("https://services1.arcgis.com/lAWlC1VwZYAIzeQJ/arcgis/rest/services/Hancock"
                     "_Parcels/FeatureServer/1"),
        "id_fields": ["MAPNUMBER", "MAPNUMBER0", "PARCEL"],
        # situs 100% clean, e.g. '0 COUNTY RD 212 FINDLAY OH 45840'
        "clerk_platform": "unknown",
    },
    "39069": {  # Henry — 19,824 parcels (1.65x housing units), edited 2026-07-28
        "county": "Henry", "state": "OH",
        "gis_rest": ("https://services.arcgis.com/osmyvTbXDC07yFxn/arcgis/rest/services/HenryPar"
                     "cels/FeatureServer/0"),
        "id_fields": ["MAPNUM", "PARCEL"],
        # situs 100% clean, e.g. 'V-586 COUNTY ROAD 20'
        "clerk_platform": "unknown",
    },
    "39075": {  # Holmes — 28,747 parcels (1.97x housing units), edited 2026-08-17
        "county": "Holmes", "state": "OH",
        "gis_rest": ("https://services6.arcgis.com/JuJ3otBHQoYlrmJI/arcgis/rest/services/parcels"
                     "_cama/FeatureServer/0"),
        "id_fields": ["GISPIN", "Parcel_Number"],
        # situs 97% clean, e.g. 'SR 39'
        "clerk_platform": "unknown",
    },
    "39077": {  # Huron — 40,309 parcels (1.58x housing units), edited 2025-06-23
        "county": "Huron", "state": "OH",
        "gis_rest": ("https://services5.arcgis.com/ZEuF9401wMEdHLM6/arcgis/rest/services/HuronCo"
                     "untyParcels/FeatureServer/0"),
        "id_fields": ["PARCELID", "Parcel"],
        # situs 100% clean, e.g. '473 TOWN LINE RD 151 NORWALK OH 44857 44'
        "clerk_platform": "unknown",
    },
    "39089": {  # Licking — 83,804 parcels (1.15x housing units), edited no edit date published
        "county": "Licking", "state": "OH",
        "gis_rest": ("https://gis.lickingcounty.gov/server/rest/services/Auditor/Parcels/Feature"
                     "Server/0"),
        "id_fields": ["EpinCount", "Parcel", "T1Parcels"],
        # situs 100% clean, e.g. 'APPLETON RD NW'
        "clerk_platform": "unknown",
    },
    "39103": {  # Medina — 83,362 parcels (1.11x housing units), edited 2024-12-30
        "county": "Medina", "state": "OH",
        "gis_rest": ("https://services5.arcgis.com/m37BbrYBtVXq1nb8/arcgis/rest/services/Medina_"
                     "Board_of_Revision_Cases_v2/FeatureServer/0"),
        "id_fields": ["ParcelPIN"],
        # situs 100% clean, e.g. '33 MARKS RD'
        "clerk_platform": "unknown",
    },
    "39109": {  # Miami — 55,276 parcels (1.18x housing units), edited 2026-08-15
        "county": "Miami", "state": "OH",
        "gis_rest": ("https://services3.arcgis.com/wCWf4EGMg4PzHwzA/arcgis/rest/services/parcel_"
                     "joined/FeatureServer/0"),
        "id_fields": ["PARCEL", "Parcel2"],
        # situs 100% clean, e.g. '7595 STALEY RD E'
        "clerk_platform": "unknown",
    },
    "39111": {  # Monroe — 17,564 parcels (2.46x housing units), edited 2026-08-12
        "county": "Monroe", "state": "OH",
        "gis_rest": ("https://services8.arcgis.com/ToWOUVqNUhbTXzVc/arcgis/rest/services/Parcels"
                     "/FeatureServer/2"),
        "id_fields": ["APN", "FORMAL_APN", "REM_ACCT_NUM"],
        # situs 72% clean, e.g. '41611 TOWNSHIP ROAD 289 OH'
        "clerk_platform": "unknown",
    },
    "39115": {  # Morgan — 19,134 parcels (2.65x housing units), edited 2026-08-07
        "county": "Morgan", "state": "OH",
        "gis_rest": ("https://services8.arcgis.com/cYuOLPdETvKbspkC/arcgis/rest/services/Morgan_"
                     "Parcels/FeatureServer/0"),
        "id_fields": ["PIN", "ParcelNumb", "Parcel_Num"],
        # situs 83% clean, e.g. '3915 S ELLIOTT RD'
        "clerk_platform": "unknown",
    },
    "39117": {  # Morrow — 28,444 parcels (1.97x housing units), edited 2026-01-31
        "county": "Morrow", "state": "OH",
        "gis_rest": ("https://services9.arcgis.com/fb2xHTkLEUUJA1y5/arcgis/rest/services/MorrowT"
                     "axParcels_withTaxData/FeatureServer/0"),
        "id_fields": ["PIN", "PIN_NoDash"],
        # situs 98% clean, e.g. 'CO RD 166 OH'
        "clerk_platform": "unknown",
    },
    "39119": {  # Muskingum — 57,671 parcels (1.5x housing units), edited 2026-08-10
        "county": "Muskingum", "state": "OH",
        "gis_rest": ("https://services5.arcgis.com/N1ybEAKiuuUIL8Mz/arcgis/rest/services/Parcel/"
                     "FeatureServer/0"),
        "id_fields": ["MAP_NUM", "ParcelNumb", "PARCELNUM"],
        # situs 98% clean, e.g. '1058 BRANDYWINE BLVD'
        "clerk_platform": "unknown",
    },
    "39129": {  # Pickaway — 31,012 parcels (1.39x housing units), edited 2024-03-08
        "county": "Pickaway", "state": "OH",
        "gis_rest": ("https://services.arcgis.com/Kky1VmxJleu73HxO/arcgis/rest/services/Pickaway"
                     "_County_School_Districts_WFL1/FeatureServer/2"),
        "id_fields": ["Parcel2"],
        # situs 100% clean, e.g. '30687 S R 180'
        "clerk_platform": "unknown",
    },
    "39149": {  # Shelby — 31,797 parcels (1.59x housing units), edited 2026-08-17
        "county": "Shelby", "state": "OH",
        "gis_rest": ("https://services6.arcgis.com/fzPZZJiNVtryYcsC/arcgis/rest/services/Parcels"
                     "/FeatureServer/0"),
        "id_fields": ["PIN_No_Dash", "PIN", "Parcel_Number"],
        # situs 100% clean, e.g. 'SHELBY RD'
        "clerk_platform": "unknown",
    },
    "39157": {  # Tuscarawas — 60,765 parcels (1.49x housing units), edited 2026-08-07
        "county": "Tuscarawas", "state": "OH",
        "gis_rest": ("https://services9.arcgis.com/9TS9JAXFNg3gQQuK/arcgis/rest/services/Tuscara"
                     "was_County_Parcels/FeatureServer/0"),
        "id_fields": ["PARCEL_ID", "Parcel_Num", "Parcel_N_1"],
        # situs 100% clean, e.g. '103 SW RAGERSVILLE RD'
        "clerk_platform": "unknown",
    },
    "39159": {  # Union — 36,768 parcels (1.59x housing units), edited no edit date published
        "county": "Union", "state": "OH",
        "gis_rest": ("https://www7.co.union.oh.us/unioncountyohio/rest/services/parcel/MapServer"
                     "/0"),
        "id_fields": ["ParcelClass", "PARCELTYPE"],
        # situs 92% clean, e.g. 'HONDA PARKWAY'
        "clerk_platform": "unknown",
    },
    "39169": {  # Wayne — 57,642 parcels (1.24x housing units), edited 2025-01-13
        "county": "Wayne", "state": "OH",
        "gis_rest": ("https://services6.arcgis.com/WiOy9S7NUTWyXUe4/arcgis/rest/services/WayneCo"
                     "_Parcels/FeatureServer/0"),
        "id_fields": ["Parcel", "Parcel2"],
        # situs 100% clean, e.g. '7130 CEDAR VALLEY RD WEST SALEM OH 44287'
        "clerk_platform": "unknown",
    },
    # ---- Left on statewide ODNR + NETROnline fallback (follow-up: each needs a verified
    #      situs-bearing county parcel REST; AGOL search did not surface one) ----
    #   Cuyahoga (39035, Cleveland ~1.26M) — parcels on a county-hosted server, not AGOL-indexed.
    #   Montgomery (39113, Dayton ~535k) — MCAuditor county-hosted service.
    #   Mahoning (39099, Youngstown), Greene (39057), Portage (39133).
    #   Delaware (39041) — only live match was the City of Columbus layer (not the county); rejected.
    # TRIED AND REJECTED 2026-08-17 by the sweep (re-run the scripts if a county republishes):
    #   Warren (39165) — the ACPF derivative is in fact a complete roll (1.1x housing units), but
    #     it was last edited 2021-04, past the 4-year freshness cutoff. Rejection stands.
    #   Noble (39121), Lawrence (39087), Harrison (39067) — complete rolls last edited 2018-2019.
    #   Logan (39091), Madison (39097) — complete, current rolls, but every address-like field
    #     holds an owner/mailing value, so situs_of() yields no street address.
}

# ---------------------------------------------------------------------------------------
# County Auditor (property) and County Recorder (deeds) portals — {fips: (county, url)}.
#
# Ohio splits what Florida gets from one Clerk across two offices, 88 of each, with no
# statewide index — which is why DEED_LINK is deliberately omitted above and OH counties fell
# back to the NETROnline directory for BOTH documents. These close part of that gap.
#
# Every URL was fetched and confirmed to serve a records page that NAMES ITS OWN COUNTY
# (scripts/verify_county_portals.py). The county-name check is not paranoia: these hostnames
# start life as pattern guesses, and probing Ohio's other plausible recorder portals found
# ohio.uslandrecords.com dead and landaccess.com 301ing to a click-tracker spam domain. A link
# to the wrong county's recorder would be worse than the NETROnline fallback it replaces.
#
# Entries marked 403 answered but refused this IP; per CLAUDE.md that means "opens in a
# browser", so they are kept. Those could not have their body checked for the county name, so
# they rest on the hostname convention alone — re-verify from a browser if one looks wrong.
#
# The remaining counties (33 auditor / 68 recorder) do not follow these hostname conventions
# and still fall back to NETROnline. Extending them means finding each portal individually.
# Already ruled out for those 33: the countyauditor.org / auditor.<county>ohio.gov hostname
# patterns (0/46 — every candidate was a DNS failure) and Schneider Beacon (33 of the 46
# return 500 = no such app). Ohio is genuinely fragmented — Lucas is on iCare, Summit on
# Datalet/propertyaccess.summitoh.net, Ashtabula on auditor.ashtabulacounty.gov/dnn — so the
# rest needs per-county lookup, not another pattern sweep.
# ---------------------------------------------------------------------------------------
AUDITOR: dict[str, tuple[str, str]] = {
    "39001": ("Adams", "https://adamscountyauditor.org/"),
    "39009": ("Athens", "https://www.athenscountyauditor.org/"),  # 403s datacenter IPs; fine in a browser
    "39011": ("Auglaize", "https://auglaizecountyauditor.org/"),
    "39013": ("Belmont", "https://belmontcountyauditor.org/"),
    "39017": ("Butler", "https://butlercountyauditor.org/"),  # 403s datacenter IPs; fine in a browser
    "39021": ("Champaign", "https://auditor.co.champaign.oh.us/"),  # 403s datacenter IPs; fine in a browser
    "39023": ("Clark", "https://clarkcountyauditor.org/"),  # 403s datacenter IPs; fine in a browser
    "39027": ("Clinton", "https://clintoncountyauditor.org/"),
    "39029": ("Columbiana", "https://columbianacountyauditor.org/"),
    "39035": ("Cuyahoga", "https://cuyahogacountyauditor.org/"),
    "39041": ("Delaware", "https://delawarecountyauditor.org/"),
    "39047": ("Fayette", "https://www.fayettecountyauditor.org"),
    "39049": ("Franklin", "https://auditor.franklincountyohio.gov/"),  # 403s datacenter IPs; fine in a browser
    "39057": ("Greene", "https://auditor.greenecountyohio.gov/Search/Name"),
    "39061": ("Hamilton", "https://hamiltoncountyauditor.org/"),
    "39071": ("Highland", "https://highlandcountyauditor.org/"),  # 403s datacenter IPs; fine in a browser
    "39075": ("Holmes", "https://www.holmescountyauditor.org/"),
    "39077": ("Huron", "https://huroncountyauditor.org/"),
    "39079": ("Jackson", "https://jacksoncountyauditor.org/"),  # 403s datacenter IPs; fine in a browser
    "39083": ("Knox", "https://knoxcountyauditor.org/"),
    "39087": ("Lawrence", "https://lawrencecountyauditor.org/"),  # 403s datacenter IPs; fine in a browser
    "39097": ("Madison", "https://auditor.co.madison.oh.us/"),  # 403s datacenter IPs; fine in a browser
    "39105": ("Meigs", "https://meigscountyauditor.org/"),
    "39107": ("Mercer", "https://auditor.mercercountyohio.gov/"),  # 403s datacenter IPs; fine in a browser
    "39115": ("Morgan", "https://www.morgancountyauditor.org"),
    "39117": ("Morrow", "https://auditor.co.morrow.oh.us/"),  # 403s datacenter IPs; fine in a browser
    "39119": ("Muskingum", "https://www.muskingumcountyauditor.org/"),
    "39123": ("Ottawa", "https://auditor.co.ottawa.oh.us/"),
    "39127": ("Perry", "https://auditor.perrycountyohio.gov/"),  # 403s datacenter IPs; fine in a browser
    "39129": ("Pickaway", "https://auditor.pickawaycountyohio.gov/"),  # 403s datacenter IPs; fine in a browser
    "39133": ("Portage", "https://portagecountyauditor.org/"),
    "39135": ("Preble", "https://preblecountyauditor.org/"),
    "39137": ("Putnam", "https://auditor.putnamcountyohio.gov/"),  # 403s datacenter IPs; fine in a browser
    "39141": ("Ross", "https://rosscountyauditor.org/"),
    "39147": ("Seneca", "https://senecacountyauditoroh.gov/"),
    "39151": ("Stark", "https://starkcountyauditor.org/"),
    "39155": ("Trumbull", "https://trumbullcountyauditor.org/"),
    "39157": ("Tuscarawas", "https://tuscarawascountyauditor.org/"),
    "39161": ("Van Wert", "https://auditor.vanwertcountyohio.gov/"),  # 403s datacenter IPs; fine in a browser
    "39163": ("Vinton", "https://vintoncountyauditor.org/"),
    "39165": ("Warren", "https://auditor.warrencountyohio.gov/"),  # 403s datacenter IPs; fine in a browser
    "39169": ("Wayne", "https://waynecountyauditor.org/"),  # 403s datacenter IPs; fine in a browser
    # --- Schneider Beacon (verified 2026-08-18) -------------------------------------------
    # These 13 run their auditor search on Beacon, not a countyauditor.org hostname, which is
    # why the hostname sweep returned 0/46 for them. Each was fetched with curl and returned
    # 200 with its own county named in the body (>=15 times).
    # BEWARE when extending this: a parallel urllib sweep reported 46/46 'hits' here, but every
    # one was a WAF 403, not a real app — re-probed serially with curl, 33 of them return 500
    # (no such Beacon app). Only a 200 whose body names the county counts.
    "39003": ("Allen", "https://beacon.schneidercorp.com/Application.aspx?App=AllenCountyOH&PageType=Search"),
    "39033": ("Crawford", "https://beacon.schneidercorp.com/Application.aspx?App=CrawfordCountyOH&PageType=Search"),
    "39045": ("Fairfield", "https://beacon.schneidercorp.com/Application.aspx?App=FairfieldCountyOH&PageType=Search"),
    "39051": ("Fulton", "https://beacon.schneidercorp.com/Application.aspx?App=FultonCountyOH&PageType=Search"),
    "39053": ("Gallia", "https://beacon.schneidercorp.com/Application.aspx?App=GalliaCountyOH&PageType=Search"),
    "39063": ("Hancock", "https://beacon.schneidercorp.com/Application.aspx?App=HancockCountyOH&PageType=Search"),
    "39065": ("Hardin", "https://beacon.schneidercorp.com/Application.aspx?App=HardinCountyOH&PageType=Search"),
    "39109": ("Miami", "https://beacon.schneidercorp.com/Application.aspx?App=MiamiCountyOH&PageType=Search"),
    "39139": ("Richland", "https://beacon.schneidercorp.com/Application.aspx?App=RichlandCountyOH&PageType=Search"),
    "39143": ("Sandusky", "https://beacon.schneidercorp.com/Application.aspx?App=SanduskyCountyOH&PageType=Search"),
    "39159": ("Union", "https://beacon.schneidercorp.com/Application.aspx?App=UnionCountyOH&PageType=Search"),
    "39173": ("Wood", "https://beacon.schneidercorp.com/Application.aspx?App=WoodCountyOH&PageType=Search"),
    "39175": ("Wyandot", "https://beacon.schneidercorp.com/Application.aspx?App=WyandotCountyOH&PageType=Search"),
}

RECORDER: dict[str, tuple[str, str]] = {
    "39013": ("Belmont", "https://belmontcountyrecorder.org/"),
    "39025": ("Clermont", "https://recorder.clermontcountyohio.gov/"),
    "39049": ("Franklin", "https://www.franklincountyohio.gov/Agency-Directory/Recorder/"),  # 403s datacenter IPs; fine in a browser
    "39055": ("Geauga", "https://recorder.co.geauga.oh.us/"),
    "39057": ("Greene", "https://www.greenecountyohio.gov/473/Recorder"),
    "39061": ("Hamilton", "https://www.hamiltoncountyohio.gov/recorder"),  # 403s datacenter IPs; fine in a browser
    "39065": ("Hardin", "https://hardincountyohio.gov/recorder/"),
    "39067": ("Harrison", "https://www.harrisoncountyohio.gov/recorder"),  # 403s datacenter IPs; fine in a browser
    "39085": ("Lake", "https://www.lakecountyohio.gov/recorder/"),
    "39091": ("Logan", "https://www.logancountyohio.gov/recorder.html"),
    "39101": ("Marion", "https://www.marioncountyohio.gov/recorder"),  # 403s datacenter IPs; fine in a browser
    "39103": ("Medina", "https://recorder.medinacounty.gov/"),
    "39107": ("Mercer", "https://www.mercercountyoh.gov/elected-officials/recorder/"),
    "39117": ("Morrow", "https://www.morrowcountyohio.gov/recorder"),  # 403s datacenter IPs; fine in a browser
    "39141": ("Ross", "https://www.rosscountyohio.gov/recorder/"),
    "39151": ("Stark", "https://www.starkcountyohio.gov/government/offices/recorder/index.php"),
    "39159": ("Union", "https://www.unioncountyohio.gov/recorder"),  # 403s datacenter IPs; fine in a browser
    "39161": ("Van Wert", "https://www.vanwertcountyohio.gov/recorder"),  # 403s datacenter IPs; fine in a browser
    "39165": ("Warren", "https://recorder.warrencountyohio.gov/"),  # 403s datacenter IPs; fine in a browser
    "39173": ("Wood", "https://recorder.co.wood.oh.us/"),
}

# Fold both into COUNTIES so they reach REGISTRY: the Auditor is Ohio's property-appraiser
# equivalent, the Recorder is its deed/plat source (services/clerk.py reads clerk_url).
for _fips, (_name, _url) in AUDITOR.items():
    COUNTIES.setdefault(_fips, {"county": _name, "state": "OH",
                                "clerk_platform": "unknown"})["appraiser_url"] = _url
for _fips, (_name, _url) in RECORDER.items():
    COUNTIES.setdefault(_fips, {"county": _name, "state": "OH",
                                "clerk_platform": "unknown"})["clerk_url"] = _url
