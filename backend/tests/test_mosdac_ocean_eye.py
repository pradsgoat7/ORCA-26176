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

# Guard against `times` being None (a live MOSDAC outage - see Test 1's
# results above) so this test reports a clean FAIL and the suite
# continues into Tests 3-5, rather than crashing the whole script with an
# unhandled TypeError on `today in times`. Tests 4/5 verify this task's
# actual fix independently of live server availability and must still run.
if times:
    today = _pick_time_for_offset(0)
    tomorrow = _pick_time_for_offset(1)
    check("today's picked time is one of the valid times", today in times, f"got {today}")
    check("tomorrow's picked time is one of the valid times", tomorrow in times, f"got {tomorrow}")
    check("tomorrow's picked time differs from today's", tomorrow != today, f"today={today} tomorrow={tomorrow}")
else:
    check("today's picked time is one of the valid times", False, "skipped - no valid times (live MOSDAC outage)")
    check("tomorrow's picked time is one of the valid times", False, "skipped - no valid times (live MOSDAC outage)")
    check("tomorrow's picked time differs from today's", False, "skipped - no valid times (live MOSDAC outage)")
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

# Section 14v: ocean_agent now calls the single parallel fetch_all()
# orchestrator (imported as fetch_mosdac_all) instead of the 4 individual
# functions one after another - patch that single call site instead,
# still following the Section 6d "patch at the importing module" pattern.
with patch.object(ocean_module, "fetch_mosdac_all", return_value={
    "temperature_c": None, "salinity_psu": None,
    "mixed_layer_depth_m": None, "current_speed_ms": None,
}):
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

# ---------- Test 5: a slow/hanging MOSDAC server must not stack sequentially ----------
print("=" * 70)
print("TEST 5: simulated slow/hanging MOSDAC point queries - Section 14v's real reliability bug")
print("(every _query_point() call already had its own 10s requests.get() timeout BEFORE this")
print(" task - the actual bug was ocean_agent calling 4 functions [5 underlying point queries,")
print(" since current speed needs east+north separately] one after another, so a merely-SLOW")
print(" MOSDAC server - not even a full outage - could stack up to ~50s of sequential waiting,")
print(" comfortably past the frontend's 35s hard timeout, despite every request already having")
print(" an explicit timeout the whole time)")

import time as time_module
import requests as requests_module

import app.services.mosdac_ocean_eye as mosdac_module

SIMULATED_DELAY_S = 2.0  # short enough to keep this suite fast; long enough to clearly tell parallel from sequential

# Pre-populate the capabilities cache directly so this scenario tests
# EXACTLY the part of the bug being fixed (the 5 point queries) without
# also depending on mocking the separate GetCapabilities call.
mosdac_module._capabilities_cache = {"times": ["2026-09-24T00:00:00.000Z"], "fetched_at": time_module.monotonic()}


def slow_hanging_get(*args, **kwargs):
    time_module.sleep(SIMULATED_DELAY_S)
    raise requests_module.exceptions.Timeout("simulated slow/hanging MOSDAC response")


with patch.object(mosdac_module.requests, "get", side_effect=slow_hanging_get):
    start = time_module.monotonic()
    result = mosdac_module.fetch_all(KOCHI_LAT, KOCHI_LON)
    elapsed = time_module.monotonic() - start

print(f"  elapsed: {elapsed:.1f}s for 5 simulated-slow point queries (each 'takes' {SIMULATED_DELAY_S}s before failing)")
print(f"  result: {result}")
check("fetch_all() returns honest None for every field when every query times out (no crash)",
      all(v is None for v in result.values()), f"got {result}")
check(f"total elapsed time stays close to ONE delay period (~{SIMULATED_DELAY_S}s) rather than the sum "
      f"of all 5 point queries (~{5 * SIMULATED_DELAY_S:.0f}s) - proves the queries run in PARALLEL now, "
      f"not stacked sequentially like before this fix",
      elapsed < SIMULATED_DELAY_S * 2.5,
      f"got {elapsed:.1f}s - a sequential-bug regression would produce ~{5 * SIMULATED_DELAY_S:.0f}s")

mosdac_module._capabilities_cache = {"times": None, "fetched_at": 0.0}  # reset for any test that runs after this
print()

# ---------- Summary ----------
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("All MOSDAC Ocean-Eye integration checks pass.")
else:
    print("Some checks failed - review the FAIL lines above before considering this feature complete.")
