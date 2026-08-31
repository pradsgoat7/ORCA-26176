"""
Risk Zones (map heatmap feature). Not a LangGraph node - called directly
by the /zones API endpoint. Deliberately reuses the exact same live
fetchers and the exact same Risk Engine that the main chat pipeline uses;
this is NOT a second/duplicate risk calculation system, just a batch
caller of the same underlying pieces across multiple locations at once.
"""

from concurrent.futures import ThreadPoolExecutor

from app.config import DEFAULT_WIND_SPEED_KMPH, DEFAULT_WAVE_HEIGHT_M, THUNDERSTORM_CODES
from app.core.risk_engine import calculate_all_metrics
from app.data.loader import MARINE_DATA
from app.services.weather_api import fetch_live_wind, fetch_live_marine


def _compute_zone_risk(loc: dict, stakeholder_type: str) -> dict:
    """Computes risk for a single zone - extracted so get_zone_risks can run
    this across all zones in parallel instead of one at a time."""
    live_wind = fetch_live_wind(loc["lat"], loc["lon"])
    live_marine = fetch_live_marine(loc["lat"], loc["lon"])

    if live_wind:
        wind_speed = live_wind["wind_speed_kmph"]
        lightning = live_wind.get("weather_code") in THUNDERSTORM_CODES
        wind_source = "live"
    else:
        wind_speed = DEFAULT_WIND_SPEED_KMPH
        lightning = False
        wind_source = "mock"

    if live_marine and live_marine.get("wave_height_m") is not None:
        wave_height = live_marine["wave_height_m"]
        ocean_source = "live"
    else:
        wave_height = DEFAULT_WAVE_HEIGHT_M
        ocean_source = "mock"

    weather = {
        "wind_speed_kmph": wind_speed,
        "cyclone_alert": loc["cyclone_alert"],
        "cyclone_name": loc.get("cyclone_name"),
        "lightning_alert": lightning,
    }
    ocean = {"wave_height_m": wave_height}

    # The actual Risk Engine call - same function the chat pipeline uses.
    structured = calculate_all_metrics(weather, ocean, stakeholder_type)

    # Primary driver = the highest-scoring individual metric, if any
    # hazard is actually present.
    top_metric = max(structured["metrics"], key=lambda m: m["score"])
    primary_driver = top_metric["name"] if top_metric["score"] > 0 else "No significant hazard"

    return {
        "name": loc["name"],
        "lat": loc["lat"],
        "lon": loc["lon"],
        "overall_score": structured["overall_score"],
        "overall_level": structured["overall_level"],
        "primary_driver": primary_driver,
        "wave_height_m": wave_height,
        "wind_speed_kmph": wind_speed,
        "recommendation": structured["recommendation"],
        "data_source": "live" if (wind_source == "live" and ocean_source == "live") else "mock",
        "has_data": True,
    }


def get_zone_risks(stakeholder_type: str = "general") -> list:
    """Computes current risk for each of ORCA's known coastal zones, for the
    map's multi-zone visualization.

    Runs across all zones IN PARALLEL via a thread pool - with 25 zones,
    each needing 2 live HTTP calls, doing this sequentially would mean 50
    requests one after another and a genuinely slow map. Each request is
    I/O-bound (waiting on the network), so threads give a real speedup here
    despite Python's GIL."""
    locations = list(MARINE_DATA.values())
    with ThreadPoolExecutor(max_workers=min(len(locations), 15)) as executor:
        zones = list(executor.map(lambda loc: _compute_zone_risk(loc, stakeholder_type), locations))

    return zones
