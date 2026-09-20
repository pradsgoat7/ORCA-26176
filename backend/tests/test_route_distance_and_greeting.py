"""
Two independent real-bug fixes from live user testing (PROJECT_CONTEXT.md
Section 14r):

1. Route distance sanity check - "route from Kochi to Mumbai" (1067 km)
   was generating a straight-line-based route that cut directly across
   land through Maharashtra/Karnataka's interior. route_planning_agent now
   checks straight-line distance BEFORE calling generate_candidate_routes()
   and refuses gracefully above MAX_REALISTIC_ROUTE_DISTANCE_KM.

2. Greeting/help intent - "hello" and "i need help" were falling through
   to planner.py's fuzzy location-guessing fallback ("help" survived
   STOPWORDS and got fuzzy-geocoded to a real village called "Helpt") -
   the same recurring bug class as "Warninglid" (Section 14h) and
   "Fishing Creek" (Section 14m). greeting_detection.py now catches this
   whole category of intent before the fallback ever runs, same principle
   as policy_detection.py's existing guard.

Usage:
    cd backend
    source venv/bin/activate
    python3 -m tests.test_route_distance_and_greeting
"""

from fastapi.testclient import TestClient

from app.config import MAX_REALISTIC_ROUTE_DISTANCE_KM
from app.core.route_engine import haversine_km
from app.graph.agents.greeting_detection import detect_greeting_or_help
from app.graph.workflow import run_query
from app.main import app

client = TestClient(app)

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
print("PART 1: Route distance sanity check")
print("=" * 70)

kochi = (9.9312, 76.2673)
mumbai = (18.9750, 72.8258)
straight_line = haversine_km(*kochi, *mumbai)
print(f"  Kochi<->Mumbai straight-line distance: {round(straight_line)} km "
      f"(threshold: {MAX_REALISTIC_ROUTE_DISTANCE_KM} km)")
check("Kochi<->Mumbai genuinely exceeds the threshold (sanity check on the test itself)",
      straight_line > MAX_REALISTIC_ROUTE_DISTANCE_KM)

r = run_query("find the safest route from Kochi to Mumbai")
route_plan = r.get("route_plan") or {}
check("Kochi->Mumbai returns a route_plan error (not a generated route)",
      bool(route_plan.get("error")), detail=str(route_plan))
check("Kochi->Mumbai error message explains the short-range design intent",
      "short-range" in (route_plan.get("error") or "").lower())
check("Kochi->Mumbai error message suggests an alternative (nearest fishing zone / nearer town)",
      "fishing zone" in (route_plan.get("error") or "").lower())
check("Kochi->Mumbai produces zero candidate routes",
      route_plan.get("candidate_routes") == [])

api_resp = client.post("/ask", json={"query": "find the safest route from Kochi to Mumbai"}).json()
check("/ask's top-level 'answer' surfaces the same graceful distance message to the user",
      api_resp["route"]["error"] in api_resp["answer"], detail=api_resp["answer"])

r2 = run_query("find the safest route from Kochi to the fishing zone")
route_plan2 = r2.get("route_plan") or {}
check("Kochi->its own PFZ (realistic short route) still works: no error",
      route_plan2.get("error") is None, detail=str(route_plan2.get("error")))
check("Kochi->its own PFZ still produces 3 candidate routes",
      len(route_plan2.get("candidate_routes") or []) == 3)

r3 = run_query("find the safest route from Rameswaram to Thoothukudi")
route_plan3 = r3.get("route_plan") or {}
check("Rameswaram->Thoothukudi (realistic short route) still works: no error",
      route_plan3.get("error") is None, detail=str(route_plan3.get("error")))
check("Rameswaram->Thoothukudi still produces 3 candidate routes",
      len(route_plan3.get("candidate_routes") or []) == 3)

print()
print("=" * 70)
print("PART 2: Greeting/help intent detection")
print("=" * 70)

for q in ["hello", "hi", "hii", "hey", "good morning", "namaste", "नमस्ते"]:
    check(f"'{q}' detected as a greeting", detect_greeting_or_help(q)["is_greeting_or_help"])

for q in ["i need help", "what can you do", "how does this work", "how do i use this"]:
    check(f"'{q}' detected as help-seeking", detect_greeting_or_help(q)["is_greeting_or_help"])

for q in ["hello", "i need help", "what can you do"]:
    r = run_query(q)
    check(f"'{q}' produces NO location error", r.get("error") is None, detail=str(r.get("error")))
    check(f"'{q}' resolves no location (as designed - same as a policy question)",
          r.get("location_data") is None)
    check(f"'{q}' never mentions 'Helpt' or any bogus geocoded place",
          "helpt" not in (r.get("answer") or "").lower())
    check(f"'{q}' gets a genuinely useful onboarding answer (mentions ORCA and a real example query)",
          "ORCA" in (r.get("answer") or "") and "Kochi" in (r.get("answer") or ""),
          detail=(r.get("answer") or "")[:200])

print()
print("  -- Regression: normal queries and policy questions must be unaffected --")

r_normal = run_query("is it safe to fish near Kochi?")
check("A normal location query still resolves Kochi correctly (no greeting misfire)",
      r_normal.get("location_data") is not None and r_normal["location_data"]["name"] == "Kochi",
      detail=str(r_normal.get("location_data")))

r_policy = run_query("why is fishing banned before a cyclone?")
check("A real policy question is still answered as policy, not swallowed as a greeting",
      bool((r_policy.get("policy_answer") or {}).get("answer")) and not r_policy.get("is_greeting_or_help"),
      detail=str(r_policy.get("policy_answer")))
r_help_policy = run_query("help me understand why fishing is banned before a cyclone")
check("Policy detection runs BEFORE greeting detection: a policy question containing "
      "'help' still gets answered as policy, not onboarding",
      bool((r_help_policy.get("policy_answer") or {}).get("answer")) and not r_help_policy.get("is_greeting_or_help"),
      detail=str(r_help_policy.get("policy_answer")))

print()
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("All route-distance and greeting/help checks pass.")
else:
    raise SystemExit(1)
