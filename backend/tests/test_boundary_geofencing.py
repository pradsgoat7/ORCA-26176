"""
Verifies the maritime boundary geofencing wired into route_engine.py +
route_planning.py (Days 3-4 work, following on from the Day 2 boundary
data sourcing in Section 13c of PROJECT_CONTEXT.md).

Builds routes with route_engine.generate_candidate_routes() - the same
pure, no-network function route_planning_agent uses - then runs the new
check_boundary_proximity() against real distance-to-boundary values from
maritime_boundary.distance_to_eez_boundary_km(). No live weather/wave
calls are needed for this check, so this test doesn't touch the network
and isn't affected by Open-Meteo being slow/down.

Scenario 1 (SHOULD trigger): Rameswaram -> a point in the Palk Strait
right at the India-Sri Lanka maritime boundary - the same stretch of
water where real Indian fishermen crossing into Sri Lankan waters is an
actual, frequently-reported problem, so this is a realistic "should
warn" case, not a contrived one.

Scenario 2 (should NOT trigger): Kochi -> Kochi's existing nearest_pfz
from marine_data.json, per the task's own suggested known-good route.

Usage:
    cd backend
    source venv/bin/activate
    python3 -m tests.test_boundary_geofencing
"""

from app.core.route_engine import generate_candidate_routes, check_boundary_proximity
from app.services.maritime_boundary import (
    distance_to_eez_boundary_km, DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM,
)

print("=" * 70)
print(f"Boundary warning threshold: {DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM} km")


def build_and_check(label, origin, destination):
    print("=" * 70)
    print(f"{label}")
    print(f"  origin={origin}  destination={destination}")
    routes = generate_candidate_routes(origin, destination)
    for route in routes:
        waypoint_distances = [
            distance_to_eez_boundary_km(wp["lat"], wp["lon"]) for wp in route["waypoints"]
        ]
        check_boundary_proximity(route, waypoint_distances, DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM)
        print(
            f"  {route['label']:8s} distance_km={route['distance_km']:6.1f}  "
            f"closest_to_boundary_km={route['boundary_distance_km']:7.2f}  "
            f"boundary_warning={route['boundary_warning']}"
        )
    print()
    return routes


# ---------- Scenario 1: SHOULD trigger ----------
rameswaram_routes = build_and_check(
    "SCENARIO 1: Rameswaram -> Palk Strait / India-Sri Lanka boundary (expect boundary_warning=True)",
    origin=(9.29, 79.31),        # Rameswaram (marine_data.json)
    destination=(9.15, 79.55),   # in the Palk Strait, right at the India-Sri Lanka EEZ line
)

# ---------- Scenario 2: should NOT trigger ----------
kochi_routes = build_and_check(
    "SCENARIO 2: Kochi -> Kochi's nearest_pfz (expect boundary_warning=False)",
    origin=(9.9312, 76.2673),    # Kochi (marine_data.json)
    destination=(9.75, 75.95),   # PFZ near Kochi coast (marine_data.json)
)

print("=" * 70)
scenario1_ok = any(r["boundary_warning"] for r in rameswaram_routes)
scenario2_ok = not any(r["boundary_warning"] for r in kochi_routes)

print(f"[{'OK' if scenario1_ok else 'FAIL'}] Scenario 1 (Rameswaram->Palk Strait) triggered boundary_warning on at least one route")
print(f"[{'OK' if scenario2_ok else 'FAIL'}] Scenario 2 (Kochi->PFZ) triggered boundary_warning on NO route")
print()

if scenario1_ok and scenario2_ok:
    print("ALL CHECKS PASSED: geofencing correctly warns on the boundary-crossing route")
    print("and stays quiet on the clearly-safe demo route.")
else:
    print("SOME CHECKS FAILED - see above.")
