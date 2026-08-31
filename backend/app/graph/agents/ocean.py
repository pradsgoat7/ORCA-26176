"""
Ocean agent - fetches live wave height for the resolved location and
requested day, falling back to generic mock values if the live API is
unreachable. Chlorophyll stays mock always (no free live source exists).
"""

from app.config import DEFAULT_SST_C, DEFAULT_WAVE_HEIGHT_M
from app.graph.state import ORCAState
from app.services.weather_api import fetch_live_marine


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
