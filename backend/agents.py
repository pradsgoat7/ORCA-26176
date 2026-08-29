"""
ORCA agents - each function below represents one "specialist agent".
They are plain Python functions wired together with LangGraph so the
Planner -> Weather/Ocean/Risk/Geospatial -> Synthesis flow is explicit
and easy to explain to judges.
"""

import json
import math
import os
import re
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypedDict, Optional

from dotenv import load_dotenv
load_dotenv()  # reads the .env file in the backend folder and loads it into os.environ

from langgraph.graph import StateGraph, END

from risk_engine import calculate_all_metrics

DATA_PATH = Path(__file__).parent / "data" / "marine_data.json"

with open(DATA_PATH, "r") as f:
    MARINE_DATA = json.load(f)["locations"]

# Native-script aliases so location matching works regardless of the
# language the user typed in. Extend this as you add more demo cities.
LOCATION_ALIASES = {
    "kochi": ["kochi", "cochin", "कोच्चि", "कोची"],
    "chennai": ["chennai", "madras", "चेन्नई"],
    "visakhapatnam": ["visakhapatnam", "vizag", "विशाखापत्तनम", "विशाखापट्टणम"],
}

# Hardcoded fallback phrases so the demo stays multilingual even when the
# Gemini API is unavailable and we can't dynamically translate.
FALLBACK_STRINGS = {
    "en": {
        "unknown_location": "Sorry, {error} Try mentioning a coastal town like Kochi, Chennai, or Visakhapatnam.",
        "main_line": "For {location}: conditions are rated '{level}'. Reasons: {reasons}.",
        "pfz_line": "Nearest fishing zone: {pfz_name} ({pfz_distance} km away).",
        "no_pfz": "No specific fishing zone advisory is available for this location in the current prototype dataset.",
    },
    "hi": {
        "unknown_location": "क्षमा करें, {error} कृपया कोच्चि, चेन्नई, या विशाखापत्तनम जैसे तटीय शहर का उल्लेख करें।",
        "main_line": "{location} के लिए: स्थिति '{level}' आंकी गई है। कारण: {reasons}।",
        "pfz_line": "निकटतम मछली पकड़ने का क्षेत्र: {pfz_name} ({pfz_distance} किमी दूर)।",
        "no_pfz": "इस स्थान के लिए वर्तमान प्रोटोटाइप डेटा में कोई विशेष मछली पकड़ने का क्षेत्र सलाह उपलब्ध नहीं है।",
    },
    "mr": {
        "unknown_location": "क्षमस्व, {error} कृपया कोची, चेन्नई, किंवा विशाखापट्टणम यासारख्या किनारपट्टीच्या शहराचा उल्लेख करा.",
        "main_line": "{location} साठी: परिस्थिती '{level}' अशी आहे. कारणे: {reasons}.",
        "pfz_line": "जवळचे मासेमारी क्षेत्र: {pfz_name} ({pfz_distance} किमी अंतरावर).",
        "no_pfz": "या ठिकाणासाठी सध्याच्या प्रोटोटाइप डेटामध्ये कोणतीही विशिष्ट मासेमारी क्षेत्र सल्ला उपलब्ध नाही.",
    },
}

RISK_LEVEL_TRANSLATIONS = {
    "en": {"safe": "SAFE", "caution": "CAUTION", "unsafe": "UNSAFE"},
    "hi": {"safe": "सुरक्षित", "caution": "सावधानी", "unsafe": "असुरक्षित"},
    "mr": {"safe": "सुरक्षित", "caution": "सावधगिरी", "unsafe": "असुरक्षित"},
}


def detect_language(text: str) -> str:
    """Lightweight heuristic language detection - good enough to pick the
    right fallback template and location aliases without needing an API
    call. Devanagari script covers both Hindi and Marathi, so we use a
    couple of common Marathi-specific words to disambiguate; Gemini
    (when available) will still produce a fully natural response in
    whichever language the query is actually in, since it understands
    the query directly rather than relying on this heuristic."""
    marathi_markers = ["आहे", "का ", "आहेत"]
    if any(marker in text for marker in marathi_markers):
        return "mr"
    if any("\u0900" <= ch <= "\u097F" for ch in text):  # Devanagari block
        return "hi"
    return "en"


# Rough reference points spanning India's coastline (plus a couple of
# neighboring coastal cities), used only to sanity-check that a geocoded
# location is actually near the sea. We don't have real coastline geometry
# data, so this is a pragmatic distance-based heuristic, not a precise
# land/water boundary - documented as a known limitation.
COASTAL_REFERENCE_POINTS = [
    ("Kandla", 23.03, 70.22),
    ("Surat", 21.17, 72.83),
    ("Mumbai", 18.94, 72.84),
    ("Ratnagiri", 17.0, 73.3),
    ("Goa", 15.5, 73.8),
    ("Mangalore", 12.9, 74.8),
    ("Kochi", 9.93, 76.27),
    ("Thiruvananthapuram", 8.5, 76.9),
    ("Chennai", 13.08, 80.27),
    ("Puducherry", 11.9, 79.8),
    ("Visakhapatnam", 17.69, 83.22),
    ("Paradip", 20.3, 86.6),
    ("Digha", 21.6, 87.5),
    ("Karachi", 24.86, 67.0),
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def is_near_coast(lat: float, lon: float, max_km: float = 120.0) -> bool:
    """True if within max_km of any reference coastal point. This is what
    prevents nonsense like 'safe to fish in Kashmir' - Open-Meteo's marine
    model apparently still returns some interpolated wave value even for
    landlocked, mountainous coordinates, so we can't rely on the marine API
    itself to reject a bad location - we have to check ourselves."""
    return any(
        _haversine_km(lat, lon, ref_lat, ref_lon) <= max_km
        for _, ref_lat, ref_lon in COASTAL_REFERENCE_POINTS
    )


def geocode_location(name: str) -> Optional[dict]:
    """Resolves ANY location name to coordinates via Open-Meteo's free
    geocoding API - not just our 3 hardcoded demo cities. Returns None on
    failure so the caller can fall back to the 'unknown location' error.

    Includes a sanity check: Open-Meteo's geocoding does fuzzy text search,
    not exact matching, so nonsense input like 'hii' can return a real but
    completely unrelated place (this actually happened - it matched 'Lake
    Havasu City'). Rejecting results where the first few letters don't
    match catches this without needing real NLP."""
    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": name, "count": 1, "language": "en", "format": "json"},
            timeout=8,
        )
        resp.raise_for_status()
        results = resp.json().get("results")
        if not results:
            return None
        r = results[0]
        result_name = r["name"]

        prefix_len = min(3, len(name))
        if result_name.lower()[:prefix_len] != name.lower()[:prefix_len]:
            return None  # fuzzy match drifted too far from the input - reject it

        return {"name": result_name, "lat": r["latitude"], "lon": r["longitude"]}
    except Exception:
        return None


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


# Used only when the live weather API is unreachable AND we have no
# per-city mock value (i.e. for a freshly geocoded, non-demo city).
DEFAULT_WIND_SPEED_KMPH = 15.0
DEFAULT_WAVE_HEIGHT_M = 1.0
DEFAULT_SST_C = 28.0

# Open-Meteo WMO weather codes for thunderstorm activity
THUNDERSTORM_CODES = {95, 96, 99}


# ---------- Live data fetchers (Open-Meteo - free, no API key needed) ----------
def fetch_live_wind(lat: float, lon: float, day_offset: int = 0) -> Optional[dict]:
    """Real wind/precipitation/weather-code forecast for a SPECIFIC day
    (day_offset=0 is today, 1 is tomorrow, etc.), not just 'right now'.
    Returns None on any failure - including the requested day being beyond
    Open-Meteo's forecast horizon - so callers fall back to mock data
    without the demo ever breaking."""
    try:
        forecast_days = min(max(day_offset + 1, 1), 16)
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "wind_speed_10m_max,precipitation_sum,weather_code",
                "wind_speed_unit": "kmh",
                "forecast_days": forecast_days,
            },
            timeout=8,
        )
        resp.raise_for_status()
        daily = resp.json()["daily"]
        return {
            "wind_speed_kmph": daily["wind_speed_10m_max"][day_offset],
            "precipitation_mm": daily["precipitation_sum"][day_offset],
            "weather_code": daily["weather_code"][day_offset],
        }
    except Exception:
        return None


def fetch_live_marine(lat: float, lon: float, day_offset: int = 0) -> Optional[dict]:
    """Real wave height forecast for a specific day. Sea surface temperature
    isn't offered as a daily forecast value by this API (only 'current'),
    so it stays as a mock/default value even when wave height is live -
    that's reflected honestly rather than silently guessed."""
    try:
        forecast_days = min(max(day_offset + 1, 1), 16)
        resp = requests.get(
            "https://marine-api.open-meteo.com/v1/marine",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "wave_height_max",
                "forecast_days": forecast_days,
            },
            timeout=8,
        )
        resp.raise_for_status()
        daily = resp.json()["daily"]
        return {
            "wave_height_m": daily["wave_height_max"][day_offset],
            "sea_surface_temp_c": None,  # not available as a daily forecast value
        }
    except Exception:
        return None


# ---------- Shared state passed between agents ----------
class ORCAState(TypedDict, total=False):
    query: str
    language: str
    day_offset: int
    stakeholder: Optional[dict]
    location_key: Optional[str]
    location_data: Optional[dict]
    weather: Optional[dict]
    ocean: Optional[dict]
    risk: Optional[dict]
    geospatial: Optional[dict]
    answer: Optional[str]
    error: Optional[str]


# ---------- Language detection node (runs first) ----------
def language_node(state: ORCAState) -> ORCAState:
    lang = detect_language(state["query"])
    return {"language": lang}


# ---------- Stakeholder detection ----------
# Keyword sets mined from the spec's own example concerns per stakeholder.
# English-primary for coast_guard/disaster_management (the spec's own examples
# are English-only for those two); fisherman includes Hindi/Marathi terms
# since that's explicitly required by the test scenarios.
STAKEHOLDER_KEYWORDS = {
    "fisherman": [
        "fish", "fishing", "fisherman", "catch", "pfz", "potential fishing zone",
        "go fishing", "safe to fish", "should i fish", "should i go",
        "venture into the sea", "offshore fishing", "wave conditions",
        "fishing zone", "fishing suitability",
        "मछली", "मासेमारी", "पकड़ना",
    ],
    "coast_guard": [
        "coast guard", "monitoring", "patrol", "vessels in danger",
        "rescue", "rescue readiness", "maritime risk", "operational hazard",
        "emergency resources", "increased monitoring", "increased patrol",
        "vessel", "coastal sector", "response priority",
    ],
    "disaster_management": [
        "disaster", "preparedness", "emergency response", "hazard level",
        "warning", "advisory", "at risk", "immediate preparedness",
        "regional risk", "coastal regions at risk", "evacuat",
        "require preparedness", "disaster risk",
    ],
}


def detect_stakeholder(query: str) -> dict:
    """Deterministic keyword-scoring classifier - not an LLM call, so it's
    free, instant, and doesn't compete with Gemini's rate limit. Picks the
    category with the most keyword hits; ties broken by dict order
    (fisherman > coast_guard > disaster_management). Returns 'general'
    with low confidence if nothing matches, per the spec's requirement to
    never force an incorrect classification."""
    query_lower = query.lower()
    scores = {}
    for stakeholder_type, keywords in STAKEHOLDER_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw.lower() in query_lower or kw in query)
        scores[stakeholder_type] = count

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score == 0:
        return {"type": "general", "confidence": 0.5}

    confidence = min(0.95, 0.55 + 0.15 * best_score)
    return {"type": best_type, "confidence": round(confidence, 2)}


def stakeholder_agent(state: ORCAState) -> ORCAState:
    # Runs regardless of location-resolution errors - a query like "Which
    # coastal areas require immediate preparedness?" has no specific city
    # at all, but should still classify correctly.
    return {"stakeholder": detect_stakeholder(state["query"])}


# ---------- Planner agent ----------
def planner_agent(state: ORCAState) -> ORCAState:
    """Figures out which location the user is asking about.
    Checks our 3 known demo cities first (native-script aliases included,
    so Hindi/Marathi queries resolve correctly). If it's not one of those,
    tries live geocoding so ANY city can work, not just the 3 hardcoded
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


# ---------- Weather agent ----------
def weather_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return {"weather": None}
    loc = state["location_data"]
    day_offset = state.get("day_offset", 0)
    forecast_date = (datetime.utcnow() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
    live = fetch_live_wind(loc["lat"], loc["lon"], day_offset)

    if live:
        lightning_live = live.get("weather_code") in THUNDERSTORM_CODES
        weather = {
            "wind_speed_kmph": round(live["wind_speed_kmph"], 1),
            "cyclone_alert": loc["cyclone_alert"],   # still mock - no free live cyclone-alert API
            "cyclone_name": loc.get("cyclone_name"),
            "lightning_alert": lightning_live,        # now live-derived from real weather code!
            "wind_source": "live",
            "lightning_source": "live",
            "forecast_date": forecast_date,
        }
    else:
        weather = {
            "wind_speed_kmph": DEFAULT_WIND_SPEED_KMPH,
            "cyclone_alert": loc["cyclone_alert"],
            "cyclone_name": loc.get("cyclone_name"),
            "lightning_alert": False,
            "wind_source": "mock",
            "lightning_source": "mock",
            "forecast_date": forecast_date,
        }
    return {"weather": weather}


# ---------- Ocean agent ----------
def ocean_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return {"ocean": None}
    loc = state["location_data"]
    day_offset = state.get("day_offset", 0)
    live = fetch_live_marine(loc["lat"], loc["lon"], day_offset)

    if live and live.get("wave_height_m") is not None:
        ocean = {
            "sea_surface_temp_c": live.get("sea_surface_temp_c") if live.get("sea_surface_temp_c") is not None else DEFAULT_SST_C,
            "chlorophyll_mg_m3": loc["chlorophyll_mg_m3"],  # still mock - may be None for non-demo cities
            "wave_height_m": round(live["wave_height_m"], 2),
            "ocean_source": "live",
        }
    else:
        ocean = {
            "sea_surface_temp_c": DEFAULT_SST_C,
            "chlorophyll_mg_m3": loc["chlorophyll_mg_m3"],
            "wave_height_m": DEFAULT_WAVE_HEIGHT_M,
            "ocean_source": "mock",
        }
    return {"ocean": ocean}


# ---------- Risk agent ----------
def risk_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return {"risk": None}
    weather = state["weather"]
    ocean = state["ocean"]

    reasons = []
    score = 0  # higher = riskier

    if weather["cyclone_alert"]:
        score += 3
        reasons.append(f"Active cyclone alert: {weather.get('cyclone_name', 'unnamed system')}")
    if weather["lightning_alert"]:
        score += 2
        reasons.append("Lightning alert in the area")
    if ocean["wave_height_m"] > 2.0:
        score += 2
        reasons.append(f"High wave height ({ocean['wave_height_m']} m)")
    if weather["wind_speed_kmph"] > 30:
        score += 1
        reasons.append(f"Strong winds ({weather['wind_speed_kmph']} km/h)")

    if score >= 3:
        level = "unsafe"
    elif score >= 1:
        level = "caution"
    else:
        level = "safe"

    if not reasons:
        reasons.append("No significant hazards detected")

    # Phase 2/3 addition: deterministic structured metrics + stakeholder-
    # weighted overall score, computed independently of the legacy score
    # above. Added alongside the existing level/score/reasons - nothing
    # existing changes, so the frontend, fallback templates, and API keep
    # working unmodified.
    stakeholder_info = state.get("stakeholder") or {}
    stakeholder_type = stakeholder_info.get("type", "general")
    structured = calculate_all_metrics(weather, ocean, stakeholder_type)

    return {
        "risk": {
            "level": level,
            "score": score,
            "reasons": reasons,
            "metrics": structured["metrics"],
            "structured_reasons": structured["reasons"],
            "overall_score": structured["overall_score"],
            "overall_level": structured["overall_level"],
            "recommendation": structured["recommendation"],
        }
    }


# ---------- Geospatial agent ----------
def geospatial_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return {"geospatial": None}
    loc = state["location_data"]
    geo = {
        "location_name": loc["name"],
        "location_coords": {"lat": loc["lat"], "lon": loc["lon"]},
        "nearest_pfz": loc.get("nearest_pfz"),  # may be None for non-demo cities
    }
    return {"geospatial": geo}


# ---------- Synthesis agent (LLM-powered, with a multilingual fallback) ----------
LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}

STAKEHOLDER_PERSONAS = {
    "fisherman": "a marine safety assistant helping a fisherman decide whether it's safe to go out to sea",
    "coast_guard": "a maritime operations assistant briefing a Coast Guard officer on operational risk and monitoring needs",
    "disaster_management": "a disaster-preparedness assistant briefing a disaster management official on regional hazard and preparedness needs",
    "general": "a marine intelligence assistant giving a general audience an overview of current marine conditions",
}

DATA_SOURCE_NOTES = {
    "en": {"live": "(live weather/wave data)", "mock": "(demo weather/wave data)"},
    "hi": {"live": "(वास्तविक मौसम/लहर डेटा)", "mock": "(डेमो मौसम/लहर डेटा)"},
    "mr": {"live": "(प्रत्यक्ष हवामान/लाट डेटा)", "mock": "(डेमो हवामान/लाट डेटा)"},
}


def _data_source_note(state: ORCAState) -> str:
    lang = state.get("language", "en")
    notes = DATA_SOURCE_NOTES.get(lang, DATA_SOURCE_NOTES["en"])
    weather_live = (state.get("weather") or {}).get("wind_source") == "live"
    ocean_live = (state.get("ocean") or {}).get("ocean_source") == "live"
    # Only claim "live" if BOTH wind and wave data actually came from the API this time
    return notes["live"] if (weather_live and ocean_live) else notes["mock"]


def _build_fallback_answer(state: ORCAState) -> str:
    lang = state.get("language", "en")
    strings = FALLBACK_STRINGS.get(lang, FALLBACK_STRINGS["en"])

    if state.get("error"):
        return strings["unknown_location"].format(error=state["error"])

    risk = state["risk"]
    geo = state["geospatial"]
    level_translated = RISK_LEVEL_TRANSLATIONS.get(lang, RISK_LEVEL_TRANSLATIONS["en"])[risk["level"]]

    main_line = strings["main_line"].format(
        location=geo["location_name"],
        level=level_translated,
        reasons="; ".join(risk["reasons"]),
    )

    pfz = geo.get("nearest_pfz")
    if pfz:
        pfz_line = strings["pfz_line"].format(pfz_name=pfz["name"], pfz_distance=pfz["distance_km"])
    else:
        pfz_line = strings["no_pfz"]

    return f"{main_line} {pfz_line} {_data_source_note(state)}"


def synthesis_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return {"answer": _build_fallback_answer(state)}

    api_key = os.environ.get("GOOGLE_API_KEY")

    if not api_key:
        print("[ORCA] No GOOGLE_API_KEY found in environment - using fallback template.")
        return {"answer": _build_fallback_answer(state)}

    try:
        language_name = LANGUAGE_NAMES.get(state.get("language", "en"), "English")
        pfz_data = state["geospatial"].get("nearest_pfz")
        if pfz_data:
            pfz_text = f"{pfz_data['name']}, located {pfz_data['distance_km']} km away"
        else:
            pfz_text = "Not available for this location in the prototype dataset."

        stakeholder_type = (state.get("stakeholder") or {}).get("type", "general")
        persona = STAKEHOLDER_PERSONAS.get(stakeholder_type, STAKEHOLDER_PERSONAS["general"])

        risk = state["risk"]
        metrics_text = "\n".join(f"- {m['name']}: {m['score']}/100" for m in risk.get("metrics", []))
        reasons_text = "\n".join(f"- {r['factor']}: {r['reason']}" for r in risk.get("structured_reasons", []))

        prompt = f"""You are {persona}. Based ONLY on the exact data below, write a short, clear,
friendly answer (3-4 sentences) to the user's question.

STRICT RULES - the numbers below come from a deterministic risk engine, not from you:
- Use the EXACT overall risk score and level given below. Never invent, change, or round it differently.
- Never claim a hazard exists if its score is 0 (for example, if Cyclone Risk is 0, do not mention any
  cyclone threat at all).
- Never contradict the overall level (for example, do not call something "safe" if the level is HIGH or
  CRITICAL, or vice versa).
- You may explain WHY the score is what it is using the reasons provided, but never add a hazard that
  isn't listed below.

IMPORTANT: The user's query is in {language_name}. You must respond entirely in {language_name},
using natural, everyday phrasing a local speaker would use - not a stiff literal translation.

User question: {state['query']}
Location: {state['geospatial']['location_name']}

Overall Risk Score: {risk.get('overall_score')}/100 ({risk.get('overall_level')})
Recommendation: {risk.get('recommendation')}

Individual risk metrics:
{metrics_text}

Contributing factors:
{reasons_text if reasons_text else '- No significant hazards detected'}

Nearest fishing zone: {pfz_text}
"""

        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "thinkingConfig": {"thinkingLevel": "low"},  # keeps latency low for a live demo
                "maxOutputTokens": 1024,
            },
        }
        # Hard timeout: if the API is ever slow, fail fast into the instant
        # rule-based fallback below rather than making the user stare at a
        # spinner for 40+ seconds during the live pitch.
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        answer = data["candidates"][0]["content"]["parts"][0]["text"]
        return {"answer": f"{answer} {_data_source_note(state)}"}
    except Exception as e:
        # Never let an API hiccup kill the live demo - but DO print the
        # real reason, so a silent failure never has to be guessed at again.
        print(f"[ORCA] Gemini synthesis failed, using fallback: {e}")
        return {"answer": _build_fallback_answer(state)}


# ---------- Build the LangGraph ----------
def build_graph():
    graph = StateGraph(ORCAState)
    graph.add_node("language_node", language_node)
    graph.add_node("planner_node", planner_agent)
    graph.add_node("stakeholder_node", stakeholder_agent)
    graph.add_node("weather_node", weather_agent)
    graph.add_node("ocean_node", ocean_agent)
    graph.add_node("risk_node", risk_agent)
    graph.add_node("geospatial_node", geospatial_agent)
    graph.add_node("synthesis_node", synthesis_agent)

    graph.set_entry_point("language_node")
    graph.add_edge("language_node", "planner_node")

    # Fan-out: the Planner dispatches to all three specialist agents at once,
    # each running independently off the Planner's output.
    graph.add_edge("planner_node", "weather_node")
    graph.add_edge("planner_node", "ocean_node")
    graph.add_edge("planner_node", "geospatial_node")
    graph.add_edge("planner_node", "stakeholder_node")

    # Risk agent acts as the sync point: it only reasons over weather+ocean
    # data, but waiting on all three edges (including geospatial) means it
    # only fires once every specialist has genuinely finished - avoiding a
    # race where Synthesis could start before every agent has reported back.
    graph.add_edge("weather_node", "risk_node")
    graph.add_edge("ocean_node", "risk_node")
    graph.add_edge("geospatial_node", "risk_node")
    graph.add_edge("stakeholder_node", "risk_node")

    graph.add_edge("risk_node", "synthesis_node")
    graph.add_edge("synthesis_node", END)

    return graph.compile()


orca_graph = build_graph()


def run_query(query: str) -> ORCAState:
    initial_state: ORCAState = {"query": query}
    result = orca_graph.invoke(initial_state)
    return result