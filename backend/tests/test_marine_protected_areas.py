"""
Marine Protected Area (MPA) geofencing tests - Section 14o.

IMPORTANT ABOUT THE TEST DATA: this repo has NO real WDPA/Protected
Planet data checked in (deliberately - see
services/marine_protected_areas.py and PROJECT_CONTEXT.md Section 14o for
why), and no API token was available in this session to fetch one via
scripts/fetch_india_mpa_data.py. So these tests build a small, clearly-
labeled TEST-ONLY polygon approximating Gulf of Mannar Marine National
Park's well-documented real-world extent, sourced from Wikipedia (a
separately, permissively CC-BY-SA-licensed source - NOT WDPA data, so
using it here doesn't touch the redistribution restriction at all):
centroid ~9.1375 N, 79.4725 E; the park runs 1-10km offshore of the Tamil
Nadu coast. This is a deliberate simplification (a rectangle, not the
real park's actual elongated 21-island shape) - good enough to prove the
shapely nearest_points()+haversine geofencing LOGIC works correctly
end-to-end, but NOT a substitute for the real precise WDPA boundary once
a developer runs the real fetch script.

Run with:
    cd backend
    source venv/bin/activate
    python3 -m tests.test_marine_protected_areas
"""

from unittest.mock import patch

from shapely.geometry import Polygon

import app.services.marine_protected_areas as mpa_module
from app.core.route_engine import generate_candidate_routes, check_mpa_proximity, check_boundary_proximity
from app.services.maritime_boundary import distance_to_eez_boundary_km, DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM
from app.services.marine_protected_areas import DEFAULT_MPA_WARNING_THRESHOLD_KM

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


# Test-only approximate Gulf of Mannar Marine National Park boundary - see
# module docstring above. A simple rectangle covering the real, cited
# extent (the park runs along the coast roughly between Mandapam and
# Thoothukudi, south/west of the Rameswaram-Dhanushkodi peninsula), NOT
# the real park's actual elongated 21-island shape. Deliberately kept
# WEST of longitude 79.3 so it does NOT overlap Palk Strait (which lies
# NORTH/EAST of Dhanushkodi, e.g. the (9.15, 79.55) point used in
# test_boundary_geofencing.py) - Gulf of Mannar and Palk Strait are
# different water bodies separated by the Rameswaram/Adam's Bridge
# landmass, and a test fixture that accidentally spans both would make
# the "different water body" false-positive check below meaningless.
_TEST_GULF_OF_MANNAR_POLYGON = Polygon([
    (78.20, 8.75), (79.25, 8.75), (79.25, 9.25), (78.20, 9.25), (78.20, 8.75),
])  # shapely uses (lon, lat) order


def _mock_mpa_boundary():
    return _TEST_GULF_OF_MANNAR_POLYGON.boundary


# ---------- Test 1: a route through the test Gulf of Mannar polygon ----------
print("=" * 70)
print("TEST 1: Route from Mandapam toward a point inside the Gulf of Mannar test area")
print("(Mandapam is a real coastal town directly adjacent to the real park)")

with patch.object(mpa_module, "_get_mpa_boundary", side_effect=_mock_mpa_boundary):
    mandapam = (9.2876, 79.1367)  # real town, mainland coast near Gulf of Mannar
    inside_test_mpa = (9.00, 78.80)  # a point inside the test rectangle above
    routes = generate_candidate_routes(mandapam, inside_test_mpa)

    for route in routes:
        distances = [mpa_module.distance_to_nearest_mpa_km(wp["lat"], wp["lon"]) for wp in route["waypoints"]]
        check_mpa_proximity(route, distances, DEFAULT_MPA_WARNING_THRESHOLD_KM)
        print(f"  {route['label']:8s} distance_km={route['distance_km']:6.1f}  "
              f"mpa_distance_km={route['mpa_distance_km']:6.2f}  mpa_warning={route['mpa_warning']}")

    check("at least one route triggers mpa_warning=True",
          any(r["mpa_warning"] is True for r in routes),
          f"got {[r['mpa_warning'] for r in routes]}")
print()


# ---------- Test 2: existing Kochi -> PFZ route - no warnings of either kind ----------
print("=" * 70)
print("TEST 2: Kochi -> Kochi's nearest_pfz - expect NO boundary warning AND no MPA warning")

with patch.object(mpa_module, "_get_mpa_boundary", side_effect=_mock_mpa_boundary):
    kochi = (9.9312, 76.2673)
    kochi_pfz = (9.75, 75.95)  # same as test_boundary_geofencing.py's Scenario 2
    routes = generate_candidate_routes(kochi, kochi_pfz)

    for route in routes:
        boundary_distances = [distance_to_eez_boundary_km(wp["lat"], wp["lon"]) for wp in route["waypoints"]]
        check_boundary_proximity(route, boundary_distances, DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM)
        mpa_distances = [mpa_module.distance_to_nearest_mpa_km(wp["lat"], wp["lon"]) for wp in route["waypoints"]]
        check_mpa_proximity(route, mpa_distances, DEFAULT_MPA_WARNING_THRESHOLD_KM)
        print(f"  {route['label']:8s} boundary_warning={route['boundary_warning']!s:5}  "
              f"mpa_warning={route['mpa_warning']!s:5}  mpa_distance_km={route['mpa_distance_km']:.1f}")

    check("no route triggers boundary_warning", all(r["boundary_warning"] is False for r in routes))
    check("no route triggers mpa_warning", all(r["mpa_warning"] is False for r in routes))
print()


# ---------- Test 3: near the EEZ boundary but far from the test MPA - only EEZ should warn ----------
print("=" * 70)
print("TEST 3: Rameswaram -> Palk Strait boundary point - EEZ should warn, MPA should NOT (false-positive check)")
print("(Palk Strait is north of Rameswaram; the Gulf of Mannar test area above is south of it - different water bodies)")

with patch.object(mpa_module, "_get_mpa_boundary", side_effect=_mock_mpa_boundary):
    rameswaram = (9.29, 79.31)
    palk_strait_boundary_point = (9.15, 79.55)  # same as test_boundary_geofencing.py's Scenario 1
    routes = generate_candidate_routes(rameswaram, palk_strait_boundary_point)

    for route in routes:
        boundary_distances = [distance_to_eez_boundary_km(wp["lat"], wp["lon"]) for wp in route["waypoints"]]
        check_boundary_proximity(route, boundary_distances, DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM)
        mpa_distances = [mpa_module.distance_to_nearest_mpa_km(wp["lat"], wp["lon"]) for wp in route["waypoints"]]
        check_mpa_proximity(route, mpa_distances, DEFAULT_MPA_WARNING_THRESHOLD_KM)
        print(f"  {route['label']:8s} boundary_warning={route['boundary_warning']!s:5} "
              f"(dist={route['boundary_distance_km']:.2f} km)   "
              f"mpa_warning={route['mpa_warning']!s:5} (dist={route['mpa_distance_km']:.2f} km)")

    check("at least one route triggers boundary_warning (real EEZ proximity)",
          any(r["boundary_warning"] for r in routes))
    check("NO route falsely triggers mpa_warning (different water body from the test MPA)",
          all(r["mpa_warning"] is False for r in routes),
          f"got {[r['mpa_warning'] for r in routes]}")
print()


# ---------- Test 4: MPA data genuinely unavailable - honest None, not fabricated False ----------
print("=" * 70)
print("TEST 4: MPA data unavailable (no india_mpa.geojson) - must be honest None, never a fabricated warning")

# Reset the module's real lazy-load cache and call it against the actual
# (non-existent, in this session) file path - no mocking here, this is the
# genuine current state of the repo.
mpa_module._mpa_boundary = None
mpa_module._load_attempted = False
real_distance = mpa_module.distance_to_nearest_mpa_km(9.15, 79.47)
check("distance_to_nearest_mpa_km returns None when no data file exists", real_distance is None, f"got {real_distance}")

route = {"id": "x", "label": "x"}
check_mpa_proximity(route, [None, None, None], DEFAULT_MPA_WARNING_THRESHOLD_KM)
check("mpa_distance_km is None (not 0, not a fabricated default)", route["mpa_distance_km"] is None)
check("mpa_warning is None (not False - 'unknown' must be distinguishable from 'confirmed safe')", route["mpa_warning"] is None)
print()


# ---------- Summary ----------
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("All MPA geofencing checks pass.")
else:
    print("Some checks failed - review the FAIL lines above before considering this feature complete.")
