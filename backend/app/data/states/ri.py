"""RI — statewide parcel service (one module per state; edit here to debug RI).

Rhode Island's official RIGIS statewide Tax_Parcels layer (~394k parcels, all 5 counties). It
carries the parcel identifier (PlatLot, e.g. "PR 020-0038-0000"; TownCode = municipality) but NO
situs street address and NO owner on the public service — so the app delivers the Parcel ID
(plat/lot) statewide + the county records link; situs/owner are a follow-up (no richer public
RIGIS parcel layer found). This flips RI from zero parcel coverage to statewide. inSR=4326 point
queries work directly. Verified 2026-08-18 (Providence returned PlatLot).

NOTE: the AGOL org services9.arcgis.com/04Mfke8TEc0Pvqvt (Parcels_011224_*) is NOT RIGIS — it is
an unrelated 2k-feature wind-siting project; do not use it.
"""
STATE = "RI"
PARCEL = {
    'kind': 'mapserver',
    'label': 'Rhode Island Statewide Tax Parcels (RIGIS)',
    'url': 'https://risegis.ri.gov/hosting/rest/services/RIDEM/Tax_Parcels/MapServer/0',
    'id_fields': ['PlatLot'],
}
COUNTIES = {}
