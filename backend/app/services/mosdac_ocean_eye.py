"""
Live ocean subsurface data from MOSDAC's Ocean-Eye WMS server
(SAC_OSF_CIRC_10KM.nc) - current, temperature, salinity, and mixed layer
depth. Follows the exact same plain-function, return-None-on-failure
pattern as services/weather_api.py, so callers never need to handle
exceptions from this module.

IMPORTANT - verified via real GetFeatureInfo requests in this session
(2026-09-15): MOSDAC also publishes a companion wave file
(SAC_OSF_WAVE_10KM.nc) for significant wave height, but that file's data
was found to be STUCK at 2026-04-26 (nearly 5 months stale) - it is
DELIBERATELY NOT used here. Wave height stays on the existing Open-Meteo
integration in weather_api.py, untouched. Only the CIRC file (current,
temperature, salinity, mixed layer depth) was verified live and
forecast-capable, with real timestamps from today through 5 days ahead in
6-hour steps.
"""

import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional
from xml.etree import ElementTree as ET

import requests

BASE_URL = "https://mosdac.gov.in/live_data/wms/OSF_CIRC/SAC_OSF_CIRC_10KM.nc"

# GetCapabilities doesn't change often - avoid re-fetching it on every
# single point query. 15 minutes is comfortably shorter than the server's
# own 6-hour time-step resolution.
_CAPABILITIES_CACHE_SECONDS = 900
_capabilities_cache = {"times": None, "fetched_at": 0.0}


def _get_valid_times() -> Optional[list]:
    """Returns the server's list of valid ISO8601 TIME values (from
    GetCapabilities' <Extent name="time">), cached briefly. Returns None
    on any failure so callers can fall back cleanly."""
    now = time.monotonic()
    if _capabilities_cache["times"] is not None and (now - _capabilities_cache["fetched_at"]) < _CAPABILITIES_CACHE_SECONDS:
        return _capabilities_cache["times"]
    try:
        resp = requests.get(
            BASE_URL,
            params={"SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetCapabilities"},
            timeout=10,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1]
            if tag == "Extent" and elem.get("name") == "time":
                times = [t.strip() for t in (elem.text or "").split(",") if t.strip()]
                if times:
                    _capabilities_cache["times"] = times
                    _capabilities_cache["fetched_at"] = now
                    return times
        return None
    except Exception:
        return None


def _pick_time_for_offset(day_offset: int) -> Optional[str]:
    """Picks the valid server timestamp closest to 'now + day_offset days',
    rather than guessing an arbitrary date that might not be one of the
    server's actual 6-hourly time steps."""
    times = _get_valid_times()
    if not times:
        return None
    target = datetime.utcnow() + timedelta(days=day_offset)
    best_time, best_diff = None, None
    for t in times:
        try:
            dt = datetime.strptime(t, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            continue
        diff = abs((dt - target).total_seconds())
        if best_diff is None or diff < best_diff:
            best_diff, best_time = diff, t
    return best_time


def _query_point(layer: str, lat: float, lon: float, time_iso: str, elevation: Optional[str] = None) -> Optional[float]:
    """Runs a single GetFeatureInfo point query and parses the <value> tag.
    A missing, non-numeric, or NaN value is treated as a normal failure
    (returns None), not an exception - the server does return NaN for
    points with no data (e.g. land pixels)."""
    try:
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": layer,
            "QUERY_LAYERS": layer,
            "SRS": "EPSG:4326",
            "BBOX": f"{lon - 0.05},{lat - 0.05},{lon + 0.05},{lat + 0.05}",
            "WIDTH": 101,
            "HEIGHT": 101,
            "X": 50,
            "Y": 50,
            "INFO_FORMAT": "text/xml",
            "TIME": time_iso,
        }
        if elevation is not None:
            params["ELEVATION"] = elevation
        resp = requests.get(BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        value_elem = root.find(".//value")
        if value_elem is None or value_elem.text is None:
            return None
        value = float(value_elem.text)
        if math.isnan(value):
            return None
        return value
    except Exception:
        return None


def fetch_ocean_temperature_c(lat: float, lon: float, day_offset: int = 0) -> Optional[float]:
    """Potential temperature at the surface (ELEVATION=-1.0). Units
    confirmed as "deg C" via MOSDAC's own GetMetadata&item=layerDetails
    endpoint for this layer - no conversion needed."""
    time_iso = _pick_time_for_offset(day_offset)
    if time_iso is None:
        return None
    return _query_point("temp", lat, lon, time_iso, elevation="-1.0")


def fetch_salinity_psu(lat: float, lon: float, day_offset: int = 0) -> Optional[float]:
    """Salinity at the surface (ELEVATION=-1.0), in psu - confirmed via
    GetMetadata&item=layerDetails ("units":"psu")."""
    time_iso = _pick_time_for_offset(day_offset)
    if time_iso is None:
        return None
    return _query_point("salinity", lat, lon, time_iso, elevation="-1.0")


def fetch_mixed_layer_depth_m(lat: float, lon: float, day_offset: int = 0) -> Optional[float]:
    """Mixed layer depth in metres. The 'hmxl' layer has no depth axis
    (it's a single 2D field, unlike temp/salinity/current), so no
    ELEVATION param is sent. Confirmed via GetMetadata&item=layerDetails
    that the server reports this layer in CENTIMETRES ("units":"cm") -
    divided by 100 here to return metres."""
    time_iso = _pick_time_for_offset(day_offset)
    if time_iso is None:
        return None
    value_cm = _query_point("hmxl", lat, lon, time_iso)
    if value_cm is None:
        return None
    return value_cm / 100.0


def fetch_current_speed_ms(lat: float, lon: float, day_offset: int = 0) -> Optional[float]:
    """Ocean current speed at the surface (ELEVATION=-1.0), combining the
    eastward and northward vector components as sqrt(east^2 + north^2).

    Unit note: confirmed via MOSDAC's own GetMetadata&item=layerDetails
    endpoint for both 'eastward_ocean_wave_current' and
    'northward_ocean_wave_current' that the server explicitly reports
    "units":"cm/s" for these layers - this is the server's own stated
    unit, not merely inferred from COLORSCALERANGE (which is a generic
    -50..250 default shared across unrelated layers and isn't a reliable
    unit signal on its own). Sanity-checked too: raw values near Kochi
    combine to ~19.8 cm/s (0.198 m/s), a physically realistic open-ocean
    current speed - treating the same raw numbers as m/s would imply an
    implausible ~19.8 m/s current. Divided by 100 here to return m/s.
    """
    time_iso = _pick_time_for_offset(day_offset)
    if time_iso is None:
        return None
    east = _query_point("eastward_ocean_wave_current", lat, lon, time_iso, elevation="-1.0")
    north = _query_point("northward_ocean_wave_current", lat, lon, time_iso, elevation="-1.0")
    if east is None or north is None:
        return None
    speed_cm_s = math.sqrt(east ** 2 + north ** 2)
    return speed_cm_s / 100.0


def fetch_all(lat: float, lon: float, day_offset: int = 0) -> dict:
    """Fetches all four Ocean-Eye fields for one location/day in PARALLEL -
    see PROJECT_CONTEXT.md Section 14v for the real reliability bug this
    fixes. Every individual `_query_point()` call already has its own
    explicit 10s `requests.get()` timeout (present since this module was
    first written) - the actual problem was that `ocean_agent` used to
    call fetch_ocean_temperature_c()/fetch_salinity_psu()/
    fetch_mixed_layer_depth_m()/fetch_current_speed_ms() one after
    another. fetch_current_speed_ms() alone issues TWO sequential
    `_query_point()` calls (east + north), so a single ocean_agent
    invocation could chain up to 6 sequential MOSDAC network calls (1
    GetCapabilities + temp + salinity + hmxl + east-current +
    north-current) - each individually timeout-bounded at 10s, but
    summing to a worst case of ~50-60 seconds if MOSDAC is genuinely slow
    (not even fully down), comfortably exceeding the frontend's 35s hard
    timeout despite every single request having an explicit timeout the
    whole time. Running the point queries CONCURRENTLY via
    ThreadPoolExecutor (the same established pattern
    route_planning_agent's waypoint sampling already uses for exactly
    this kind of "many independent network calls, bound total wall-clock
    time" problem) bounds the worst case to roughly ONE timeout period
    instead of the sum of all of them.

    Returns a dict with keys temperature_c/salinity_psu/
    mixed_layer_depth_m/current_speed_ms, each honestly None on any
    individual failure - never raises, matching every other function in
    this module."""
    time_iso = _pick_time_for_offset(day_offset)
    if time_iso is None:
        # No valid timestamp at all (GetCapabilities itself failed/timed
        # out) - every point query would fail anyway without a TIME value,
        # so fail fast here rather than firing 5 doomed parallel requests.
        return {
            "temperature_c": None,
            "salinity_psu": None,
            "mixed_layer_depth_m": None,
            "current_speed_ms": None,
        }

    with ThreadPoolExecutor(max_workers=5) as executor:
        temp_future = executor.submit(_query_point, "temp", lat, lon, time_iso, "-1.0")
        salinity_future = executor.submit(_query_point, "salinity", lat, lon, time_iso, "-1.0")
        hmxl_future = executor.submit(_query_point, "hmxl", lat, lon, time_iso)
        east_future = executor.submit(_query_point, "eastward_ocean_wave_current", lat, lon, time_iso, "-1.0")
        north_future = executor.submit(_query_point, "northward_ocean_wave_current", lat, lon, time_iso, "-1.0")

        temp = temp_future.result()
        salinity = salinity_future.result()
        hmxl_cm = hmxl_future.result()
        east = east_future.result()
        north = north_future.result()

    mld = (hmxl_cm / 100.0) if hmxl_cm is not None else None
    current = (math.sqrt(east ** 2 + north ** 2) / 100.0) if (east is not None and north is not None) else None

    return {
        "temperature_c": temp,
        "salinity_psu": salinity,
        "mixed_layer_depth_m": mld,
        "current_speed_ms": current,
    }
