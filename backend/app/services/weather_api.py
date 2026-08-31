"""
Live environmental data fetchers - Open-Meteo (free, no API key needed).
Every part of ORCA that needs live weather/wave data (the main chat
pipeline, the zone risk map, route sampling) calls through these two
functions, so there's exactly one place that talks to Open-Meteo.
"""

from typing import Optional

import requests

from app.config import THUNDERSTORM_CODES  # re-exported for convenience


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
