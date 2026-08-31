"""
Planner agent - figures out which coastal location a query is about, and
which day it's asking about. Tries known demo cities first (with
native-script aliases), then falls back to live geocoding for any city.
"""

import re
from typing import Optional

from app.data.loader import MARINE_DATA, LOCATION_ALIASES
from app.graph.state import ORCAState
from app.services.geocoding import geocode_location, is_near_coast

STOPWORDS = {
    "what", "about", "is", "it", "safe", "to", "fish", "should", "i", "go",
    "sea", "today", "tomorrow", "near", "at", "in", "around", "the", "a",
    "an", "of", "for", "conditions", "weather", "and", "or", "will", "be",
    "can", "does", "do", "are", "there", "any", "alerts", "cyclone",
    "lightning", "safe", "unsafe", "please", "check",
    "hi", "hii", "hello", "helloo", "hey", "yo", "ok", "okay", "thanks",
    "thank", "you", "bye", "test", "testing",
}


def extract_location_phrase(query: str) -> Optional[str]:
    """Tries a preposition pattern first ("near X", "at X") with proper word
    boundaries - fixes a real bug where 'at' inside 'what' was matching and
    grabbing the wrong word entirely. Falls back to the last non-stopword
    in the query, which handles casual phrasing like 'what about mumbai'
    that has no preposition before the city name at all."""
    match = re.search(r"\b(?:near|at|in|around)\b\s+([A-Za-z]+)", query, re.IGNORECASE)
    if match:
        return match.group(1)

    words = re.findall(r"[A-Za-z]+", query)
    candidates = [w for w in words if w.lower() not in STOPWORDS]
    return candidates[-1] if candidates else None


def parse_time_offset(query: str) -> int:
    """Figures out how many days in the future the query is asking about,
    so we fetch an actual forecast for that day instead of always returning
    'right now'. Supports English, Hindi, and Marathi common phrasings.
    Defaults to 0 (today) if nothing specific is detected."""
    q_lower = query.lower()

    # "N days later/after" (English)
    match = re.search(r"(\d+)\s*day", q_lower)
    if match:
        return max(int(match.group(1)), 0)

    # "N दिन बाद" (Hindi)
    match = re.search(r"(\d+)\s*दिन", query)
    if match:
        return max(int(match.group(1)), 0)

    # "N दिवसांनी" (Marathi)
    match = re.search(r"(\d+)\s*दिवस", query)
    if match:
        return max(int(match.group(1)), 0)

    if "tomorrow" in q_lower or "कल" in query or "उद्या" in query:
        return 1

    return 0  # today, or no time reference found


def planner_agent(state: ORCAState) -> ORCAState:
    """Figures out which location the user is asking about.
    Checks our known demo cities first (native-script aliases included,
    so Hindi/Marathi queries resolve correctly). If it's not one of those,
    tries live geocoding so ANY city can work, not just the hardcoded
    demo locations - though that city won't have PFZ/chlorophyll data."""
    query = state["query"]
    query_lower = query.lower()
    day_offset = parse_time_offset(query)

    for key, aliases in LOCATION_ALIASES.items():
        if any(alias in query_lower or alias in query for alias in aliases):
            return {"location_key": key, "location_data": MARINE_DATA[key], "day_offset": day_offset}

    phrase = extract_location_phrase(query)
    if phrase:
        geo = geocode_location(phrase)
        if geo:
            if not is_near_coast(geo["lat"], geo["lon"]):
                return {
                    "error": f"{geo['name']} doesn't appear to be a coastal location, "
                             f"so marine fishing/safety advisories don't apply there."
                }
            dynamic_loc = {
                "name": geo["name"],
                "lat": geo["lat"],
                "lon": geo["lon"],
                "chlorophyll_mg_m3": None,   # no free live source, and not a demo city
                "cyclone_alert": False,       # no free live source
                "cyclone_name": None,
                "nearest_pfz": None,          # INCOIS has no public API - no PFZ data for non-demo cities
            }
            return {"location_key": phrase.lower(), "location_data": dynamic_loc, "day_offset": day_offset}

    return {"error": "Could not identify a known location in the query."}
