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

DATA_DIR = Path(__file__).resolve().parent / "data"
MARINE_DATA_PATH = DATA_DIR / "marine_data.json"

# Used only when a live API is unreachable AND there's no per-city mock
# value (e.g. for a freshly geocoded, non-demo city).
DEFAULT_WIND_SPEED_KMPH = 15.0
DEFAULT_WAVE_HEIGHT_M = 1.0
DEFAULT_SST_C = 28.0

# Open-Meteo WMO weather codes for thunderstorm activity
THUNDERSTORM_CODES = {95, 96, 99}
