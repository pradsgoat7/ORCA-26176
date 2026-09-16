"""
Policy/explanatory question detection - deterministic keyword classifier
(same style as detect_route_request()) for "why"/"what does X mean"-style
questions that need real document knowledge (the NDMA/IMD RAG index built
in PROJECT_CONTEXT.md Section 14g), not live sensor data.

CRITICAL: detect_policy_request() is called from TWO places - the graph
node below, AND planner.py directly (as a plain function import, not via
the graph). This is deliberate: a pure policy question with no location
at all (e.g. "why do fishermen need to return to shore during a cyclone
warning") was found to fall through to planner.py's last-resort
location-guessing fallback, which extracted the leftover word "warning"
and fuzzy-geocoded it to a real English village called "Warninglid",
producing a nonsensical location error instead of a policy answer.
planner.py now checks detect_policy_request() BEFORE attempting that
fallback and skips it entirely for policy questions that didn't already
match a known city - see the guard in planner_agent().
"""

import re

from app.graph.state import ORCAState

# "why"/explanatory question forms. Deliberately narrow (not just "why")
# so this stays a genuine signal rather than firing on every question.
POLICY_QUESTION_PATTERNS = [
    r"\bwhy\b",
    r"\bwhat does\b.*\bmean\b",
    r"\bwhat is the meaning of\b",
    r"\bexplain\b",
    r"\bwhat is the (?:role|purpose|reason)\b",
    # Broader causal/explanatory phrasing (Section 14k) - "What factors
    # affect marine fish catch trends in India?" style questions ask the
    # same kind of "why does this happen" thing as a "why" question, just
    # phrased as "what factors/causes/...". Still requires a domain word
    # below to actually flag as a policy request, so this alone doesn't
    # widen what fires - it only lets non-"why"-phrased causal questions
    # reach that same AND check.
    r"\bwhat (?:factors|causes|leads to|affects|influences|impacts)\b",
]

# General safety/best-practices phrasing (Section 14m) - "best practices
# while fishing", "safety tips for going to sea", "how to stay safe
# fishing", "what should I carry before going to sea". Found via a real
# bug: "best practices while fishing" has no location, no "why"/"what
# factors" shape, and no POLICY_DOMAIN_WORD - it fell through every
# existing detector straight to planner.py's fuzzy fallback, which
# geocoded the word "fishing" to a real place called "Fishing Creek" -
# same bug family as "Warninglid" (Section 14h), different trigger word.
# Unlike the why/what-factors patterns above, these are checked as a
# SEPARATE, self-sufficient signal (see detect_policy_request) rather
# than requiring a POLICY_DOMAIN_WORD too - the phrase itself already
# encodes enough fishing/sea/safety context to mean something specific in
# this app's narrow marine-safety domain, so it doesn't need the same
# disambiguation "why" alone needs.
SAFETY_PRACTICE_PATTERNS = [
    r"\bbest practices?\b",
    r"\bsafety tips?\b",
    r"\bhow to (?:fish|stay) safe(?:ly)?\b",
    r"\bwhat should i (?:do|carry|check|bring) before (?:fishing|going to sea|heading out|setting sail)\b",
    r"\bsafety (?:equipment|gear|checklist|precautions)\b",
]

# Policy/regulation/disaster-management domain words. Requiring one of
# these ALONGSIDE a question pattern above is what keeps ordinary live-data
# questions ("why is it windy today") from misfiring - "why" alone is far
# too broad a signal on its own, since "windy"/"today" aren't policy words.
POLICY_DOMAIN_WORDS = [
    "ban", "banned", "regulation", "regulations", "guideline", "guidelines",
    "advisory", "advisories", "sop", "procedure", "procedures", "policy",
    "policies", "authority", "authorities", "warning", "warnings", "alert",
    "alerts", "disaster management", "dma", "ndma", "imd", "protocol",
    "cyclone warning", "evacuation", "shelter", "mitigation", "preparedness",
    # Added when the CMFRI fisheries documents were indexed (Section 14j) -
    # closes the detection-side gap where a well-formed, well-answerable
    # fish-productivity question (the PS's own example) had no domain word
    # to match on and fell through to the location-guessing fallback instead.
    "fish stock", "overfishing", "productivity", "fish production",
    "catch trends", "declined", "decline",
]


def detect_policy_request(query: str) -> dict:
    """Deterministic keyword-based policy-question classifier. Flags a
    query as a policy request if EITHER:
    - it has BOTH a question-pattern signal (why/explain/what does X
      mean/what factors) AND a policy-domain word - a query needs both,
      so a plain weather question never gets misrouted into the
      document-retrieval path just because it happens to contain the
      word 'why'; OR
    - it matches a general safety/best-practices phrasing (Section 14m) -
      these are self-sufficiently specific on their own and don't need a
      separate domain word to mean something in this app's narrow
      marine-safety domain."""
    query_lower = query.lower()

    has_question_pattern = any(re.search(p, query_lower) for p in POLICY_QUESTION_PATTERNS)
    has_domain_word = any(w in query_lower for w in POLICY_DOMAIN_WORDS)
    has_safety_practice_pattern = any(re.search(p, query_lower) for p in SAFETY_PRACTICE_PATTERNS)

    is_policy_request = (has_question_pattern and has_domain_word) or has_safety_practice_pattern
    return {"is_policy_request": is_policy_request}


def policy_detection_agent(state: ORCAState) -> ORCAState:
    # Runs regardless of location-resolution errors/results, same
    # rationale as route_detection_agent - detecting a policy question
    # doesn't depend on whether the main query's location resolved.
    return {"policy_request": detect_policy_request(state["query"])}
