"""
Synthesis agent - produces the final natural-language answer. Uses Gemini
when available, with a fully deterministic multilingual fallback template
so the demo never breaks without an API key or if the call fails/times out.
Route requests skip Gemini entirely, since their answer is built
deterministically from the already-computed route plan (see
app.api.routes._build_route_answer) and would otherwise waste API quota
on an answer that gets thrown away.
"""

import requests

from app.config import GOOGLE_API_KEY
from app.graph.state import ORCAState

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

    # Route requests get their user-facing answer built deterministically
    # from the already-computed route plan (see app.api.routes). Skip the
    # Gemini call entirely here - it would just generate an unrelated
    # fishing-safety answer about the origin city that gets thrown away
    # anyway, wasting API quota for nothing.
    if (state.get("route_request") or {}).get("is_route_request"):
        return {"answer": "(route recommendation - see route details)"}

    if not GOOGLE_API_KEY:
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
        headers = {"x-goog-api-key": GOOGLE_API_KEY, "Content-Type": "application/json"}
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
