"""
Quick manual test for Phases 1-3 (stakeholder detection + risk engine).
Run this directly - it bypasses FastAPI entirely, since main.py hasn't
been updated yet to expose the new fields (that's Phase 4).

Usage:
    cd backend
    source venv/bin/activate
    python3 test_phase3.py
"""

from agents import run_query

TEST_QUERIES = [
    ("Is it safe to fish near Kochi tomorrow?", "fisherman"),
    ("Which coastal areas near Chennai need increased monitoring?", "coast_guard"),
    ("Which coastal areas require immediate preparedness near Visakhapatnam?", "disaster_management"),
    ("Should I go to sea near Chennai today?", "fisherman"),
]

for query, expected_stakeholder in TEST_QUERIES:
    print("=" * 70)
    print(f"QUERY: {query}")
    result = run_query(query)

    stakeholder = result.get("stakeholder")
    risk = result.get("risk")  # may be None if no location was resolved

    print(f"Stakeholder detected: {stakeholder}")
    match = "OK" if stakeholder and stakeholder["type"] == expected_stakeholder else "CHECK THIS"
    print(f"  -> expected '{expected_stakeholder}': {match}")

    if risk is None:
        print("Risk: N/A (no specific location was resolved for this query - expected for")
        print("      region-wide questions like 'which coastal areas...' with no named city)")
        print()
        continue

    print(f"Overall score: {risk.get('overall_score')} ({risk.get('overall_level')})")
    print(f"Recommendation: {risk.get('recommendation')}")
    print("Individual metrics:")
    for m in risk.get("metrics", []):
        print(f"  - {m['name']}: {m['score']}/100")
    print()

print("=" * 70)
print("If every 'Stakeholder detected' line shows a real type (not None)")
print("and 'Overall score' shows a number with metrics listed below it,")
print("Phases 1-3 are working correctly.")