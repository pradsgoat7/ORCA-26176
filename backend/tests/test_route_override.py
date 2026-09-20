"""
Tests the hard-safety override layer applied to route scoring (Section
14t) - route_planning_agent now runs apply_safety_override() per
candidate route using that route's own worst waypoint (the exact same
waypoint score_route() already identifies as the route's worst - see
route_engine.py), and select_recommended_route() now ranks routes by
their FINAL (post-override) severity FIRST, using the existing
risk+distance combined_score only as a tie-breaker within the same
severity tier.

Two tiers of testing here, deliberately:

1. A focused UNIT test directly on select_recommended_route() with
   hand-constructed route dicts, proving the SELECTION ALGORITHM ITSELF
   is override-aware - not just "happened to agree" on one example.
   Constructed so that comparing raw combined_score ALONE (the
   pre-Section-14t behavior) would have picked the WRONG (CRITICAL)
   route, and confirms the new logic correctly does not.

2. An END-TO-END test through the real route_planning_agent with
   fetch_live_wind/fetch_live_marine mocked (same patching convention as
   test_phase7.py's Scenario 4 - patched at the module that USES them,
   not where they're defined) so ONE waypoint on the Direct route
   genuinely has a >=4m 'Very Rough' wave reading while every other
   waypoint (on Direct itself, and on Route B/Route C, which bend away
   from that point) stays calm - proving the real wiring (worst-waypoint
   identification -> per-route override -> API response fields) actually
   works together, not just in isolation.

Honest note on why Part 2 doesn't ALSO demonstrate an old-logic-would-
have-been-wrong case like Part 1 does: for Kochi -> its own nearest_pfz,
the geometry only adds ~2km (~4.0 combined-score points) of detour for
Route B/Route C, and the risk-engine's wave-risk metric formula already
saturates to a score of 100 at any wave height >=3m - meaning ANY
wave-height-triggered override already carries a raw weighted score high
enough (>=35 for a fisherman) to lose on raw combined_score alone in this
particular short-route geometry too. That's a genuine, honest finding
about THIS scenario's numbers, not a flaw in the fix - Part 1's synthetic
case proves the algorithm is correct in principle (matters for longer
detours or milder trigger margins), and Part 2 proves the real wiring
actually connects end-to-end. See PROJECT_CONTEXT.md Section 14t.

Usage:
    cd backend
    source venv/bin/activate
    python3 -m tests.test_route_override
"""

from unittest.mock import patch

from app.api.routes import _build_route_field
from app.core.route_engine import haversine_km, select_recommended_route
from app.data.loader import MARINE_DATA
from app.graph.agents.route_planning import route_planning_agent
import app.graph.agents.route_planning as route_planning_module

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


print("=" * 70)
print("PART 1: select_recommended_route() unit test - proves the ALGORITHM")
print("is override-aware, not just coincidentally correct on one example")
print("=" * 70)

# Direct: short (0 extra-km penalty), a LOW raw weighted score (10) - but
# override_fired (e.g. an active cyclone alert) forces it to CRITICAL.
# Route B: longer (2 extra km -> +4.0 combined-score penalty at the
# existing distance_penalty_per_km=2.0), raw score 13, no override ->
# stays LOW. Under the OLD (pre-Section-14t) "just compare combined_score"
# logic, Direct's combined_score (10) would have beaten Route B's
# (13+4=17) and been WRONGLY recommended despite being CRITICAL.
synthetic_routes = [
    {"id": "route_direct", "label": "Direct", "distance_km": 40.2, "route_risk_score": 10, "route_risk_level": "CRITICAL"},
    {"id": "route_b", "label": "Route B", "distance_km": 42.2, "route_risk_score": 13, "route_risk_level": "LOW"},
    {"id": "route_c", "label": "Route C", "distance_km": 42.2, "route_risk_score": 13, "route_risk_level": "LOW"},
]
old_logic_winner = min(
    synthetic_routes,
    key=lambda r: r["route_risk_score"] + max(0.0, r["distance_km"] - 40.2) * 2.0,
)
check("sanity check on the test itself: raw combined_score ALONE would have picked the CRITICAL route",
      old_logic_winner["id"] == "route_direct")

best = select_recommended_route(synthetic_routes)
check("select_recommended_route() correctly avoids the CRITICAL route despite its lower raw combined_score",
      best["id"] != "route_direct", detail=f"picked {best['id']}")
check("select_recommended_route() picked a genuinely LOW-severity alternative",
      best["route_risk_level"] == "LOW")
check("is_recommended flag correctly matches the picked route across all candidates",
      sum(1 for r in synthetic_routes if r["is_recommended"]) == 1
      and next(r for r in synthetic_routes if r["is_recommended"])["id"] == best["id"])
check("tie-break among same-severity routes (B vs C) still lands on a LOW route, never Direct",
      best["id"] in ("route_b", "route_c"))

print()
print("=" * 70)
print("PART 2: end-to-end via route_planning_agent - real worst-waypoint wiring")
print("=" * 70)

kochi = MARINE_DATA["kochi"]
# The Direct route's own midpoint waypoint (t=0.5) between Kochi and its
# real nearest_pfz - taken directly from generate_candidate_routes()'s own
# geometry (confirmed by running it), not guessed.
DANGER_LAT, DANGER_LON = 9.8406, 76.10865


def fake_fetch_live_wind(lat, lon):
    return {"wind_speed_kmph": 15.0, "weather_code": 0}


def fake_fetch_live_marine(lat, lon):
    if haversine_km(lat, lon, DANGER_LAT, DANGER_LON) < 1.0:
        return {"wave_height_m": 4.5}  # >= VERY_ROUGH_SEA_THRESHOLD_M (4.0)
    return {"wave_height_m": 0.5}


state = {
    "route_request": {
        "is_route_request": True,
        "origin_text": "Kochi",
        "destination_text": None,
        "destination_is_pfz": True,
    },
    "location_data": kochi,
    "stakeholder": {"type": "fisherman"},
}

with patch.object(route_planning_module, "fetch_live_wind", side_effect=fake_fetch_live_wind), \
     patch.object(route_planning_module, "fetch_live_marine", side_effect=fake_fetch_live_marine):
    result = route_planning_agent(state)

route_plan = result["route_plan"]
check("route plan computed with no error", route_plan.get("error") is None, detail=str(route_plan.get("error")))

direct = next(r for r in route_plan["candidate_routes"] if r["id"] == "route_direct")
route_b = next(r for r in route_plan["candidate_routes"] if r["id"] == "route_b")
route_c = next(r for r in route_plan["candidate_routes"] if r["id"] == "route_c")

check("(a) Direct route (which passes through the dangerous waypoint) gets escalated",
      direct["override_fired"] is True, detail=str(direct.get("override_reasons")))
check("Direct route's override reason correctly cites the real wave height and Douglas Sea Scale",
      any("Very Rough" in r for r in direct["override_reasons"]))
check("Direct route's pre_override_level is preserved (not hidden)",
      direct["pre_override_level"] is not None)
check("Direct route's route_risk_level reflects the FINAL (post-override) level, at least HIGH",
      direct["route_risk_level"] in ("HIGH", "CRITICAL"), detail=direct["route_risk_level"])
check("Direct route's route_risk_score is left untouched by the override (still the raw weighted score, not forced to 100)",
      direct["route_risk_score"] < 50, detail=str(direct["route_risk_score"]))

check("Route B (bends away from the danger point) is NOT escalated", route_b["override_fired"] is False)
check("Route C (bends away from the danger point) is NOT escalated", route_c["override_fired"] is False)

check("(b) route SELECTION correctly avoids recommending the escalated Direct route",
      route_plan["recommended_route_id"] != "route_direct", detail=route_plan["recommended_route_id"])
recommended = next(r for r in route_plan["candidate_routes"] if r["is_recommended"])
check("the actually-recommended route is a genuinely safer, non-escalated alternative",
      recommended["override_fired"] is False)

# Confirm the fields actually reach the API response shape too (routes.py's
# _build_route_field), not just internal state.
route_field = _build_route_field({"route_plan": route_plan})
api_direct = next(r for r in route_field["candidate_routes"] if r["id"] == "route_direct")
check("override fields are present, additive, in the API route response",
      {"pre_override_level", "override_fired", "override_reasons"} <= api_direct.keys())
check("API response's Direct route also shows override_fired=True", api_direct["override_fired"] is True)

print()
print("=" * 70)
print("PART 3: regression - a normal route with NO override conditions anywhere")
print("=" * 70)


def calm_fetch_live_wind(lat, lon):
    return {"wind_speed_kmph": 15.0, "weather_code": 0}


def calm_fetch_live_marine(lat, lon):
    return {"wave_height_m": 0.5}


with patch.object(route_planning_module, "fetch_live_wind", side_effect=calm_fetch_live_wind), \
     patch.object(route_planning_module, "fetch_live_marine", side_effect=calm_fetch_live_marine):
    calm_result = route_planning_agent(state)

calm_plan = calm_result["route_plan"]
check("calm scenario: no route gets escalated anywhere",
      all(r["override_fired"] is False for r in calm_plan["candidate_routes"]))
check("calm scenario: every route's final level equals its pre_override_level (nothing silently changed)",
      all(r["route_risk_level"] == r["pre_override_level"] for r in calm_plan["candidate_routes"]))
check("calm scenario: recommended route is still Direct (shortest, all else equal) - matches pre-14t behavior",
      calm_plan["recommended_route_id"] == "route_direct", detail=calm_plan["recommended_route_id"])

print()
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("All route-override checks pass.")
else:
    raise SystemExit(1)
