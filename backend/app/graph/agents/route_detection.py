"""
Route request detection - deterministic keyword classifier that decides
whether a query is genuinely asking for navigation/routing, without ever
misclassifying an ordinary fishing-safety or weather question.
"""

import re

from app.graph.state import ORCAState

ROUTE_KEYWORDS = [
    "route", "navigate", "navigation", "way to reach", "how do i get",
    "how should i reach", "which route", "safest way", "path to",
    "मार्ग", "रास्ता", "कैसे पहुंचूं", "कसे पोहोचू",
]

PFZ_DESTINATION_KEYWORDS = [
    "pfz", "fishing zone", "fishing area", "potential fishing zone",
    "मछली पकड़ने", "मासेमारी",  # Hindi / Marathi for "fishing"
]


def detect_route_request(query: str) -> dict:
    """Deterministic keyword-based route-request classifier, mirroring the
    same style as detect_stakeholder(). This runs on EVERY query, but only
    activates the route feature when it's genuinely a routing question -
    ordinary queries like 'is it safe to fish near Kochi' must never be
    reinterpreted as a route request just because this function runs."""
    query_lower = query.lower()
    is_route = any(kw in query_lower or kw in query for kw in ROUTE_KEYWORDS)

    if not is_route:
        return {"is_route_request": False}

    # "from X to Y" - the clearest, most reliable origin signal
    origin_text = None
    match = re.search(r"from\s+([A-Za-z]+)\s+to", query, re.IGNORECASE)
    if match:
        origin_text = match.group(1)

    destination_is_pfz = any(kw in query_lower for kw in PFZ_DESTINATION_KEYWORDS)

    # Fallback destination extraction for non-PFZ cases (e.g. "to the vessel").
    # This is intentionally rough - for destinations we have no coordinates
    # for (a specific vessel, "the affected area"), the extracted text is
    # mainly used to produce an honest, specific error message, not to
    # invent a location.
    destination_text = None
    if not destination_is_pfz:
        match2 = re.search(r"\bto\s+(?:the\s+)?([A-Za-z]+)", query, re.IGNORECASE)
        if match2:
            destination_text = match2.group(1)

    return {
        "is_route_request": True,
        "origin_text": origin_text,
        "destination_text": destination_text,
        "destination_is_pfz": destination_is_pfz,
    }


def route_detection_agent(state: ORCAState) -> ORCAState:
    # Runs regardless of location-resolution errors, same rationale as
    # stakeholder_agent - route detection doesn't depend on whether the
    # main query's location happened to resolve successfully.
    return {"route_request": detect_route_request(state["query"])}
