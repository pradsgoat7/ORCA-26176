"""
MOSDAC Ocean-Eye integration test - verifies the live WMS point-query
functions in services/mosdac_ocean_eye.py, the day_offset -> timestamp
picking logic, the end-to-end wiring into ocean_agent/run_query(), and the
graceful-fallback behaviour when MOSDAC is unreachable.

Run with:
    cd backend
    source venv/bin/activate
    python3 -m tests.test_mosdac_ocean_eye
"""

from unittest.mock import patch

import app.graph.agents.ocean as ocean_module
from app.graph.workflow import run_query
from app.services.mosdac_ocean_eye import (
    _get_valid_times,
    _pick_time_for_offset,
    fetch_current_speed_ms,
    fetch_mixed_layer_depth_m,
    fetch_ocean_temperature_c,
    fetch_salinity_psu,
)

passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {label}")
        passed += 1
    else:
        print(f"  FAIL: {label} {detail}")
        failed += 1


KOCHI_LAT, KOCHI_LON = 9.9312, 76.2673

# ---------- Test 1: individual live functions against Kochi ----------
print("=" * 70)
print("TEST 1: Individual MOSDAC functions - real calls, Kochi")

temp = fetch_ocean_temperature_c(KOCHI_LAT, KOCHI_LON)
print(f"  temp = {temp}")
check("temp is a plausible SST (10-35 C)", temp is not None and 10 <= temp <= 35, f"got {temp}")

salinity = fetch_salinity_psu(KOCHI_LAT, KOCHI_LON)
print(f"  salinity = {salinity}")
check("salinity is plausible (20-40 psu)", salinity is not None and 20 <= salinity <= 40, f"got {salinity}")

mld = fetch_mixed_layer_depth_m(KOCHI_LAT, KOCHI_LON)
print(f"  mixed_layer_depth_m = {mld}")
check("MLD is plausible (0-200 m)", mld is not None and 0 <= mld <= 200, f"got {mld}")

current = fetch_current_speed_ms(KOCHI_LAT, KOCHI_LON)
print(f"  current_speed_ms = {current}")
check("current speed is plausible (0-3 m/s, not cm/s-scale)", current is not None and 0 <= current <= 3, f"got {current}")
print()

# ---------- Test 2: day_offset picks a sensible forecast timestamp ----------
print("=" * 70)
print("TEST 2: day_offset -> timestamp selection")

times = _get_valid_times()
check("GetCapabilities returned a non-empty time extent", bool(times), f"got {times}")

today = _pick_time_for_offset(0)
tomorrow = _pick_time_for_offset(1)
check("today's picked time is one of the valid times", today in times, f"got {today}")
check("tomorrow's picked time is one of the valid times", tomorrow in times, f"got {tomorrow}")
check("tomorrow's picked time differs from today's", tomorrow != today, f"today={today} tomorrow={tomorrow}")
print()

# ---------- Test 3: full ocean_agent / run_query() end-to-end ----------
print("=" * 70)
print("TEST 3: run_query() end-to-end - new ocean fields populated")

r = run_query("Is it safe to fish near Kochi today?")
ocean = r["ocean"]
print(f"  ocean = {ocean}")
check("ocean dict present", ocean is not None)
check("salinity_psu populated", ocean.get("salinity_psu") is not None, f"got {ocean}")
check("current_speed_ms populated", ocean.get("current_speed_ms") is not None, f"got {ocean}")
check("mixed_layer_depth_m populated", ocean.get("mixed_layer_depth_m") is not None, f"got {ocean}")
check("sea_surface_temp_c populated (MOSDAC-preferred)", ocean.get("sea_surface_temp_c") is not None, f"got {ocean}")
check("wave_height_m untouched (still Open-Meteo)", ocean.get("wave_height_m") is not None, f"got {ocean}")
check("risk engine still ran", r["risk"] is not None)
print()

# ---------- Test 4: MOSDAC unreachable -> graceful fallback, no crash ----------
print("=" * 70)
print("TEST 4: MOSDAC outage - graceful fallback (mocked at the importing module)")

with patch.object(ocean_module, "fetch_ocean_temperature_c", return_value=None), \
     patch.object(ocean_module, "fetch_salinity_psu", return_value=None), \
     patch.object(ocean_module, "fetch_mixed_layer_depth_m", return_value=None), \
     patch.object(ocean_module, "fetch_current_speed_ms", return_value=None):
    r_outage = run_query("Is it safe to fish near Kochi today?")

ocean_outage = r_outage["ocean"]
print(f"  ocean during outage = {ocean_outage}")
check("no crash - result still returned", r_outage is not None)
check("salinity_psu falls back to None (no mock exists for it)", ocean_outage.get("salinity_psu") is None)
check("current_speed_ms falls back to None", ocean_outage.get("current_speed_ms") is None)
check("mixed_layer_depth_m falls back to None", ocean_outage.get("mixed_layer_depth_m") is None)
check("sea_surface_temp_c still falls back to a mock/live default", ocean_outage.get("sea_surface_temp_c") is not None)
check("risk engine still ran during outage", r_outage["risk"] is not None)
print()

# ---------- Summary ----------
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("All MOSDAC Ocean-Eye integration checks pass.")
else:
    print("Some checks failed - review the FAIL lines above before considering this feature complete.")
