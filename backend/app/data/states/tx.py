"""TX — statewide parcel service + per-county records links (edit here to debug TX).

Texas is the **3rd order-volume state (~7.1%)**, behind FL (51.7%) and GA (33.8%).

PARCELS — statewide, all 254 counties. The state StratMap program (TxGIO, formerly TNRIS)
publishes a statewide parcel FeatureServer with owner, situs, legal description and area.
NOTE the service NAME still says "2019", but the layer it serves is
`Stratmap25_landparcels_48` — the **2025** vintage, 14,333,926 parcels (verified 2026-08-20),
and the AGOL item is titled "2025 Texas Parcels StratMap". So the data is current; only the
URL is legacy. Don't "fix" the URL to a 2025-named service — this is the live one.
The layer carries both SITUS_ADDR and MAIL_ADDR; situs_of prefers the "situs" alias and skips
"mail", so no situs_exclude is needed.
Spot-checked 2026-08-20: Harris, Dallas and Comal each return the right parcel with an exact
situs + owner match. Known rough edge (not new, and correctly FLAGGED rather than wrong): in
dense downtown blocks the geocoder's street-centerline point can miss every polygon, and the
40 m buffer then returns up to the 400-record cap, so no candidate matches the house number —
the result comes back with address_match=False for the user to verify (e.g. 1000 Guadalupe St,
Austin picks up a pipeline-easement parcel).

DEEDS/PLATS — Texas has no statewide index (records live with each County Clerk), so this is
county-by-county. The useful finding is a PLATFORM BATCH: **18 of the top 38 counties run
Kofile "PublicSearch" at `<county>.tx.publicsearch.us`**, all serving the identical
"Official Record Search" app. That is one scraper adapter for a large share of TX order
volume — the same leverage the acclaim/landmark adapters give in FL. Counties not on it
resolved to their own in-house portal. Verified live 2026-08-20; counties whose subdomain
does not exist returned DNS failures (a clean negative), not false positives.

APPRAISER/TAX — the county CAD (Central Appraisal District). All 40 below were verified by
fetching the live site and requiring it to identify as that county's appraisal district.
This matters because the obvious `<county>cad.com` guesses are frequently DOMAIN SQUATTERS:
bellcad.com, webbcad.com and mclennancad.com all serve "Coming Soon" parking pages, and
cameroncad.com / ectorcad(.com) / milamcad.org redirect into ad networks. The real districts
are the .org hosts below.
"""
STATE = "TX"
PARCEL = {
    "url": ("https://services1.arcgis.com/1mtXwieMId59thmg/arcgis/rest/services/"
            "2019_Texas_Parcels_StratMap/FeatureServer/0"),
    "kind": "featureserver",
    "label": "Texas Parcels StratMap 2025 (TxGIO)",
    "id_fields": ["Prop_ID"],   # Parcel-ID search column for this layer
}

# Kofile PublicSearch — one platform, many counties: https://<slug>.tx.publicsearch.us/
_PS = "https://{}.tx.publicsearch.us/"


def _ps(slug):
    return _PS.format(slug)


COUNTIES = {
    # ---- Top TX counties: verified CAD (appraiser) + County Clerk records portal ----
    "48201": {  # Harris — 4.8M, Houston
        "county": "Harris", "state": "TX",
        # hcad.org itself intermittently returns a Cloudflare 521 to automated clients; the
        # property-search host is the one that answers and is what a researcher wants.
        "appraiser_url": "https://public.hcad.org/",
        "clerk_url": "https://www.cclerk.hctx.net/applications/websearch/RP.aspx",
        "clerk_platform": "inhouse",
        "clerk_note": "Harris County Clerk 'Web Inquiry' real-property search.",
    },
    "48113": {  # Dallas — 2.6M
        "county": "Dallas", "state": "TX",
        "appraiser_url": "https://www.dallascad.org/",
        "clerk_url": _ps("dallas"), "clerk_platform": "publicsearch",
    },
    "48439": {  # Tarrant — 2.1M, Fort Worth
        "county": "Tarrant", "state": "TX",
        "appraiser_url": "https://www.tad.org/",
        "clerk_url": _ps("tarrant"), "clerk_platform": "publicsearch",
    },
    "48029": {  # Bexar — 2.0M, San Antonio
        "county": "Bexar", "state": "TX",
        "appraiser_url": "https://bcad.org/",
        "clerk_url": _ps("bexar"), "clerk_platform": "publicsearch",
    },
    "48453": {  # Travis — 1.3M, Austin
        "county": "Travis", "state": "TX",
        "appraiser_url": "https://traviscad.org/",
        "clerk_url": "https://countyclerk.traviscountytx.gov/",
        "clerk_platform": "inhouse",
    },
    "48085": {  # Collin — 1.2M, Plano/McKinney
        "county": "Collin", "state": "TX",
        "appraiser_url": "https://collincad.org/",
        "clerk_url": _ps("collin"), "clerk_platform": "publicsearch",
    },
    "48121": {  # Denton — 1.0M
        "county": "Denton", "state": "TX",
        "appraiser_url": "https://www.dentoncad.com/",
        "clerk_url": _ps("denton"), "clerk_platform": "publicsearch",
    },
    "48215": {  # Hidalgo — 870k, McAllen
        "county": "Hidalgo", "state": "TX",
        "appraiser_url": "https://www.hidalgocad.org/",
        "clerk_url": _ps("hidalgo"), "clerk_platform": "publicsearch",
    },
    "48157": {  # Fort Bend — 860k, Sugar Land
        "county": "Fort Bend", "state": "TX",
        "appraiser_url": "https://www.fbcad.org/",
        "clerk_url": ("https://www.fortbendcountytx.gov/government/departments/"
                      "county-clerk"),
        "clerk_platform": "inhouse",
    },
    "48141": {  # El Paso — 860k
        "county": "El Paso", "state": "TX",
        "appraiser_url": "https://epcad.org/",
        "clerk_url": "https://apps.epcountytx.gov/publicrecords/OfficialPublicRecords",
        "clerk_platform": "inhouse",
    },
    "48491": {  # Williamson — 680k, Round Rock/Georgetown
        "county": "Williamson", "state": "TX",
        "appraiser_url": "https://www.wcad.org/",
        "clerk_url": _ps("williamson"), "clerk_platform": "publicsearch",
    },
    "48339": {  # Montgomery — 680k, Conroe/The Woodlands
        "county": "Montgomery", "state": "TX",
        "appraiser_url": "https://mcad-tx.org/",
        "clerk_url": _ps("montgomery"), "clerk_platform": "publicsearch",
    },
    "48061": {  # Cameron — 430k, Brownsville
        "county": "Cameron", "state": "TX",
        "appraiser_url": "https://www.cameroncad.org/",
        "clerk_url": _ps("cameron"), "clerk_platform": "publicsearch",
    },
    "48039": {  # Brazoria — 370k, Pearland/Angleton
        "county": "Brazoria", "state": "TX",
        "appraiser_url": "https://brazoriacad.org/",
        # 403 to automated clients (WAF) — opens in a browser.
        "clerk_url": "https://www.brazoriacountyclerktx.gov/search-records",
        "clerk_platform": "inhouse",
    },
    "48027": {  # Bell — 390k, Killeen/Temple
        "county": "Bell", "state": "TX",
        "appraiser_url": "https://bellcad.org/",
        "clerk_url": _ps("bell"), "clerk_platform": "publicsearch",
    },
    "48167": {  # Galveston — 350k
        "county": "Galveston", "state": "TX",
        "appraiser_url": "https://galvestoncad.org/",
        # 403 to automated clients (WAF) — opens in a browser.
        "clerk_url": ("https://www.galvestoncountytx.gov/our-county/county-clerk/"
                      "records-search"),
        "clerk_platform": "inhouse",
    },
    "48355": {  # Nueces — 350k, Corpus Christi
        "county": "Nueces", "state": "TX",
        "appraiser_url": "https://nuecescad.net/",
        "clerk_url": _ps("nueces"), "clerk_platform": "publicsearch",
    },
    "48303": {  # Lubbock — 320k
        "county": "Lubbock", "state": "TX",
        "appraiser_url": "https://lubbockcad.org/",
        # No county-clerk records-search URL verified yet (the county site's clerk path
        # 404s); left unset so clerk.py falls back to the NETROnline directory link.
    },
    "48479": {  # Webb — 270k, Laredo
        "county": "Webb", "state": "TX",
        "appraiser_url": "https://www.webbcad.org/",
        # webbcountytx.gov fails TLS from here — do not guess a records URL.
    },
    "48423": {  # Smith — 240k, Tyler
        "county": "Smith", "state": "TX",
        "appraiser_url": "https://smithcad.org/",
        "clerk_url": _ps("smith"), "clerk_platform": "publicsearch",
    },
    "48309": {  # McLennan — 260k, Waco
        "county": "McLennan", "state": "TX",
        "appraiser_url": "https://www.mclennancad.org/",
        "clerk_url": "https://www.mclennan.gov/178/Official-Public-Records",
        "clerk_platform": "inhouse",
        "clerk_note": "Online index covers 1996-present; 1849-1995 are book volumes.",
    },
    "48041": {  # Brazos — 250k, Bryan/College Station
        "county": "Brazos", "state": "TX",
        "appraiser_url": "https://brazoscad.org/",
        "clerk_url": _ps("brazos"), "clerk_platform": "publicsearch",
    },
    "48245": {  # Jefferson — 250k, Beaumont
        "county": "Jefferson", "state": "TX",
        "appraiser_url": "https://jcad.org/",
        "clerk_url": _ps("jefferson"), "clerk_platform": "publicsearch",
    },
    "48091": {  # Comal — 160k, New Braunfels
        "county": "Comal", "state": "TX",
        "appraiser_url": "https://www.comalcad.org/",
        "clerk_url": "https://comal.landrecordsonline.com/",
        "clerk_platform": "inhouse",
        "clerk_note": "Comal County Public Access (landrecordsonline).",
    },
    "48187": {  # Guadalupe — 170k, Seguin
        "county": "Guadalupe", "state": "TX",
        "appraiser_url": "https://guadalupead.org/",
        "clerk_url": "https://www.guadalupetx.gov/page/coclerk.opr",
        "clerk_platform": "inhouse",
        "clerk_note": "County Clerk Official Public Records page (records back to 1832).",
    },
    "48209": {  # Hays — 260k, San Marcos/Kyle
        "county": "Hays", "state": "TX",
        "appraiser_url": "https://www.hayscad.org/",
        "clerk_url": "https://www.hayscountytx.gov/202/Records-Division",
        "clerk_platform": "inhouse",
        "clerk_note": "Records Division; self-service index from 1848-present.",
    },
    "48139": {  # Ellis — 200k, Waxahachie
        "county": "Ellis", "state": "TX",
        "appraiser_url": "https://www.elliscad.com/",
        "clerk_url": ("https://www.elliscountytx.gov/956/"
                      "New-Online-Records-Search-Information"),
        "clerk_platform": "inhouse",
        "clerk_note": "County landing page for the online records search.",
    },
    "48251": {  # Johnson — 200k, Cleburne
        "county": "Johnson", "state": "TX",
        "appraiser_url": "https://johnsoncad.com/",
        "clerk_url": _ps("johnson"), "clerk_platform": "publicsearch",
    },
    "48367": {  # Parker — 150k, Weatherford
        "county": "Parker", "state": "TX",
        "appraiser_url": "https://www.parkercad.org/",
        "clerk_url": "https://www.parkercountytx.gov/114/Public-Records",
        "clerk_platform": "inhouse",
    },
    "48181": {  # Grayson — 140k, Sherman/Denison
        "county": "Grayson", "state": "TX",
        "appraiser_url": "https://www.graysoncad.org/",
        "clerk_url": _ps("grayson"), "clerk_platform": "publicsearch",
    },
    "48257": {  # Kaufman — 150k, Terrell
        "county": "Kaufman", "state": "TX",
        "appraiser_url": "https://www.kaufmancad.org/",
        # Only a vendor login page found (not county-specific) — left to the fallback.
    },
    "48135": {  # Ector — 160k, Odessa
        "county": "Ector", "state": "TX",
        "appraiser_url": "https://www.ectorcad.org/",
        "clerk_url": "https://www.ectorcountytx.gov/172/County-Clerk",
        "clerk_platform": "inhouse",
    },
    "48329": {  # Midland — 170k
        "county": "Midland", "state": "TX",
        "appraiser_url": "https://midcad.org/",
        "clerk_url": _ps("midland"), "clerk_platform": "publicsearch",
    },
    "48441": {  # Taylor — 140k, Abilene
        "county": "Taylor", "state": "TX",
        "appraiser_url": "https://www.taylorcad.org/",
    },
    "48183": {  # Gregg — 120k, Longview
        "county": "Gregg", "state": "TX",
        "appraiser_url": "https://gcad.org/",
    },
    "48485": {  # Wichita — 130k, Wichita Falls
        "county": "Wichita", "state": "TX",
        "appraiser_url": "https://wadtx.com/",
    },
    "48381": {  # Randall — 140k, Amarillo (south) — joint district with Potter
        "county": "Randall", "state": "TX",
        "appraiser_url": "https://www.prad.org/",
    },
    "48375": {  # Potter — 110k, Amarillo (north) — joint district with Randall
        "county": "Potter", "state": "TX",
        "appraiser_url": "https://www.prad.org/",
        "clerk_url": _ps("potter"), "clerk_platform": "publicsearch",
    },
    "48213": {  # Henderson — 84k, Athens
        "county": "Henderson", "state": "TX",
        "appraiser_url": "https://www.hendersoncad.org/",
    },
    "48331": {  # Milam — 25k, Cameron
        "county": "Milam", "state": "TX",
        "appraiser_url": "https://milamad.org/",
    },
    # TODO — next TX batch: the remaining 214 counties fall back to the NETROnline
    # directory for deed/plat + appraiser (parcels already auto-fetch statewide). Highest
    # value follow-ups: (1) probe `<slug>.tx.publicsearch.us` across all 254 counties, since
    # that one platform already covers 18 of the top 38 and a single adapter would unlock
    # deed/plat AUTO-DOWNLOAD for all of them; (2) fill the clerk gaps left above
    # (Lubbock, Webb, Kaufman, Taylor, Gregg, Wichita, Randall, Henderson, Milam).
}
