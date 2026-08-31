"""
Loads the marine dataset (mock/demo data for the 25 known coastal cities)
once at import time. Every module that needs MARINE_DATA imports it from
here, so there's a single source of truth for the loaded dict.
"""

import json

from app.config import MARINE_DATA_PATH

with open(MARINE_DATA_PATH, "r") as f:
    MARINE_DATA = json.load(f)["locations"]

# Native-script aliases so location matching works regardless of the
# language the user typed in. Extend this as you add more demo cities.
LOCATION_ALIASES = {
    "kochi": ["kochi", "cochin", "कोच्चि", "कोची"],
    "chennai": ["chennai", "madras", "चेन्नई"],
    "visakhapatnam": ["visakhapatnam", "vizag", "विशाखापत्तनम", "विशाखापट्टणम"],
    # English-only aliases for the newer 22 demo cities - Hindi/Marathi
    # native-script coverage for these is a known gap, matching the same
    # scope limit already documented for non-demo geocoded cities.
    "kandla": ["kandla"],
    "porbandar": ["porbandar"],
    "surat": ["surat"],
    "mumbai": ["mumbai", "bombay"],
    "ratnagiri": ["ratnagiri"],
    "malvan": ["malvan"],
    "goa": ["goa", "panaji", "panjim"],
    "karwar": ["karwar"],
    "mangalore": ["mangalore", "mangaluru"],
    "kozhikode": ["kozhikode", "calicut"],
    "alappuzha": ["alappuzha", "alleppey"],
    "kollam": ["kollam", "quilon"],
    "thiruvananthapuram": ["thiruvananthapuram", "trivandrum"],
    "kanyakumari": ["kanyakumari", "cape comorin"],
    "thoothukudi": ["thoothukudi", "tuticorin"],
    "rameswaram": ["rameswaram"],
    "puducherry": ["puducherry", "pondicherry"],
    "nellore": ["nellore"],
    "kakinada": ["kakinada"],
    "paradip": ["paradip"],
    "puri": ["puri"],
    "digha": ["digha"],
}
