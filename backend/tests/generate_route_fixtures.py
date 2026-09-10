"""
Regenerates frontend/tests/route_fixtures.json - real route_field JSON for
the frontend boundary-warning UI test (test_boundary_warning_ui.js).

Runs the EXACT SAME pipeline route_planning_agent.py uses (live weather
sampling included, real network calls to Open-Meteo) for two scenarios,
then passes the result through the real _build_route_field() from
routes.py - so the frontend test consumes literally the same shape/values
the live /ask endpoint would produce, never hand-typed fake JSON. See
PROJECT_CONTEXT.md Section 14e.

Not run as part of the normal test suite (it hits the network and its
output is meant to be a stable, committed fixture, not regenerated on
every run) - only re-run this deliberately if the route response shape
changes, or to refresh the live-data-derived risk numbers.

Usage:
    cd backend
    source venv/bin/activate
    python3 -m tests.generate_route_fixtures
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.api.routes import _build_route_field
from app.config import BACKEND_DIR, DEFAULT_WIND_SPEED_KMPH, DEFAULT_WAVE_HEIGHT_M, THUNDERSTORM_CODES
from app.core.risk_engine import calculate_all_metrics, classify_level
from app.core.route_engine import (
    generate_candidate_routes, estimate_travel_time_minutes,
    score_route, select_recommended_route, build_route_explanation,
    check_boundary_proximity,
)
from app.services.maritime_boundary import distance_to_eez_boundary_km, DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM
from app.services.weather_api import fetch_live_wind, fetch_live_marine

OUTPUT_PATH = BACKEND_DIR.parent / "frontend" / "tests" / "route_fixtures.json"


def build_route_plan(origin: dict, destination: dict, stakeholder_type: str = "fisherman") -> dict:
    """Mirrors route_planning_agent's logic exactly (same functions, same
    order) so the fixture is indistinguishable from a real API response -
    just run standalone with hand-picked origin/destination instead of
    going through NL query parsing."""
    candidate_routes = generate_candidate_routes(
        (origin["lat"], origin["lon"]), (destination["lat"], destination["lon"])
    )

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
        return {"lat": wp["lat"], "lon": wp["lon"], "wind_speed_kmph": wind_speed,
                "wave_height_m": wave_height, "lightning_alert": lightning}

    all_waypoints = [wp for route in candidate_routes for wp in route["waypoints"]]
    with ThreadPoolExecutor(max_workers=min(len(all_waypoints), 15)) as executor:
        all_samples = list(executor.map(sample_waypoint, all_waypoints))

    idx = 0
    for route in candidate_routes:
        n = len(route["waypoints"])
        samples = all_samples[idx:idx + n]
        route["travel_time_min"] = estimate_travel_time_minutes(route["distance_km"])
        idx += n

        sample_overall_scores, sample_metrics_lists = [], []
        for s in samples:
            weather = {"wind_speed_kmph": s["wind_speed_kmph"], "cyclone_alert": False,
                       "cyclone_name": None, "lightning_alert": s["lightning_alert"]}
            ocean = {"wave_height_m": s["wave_height_m"]}
            structured = calculate_all_metrics(weather, ocean, stakeholder_type)
            sample_overall_scores.append(structured["overall_score"])
            sample_metrics_lists.append(structured["metrics"])

        score_route(route, sample_overall_scores, sample_metrics_lists)
        route["route_risk_level"] = classify_level(route["route_risk_score"])

        waypoint_boundary_distances = [
            distance_to_eez_boundary_km(wp["lat"], wp["lon"]) for wp in route["waypoints"]
        ]
        check_boundary_proximity(route, waypoint_boundary_distances, DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM)

    recommended = select_recommended_route(candidate_routes)
    explanation = build_route_explanation(recommended, candidate_routes)

    return {
        "error": None, "origin": origin, "destination": destination,
        "candidate_routes": candidate_routes,
        "recommended_route_id": recommended["id"], "explanation": explanation,
    }


SCENARIOS = {
    # Rameswaram -> a point in the Palk Strait right at the India-Sri Lanka
    # EEZ line - the same stretch of water where Indian fishermen actually
    # crossing into Sri Lankan waters is a real, frequently-reported
    # problem, so this is a realistic "should warn" case.
    "boundary_warning": {
        "origin": {"lat": 9.29, "lon": 79.31, "name": "Rameswaram"},
        "destination": {"lat": 9.15, "lon": 79.55, "name": "Palk Strait waypoint (India-Sri Lanka EEZ boundary, demo)"},
    },
    # Kochi -> Kochi's existing nearest_pfz from marine_data.json - the
    # task's own suggested known-good, clearly-safe route.
    "no_warning": {
        "origin": {"lat": 9.9312, "lon": 76.2673, "name": "Kochi"},
        "destination": {"lat": 9.75, "lon": 75.95, "name": "PFZ near Kochi coast"},
    },
}

if __name__ == "__main__":
    fixtures = {}
    for key, s in SCENARIOS.items():
        route_plan = build_route_plan(s["origin"], s["destination"])
        route_field = _build_route_field({"route_plan": route_plan})
        fixtures[key] = route_field
        print(f"=== {key} ===")
        for r in route_field["candidate_routes"]:
            print(f"  {r['id']:12s} risk={r['route_risk_score']:3d}({r['route_risk_level']:8s}) "
                  f"boundary_warning={r['boundary_warning']!s:5s} boundary_distance_km={r['boundary_distance_km']}")
        print(f"  recommended_route_id={route_field['recommended_route_id']}")
        print()

    OUTPUT_PATH.write_text(json.dumps(fixtures, indent=2))
    print(f"Wrote {OUTPUT_PATH}")
