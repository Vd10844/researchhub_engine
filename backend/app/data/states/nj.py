"""NJ — statewide parcel service + statewide assessment search (edit here to debug NJ).

NJ is the 5th order-volume state (~1.1%). Both the parcel record AND the assessor/tax card
have genuine STATEWIDE sources here, so no per-county work is needed for those two:

* PARCEL — NJOGIS Framework Cadastral (parcels + MOD-IV attributes), all 21 counties.
* APPRAISER — "NJ Assessment Records Search", the public front end to MOD-IV, New Jersey's
  statewide property-assessment system. It covers every municipality in all 21 counties
  (block/lot, owner, assessed value, sales), so it is wired as APPRAISER_LINK rather than
  copied into 21 county entries. Verified live 2026-08-20.

DEEDS/PLATS stay per-county: each of the 21 counties has its own County Clerk (Essex and
Hudson call theirs a Register of Deeds), and there is NO statewide NJ land-records portal —
njlandrecords.com and the Fidlar `*.uslandrecords.com/njlr/` pattern both fail to resolve, so
counties without a verified portal below fall through to the NETROnline directory link.
"""
STATE = "NJ"
PARCEL = {'kind': 'mapserver',
          'label': 'New Jersey Parcels & MOD-IV (NJOGIS)',
          'url': 'https://maps.nj.gov/arcgis/rest/services/Framework/Cadastral/MapServer/0'}

# Statewide MOD-IV assessment search — used as the appraiser/tax link for ALL 21 counties.
APPRAISER_LINK = "https://www.taxrecords-nj.com/pub/cgi/prc6.cgi?menu=index&ms_user=monm&passwd="

def _c(name, clerk, platform="inhouse", note=None):
    e = {"county": name, "state": "NJ", "clerk_url": clerk, "clerk_platform": platform}
    if note:
        e["clerk_note"] = note
    return e


# All 21 county clerks / registers of deeds — verified live 2026-08-20. The official domains
# are too varied to pattern-probe (a sweep of the 6 obvious host shapes found only 3 of 21), so
# the rest were each resolved individually.
#
# Two platform notes that matter for future deed/plat AUTO-DOWNLOAD (not just links):
#   * Somerset runs AcclaimWeb — the same platform as the existing `acclaim` adapter.
#   * Middlesex, Morris and Cape May run NewVision "BrowserView"/public-search — the same
#     family as the Polk FL adapter in clerk_scraper.py.
# So NJ deed/plat automation is reachable later without writing a new scraper.
COUNTIES = {
    "34001": _c("Atlantic",  "https://www.atlanticcountyclerk.org/"),
    "34003": _c("Bergen",    "https://www.bergencountyclerk.gov/",
                note="Bergen County Clerk land-record services."),
    "34005": _c("Burlington",
                "https://press.co.burlington.nj.us/PRESS/clerk/ClerkHome.aspx",
                note="PRESS (Public Records Electronic Search System); guest login available."),
    "34007": _c("Camden",    "https://www.camdencounty.com/service/county-clerk/"),
    "34009": _c("Cape May",  "https://capemaycountynj.gov/189/County-Clerk",
                note=("County Clerk page. The records host clerk.capemaycountynj.gov "
                      "(NewVision publicsearch) fails TLS from this network — index goes "
                      "back to 2000, deeds/mortgages to 1996.")),
    "34011": _c("Cumberland",
                "https://cumberlandcountyclerknj.gov/public-land-records/",
                note="Online deeds/mortgages from 2002; ImageSync covers 1960-1987."),
    "34013": _c("Essex",     "https://www.essexclerk.com/",
                note="Essex has a Register of Deeds rather than a County Clerk."),
    "34015": _c("Gloucester", "https://www.gloucestercountynj.gov/370/Land-Records"),
    "34017": _c("Hudson",    "https://www.hudsoncountyclerk.org/",
                note="Hudson has a Register of Deeds rather than a County Clerk."),
    "34019": _c("Hunterdon", "https://www.co.hunterdon.nj.us/263/Recording-Section",
                note="Records from 1785 onward."),
    "34021": _c("Mercer",    "http://records.mercercounty.org/RecordsNG_Search/",
                note="Official Records public search."),
    "34023": _c("Middlesex", "https://mcrecords.co.middlesex.nj.us/publicsearch1/",
                note=("NewVision BrowserView — deeds 1929+, mortgages 1950+, other docs "
                      "1958+. Same platform family as the Polk FL scraper adapter.")),
    "34025": _c("Monmouth",  "https://www.monmouthcountyclerk.gov/"),
    "34027": _c("Morris",    "https://mcclerksng.co.morris.nj.us/publicsearch/",
                note=("NewVision BrowserView — same platform as the Polk FL adapter; "
                      "records vault goes back to the late 1700s.")),
    "34029": _c("Ocean",     "https://sng.co.ocean.nj.us/searchapplication/",
                note="Official records from 1977-04-01 onward."),
    "34031": _c("Passaic",
                "https://www.passaiccountynj.org/government/passaic-county-clerk/land-records",
                note="PRESS grantor/grantee index covers 2000-12 onward."),
    "34033": _c("Salem",     "https://salemcountyclerk.org/public-records-search/",
                note="Deeds from 1941; mortgages from 2003 (partial)."),
    "34035": _c("Somerset",  "https://liveacclaim.co.somerset.nj.us/AcclaimWeb/", "acclaim",
                note=("AcclaimWeb — the SAME platform as the existing `acclaim` adapter, so "
                      "deed/plat auto-download is reachable here without new scraper work.")),
    "34037": _c("Sussex",    "https://www.sussexcountyclerk.org"),
    "34039": _c("Union",     "https://ucnj.org/county-clerk/"),
    "34041": _c("Warren",
                "https://www.warrencountynj.gov/government/warren-county-clerk-s-office/"
                "public-land-records",
                note="Search IQS: name, date, doc type, book/page, address, instrument no."),
}
