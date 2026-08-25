"""County records-platform registry.

Keyed by 5-digit county FIPS (state+county). Each entry names the Clerk/Recorder
official-records portal (deeds, plats), its software platform, the Property Appraiser /
Assessor site, and - where verified - an ArcGIS REST parcel service the app can query
directly.

Seeded with the 8 major Florida counties (verified live 2026-07-20). Any county not in
the registry falls back to a NETROnline directory deep-link so the app stays
national-ready: it always returns *where* to look, and auto-fetches whatever has an API.

Platforms:
  acclaim  - Harris Recording Solutions (AcclaimWeb)   -> one scraper adapter, many counties
  landmark - Pioneer Technology Group (LandmarkWeb)     -> one scraper adapter, many counties
  eagle    - Tyler Technologies (Eagle recorder)        -> one scraper adapter
  inhouse  - county-built portal                        -> bespoke adapter
"""

REGISTRY: dict[str, dict] = {
    # ---- FLORIDA (verified) ----
    "12127": {  # Volusia
        "county": "Volusia", "state": "FL",
        "clerk_url": "https://app02.clerk.org/or_m/",
        "clerk_platform": "inhouse",
        "clerk_note": "In-house Document Inquiry. ToS prohibits bulk reproduction - per-job lookups only. Index from 1988-04-04.",
        "appraiser_url": "https://vcpa.vcgov.org/searches.html",
        "gis_rest": None,
    },
    "12105": {  # Polk
        "county": "Polk", "state": "FL",
        "clerk_url": "https://apps.polkcountyclerk.net/browserviewor/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.polkflpa.gov/CamaSearch.aspx",
        "gis_rest": None,
    },
    "12103": {  # Pinellas
        "county": "Pinellas", "state": "FL",
        "clerk_url": "https://officialrecords.mypinellasclerk.gov/",
        "clerk_platform": "acclaim",
        "appraiser_url": "https://www.pcpao.gov/",
        "gis_rest": "https://egis.pinellas.gov/gis/rest/services/PublicWebGIS/Parcels/MapServer",
        "parcel_layer_hint": "parcel",
    },
    "12009": {  # Brevard
        "county": "Brevard", "state": "FL",
        "clerk_url": "https://vaclmweb1.brevardclerk.us/AcclaimWeb/",
        "clerk_platform": "acclaim",
        "appraiser_url": "https://www.bcpao.us/",
        "appraiser_api": "https://www.bcpao.us/api/v1/",
        "gis_rest": None,
    },
    "12057": {  # Hillsborough
        "county": "Hillsborough", "state": "FL",
        "clerk_url": "https://publicaccess.hillsclerk.com/oripublicaccess/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.hcpafl.org/",
        "gis_rest": None,
    },
    "12011": {  # Broward
        "county": "Broward", "state": "FL",
        "clerk_url": "https://officialrecords.broward.org/AcclaimWeb/",
        "clerk_platform": "acclaim",
        "clerk_note": "Free bulk FTP feed (10 rolling days of images + index). All plats searchable regardless of date.",
        "appraiser_url": "https://web.bcpa.net/",
        "gis_rest": None,
    },
    "12095": {  # Orange
        "county": "Orange", "state": "FL",
        "clerk_url": "https://or.occompt.com/recorder/web/",
        "clerk_platform": "eagle",
        "appraiser_url": "https://ocpafl.org/",
        "gis_rest": None,
    },
    "12086": {  # Miami-Dade
        "county": "Miami-Dade", "state": "FL",
        "clerk_url": "https://onlineservices.miamidadeclerk.gov/officialrecords/StandardSearch.aspx",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.miamidade.gov/pa/",
        "gis_rest": "https://gisweb.miamidade.gov/arcgis/rest/services/MD_LandInformation/MapServer",
        "parcel_layer_hint": "parcel",
    },
    "12069": {  # Lake (Landmark example)
        "county": "Lake", "state": "FL",
        "clerk_url": "https://officialrecords.lakecountyclerk.org/",
        "clerk_platform": "landmark",
        "appraiser_url": "https://www.lakecopropappr.com/",
        "gis_rest": None,
    },
    # ---- FLORIDA (researched 2026-07-21; parcels auto-fetch via STATE_PARCEL) ----
    "12115": {  # Sarasota
        "county": "Sarasota", "state": "FL",
        "clerk_url": "https://secure.sarasotaclerk.com/OfficialRecords.aspx",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.sc-pa.com/",
        "gis_rest": None,
    },
    "12121": {  # Suwannee
        "county": "Suwannee", "state": "FL",
        "clerk_url": "https://www.myfloridacounty.com/orisearch/61",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.suwanneepa.com/",
        "gis_rest": None,
    },
    "12133": {  # Washington
        "county": "Washington", "state": "FL",
        "clerk_url": "https://www.myfloridacounty.com/orisearch/67",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.qpublic.net/fl/washington/",
        "gis_rest": None,
    },
    "12031": {  # Duval (Jacksonville)
        "county": "Duval", "state": "FL",
        "clerk_url": "https://or.duvalclerk.com/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.jacksonville.gov/departments/property-appraiser",
        "gis_rest": None,
    },
    "12071": {  # Lee (Fort Myers)
        "county": "Lee", "state": "FL",
        "clerk_url": "https://www.leeclerk.org/departments/official-records-services/search-official-records",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.leepa.org/",
        "gis_rest": None,
    },
    "12021": {  # Collier (Naples)
        "county": "Collier", "state": "FL",
        "clerk_url": "https://cor.collierclerk.com/coraccess/search/document",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.collierappraiser.com/",
        "gis_rest": None,
    },
    "12033": {  # Escambia (Pensacola)
        "county": "Escambia", "state": "FL",
        "clerk_url": "https://www.escambiaclerk.com/258/Online-Public-Records",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.escpa.org/",
        "gis_rest": None,
    },
    "12099": {  # Palm Beach
        "county": "Palm Beach", "state": "FL",
        "clerk_url": "https://erec.mypalmbeachclerk.com/",
        "clerk_platform": "landmark",
        "appraiser_url": "https://pbcpao.gov/",
        "gis_rest": None,
    },
    "12101": {  # Pasco
        "county": "Pasco", "state": "FL",
        "clerk_url": "https://www.pascoclerk.com/333/Pasco-County-Official-Records-Search",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://pascopa.com/",
        "gis_rest": None,
    },
    "12117": {  # Seminole
        "county": "Seminole", "state": "FL",
        "clerk_url": "https://recording.seminoleclerk.org/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.scpafl.org/",
        "gis_rest": None,
    },
    "12083": {  # Marion
        "county": "Marion", "state": "FL",
        "clerk_url": "https://www.marioncountyclerk.org/departments/records-recording/official-records-recording/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.pa.marion.fl.us/",
        "gis_rest": None,
    },
    "12081": {  # Manatee
        "county": "Manatee", "state": "FL",
        "clerk_url": "https://records.manateeclerk.com/OfficialRecords/Search",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.manateepao.gov/",
        "gis_rest": None,
    },
    "12097": {  # Osceola
        "county": "Osceola", "state": "FL",
        "clerk_url": "https://officialrecords.osceolaclerk.org/searchng_ssl/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.property-appraiser.org/",
        "gis_rest": None,
    },
    "12111": {  # St. Lucie
        "county": "St. Lucie", "state": "FL",
        "clerk_url": "https://stlucieclerk.gov/search-official-records",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.paslc.gov/",
        "gis_rest": None,
    },
    "12109": {  # St. Johns
        "county": "St. Johns", "state": "FL",
        "clerk_url": "https://apps.stjohnsclerk.com/Landmark",
        "clerk_platform": "landmark",
        "appraiser_url": "https://www.sjcpa.gov/",
        "gis_rest": None,
    },
    "12001": {  # Alachua (Gainesville)
        "county": "Alachua", "state": "FL",
        "clerk_url": "https://isol.alachuaclerk.org/RealEstate/SearchEntry.aspx?e=newSession",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.acpafl.org/",
        "gis_rest": None,
    },
    "12005": {  # Bay (Panama City)
        "county": "Bay", "state": "FL",
        "clerk_url": "https://www.baycoclerk.com/public-records/search-official-records/",
        "clerk_platform": "landmark",
        "appraiser_url": "https://baypa.net/",
        "gis_rest": None,
    },
    "12019": {  # Clay
        "county": "Clay", "state": "FL",
        "clerk_url": "https://landmark.clayclerk.com/landmarkweb",
        "clerk_platform": "landmark",
        "appraiser_url": "https://www.ccpao.com/",
        "gis_rest": None,
    },
    "12015": {  # Charlotte
        "county": "Charlotte", "state": "FL",
        "clerk_url": "https://or.charlotteclerk.com/recording/",
        "clerk_platform": "landmark",
        "appraiser_url": "https://www.ccappraiser.com/",
        "gis_rest": None,
    },
    "12017": {  # Citrus
        "county": "Citrus", "state": "FL",
        "clerk_url": "https://search.citrusclerk.org/LandmarkWeb",
        "clerk_platform": "landmark",
        "appraiser_url": "https://www.citruspa.org/",
        "gis_rest": None,
    },
    "12053": {  # Hernando
        "county": "Hernando", "state": "FL",
        "clerk_url": "https://or.hernandoclerk.com/landmarkweb/",
        "clerk_platform": "landmark",
        "appraiser_url": "https://hernandopa-fl.us/",
        "gis_rest": None,
    },
    "12085": {  # Martin
        "county": "Martin", "state": "FL",
        "clerk_url": "https://or.martinclerk.com/LandmarkWeb",
        "clerk_platform": "landmark",
        "appraiser_url": "https://www.pamartinfl.gov/",
        "gis_rest": None,
    },
    "12061": {  # Indian River (Vero Beach)
        "county": "Indian River", "state": "FL",
        "clerk_url": "https://landmark.indian-river.org/",
        "clerk_platform": "landmark",
        "appraiser_url": "https://www.ircpa.org/",
        "gis_rest": None,
    },
    "12073": {  # Leon (Tallahassee)
        "county": "Leon", "state": "FL",
        "clerk_url": "https://leonclerk.com/helpful-resources/records/official-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.leonpa.gov/",
        "gis_rest": None,
    },
    "12091": {  # Okaloosa (Fort Walton Beach)
        "county": "Okaloosa", "state": "FL",
        "clerk_url": "https://okaloosacountyfl-web.tylerhost.net/web",
        "clerk_platform": "eagle",
        "appraiser_url": "https://www.okaloosapa.com/",
        "gis_rest": None,
    },
    "12113": {  # Santa Rosa
        "county": "Santa Rosa", "state": "FL",
        "clerk_url": "https://santarosaclerk.com/courts/search-public-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://srcpa.gov/",
        "gis_rest": None,
    },
    "12087": {  # Monroe (Key West)
        "county": "Monroe", "state": "FL",
        "clerk_url": "https://monroe-clerk.com/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.mcpafl.org/",
        "gis_rest": None,
    },
    "12089": {  # Nassau (Fernandina Beach)
        "county": "Nassau", "state": "FL",
        "clerk_url": "https://www.nassauclerk.com/174/Official-Records",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.nassauflpa.com/",
        "gis_rest": None,
    },
    "12035": {  # Flagler (Palm Coast / Bunnell)
        "county": "Flagler", "state": "FL",
        "clerk_url": "https://records.flaglerclerk.gov/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://flaglerpa.com/",
        "gis_rest": None,
    },
    "12023": {  # Columbia (Lake City)
        "county": "Columbia", "state": "FL",
        "clerk_url": "https://columbiaclerk.com/online-services/search-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://columbia.floridapa.com/",
        "gis_rest": None,
    },
    "12119": {  # Sumter (The Villages / Bushnell)
        "county": "Sumter", "state": "FL",
        "clerk_url": "https://www.sumterclerk.com/public-records/official-records/search-official-records-online/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.sumterpa.com/",
        "gis_rest": None,
    },
    "12055": {  # Highlands (Sebring)
        "county": "Highlands", "state": "FL",
        "clerk_url": "https://www.highlandsclerkfl.gov/popular_services/official_records_search.php",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.hcpao.org/",
        "gis_rest": None,
    },
    "12107": {  # Putnam (Palatka)
        "county": "Putnam", "state": "FL",
        "clerk_url": "https://putnamclerk.com/county-recorder/official-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://pa.putnam-fl.com/",
        "gis_rest": None,
    },
    "12051": {  # Hendry (LaBelle)
        "county": "Hendry", "state": "FL",
        "clerk_url": "https://www.hendryclerk.org/courts/official-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://hendryprop.com/",
        "gis_rest": None,
    },
    "12027": {  # DeSoto (Arcadia)
        "county": "DeSoto", "state": "FL",
        "clerk_url": "https://www.desotoclerk.com/records/records-search/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.desotopa.com/",
        "gis_rest": None,
    },
    "12049": {  # Hardee (Wauchula)
        "county": "Hardee", "state": "FL",
        "clerk_url": "https://www.hardeeclerk.com/departments/recording/recording-official-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://hardeepa.com/",
        "gis_rest": None,
    },
    "12093": {  # Okeechobee
        "county": "Okeechobee", "state": "FL",
        "clerk_url": "https://www.okeechobeelandmark.com/",
        "clerk_platform": "landmark",
        "appraiser_url": "https://www.okeechobeepa.com/",
        "gis_rest": None,
    },
    "12003": {  # Baker (Macclenny)
        "county": "Baker", "state": "FL",
        "clerk_url": "https://recording.bakerclerk.com/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.bakerpa.com/",
        "gis_rest": None,
    },
    "12007": {  # Bradford (Starke)
        "county": "Bradford", "state": "FL",
        "clerk_url": "https://bradfordclerk.com/official-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.bradfordappraiser.com/",
        "gis_rest": None,
    },
    "12131": {  # Walton (DeFuniak Springs)
        "county": "Walton", "state": "FL",
        "clerk_url": "https://orsearch.clerkofcourts.co.walton.fl.us/",
        "clerk_platform": "landmark",
        "appraiser_url": "https://waltonpa.com/",
        "gis_rest": None,
    },
    "12063": {  # Jackson (Marianna)
        "county": "Jackson", "state": "FL",
        "clerk_url": "https://www.jacksonclerk.com/search-official-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://jacksonpa.com/",
        "gis_rest": None,
    },
    "12039": {  # Gadsden (Quincy)
        "county": "Gadsden", "state": "FL",
        "clerk_url": "https://www.gadsdenclerk.com/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://gadsdenpa.com/",
        "gis_rest": None,
    },
    "12075": {  # Levy (Bronson)
        "county": "Levy", "state": "FL",
        "clerk_url": "https://levyclerk.com/departments-services/records-management/official-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.qpublic.net/fl/levy/",
        "gis_rest": None,
    },
    "12129": {  # Wakulla (Crawfordville)
        "county": "Wakulla", "state": "FL",
        "clerk_url": "https://wakullaclerk.org/official-records/",
        "clerk_platform": "landmark",
        "appraiser_url": "https://mywakullapa.com/",
        "gis_rest": None,
    },
    "12123": {  # Taylor (Perry)
        "county": "Taylor", "state": "FL",
        "clerk_url": "https://taylorclerk.com/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://qpublic.net/fl/taylor/",
        "gis_rest": None,
    },
    "12079": {  # Madison
        "county": "Madison", "state": "FL",
        "clerk_url": "https://www.madisonclerk.com/departments-services/records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://madisonpa.com/",
        "gis_rest": None,
    },
    "12065": {  # Jefferson (Monticello)
        "county": "Jefferson", "state": "FL",
        "clerk_url": "https://www.jeffersonclerk.com/departments/recording-official-records/official-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://jeffersonpa.net/",
        "gis_rest": None,
    },
    "12013": {  # Calhoun (Blountstown)
        "county": "Calhoun", "state": "FL",
        "clerk_url": "https://calhounclerk.com/records-search/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.qpublic.net/fl/calhoun/",
        "gis_rest": None,
    },
    "12037": {  # Franklin (Apalachicola)
        "county": "Franklin", "state": "FL",
        "clerk_url": "https://www.franklinclerk.com/online-services/records-search/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://franklincountypa.net/",
        "gis_rest": None,
    },
    "12041": {  # Gilchrist (Trenton)
        "county": "Gilchrist", "state": "FL",
        "clerk_url": "https://gilchristclerk.com/recording/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.qpublic.net/fl/gilchrist/",
        "gis_rest": None,
    },
    "12043": {  # Glades (Moore Haven)
        "county": "Glades", "state": "FL",
        "clerk_url": "https://gladesclerk.com/official-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://qpublic.net/fl/glades/",
        "gis_rest": None,
    },
    "12045": {  # Gulf (Port St. Joe)
        "county": "Gulf", "state": "FL",
        "clerk_url": "https://www.gulfclerk.com/record-search/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://gulfpa.com/",
        "gis_rest": None,
    },
    "12047": {  # Hamilton (Jasper)
        "county": "Hamilton", "state": "FL",
        "clerk_url": "https://hamiltonclerk.com/official-record-search/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://hamiltonpa.com/",
        "gis_rest": None,
    },
    "12059": {  # Holmes (Bonifay)
        "county": "Holmes", "state": "FL",
        "clerk_url": "https://holmesclerk.com/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.qpublic.net/fl/holmes/",
        "gis_rest": None,
    },
    "12067": {  # Lafayette (Mayo)
        "county": "Lafayette", "state": "FL",
        "clerk_url": "https://www.lafayetteclerk.com/departments-services/records-search/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.lafayettepa.com/",
        "gis_rest": None,
    },
    "12077": {  # Liberty (Bristol)
        "county": "Liberty", "state": "FL",
        "clerk_url": "https://libertyclerk.com/clerk-services/official-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://libertypa.org/",
        "gis_rest": None,
    },
    "12125": {  # Union (Lake Butler)
        "county": "Union", "state": "FL",
        "clerk_url": "https://recording.unionclerk.com/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://union.floridapa.com/",
        "gis_rest": None,
    },
    "12029": {  # Dixie (Cross City)
        "county": "Dixie", "state": "FL",
        "clerk_url": "https://dixieclerk.com/departments-services/online-records/",
        "clerk_platform": "inhouse",
        "appraiser_url": "https://www.qpublic.net/fl/dixie/",
        "gis_rest": None,
    },
}

# Statewide parcel services + per-county overrides now live in per-state modules under
# data/states/ (one file per state — easy to debug/track). Aggregated + merged here.
from .states import (STATE_PARCEL, STATE_COUNTIES, STATE_DEED, STATE_PLAT,  # noqa: E402
                     STATE_APPRAISER)
REGISTRY.update(STATE_COUNTIES)  # per-county overrides contributed by state modules


def _merge_bulk_links() -> None:
    """Merge `records_links.json` — bulk-verified clerk (deed/plat) + appraiser links.

    Some states need HUNDREDS of county records links (TX alone has 254 appraisal districts),
    which is impractical to hand-write in a state module. Those are discovered and verified by
    `scripts/verify_records_links.py`, stored in that JSON with the SOURCE recorded per county,
    and merged here.

    Merge rule: a hand-written state-module value always WINS — every key is applied with
    setdefault, so an explicitly curated entry (richer notes, a scraper platform, a parcel
    service) is never clobbered by the bulk file.
    """
    import json
    import pathlib
    path = pathlib.Path(__file__).with_name("records_links.json")
    if not path.exists():
        return
    for fips, entry in json.loads(path.read_text(encoding="utf-8")).items():
        if not (len(fips) == 5 and fips.isdigit()):
            continue
        cur = REGISTRY.setdefault(fips, {})
        for k, v in entry.items():
            if v:
                cur.setdefault(k, v)


_merge_bulk_links()


PLATFORM_LABEL = {
    "acclaim": "Acclaim (Harris Recording Solutions)",
    "landmark": "Landmark (Pioneer Technology Group)",
    "eagle": "Tyler Eagle",
    "publicsearch": "PublicSearch (Kofile)",
    "inhouse": "In-house / county-built",
    "unknown": "Unknown - use directory link",
}


def lookup(county_fips: str) -> dict | None:
    return REGISTRY.get(county_fips)


def netronline(state_abbr: str, county_name: str) -> str:
    slug = county_name.strip().lower().replace(" ", "-")
    return f"https://publicrecords.netronline.com/state/{state_abbr}/county/{slug}"
