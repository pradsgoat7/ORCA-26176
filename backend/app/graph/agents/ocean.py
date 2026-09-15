"""
Ocean agent - fetches live wave height (Open-Meteo) and live current/
temperature/salinity/mixed-layer-depth (MOSDAC Ocean-Eye) for the resolved
location and requested day, falling back to generic mock values if a live
API is unreachable. Chlorophyll stays mock always (no free live source
exists).

Wave height is DELIBERATELY untouched by the MOSDAC integration - MOSDAC's
own wave product (SAC_OSF_WAVE_10KM.nc) was verified stale (stuck almost
5 months behind), so it stays on Open-Meteo entirely. Only sea surface
temperature now prefers MOSDAC (verified live) over Open-Meteo's marine
API (which doesn't offer SST as a daily forecast value anyway).
"""

from app.config import DEFAULT_SST_C, DEFAULT_WAVE_HEIGHT_M
from app.graph.state import ORCAState
from app.services.mosdac_ocean_eye import (
    fetch_current_speed_ms,
    fetch_mixed_layer_depth_m,
    fetch_ocean_temperature_c,
    fetch_salinity_psu,
)
from app.services.weather_api import fetch_live_marine


def ocean_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return {"ocean": None}
    loc = state["location_data"]
    day_offset = state.get("day_offset", 0)
    lat, lon = loc["lat"], loc["lon"]

    live = fetch_live_marine(lat, lon, day_offset)
    mosdac_temp = fetch_ocean_temperature_c(lat, lon, day_offset)
    mosdac_salinity = fetch_salinity_psu(lat, lon, day_offset)
    mosdac_mld = fetch_mixed_layer_depth_m(lat, lon, day_offset)
    mosdac_current = fetch_current_speed_ms(lat, lon, day_offset)

    if mosdac_temp is not None:
        sst = round(mosdac_temp, 2)
    elif live and live.get("sea_surface_temp_c") is not None:
        sst = round(live["sea_surface_temp_c"], 2)
    else:
        sst = DEFAULT_SST_C

    if live and live.get("wave_height_m") is not None:
        wave_height = round(live["wave_height_m"], 2)
        ocean_source = "live"
    else:
        wave_height = DEFAULT_WAVE_HEIGHT_M
        ocean_source = "mock"

    ocean = {
        "sea_surface_temp_c": sst,
        "chlorophyll_mg_m3": loc["chlorophyll_mg_m3"],  # still mock - may be None for non-demo cities
        "wave_height_m": wave_height,
        "salinity_psu": round(mosdac_salinity, 2) if mosdac_salinity is not None else None,
        "current_speed_ms": round(mosdac_current, 3) if mosdac_current is not None else None,
        "mixed_layer_depth_m": round(mosdac_mld, 2) if mosdac_mld is not None else None,
        "ocean_source": ocean_source,
    }
    return {"ocean": ocean}
