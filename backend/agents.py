"""
ORCA agents - each function below represents one "specialist agent".
They are plain Python functions wired together with LangGraph so the
Planner -> Weather/Ocean/Risk/Geospatial -> Synthesis flow is explicit
and easy to explain to judges.
"""

import json
import os
from pathlib import Path
from typing import TypedDict, Optional

from dotenv import load_dotenv
load_dotenv()  # reads the .env file in the backend folder and loads it into os.environ

from langgraph.graph import StateGraph, END

DATA_PATH = Path(__file__).parent / "data" / "marine_data.json"

with open(DATA_PATH, "r") as f:
    MARINE_DATA = json.load(f)["locations"]


# ---------- Shared state passed between agents ----------
class ORCAState(TypedDict, total=False):
    query: str
    location_key: Optional[str]
    location_data: Optional[dict]
    weather: Optional[dict]
    ocean: Optional[dict]
    risk: Optional[dict]
    geospatial: Optional[dict]
    answer: Optional[str]
    error: Optional[str]


# ---------- Planner agent ----------
def planner_agent(state: ORCAState) -> ORCAState:
    """Figures out which location the user is asking about.
    Simple keyword match for the hackathon demo - swap for an LLM call
    later if you want free-form location extraction."""
    query_lower = state["query"].lower()
    matched = None
    for key in MARINE_DATA.keys():
        if key in query_lower:
            matched = key
            break

    if not matched:
        return {**state, "error": "Could not identify a known location in the query."}

    return {**state, "location_key": matched, "location_data": MARINE_DATA[matched]}


# ---------- Weather agent ----------
def weather_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return state
    loc = state["location_data"]
    weather = {
        "wind_speed_kmph": loc["wind_speed_kmph"],
        "cyclone_alert": loc["cyclone_alert"],
        "cyclone_name": loc.get("cyclone_name"),
        "lightning_alert": loc["lightning_alert"],
    }
    return {**state, "weather": weather}


# ---------- Ocean agent ----------
def ocean_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return state
    loc = state["location_data"]
    ocean = {
        "sea_surface_temp_c": loc["sea_surface_temp_c"],
        "chlorophyll_mg_m3": loc["chlorophyll_mg_m3"],
        "wave_height_m": loc["wave_height_m"],
    }
    return {**state, "ocean": ocean}


# ---------- Risk agent ----------
def risk_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return state
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

    return {**state, "risk": {"level": level, "score": score, "reasons": reasons}}


# ---------- Geospatial agent ----------
def geospatial_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return state
    loc = state["location_data"]
    geo = {
        "location_name": loc["name"],
        "location_coords": {"lat": loc["lat"], "lon": loc["lon"]},
        "nearest_pfz": loc["nearest_pfz"],
    }
    return {**state, "geospatial": geo}


# ---------- Synthesis agent (LLM-powered, with a safe fallback) ----------
def synthesis_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return {**state, "answer": f"Sorry, {state['error']} Try mentioning a coastal town like Kochi, Chennai, or Visakhapatnam."}

    api_key = os.environ.get("GOOGLE_API_KEY")

    if not api_key:
        # Rule-based fallback so the demo never breaks without a key
        risk = state["risk"]
        geo = state["geospatial"]
        answer = (
            f"For {geo['location_name']}: conditions are rated '{risk['level'].upper()}'. "
            f"Reasons: {'; '.join(risk['reasons'])}. "
            f"Nearest fishing zone: {geo['nearest_pfz']['name']} "
            f"({geo['nearest_pfz']['distance_km']} km away)."
        )
        return {**state, "answer": answer}

    try:
        import requests

        prompt = f"""You are a marine safety assistant for fishermen. Based on this data, write a short,
clear, friendly answer (3-4 sentences) to the user's question. Mention the safety verdict,
the key reasons, and the nearest fishing zone. Keep it simple, no jargon.

User question: {state['query']}
Location: {state['geospatial']['location_name']}
Weather: {state['weather']}
Ocean conditions: {state['ocean']}
Risk assessment: {state['risk']}
Nearest fishing zone: {state['geospatial']['nearest_pfz']}
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
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        answer = data["candidates"][0]["content"]["parts"][0]["text"]
        return {**state, "answer": answer}
    except Exception as e:
        # Never let an API hiccup kill the live demo
        risk = state["risk"]
        geo = state["geospatial"]
        answer = (
            f"[Fallback - LLM call failed: {e}] "
            f"For {geo['location_name']}: conditions are rated '{risk['level'].upper()}'. "
            f"Reasons: {'; '.join(risk['reasons'])}."
        )
        return {**state, "answer": answer}


# ---------- Build the LangGraph ----------
def build_graph():
    graph = StateGraph(ORCAState)
    graph.add_node("planner_node", planner_agent)
    graph.add_node("weather_node", weather_agent)
    graph.add_node("ocean_node", ocean_agent)
    graph.add_node("risk_node", risk_agent)
    graph.add_node("geospatial_node", geospatial_agent)
    graph.add_node("synthesis_node", synthesis_agent)

    graph.set_entry_point("planner_node")
    graph.add_edge("planner_node", "weather_node")
    graph.add_edge("weather_node", "ocean_node")
    graph.add_edge("ocean_node", "risk_node")
    graph.add_edge("risk_node", "geospatial_node")
    graph.add_edge("geospatial_node", "synthesis_node")
    graph.add_edge("synthesis_node", END)

    return graph.compile()


orca_graph = build_graph()


def run_query(query: str) -> ORCAState:
    initial_state: ORCAState = {"query": query}
    result = orca_graph.invoke(initial_state)
    return result