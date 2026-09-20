"""
App-wide configuration: environment variables and file paths.
Centralizing this avoids every module re-reading .env or re-deriving paths.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# app/config.py -> app/ -> backend/  (two parents up from this file)
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# Only needed to run scripts/fetch_india_mpa_data.py (Marine Protected Area
# geofencing setup - see PROJECT_CONTEXT.md Section 14o for why this data
# is fetched live via Protected Planet's API rather than committed to the
# repo). Not required for the main app to run.
PROTECTEDPLANET_API_TOKEN = os.environ.get("PROTECTEDPLANET_API_TOKEN")

DATA_DIR = Path(__file__).resolve().parent / "data"
MARINE_DATA_PATH = DATA_DIR / "marine_data.json"

# Used only when a live API is unreachable AND there's no per-city mock
# value (e.g. for a freshly geocoded, non-demo city).
DEFAULT_WIND_SPEED_KMPH = 15.0
DEFAULT_WAVE_HEIGHT_M = 1.0
DEFAULT_SST_C = 28.0

# Open-Meteo WMO weather codes for thunderstorm activity
THUNDERSTORM_CODES = {95, 96, 99}

# generate_candidate_routes() (route_engine.py) builds routes via straight-
# line interpolation + a perpendicular bend - a reasonable approximation for
# realistic short coastal/fishing-zone trips, but it breaks down over long
# distances since India's coastline curves significantly, producing routes
# that cut directly across land. 200km is chosen as the ceiling because it
# already represents roughly a full working day one-way at this app's own
# small-fishing-vessel speed assumption (estimate_travel_time_minutes()'s
# 15 km/h -> 200km takes ~13.3 hours), well beyond what a small-scale
# fishing vessel (this app's target user, per the FAO safety-at-sea
# document - see PROJECT_CONTEXT.md Section 14m) would realistically travel
# point-to-point. Beyond this, ORCA should say so honestly rather than
# silently generating a nonsensical land-crossing route.
MAX_REALISTIC_ROUTE_DISTANCE_KM = 200.0
