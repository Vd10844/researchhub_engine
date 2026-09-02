"""Static reference data. Residential land survey scope: the research-phase
document set, the survey matrix, and the source directory used by the engine's
per-source adapters (``engine/orchestration/sources.py``)."""

# Single survey type in scope for the POC.
SURVEY_TYPES = [
    {"name": "Residential Land Survey",
     "purpose": "Retrace/establish residential property boundaries (boundary / mortgage-location).",
     "standard": "FL Rule 5J-17.052 FAC — records research mandatory.",
     "public_set": ["deed", "adjoiner deeds", "plat", "easements/covenants", "prior surveys",
                    "parcel/appraiser", "FEMA flood", "GLO/PLSS", "condo declaration"]},
]

# The research-phase document set for a Florida residential land survey.
# requirement: "mandatory" | "conditional" | "recommended".
# source: which module fetches/links it — parcel | clerk | fema | ngs | glo.
RESIDENTIAL_DOCS = [
    {"key": "parcel", "label": "Parcel record & Parcel ID", "requirement": "mandatory",
     "source": "parcel",
     "description": "The Property Appraiser's record for the parcel — its unique Parcel ID, "
                    "owner, legal description, subdivision and (often) the deed & plat book/page. "
                    "It's the anchor that identifies the property and seeds every other lookup.",
     "guidance": "County appraiser parcel: legal description, owner, OR book/page, subdivision, section-township-range."},
    {"key": "appraiser", "label": "Property Appraiser / Tax record", "requirement": "mandatory",
     "source": "appraiser",
     "description": "The county tax-roll record — owner, situs, use code, land & living area, "
                    "just/assessed/taxable values and the last recorded sale (OR book/page). "
                    "Used to confirm identity, size and the authoritative deed reference.",
     "guidance": "County Property Appraiser / DOR tax roll: owner, values, area, last sale OR book/page."},
    {"key": "deed", "label": "Deed — subject parcel", "requirement": "mandatory",
     "source": "clerk",
     "description": "The recorded instrument that conveys ownership. It carries the record "
                    "legal description the survey must retrace, plus the OR book/page reference.",
     "guidance": "Current vesting deed — search Official Records by OR book/page or owner name."},
    {"key": "plat", "label": "Recorded plat / subdivision map", "requirement": "mandatory",
     "source": "clerk", "condition": "if the parcel is in a recorded subdivision",
     "description": "The recorded map that created the subdivision's lots, blocks, streets and "
                    "easements — giving platted lot dimensions, bearings and dedicated easements.",
     "guidance": "Search the Plat Book / subdivision name for the recorded plat."},
    {"key": "adjoiners", "label": "Deeds — adjoining parcels", "requirement": "mandatory",
     "source": "clerk",
     "description": "The deeds of the neighboring parcels — used to resolve gaps, overlaps and "
                    "boundary conflicts with adjoiners (required by FL Rule 5J-17.052).",
     "guidance": "Retrieve deeds for the abutting parcels to resolve boundary calls."},
    {"key": "easements", "label": "Easements / ROW / covenants (CC&Rs)", "requirement": "mandatory",
     "source": "clerk",
     "description": "Recorded rights that affect the land — utility/access easements, rights-of-way "
                    "and restrictive covenants — which must be located and shown on the survey.",
     "guidance": "Search Official Records for recorded easements, rights-of-way and restrictive covenants."},
    {"key": "prior_survey", "label": "Prior recorded surveys", "requirement": "recommended",
     "source": "clerk",
     "description": "Earlier recorded surveys of the parcel or subdivision — prior monumentation "
                    "and measurements to compare against and reconcile.",
     "guidance": "Search Official Records for previously recorded surveys of the parcel or subdivision."},
    {"key": "flood", "label": "FEMA flood zone / FIRM", "requirement": "conditional",
     "source": "fema", "condition": "lender-required; if near a Special Flood Hazard Area",
     "description": "The FEMA flood-hazard designation for the parcel — flood zone (e.g. X, AE, VE), "
                    "FIRM panel and Base Flood Elevation — i.e. whether it sits in a Special Flood "
                    "Hazard Area. Lenders and insurers require this determination.",
     "guidance": "NFHL flood zone, FIRM panel and Base Flood Elevation."},
    {"key": "benchmarks", "label": "NGS geodetic control (benchmarks)", "requirement": "recommended",
     "source": "ngs",
     "description": "Nearby NGS survey monuments with published coordinates and elevations — used "
                    "to tie the survey to the correct datum (e.g. NAVD88) and horizontal control.",
     "guidance": "Nearby NGS control marks for datum / horizontal & vertical control."},
    {"key": "glo", "label": "GLO / PLSS plats & field notes", "requirement": "conditional",
     "source": "glo", "condition": "if the legal is section-township-range (PLSS) / metes-and-bounds",
     "description": "The original U.S. General Land Office township plats and field notes that "
                    "established the PLSS section corners — the basis for section / metes-and-bounds "
                    "descriptions.",
     "guidance": "BLM GLO original township plats & field notes for the section."},
    {"key": "condo", "label": "Condominium declaration & exhibits", "requirement": "conditional",
     "source": "clerk", "condition": "if the property is a condominium unit",
     "description": "The recorded declaration (with its survey / plot-plan exhibits) that legally "
                    "creates the condominium and defines the units and common elements (FL s.718.104).",
     "guidance": "Search Official Records for the recorded condo declaration and survey exhibits."},
    {"key": "zoning", "label": "Zoning / setback ordinance", "requirement": "conditional",
     "source": "gis", "condition": "if setbacks / permitted use affect the survey (most boundary work)",
     "description": "The zoning classification and applicable setback / land-use ordinances for the "
                    "parcel — used to check conforming use, buildable area and setback lines shown "
                    "on the survey.",
     "guidance": "Search the county/municipal zoning GIS or permitting portal for the parcel's zoning "
                 "classification and setback ordinance."},
]

# Column order matches SURVEY_TYPES names
DOC_MATRIX = {
    "columns": ["Boundary", "ALTA", "Mortgage/Loc.", "Topo", "FEMA EC",
                "Subdiv./Plat", "Constr./As-built", "Route/ROW", "Hydro", "Condo"],
    "rows": [
        {"doc": "Deed - subject parcel", "access": "Public",
         "cells": ["M", "M", "M", "R", "M", "M", "R", "M", "C", "M"], "auto": True},
        {"doc": "Deeds - adjoining parcels", "access": "Public",
         "cells": ["M", "M/R", "R", "-", "-", "M", "-", "M", "-", "R"], "auto": True},
        {"doc": "Recorded subdivision plat(s)", "access": "Public",
         "cells": ["M*", "M*", "M*", "R", "R", "M", "R", "M", "C", "M"], "auto": True},
        {"doc": "Prior recorded surveys", "access": "Public",
         "cells": ["R/M", "R", "R", "-", "-", "R", "R", "R", "R", "R"], "auto": True},
        {"doc": "Prior unrecorded surveys", "access": "Private",
         "cells": ["R", "R", "R", "R", "R", "R", "R", "R", "R", "R"], "auto": False},
        {"doc": "Title commitment / opinion", "access": "Private",
         "cells": ["R", "M", "R", "-", "-", "M", "-", "M", "-", "R"], "auto": False},
        {"doc": "Recorded easements / ROW / covenants", "access": "Public",
         "cells": ["M/C", "M", "R", "R", "-", "M", "C", "M", "C", "M"], "auto": True},
        {"doc": "Tax / parcel map + appraiser data", "access": "Public",
         "cells": ["R", "R/M", "R", "R", "M", "R", "-", "M", "-", "R"], "auto": True},
        {"doc": "FEMA FIRM / FIS (flood zone)", "access": "Public",
         "cells": ["-", "C", "R", "R", "M", "R", "C", "C", "C", "C"], "auto": True},
        {"doc": "NGS / geodetic control (benchmarks)", "access": "Public",
         "cells": ["R", "R", "-", "M", "M", "M", "R", "M", "M", "R"], "auto": True},
        {"doc": "DOT right-of-way maps", "access": "Public",
         "cells": ["C", "C", "C", "C", "-", "C", "C", "M", "-", "C"], "auto": True},
        {"doc": "GLO / BLM original plats & field notes", "access": "Public",
         "cells": ["M**", "C", "-", "-", "-", "C", "-", "M**", "C", "-"], "auto": True},
        {"doc": "Condominium declaration + exhibits", "access": "Public",
         "cells": ["C", "C", "C", "-", "C", "-", "-", "-", "-", "M"], "auto": True},
        {"doc": "Utility records / 811 locates", "access": "Mixed",
         "cells": ["-", "C", "-", "R", "-", "R", "M", "R", "C", "R"], "auto": False},
        {"doc": "Zoning report / ordinance", "access": "Mixed",
         "cells": ["-", "C", "-", "R", "-", "M", "C", "C", "-", "R"], "auto": False},
        {"doc": "Design / engineering plans", "access": "Private",
         "cells": ["-", "-", "-", "-", "C", "R", "M", "M", "C", "M"], "auto": False},
    ],
    "legend": "M = Mandatory · R = Recommended · C = Conditional (if applicable / ALTA Table A) · - = N/A. "
              "M* = if platted · M** = in PLSS descriptions.",
}

SOURCES = [
    {"category": "Federal", "name": "FEMA Map Service Center", "url": "https://msc.fema.gov/portal/home",
     "coverage": "USA", "access": "Free, no account", "api": "Product listing + downloads",
     "feasibility": "High", "verified": "V"},
    {"category": "Federal", "name": "FEMA NFHL REST", "url": "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer",
     "coverage": "USA", "access": "Free", "api": "ArcGIS REST", "feasibility": "High", "verified": "V"},
    {"category": "Federal", "name": "NGS Datasheets / NDE API", "url": "https://geodesy.noaa.gov/api/nde/",
     "coverage": "USA", "access": "Free", "api": "JSON (pid/bounds/radial)", "feasibility": "High", "verified": "V"},
    {"category": "Federal", "name": "USGS TNM Access", "url": "https://tnmaccess.nationalmap.gov/api/v1/docs",
     "coverage": "USA", "access": "Free", "api": "REST", "feasibility": "High", "verified": "V"},
    {"category": "Federal", "name": "BLM GLO Records", "url": "https://glorecords.blm.gov/",
     "coverage": "PLSS states", "access": "Free", "api": "None (JS SPA)", "feasibility": "Medium", "verified": "V"},
    {"category": "FL Clerk", "name": "Pinellas Official Records", "url": "https://officialrecords.mypinellasclerk.gov/",
     "coverage": "Pinellas", "access": "Free guest", "api": "None (Acclaim)", "feasibility": "Medium", "verified": "V"},
    {"category": "FL Clerk", "name": "Broward Official Records", "url": "https://officialrecords.broward.org/AcclaimWeb/",
     "coverage": "Broward", "access": "Free + FTP bulk", "api": "FTP feed", "feasibility": "High", "verified": "V"},
    {"category": "FL Clerk", "name": "Orange Official Records", "url": "https://or.occompt.com/recorder/web/",
     "coverage": "Orange", "access": "Free", "api": "None (Tyler Eagle)", "feasibility": "Medium", "verified": "V"},
    {"category": "FL Clerk", "name": "Miami-Dade Official Records", "url": "https://onlineservices.miamidadeclerk.gov/officialrecords/StandardSearch.aspx",
     "coverage": "Miami-Dade", "access": "Free; paid bulk", "api": "None", "feasibility": "Medium", "verified": "V"},
    {"category": "FL Appraiser", "name": "Miami-Dade GIS REST", "url": "https://gisweb.miamidade.gov/arcgis/rest/services",
     "coverage": "Miami-Dade", "access": "Free", "api": "ArcGIS REST", "feasibility": "High", "verified": "V"},
    {"category": "FL Appraiser", "name": "Pinellas eGIS REST", "url": "https://egis.pinellas.gov/gis/rest/services",
     "coverage": "Pinellas", "access": "Free", "api": "ArcGIS REST", "feasibility": "High", "verified": "V"},
    {"category": "FL Statewide", "name": "FGIO Geodata Portal", "url": "https://geodata.floridagio.gov",
     "coverage": "All 67 FL counties", "access": "Free", "api": "Feature services + bulk", "feasibility": "High", "verified": "R"},
    {"category": "FL Statewide", "name": "FL DOR Statewide Cadastral (parcels)",
     "url": "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0",
     "coverage": "All 67 FL counties (~10.8M parcels)", "access": "Free", "api": "ArcGIS FeatureServer (point query)",
     "feasibility": "High", "verified": "V"},
    {"category": "Aggregator", "name": "NETROnline directory", "url": "https://publicrecords.netronline.com/",
     "coverage": "All US counties", "access": "Free", "api": "None (directory)", "feasibility": "High", "verified": "V"},
    {"category": "Aggregator", "name": "Regrid", "url": "https://regrid.com",
     "coverage": "Nationwide parcels", "access": "Paid API", "api": "Parcel API", "feasibility": "High", "verified": "R"},
    {"category": "Aggregator", "name": "MapWise", "url": "https://www.mapwise.com",
     "coverage": "Florida", "access": "Paid (trial)", "api": "Documented API", "feasibility": "High", "verified": "V"},
    {"category": "Zoning", "name": "Municode", "url": "https://library.municode.com/fl",
     "coverage": "Most FL municipalities", "access": "Free", "api": "None (stable URLs)", "feasibility": "Medium", "verified": "R"},
]
