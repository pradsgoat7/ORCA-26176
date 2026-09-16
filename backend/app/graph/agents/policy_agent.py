"""
Policy agent - answers "why"/explanatory questions (cyclone warnings,
fishing bans, disaster-management procedures) by retrieving real passages
from the ChromaDB index built in scripts/build_policy_index.py (see
PROJECT_CONTEXT.md Section 14g) and grounding a Gemini answer strictly in
that retrieved text. Falls back to the raw retrieved chunk text if Gemini
is unavailable - same deterministic-fallback philosophy as synthesis.py.

Runs only when policy_detection_agent flagged a policy request; every
other query gets policy_answer=None at essentially zero cost - same
zero-cost-when-not-needed pattern as route_planning_agent.
"""

from pathlib import Path
from typing import Optional

import requests

from app.config import GOOGLE_API_KEY
from app.graph.state import ORCAState

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
POLICY_INDEX_DIR = BACKEND_DIR / "app" / "data" / "policy_index"
COLLECTION_NAME = "orca_policy_docs"
N_RESULTS = 4

# Lazily loaded and cached - the index may not exist yet on a fresh clone
# (it's built by a separate one-time script), so this must never raise or
# block server startup. Mirrors the return-None-on-failure philosophy used
# throughout services/ (e.g. weather_api.py).
_collection = None
_collection_load_attempted = False


def _get_collection():
    global _collection, _collection_load_attempted
    if _collection is not None or _collection_load_attempted:
        return _collection
    _collection_load_attempted = True
    try:
        import chromadb
        from chromadb.utils import embedding_functions

        client = chromadb.PersistentClient(path=str(POLICY_INDEX_DIR))
        embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        _collection = client.get_collection(name=COLLECTION_NAME, embedding_function=embedding_fn)
    except Exception as e:
        print(f"[ORCA] Policy index unavailable ({e}) - policy questions will get an honest 'unavailable' answer.")
        _collection = None
    return _collection


def _retrieve_chunks(query: str, n_results: int = N_RESULTS) -> Optional[list]:
    """Returns a list of (chunk_text, metadata) tuples, or None on any
    failure (missing index, query error)."""
    collection = _get_collection()
    if collection is None:
        return None
    try:
        results = collection.query(query_texts=[query], n_results=n_results)
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        if not docs:
            return None
        return list(zip(docs, metas))
    except Exception as e:
        print(f"[ORCA] Policy retrieval failed: {e}")
        return None


def _dedupe_sources(chunks: list) -> list:
    seen = set()
    sources = []
    for _, meta in chunks:
        key = (meta["title"], meta["page"])
        if key not in seen:
            seen.add(key)
            sources.append({"title": meta["title"], "page": meta["page"], "source_url": meta["source_url"]})
    return sources


def _build_grounded_prompt(query: str, chunks: list) -> str:
    context = "\n\n".join(
        f"[Source: {meta['title']}, page {meta['page']}]\n{doc}"
        for doc, meta in chunks
    )
    return f"""You are answering a question using ONLY the real government document excerpts
provided below (official NDMA and IMD publications on cyclone management).

STRICT RULES:
- Answer ONLY using the text provided below. Do not use outside knowledge.
- If the provided text does not actually answer the question, say so honestly
  (for example: "The available documents don't specifically cover this") rather
  than guessing or inventing an answer.
- Keep the answer clear and concise (3-5 sentences).
- You may mention which document the information comes from.

Question: {query}

--- Retrieved document excerpts ---
{context}
--- end of excerpts ---
"""


def _raw_chunks_fallback(chunks: list) -> str:
    """Deterministic fallback when Gemini is unavailable - returns the
    actual retrieved text plainly, clearly labeled as unprocessed source
    material rather than an AI-composed answer."""
    lines = [
        "I couldn't generate a summarized answer right now, so here is the "
        "raw source material retrieved from the indexed official documents "
        "(this is unprocessed source text, not an AI-written answer):"
    ]
    for doc, meta in chunks:
        lines.append(f"\n[{meta['title']}, page {meta['page']}]\n{doc}")
    return "\n".join(lines)


def _call_gemini(prompt: str) -> str:
    """Raises on any failure - caller catches and falls back. Same
    endpoint/model/timeout convention as synthesis_agent's Gemini call."""
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
    headers = {"x-goog-api-key": GOOGLE_API_KEY, "Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "thinkingConfig": {"thinkingLevel": "low"},
            # Same shared thinking+output token budget issue diagnosed and
            # fixed in synthesis_agent (see PROJECT_CONTEXT.md) - raised
            # here too since this call uses the identical pattern and
            # would otherwise be equally exposed to MAX_TOKENS truncation.
            "maxOutputTokens": 2048,
        },
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def policy_agent(state: ORCAState) -> ORCAState:
    policy_req = state.get("policy_request") or {}
    if not policy_req.get("is_policy_request"):
        return {"policy_answer": None}

    query = state["query"]
    chunks = _retrieve_chunks(query)

    if not chunks:
        return {
            "policy_answer": {
                "answer": "I couldn't find anything relevant in the indexed policy documents to "
                          "answer this right now. Try asking about cyclone warnings, fishing bans, "
                          "or disaster management procedures.",
                "mode": "no_index_or_no_results",
                "sources": [],
            }
        }

    sources = _dedupe_sources(chunks)

    if not GOOGLE_API_KEY:
        print("[ORCA] No GOOGLE_API_KEY found - policy_agent using raw-chunk fallback.")
        return {"policy_answer": {"answer": _raw_chunks_fallback(chunks), "mode": "fallback_raw_chunks", "sources": sources}}

    try:
        answer = _call_gemini(_build_grounded_prompt(query, chunks))
        return {"policy_answer": {"answer": answer, "mode": "llm", "sources": sources}}
    except Exception as e:
        print(f"[ORCA] Gemini policy synthesis failed, using raw-chunk fallback: {e}")
        return {"policy_answer": {"answer": _raw_chunks_fallback(chunks), "mode": "fallback_raw_chunks", "sources": sources}}
