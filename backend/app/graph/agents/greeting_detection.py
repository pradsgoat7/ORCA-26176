"""
Greeting/help-seeking detection - deterministic keyword classifier (same
style as detect_policy_request() in policy_detection.py) for onboarding-
style messages ("hello", "hi", "i need help", "what can you do") that have
no location intent at all.

CRITICAL: detect_greeting_or_help() must be checked from planner.py
directly (a plain function import, not just via a graph node) BEFORE the
fuzzy location-guessing fallback - the exact same principle, fixing the
SAME recurring bug class, as detect_policy_request()'s guard in
planner.py. This is the 4th real instance of that bug family
("Warninglid" - Section 14h, "Fishing Creek" - Section 14m, "India" -
Section 14k/14l, and now "Helpt": a real village that "i need help"
fuzzy-geocoded to, since "help" survives planner.py's STOPWORDS list and
becomes the last leftover word). Rather than patch a 5th individual
trigger word into STOPWORDS, this builds a real systemic fix: an entire
category of intent - greetings and onboarding questions - that should
never reach location resolution at all, checked up front, the same way a
policy question never should.
"""

import re

from app.graph.state import ORCAState

# Simple greetings, English + common Hindi/Marathi equivalents (romanized
# and Devanagari both, since users type in either). Matched as whole
# tokens/phrases, not substrings, so this never fires on an unrelated word
# that happens to contain one of these as a fragment.
GREETING_PATTERNS = [
    r"\bhi+\b",              # hi, hii, hiii
    r"\bhello+\b",
    r"\bhey+\b",
    r"\byo\b",
    r"\bgood\s+(?:morning|afternoon|evening)\b",
    r"\bnamaste\b",
    r"\bnamaskar\b",
    # Devanagari script: no \b word-boundary here - Python's \b relies on
    # \w transitions, and Devanagari combining vowel signs don't reliably
    # trigger those the way ASCII word boundaries do. Plain substring
    # matching is what this project already uses elsewhere for Devanagari
    # keywords (e.g. route_detection.py's PFZ_DESTINATION_KEYWORDS).
    r"नमस्ते",
    r"नमस्कार",
    r"हाय",
    r"हेलो",
]

# Help-seeking / "how do I use this" onboarding questions. Deliberately
# phrase-level (not a bare "help" substring match beyond the standalone
# word itself) so this stays a genuine onboarding signal.
HELP_PATTERNS = [
    r"\bhelp\b",
    r"\bhow do i use this\b",
    r"\bhow (?:does|do) (?:this|it|orca) work\b",
    r"\bwhat can you do\b",
    r"\bwhat can i ask\b",
    r"\bwhat do you do\b",
    r"\bhow to use\b",
]


def detect_greeting_or_help(query: str) -> dict:
    """Deterministic keyword-based greeting/help classifier. Flags a query
    as a greeting-or-help request if it matches a greeting pattern OR a
    help-seeking pattern - either one is a complete, self-sufficient
    signal on its own (unlike policy detection's two-part AND), since a
    bare "hello" or "help" already fully expresses the intent with no
    further context needed."""
    query_lower = query.lower()

    is_greeting = any(re.search(p, query_lower) for p in GREETING_PATTERNS)
    is_help = any(re.search(p, query_lower) for p in HELP_PATTERNS)

    return {"is_greeting_or_help": is_greeting or is_help}


# Real example questions reused verbatim from this project's own frontend
# "Try:" suggestions (Ask ORCA tab) and Knowledge Base example buttons
# (PROJECT_CONTEXT.md Section 14q) - never invented for this message,
# so every example genuinely works if the user tries it.
ONBOARDING_MESSAGES = {
    "en": (
        "Hi! I'm ORCA, a marine intelligence assistant for fishermen, coast guard, "
        "and disaster management teams along India's coast. I can assess real-time "
        "fishing safety risk for a location, plan a safer route between coastal "
        "points, and answer questions from real government safety and fisheries "
        "documents. Try asking:\n"
        "- \"Is it safe to fish tomorrow near Kochi?\"\n"
        "- \"Find the safest route from Kochi to the fishing zone\"\n"
        "- \"Why is fishing banned before a cyclone?\"\n"
        "- \"What safety equipment should I carry before going to sea?\""
    ),
    "hi": (
        "नमस्ते! मैं ORCA हूं, भारत के तटीय क्षेत्र में मछुआरों, तटरक्षक बल और आपदा प्रबंधन "
        "टीमों के लिए एक समुद्री सूचना सहायक। मैं किसी स्थान के लिए वास्तविक समय में मछली "
        "पकड़ने की सुरक्षा जोखिम का आकलन कर सकता हूं, तटीय स्थानों के बीच एक सुरक्षित मार्ग "
        "की योजना बना सकता हूं, और वास्तविक सरकारी सुरक्षा एवं मत्स्य दस्तावेज़ों से सवालों "
        "के जवाब दे सकता हूं। इन्हें आज़माएं:\n"
        "- \"क्या कल कोच्चि के पास मछली पकड़ना सुरक्षित है?\"\n"
        "- \"कोच्चि से मछली पकड़ने के क्षेत्र तक सबसे सुरक्षित मार्ग बताएं\"\n"
        "- \"चक्रवात से पहले मछली पकड़ना क्यों प्रतिबंधित है?\"\n"
        "- \"समुद्र में जाने से पहले मुझे कौन सा सुरक्षा उपकरण साथ रखना चाहिए?\""
    ),
    "mr": (
        "नमस्कार! मी ORCA आहे, भारताच्या किनारपट्टीवरील मच्छिमार, तटरक्षक दल आणि आपत्ती "
        "व्यवस्थापन पथकांसाठी एक सागरी माहिती सहाय्यक. मी एखाद्या ठिकाणासाठी प्रत्यक्ष वेळेत "
        "मासेमारी सुरक्षा जोखमीचे मूल्यांकन करू शकतो, किनारपट्टीवरील ठिकाणांदरम्यान सुरक्षित "
        "मार्गाची आखणी करू शकतो, आणि खऱ्या सरकारी सुरक्षा व मत्स्यव्यवसाय कागदपत्रांमधून "
        "प्रश्नांची उत्तरे देऊ शकतो. हे विचारून पहा:\n"
        "- \"उद्या कोचीजवळ मासेमारी करणे सुरक्षित आहे का?\"\n"
        "- \"कोचीपासून मासेमारी क्षेत्रापर्यंतचा सर्वात सुरक्षित मार्ग शोधा\"\n"
        "- \"चक्रीवादळापूर्वी मासेमारीवर बंदी का असते?\"\n"
        "- \"समुद्रात जाण्यापूर्वी मी कोणती सुरक्षा उपकरणे सोबत ठेवावीत?\""
    ),
}


def greeting_detection_agent(state: ORCAState) -> ORCAState:
    # Runs regardless of location-resolution errors/results, same
    # rationale as policy_detection_agent - detecting a greeting doesn't
    # depend on whether the main query's location resolved.
    return {"greeting_request": detect_greeting_or_help(state["query"])}
