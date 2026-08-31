"""
Language detection - the first node in the ORCA graph. Determines
English / Hindi / Marathi so downstream agents can pick the right
fallback templates and location aliases.
"""

from app.graph.state import ORCAState


def detect_language(text: str) -> str:
    """Lightweight heuristic language detection - good enough to pick the
    right fallback template and location aliases without needing an API
    call. Devanagari script covers both Hindi and Marathi, so we use a
    couple of common Marathi-specific words to disambiguate; Gemini
    (when available) will still produce a fully natural response in
    whichever language the query is actually in, since it understands
    the query directly rather than relying on this heuristic."""
    marathi_markers = ["आहे", "का ", "आहेत"]
    if any(marker in text for marker in marathi_markers):
        return "mr"
    if any("\u0900" <= ch <= "\u097F" for ch in text):  # Devanagari block
        return "hi"
    return "en"


def language_node(state: ORCAState) -> ORCAState:
    lang = detect_language(state["query"])
    return {"language": lang}
