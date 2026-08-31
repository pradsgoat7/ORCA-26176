"""
Stakeholder detection - deterministic keyword-scoring classifier that
identifies whether a query is coming from a fisherman, coast guard,
disaster management official, or general audience.
"""

from app.graph.state import ORCAState

# Keyword sets mined from the spec's own example concerns per stakeholder.
# English-primary for coast_guard/disaster_management (the spec's own
# examples are English-only for those two); fisherman includes Hindi/Marathi
# terms since that's explicitly required by the test scenarios.
STAKEHOLDER_KEYWORDS = {
    "fisherman": [
        "fish", "fishing", "fisherman", "catch", "pfz", "potential fishing zone",
        "go fishing", "safe to fish", "should i fish", "should i go",
        "venture into the sea", "offshore fishing", "wave conditions",
        "fishing zone", "fishing suitability",
        "मछली", "मासेमारी", "पकड़ना",
    ],
    "coast_guard": [
        "coast guard", "monitoring", "patrol", "vessels in danger",
        "rescue", "rescue readiness", "maritime risk", "operational hazard",
        "emergency resources", "increased monitoring", "increased patrol",
        "vessel", "coastal sector", "response priority",
    ],
    "disaster_management": [
        "disaster", "preparedness", "emergency response", "hazard level",
        "warning", "advisory", "at risk", "immediate preparedness",
        "regional risk", "coastal regions at risk", "evacuat",
        "require preparedness", "disaster risk",
    ],
}


def detect_stakeholder(query: str) -> dict:
    """Deterministic keyword-scoring classifier - not an LLM call, so it's
    free, instant, and doesn't compete with Gemini's rate limit. Picks the
    category with the most keyword hits; ties broken by dict order
    (fisherman > coast_guard > disaster_management). Returns 'general'
    with low confidence if nothing matches, per the spec's requirement to
    never force an incorrect classification."""
    query_lower = query.lower()
    scores = {}
    for stakeholder_type, keywords in STAKEHOLDER_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw.lower() in query_lower or kw in query)
        scores[stakeholder_type] = count

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score == 0:
        return {"type": "general", "confidence": 0.5}

    confidence = min(0.95, 0.55 + 0.15 * best_score)
    return {"type": best_type, "confidence": round(confidence, 2)}


def stakeholder_agent(state: ORCAState) -> ORCAState:
    # Runs regardless of location-resolution errors - a query like "Which
    # coastal areas require immediate preparedness?" has no specific city
    # at all, but should still classify correctly.
    return {"stakeholder": detect_stakeholder(state["query"])}
