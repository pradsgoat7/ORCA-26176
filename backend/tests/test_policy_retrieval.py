"""
RAG STEP 1 verification - proves retrieval quality against the real,
already-built policy index (see scripts/build_policy_index.py), before
any agent/LangGraph wiring is attempted.

This is deliberately a READ-only script against the persisted ChromaDB
collection - it does not rebuild the index. Run
scripts/build_policy_index.py first if app/data/policy_index/ doesn't
exist yet.

This prints the actual retrieved chunks for each query so a human can
judge relevance directly - passing "the code ran without errors" is NOT
sufficient per this project's testing philosophy (PROJECT_CONTEXT.md
Section 7); the printed text itself is the real verification.

Run with:
    cd backend
    source venv/bin/activate
    python3 -m tests.test_policy_retrieval
"""

from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

BACKEND_DIR = Path(__file__).resolve().parent.parent
POLICY_INDEX_DIR = BACKEND_DIR / "app" / "data" / "policy_index"
COLLECTION_NAME = "orca_policy_docs"

TEST_QUERIES = [
    # Original cyclone-focused queries (NDMA + IMD docs)
    "why do cyclone warnings matter for fishermen",
    "what should coastal authorities do during a cyclone",
    "why is fishing banned before a cyclone",
    "what is the role of the district disaster management authority in a cyclone",
    "how does IMD classify cyclone intensity",
    # Added when the CMFRI fisheries documents were indexed (see
    # PROJECT_CONTEXT.md Section 14j) - target the fish-productivity/
    # decline coverage gap, directly from the PS's own example question.
    "Why has fish productivity declined in a particular coastal region?",
    "Why has fish production declined in Kerala?",
    "What factors affect marine fish catch trends in India?",
    # Added when the FAO safety-at-sea document was indexed (see
    # PROJECT_CONTEXT.md Section 14m) - target the general safety/
    # best-practices coverage gap found via the "Fishing Creek" bug.
    "best practices while fishing",
    "what safety equipment should I carry before going to sea?",
    "safety tips for fishermen",
]

N_RESULTS = 3


def run() -> None:
    if not POLICY_INDEX_DIR.exists():
        print(f"ERROR: index not found at {POLICY_INDEX_DIR}")
        print("Run 'python3 scripts/build_policy_index.py' first.")
        return

    client = chromadb.PersistentClient(path=str(POLICY_INDEX_DIR))
    embedding_fn = embedding_functions.DefaultEmbeddingFunction()
    collection = client.get_collection(name=COLLECTION_NAME, embedding_function=embedding_fn)

    print(f"Collection '{COLLECTION_NAME}' loaded - {collection.count()} chunks total.\n")

    for query in TEST_QUERIES:
        print("=" * 70)
        print(f"QUERY: {query}")
        print("=" * 70)
        results = collection.query(query_texts=[query], n_results=N_RESULTS)

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        for rank, (doc, meta, dist) in enumerate(zip(docs, metas, dists), start=1):
            print(f"\n  [{rank}] distance={dist:.4f}  source={meta['title']} (p.{meta['page']})")
            print(f"      {doc}")
        print()


if __name__ == "__main__":
    run()
