"""
Route planning agent - the Marine Route Optimization feature. Resolves
origin/destination (reusing existing location resolution and PFZ data,
never inventing coordinates), generates candidate routes, samples live
environmental data along each, and scores every route using the EXISTING
Risk Engine - not a second/duplicate risk system.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from app.config import DEFAULT_WIND_SPEED_KMPH, DEFAULT_WAVE_HEIGHT_M, THUNDERSTORM_CODES
from app.core.risk_engine import calculate_all_metrics, classify_level
from app.core.route_engine import (
    generate_candidate_routes, estimate_travel_time_minutes,
    score_route, select_recommended_route, build_route_explanation,
)
from app.data.loader import MARINE_DATA, LOCATION_ALIASES
from app.graph.state import ORCAState
from app.services.geocoding import geocode_location, is_near_coast
from app.services.weather_api import fetch_live_wind, fetch_live_marine


def _resolve_named_location(text: str) -> Optional[dict]:
    """Shared helper: resolves a place name to {lat, lon, name} using the
    exact same known-city/geocoding/coastal-check pipeline the main planner
    uses - never a separate location source."""
    text_lower = text.lower()
    for key, aliases in LOCATION_ALIASES.items():
        if any(alias in text_lower for alias in aliases):
            loc = MARINE_DATA[key]
            return {"lat": loc["lat"], "lon": loc["lon"], "name": loc["name"]}

    geo = geocode_location(text)
    if geo and is_near_coast(geo["lat"], geo["lon"]):
        return {"lat": geo["lat"], "lon": geo["lon"], "name": geo["name"]}
    return None


def resolve_route_endpoints(route_req: dict, location_data: Optional[dict]) -> dict:
    """Resolves origin/destination coordinates for a route request. Never
    invents coordinates - returns {'error': ...} when something genuinely
    can't be determined, per the spec's explicit requirement."""
    origin_text = route_req.get("origin_text")
    if origin_text:
        origin = _resolve_named_location(origin_text)
    elif location_data:
        # No explicit "from X" - fall back to whatever location the main
        # query already resolved (e.g. "give me a safe route to the PFZ"
        # implies "from where I'm already asking about").
        origin = {"lat": location_data["lat"], "lon": location_data["lon"], "name": location_data["name"]}
    else:
        origin = None

    if not origin:
        if origin_text:
            return {"error": f"I couldn't find '{origin_text}' as a known coastal location for this route. "
                              f"Try mentioning a coastal town, e.g. 'route from Kochi to the fishing zone'."}
        return {"error": "I couldn't determine a starting location for this route. "
                          "Try mentioning a coastal town, e.g. 'route from Kochi to the fishing zone'."}

    if route_req.get("destination_is_pfz"):
        # Reuse the EXISTING PFZ data tied to the resolved origin - never a
        # separate/fabricated data source, per the spec.
        pfz = (location_data or {}).get("nearest_pfz")
        if not pfz:
            return {"error": f"No fishing zone (PFZ) data is available for {origin['name']} "
                              f"in the current prototype dataset, so a route there can't be calculated."}
        destination = {"lat": pfz["lat"], "lon": pfz["lon"], "name": pfz["name"]}
    else:
        dest_text = route_req.get("destination_text")
        destination = _resolve_named_location(dest_text) if dest_text else None

    if not destination:
        return {"error": f"I don't have coordinates for the destination "
                          f"('{route_req.get('destination_text') or 'unspecified'}') in this prototype, "
                          f"so I can't calculate a route there. Try asking for a route to a coastal "
                          f"town or 'the fishing zone'."}

    return {"origin": origin, "destination": destination}


def _lookup_cyclone_alert(name: str) -> tuple:
    """Returns (cyclone_alert, cyclone_name) if this location name matches
    one of our known demo cities' mock data; otherwise (False, None), since
    there's no live cyclone source to check for other locations - never
    fabricated, per the spec's explicit requirement."""
    for loc in MARINE_DATA.values():
        if loc["name"] == name:
            return loc.get("cyclone_alert", False), loc.get("cyclone_name")
    return False, None


def route_planning_agent(state: ORCAState) -> ORCAState:
    """Generates candidate routes, samples live environmental conditions
    along each, and scores every route by running every sample through
    the EXISTING Risk Engine (calculate_all_metrics) - not a second/
    duplicate risk system - then picks a recommended route using
    route_engine's pure comparison logic. Runs only when
    route_detection_agent flagged a route request; every other query
    gets route_plan=None at essentially zero cost."""
    route_req = state.get("route_request") or {}
    if not route_req.get("is_route_request"):
        return {"route_plan": None}

    endpoints = resolve_route_endpoints(route_req, state.get("location_data"))
    if "error" in endpoints:
        return {"route_plan": {"error": endpoints["error"], "candidate_routes": []}}

    origin = (endpoints["origin"]["lat"], endpoints["origin"]["lon"])
    destination = (endpoints["destination"]["lat"], endpoints["destination"]["lon"])
    candidate_routes = generate_candidate_routes(origin, destination)

    # Flatten (route, waypoint) pairs so environmental sampling can run in
    # parallel across ALL of them - 3 routes x 5 waypoints x 2 live calls
    # sequentially would be 30 blocking network calls per route request.
    def sample_waypoint(wp):
        live_wind = fetch_live_wind(wp["lat"], wp["lon"])
        live_marine = fetch_live_marine(wp["lat"], wp["lon"])
        wind_speed = live_wind["wind_speed_kmph"] if live_wind else DEFAULT_WIND_SPEED_KMPH
        wave_height = (
            live_marine["wave_height_m"]
            if (live_marine and live_marine.get("wave_height_m") is not None)
            else DEFAULT_WAVE_HEIGHT_M
        )
        lightning = live_wind.get("weather_code") in THUNDERSTORM_CODES if live_wind else False
        data_source = "live" if (live_wind and live_marine and live_marine.get("wave_height_m") is not None) else "mock"
        return {
            "lat": wp["lat"], "lon": wp["lon"],
            "wind_speed_kmph": wind_speed, "wave_height_m": wave_height,
            "lightning_alert": lightning, "data_source": data_source,
        }

    all_waypoints = [wp for route in candidate_routes for wp in route["waypoints"]]
    with ThreadPoolExecutor(max_workers=min(len(all_waypoints), 15)) as executor:
        all_samples = list(executor.map(sample_waypoint, all_waypoints))

    # Cyclone status has no live per-point source - reuse whatever mock
    # data applies to the actual endpoints being routed between, rather
    # than fabricating a value for arbitrary waypoints along the way.
    origin_cyclone, origin_cyclone_name = _lookup_cyclone_alert(endpoints["origin"]["name"])
    dest_cyclone, dest_cyclone_name = _lookup_cyclone_alert(endpoints["destination"]["name"])
    route_cyclone_alert = origin_cyclone or dest_cyclone
    route_cyclone_name = origin_cyclone_name or dest_cyclone_name

    stakeholder_type = (state.get("stakeholder") or {}).get("type", "general")

    # Reassign sampled results back to their routes, then run EVERY sample
    # through the existing Risk Engine and aggregate to a route-level score.
    idx = 0
    for route in candidate_routes:
        n = len(route["waypoints"])
        samples = all_samples[idx:idx + n]
        route["samples"] = samples
        route["travel_time_min"] = estimate_travel_time_minutes(route["distance_km"])
        idx += n

        sample_overall_scores = []
        sample_metrics_lists = []
        for s in samples:
            weather = {
                "wind_speed_kmph": s["wind_speed_kmph"],
                "cyclone_alert": route_cyclone_alert,
                "cyclone_name": route_cyclone_name,
                "lightning_alert": s["lightning_alert"],
            }
            ocean = {"wave_height_m": s["wave_height_m"]}
            structured = calculate_all_metrics(weather, ocean, stakeholder_type)
            sample_overall_scores.append(structured["overall_score"])
            sample_metrics_lists.append(structured["metrics"])

        score_route(route, sample_overall_scores, sample_metrics_lists)
        route["route_risk_level"] = classify_level(route["route_risk_score"])

    recommended = select_recommended_route(candidate_routes)
    explanation = build_route_explanation(recommended, candidate_routes)

    return {
        "route_plan": {
            "error": None,
            "origin": endpoints["origin"],
            "destination": endpoints["destination"],
            "candidate_routes": candidate_routes,
            "recommended_route_id": recommended["id"],
            "explanation": explanation,
        }
    }
