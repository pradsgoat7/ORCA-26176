"""
Policy RAG STEP 2 - end-to-end test suite for policy_detection.py +
policy_agent.py wired into the LangGraph workflow. Covers the exact
scenarios from this session's task, run for real (real ChromaDB
retrieval; Gemini calls too, with graceful fallback if rate-limited/
unavailable - never a hard requirement for these checks to pass).

Run with:
    cd backend
    source venv/bin/activate
    python3 -m tests.test_policy_agent
"""

from unittest.mock import patch

from app.graph.workflow import run_query
import app.graph.agents.policy_agent as policy_agent_module

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


# ---------- Test 1: pure policy question, NO location at all ----------
# This is the exact bug scenario: "warning" was previously extracted as a
# location guess and fuzzy-geocoded to a real English village called
# "Warninglid". Confirms that no longer happens, and that a real answer
# from the indexed documents comes back instead - without ever routing
# through the generic "could not identify a known location" error.
print("=" * 70)
print("TEST 1: Pure policy question, no location - the Warninglid bug scenario")
r = run_query("Why do fishermen need to return to shore during a cyclone warning?")
check("no bogus location resolved (location_key is None)", r.get("location_key") is None, f"got {r.get('location_key')}")
check("no bogus location resolved (location_data is None)", r.get("location_data") is None, f"got {r.get('location_data')}")
check("did NOT resolve to 'Warninglid' or any place", "warninglid" not in str(r.get("location_data")).lower())
check("no error at all", r.get("error") is None, f"got {r.get('error')}")
check("error is specifically NOT the generic location error",
      r.get("error") != "Could not identify a known location in the query.")
check("policy_request correctly flagged", r.get("policy_request", {}).get("is_policy_request") is True)
check("policy_answer present", r.get("policy_answer") is not None)
check("policy_answer has real, non-empty text", bool((r.get("policy_answer") or {}).get("answer", "").strip()))
check("policy_answer cites real sources", len((r.get("policy_answer") or {}).get("sources", [])) > 0)
print(f"  (mode: {(r.get('policy_answer') or {}).get('mode')})")
print()


# ---------- Test 2: policy question WITH a known location (Chennai) ----------
# Decision (documented in PROJECT_CONTEXT.md): both pipelines run
# independently - Chennai's normal risk calculation is untouched, AND a
# real policy_answer is added additively.
print("=" * 70)
print("TEST 2: Policy question WITH a known location (Chennai) - both should run")
r2 = run_query("Why is fishing banned before a cyclone near Chennai?")
check("Chennai's location resolved normally", r2.get("location_key") == "chennai", f"got {r2.get('location_key')}")
check("normal risk pipeline still ran", r2.get("risk") is not None)
check("policy_request correctly flagged", r2.get("policy_request", {}).get("is_policy_request") is True)
check("policy_answer ALSO present (additive)", r2.get("policy_answer") is not None)
check("main answer is the risk-based answer, untouched (not the raw-chunk policy fallback text)",
      "Chennai" in r2.get("answer", "") and "raw source material" not in r2.get("answer", ""))
print()


# ---------- Test 3: the known weak-retrieval case (district DMA) ----------
# Step 1 (n_results=3) found this borderline; policy_agent uses
# n_results=4, which in practice surfaced genuinely district-specific
# content. Either way, this must never be a confidently WRONG answer -
# check for absence of fabrication markers is hard to automate, so this
# mainly confirms the pipeline runs cleanly and returns real, sourced text
# (a human judged the actual answer content separately - see
# PROJECT_CONTEXT.md).
print("=" * 70)
print("TEST 3: District DMA question - known borderline retrieval case")
r3 = run_query("What is the role of the district disaster management authority?")
check("policy_request correctly flagged", r3.get("policy_request", {}).get("is_policy_request") is True)
check("policy_answer present", r3.get("policy_answer") is not None)
check("policy_answer has real, non-empty text", bool((r3.get("policy_answer") or {}).get("answer", "").strip()))
print(f"  answer: {(r3.get('policy_answer') or {}).get('answer', '')[:200]}...")
print()


# ---------- Test 4: a completely normal existing query - must be unaffected ----------
print("=" * 70)
print("TEST 4: Normal existing query - must be 100% unaffected")
r4 = run_query("Is it safe to fish near Kochi tomorrow?")
check("policy_request correctly NOT flagged", r4.get("policy_request", {}).get("is_policy_request") is False)
check("policy_answer is None", r4.get("policy_answer") is None)
check("normal risk pipeline works", r4.get("risk") is not None)
check("normal weather/ocean data present", r4.get("weather") is not None and r4.get("ocean") is not None)
print()


# ---------- Test 5: policy_agent failure path - index/Gemini both down ----------
print("=" * 70)
print("TEST 5: Policy retrieval unavailable - graceful fallback, no crash")
with patch.object(policy_agent_module, "_get_collection", return_value=None):
    r5 = run_query("Why is fishing banned during a cyclone warning?")
check("no crash - result still returned", r5 is not None)
check("policy_answer still present (honest 'unavailable' message)", r5.get("policy_answer") is not None)
check("mode reflects unavailability", (r5.get("policy_answer") or {}).get("mode") == "no_index_or_no_results")
check("still no bogus location / no generic location error", r5.get("location_data") is None and r5.get("error") is None)
print()


# ---------- Test 6: "best practices while fishing" - the Fishing Creek bug scenario ----------
# Same bug family as Test 1's Warninglid case, different trigger word:
# "best practices while fishing" has no location, no why/what-factors
# shape, and no POLICY_DOMAIN_WORD, so it fell through every existing
# detector to planner.py's fuzzy fallback, which geocoded "fishing" to a
# real place called "Fishing Creek" (Section 14m). Fixed with a separate
# SAFETY_PRACTICE_PATTERNS signal that doesn't require a domain word.
print("=" * 70)
print("TEST 6: 'best practices while fishing' - the Fishing Creek bug scenario")
r6 = run_query("best practices while fishing")
check("policy_request correctly flagged", r6.get("policy_request", {}).get("is_policy_request") is True)
check("no bogus location resolved (location_key is None)", r6.get("location_key") is None, f"got {r6.get('location_key')}")
check("did NOT resolve to 'Fishing Creek' or any place", "fishing creek" not in str(r6.get("location_data")).lower())
check("no error at all", r6.get("error") is None, f"got {r6.get('error')}")
check("policy_answer present", r6.get("policy_answer") is not None)
check("policy_answer has real, non-empty text", bool((r6.get("policy_answer") or {}).get("answer", "").strip()))
check("policy_answer cites the FAO safety document",
      any("Safety at Sea" in s.get("title", "") for s in (r6.get("policy_answer") or {}).get("sources", [])),
      f"got sources {r6.get('policy_answer', {}).get('sources')}")
print(f"  (mode: {(r6.get('policy_answer') or {}).get('mode')})")
print()


# ---------- Test 7: safety-practice patterns must not miscapture normal risk queries ----------
print("=" * 70)
print("TEST 7: Safety-practice patterns must not miscapture normal risk queries")
for q in [
    "What are the wave conditions near Kochi?",
    "Is it safe to fish near Kochi tomorrow?",
    "What are the conditions near Visakhapatnam?",
]:
    from app.graph.agents.policy_detection import detect_policy_request
    result = detect_policy_request(q)
    check(f"'{q}' stays is_policy_request=False", result["is_policy_request"] is False, f"got {result}")
print()


# ---------- Summary ----------
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("All policy RAG Step 2 checks pass.")
else:
    print("Some checks failed - review the FAIL lines above before considering this feature complete.")
