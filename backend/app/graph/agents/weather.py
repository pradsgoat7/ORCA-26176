"""
Weather agent - fetches live wind/lightning data for the resolved
location and requested day, falling back to generic mock values if the
live API is unreachable.
"""

from datetime import datetime, timedelta

from app.config import DEFAULT_WIND_SPEED_KMPH, THUNDERSTORM_CODES
from app.graph.state import ORCAState
from app.services.weather_api import fetch_live_wind


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
