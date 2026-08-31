"""
Phase 7 - End-to-end test suite covering the six scenarios from the spec:
1. Fisherman query
2. Coast Guard query
3. Disaster Management query
4. High-risk fisherman query (forced via mocked severe conditions, since we
   can't guarantee real weather will be severe whenever this test runs)
5. Hindi fisherman query
6. Marathi fisherman query

Run with:
    cd backend
    source venv/bin/activate
    python3 -m tests.test_phase7
"""

from unittest.mock import patch

from app.graph.workflow import run_query
# Patched at the modules that actually USE these functions (weather.py /
# ocean.py import them directly), not at app.services.weather_api where
# they're defined - patching the source module wouldn't affect names
# already bound via "from X import Y" in the importing modules.
import app.graph.agents.weather as weather_module
import app.graph.agents.ocean as ocean_module

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


# ---------- Test 1: Fisherman ----------
print("=" * 70)
print("TEST 1: Fisherman query")
r = run_query("Is it safe to fish near Kochi tomorrow?")
check("stakeholder is fisherman", r["stakeholder"]["type"] == "fisherman", f"got {r['stakeholder']}")
check("risk data present", r["risk"] is not None)
check("overall_score is a number", isinstance(r["risk"]["overall_score"], int))
check("4 individual metrics present", len(r["risk"]["metrics"]) == 4)
print()


# ---------- Test 2: Coast Guard ----------
print("=" * 70)
print("TEST 2: Coast Guard query")
r = run_query("Which coastal areas near Chennai need increased monitoring?")
check("stakeholder is coast_guard", r["stakeholder"]["type"] == "coast_guard", f"got {r['stakeholder']}")
check("risk data present", r["risk"] is not None)
check("recommendation is operational, not fishing-specific",
      "fish" not in r["risk"]["recommendation"].lower())
print()


# ---------- Test 3: Disaster Management ----------
print("=" * 70)
print("TEST 3: Disaster Management query")
r = run_query("Which coastal areas require immediate preparedness near Visakhapatnam?")
check("stakeholder is disaster_management", r["stakeholder"]["type"] == "disaster_management", f"got {r['stakeholder']}")
check("risk data present", r["risk"] is not None)
print()


# ---------- Test 4: High-risk fisherman (forced via mocked severe conditions) ----------
print("=" * 70)
print("TEST 4: High-risk fisherman query (forced severe conditions)")

severe_wind = {"wind_speed_kmph": 45, "precipitation_mm": 20, "weather_code": 95}
severe_marine = {"wave_height_m": 3.2, "sea_surface_temp_c": 29.0}

with patch.object(weather_module, "fetch_live_wind", return_value=severe_wind), \
     patch.object(ocean_module, "fetch_live_marine", return_value=severe_marine):
    # Chennai already has cyclone_alert=True in the mock data, so combined
    # with severe live wind/wave/lightning, all four metrics should be high.
    r = run_query("Should I go to sea near Chennai today?")

check("stakeholder is fisherman", r["stakeholder"]["type"] == "fisherman", f"got {r['stakeholder']}")
check("overall_level is HIGH or CRITICAL", r["risk"]["overall_level"] in ("HIGH", "CRITICAL"),
      f"got {r['risk']['overall_level']} (score {r['risk']['overall_score']})")
check("wave_risk metric is high", r["risk"]["metrics"][0]["score"] >= 75,
      f"got {r['risk']['metrics'][0]}")
check("cyclone_risk metric is 100", r["risk"]["metrics"][2]["score"] == 100,
      f"got {r['risk']['metrics'][2]}")
check("recommendation discourages going to sea",
      "avoid" in r["risk"]["recommendation"].lower() or "do not" in r["risk"]["recommendation"].lower(),
      f"got: {r['risk']['recommendation']}")
print(f"  (For reference: overall_score={r['risk']['overall_score']}, level={r['risk']['overall_level']})")
print()


# ---------- Test 5: Hindi ----------
print("=" * 70)
print("TEST 5: Hindi fisherman query")
r = run_query("क्या कल कोच्चि के पास मछली पकड़ना सुरक्षित है?")
check("language detected as Hindi", r["language"] == "hi", f"got {r['language']}")
check("stakeholder is fisherman", r["stakeholder"]["type"] == "fisherman", f"got {r['stakeholder']}")
check("risk data present", r["risk"] is not None)
print()


# ---------- Test 6: Marathi ----------
print("=" * 70)
print("TEST 6: Marathi fisherman query")
r = run_query("उद्या चेन्नईजवळ मासेमारी करणे सुरक्षित आहे का?")
check("language detected as Marathi", r["language"] == "mr", f"got {r['language']}")
check("stakeholder is fisherman", r["stakeholder"]["type"] == "fisherman", f"got {r['stakeholder']}")
check("risk data present", r["risk"] is not None)
print()


# ---------- Summary ----------
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("All Phase 7 scenarios pass. Stakeholder detection + risk engine are working end-to-end.")
else:
    print("Some checks failed - review the FAIL lines above before considering this feature complete.")
