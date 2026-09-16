"""
One-time (re-runnable) ingestion script for ORCA's policy RAG index.

Extracts text from the real policy PDFs in app/data/policy_docs/, splits
them into overlapping chunks, embeds each chunk with ChromaDB's built-in
default embedding function (all-MiniLM-L6-v2 via onnxruntime - no separate
embedding API/model needed), and persists everything to a local ChromaDB
collection on disk at app/data/policy_index/, so the server never needs to
re-run this at startup.

This is STEP 1 of the RAG feature only: build the index and prove
retrieval works (see tests/test_policy_retrieval.py). No agent/LangGraph
wiring happens here - that's a deliberately separate next step, after
retrieval quality is confirmed.

Run with:
    cd backend
    source venv/bin/activate
    python3 scripts/build_policy_index.py
"""

import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader

BACKEND_DIR = Path(__file__).resolve().parent.parent
POLICY_DOCS_DIR = BACKEND_DIR / "app" / "data" / "policy_docs"
POLICY_INDEX_DIR = BACKEND_DIR / "app" / "data" / "policy_index"
COLLECTION_NAME = "orca_policy_docs"

CHUNK_SIZE = 700
CHUNK_OVERLAP = 120

# Real, publicly available documents - not invented. Each entry's "source"
# is kept as chunk metadata so retrieved passages can always be traced back
# to an actual, citable government document (same honesty principle as the
# rest of ORCA's data sourcing - see PROJECT_CONTEXT.md Section 4).
POLICY_DOCS = [
    {
        "filename": "ndma_cyclone_management_guidelines.pdf",
        "title": "National Disaster Management Guidelines: Management of Cyclones",
        "source_url": "https://ndma.gov.in/sites/default/files/PDF/Guidelines/cyclones.pdf",
        "publisher": "National Disaster Management Authority (NDMA), Government of India",
    },
    {
        "filename": "imd_cyclone_warning_sop.pdf",
        "title": "Cyclone Warning in India: Standard Operation Procedure",
        "source_url": "https://mausam.imd.gov.in/imd_latest/contents/pdf/cyclone_sop.pdf",
        "publisher": "India Meteorological Department (IMD)",
    },
    {
        "filename": "cmfri_marine_fisheries_overview.pdf",
        "title": "Overview of Marine Fisheries of India",
        "source_url": "https://eprints.cmfri.org.in/17860/1/AARDO_2023_T%20M%20Najmudeen.pdf",
        "publisher": "ICAR-Central Marine Fisheries Research Institute (CMFRI) / AARDO, 2023 (T M Najmudeen)",
    },
    {
        "filename": "cmfri_kerala_fisheries_policy_brief.pdf",
        "title": "Marine Fisheries Policy Brief - Kerala",
        "source_url": "https://eprints.cmfri.org.in/4000/1/CMFRI_SP_100_ENG.pdf",
        "publisher": "ICAR-Central Marine Fisheries Research Institute (CMFRI)",
    },
    {
        "filename": "fao_safety_at_sea_small_scale_fishers.pdf",
        "title": "Safety at Sea for Small-Scale Fishers",
        "source_url": "https://openknowledge.fao.org/server/api/core/bitstreams/c24d3838-177d-4574-b194-fdac341088e8/content",
        "publisher": "Food and Agriculture Organization of the United Nations (FAO), 2021",
    },
]


def _clean_page_text(text: str) -> str:
    """Collapses PDF-extraction artifacts (stray line breaks, repeated
    whitespace from multi-column layouts) into plain, chunk-friendly text
    without altering the actual words."""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)  # single newlines mid-paragraph -> space
    return text.strip()


def _extract_pages(pdf_path: Path) -> list:
    """Returns a list of (page_number, cleaned_text) for every page that
    actually contains extractable text (skips blank/image-only pages)."""
    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages):
        raw = page.extract_text() or ""
        cleaned = _clean_page_text(raw)
        if cleaned:
            pages.append((i + 1, cleaned))
    return pages


def _chunk_with_page_numbers(pages: list, chunk_size: int, overlap: int) -> list:
    """Concatenates all pages into one text stream (tracking each page's
    start offset), then slides a character window over it - snapping each
    chunk boundary out to the nearest whitespace so words are never split
    mid-token, and overlapping windows so a sentence cut at a chunk
    boundary still appears in full in the neighbouring chunk. Returns a
    list of (chunk_text, page_number) using the page the chunk STARTS on."""
    full_text = ""
    page_offsets = []  # (offset_in_full_text, page_number)
    for page_number, text in pages:
        page_offsets.append((len(full_text), page_number))
        full_text += text + " "

    def page_for_offset(offset: int) -> int:
        page = page_offsets[0][1] if page_offsets else 1
        for off, pg in page_offsets:
            if off <= offset:
                page = pg
            else:
                break
        return page

    chunks = []
    n = len(full_text)
    start = 0
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            while end < n and not full_text[end].isspace():
                end += 1
        chunk_text = full_text[start:end].strip()
        if chunk_text:
            chunks.append((chunk_text, page_for_offset(start)))
        if end >= n:
            break
        next_start = end - overlap
        start = next_start if next_start > start else end
    return chunks


def build_index() -> None:
    POLICY_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(POLICY_INDEX_DIR))

    # Re-runnable: drop any previous version of the collection so this
    # script can be re-run after adding/changing source documents without
    # accumulating duplicate/stale chunks.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    embedding_fn = embedding_functions.DefaultEmbeddingFunction()
    collection = client.create_collection(name=COLLECTION_NAME, embedding_function=embedding_fn)

    total_chunks = 0
    for doc in POLICY_DOCS:
        pdf_path = POLICY_DOCS_DIR / doc["filename"]
        if not pdf_path.exists():
            print(f"  SKIP (file not found): {pdf_path}")
            continue

        pages = _extract_pages(pdf_path)
        print(f"  {doc['filename']}: {len(pages)} pages with extractable text")

        chunks = _chunk_with_page_numbers(pages, CHUNK_SIZE, CHUNK_OVERLAP)
        print(f"  {doc['filename']}: {len(chunks)} chunks (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")

        ids = [f"{doc['filename']}::chunk_{i}" for i in range(len(chunks))]
        documents = [c[0] for c in chunks]
        metadatas = [
            {
                "source_file": doc["filename"],
                "title": doc["title"],
                "source_url": doc["source_url"],
                "publisher": doc["publisher"],
                "page": page_number,
                "chunk_index": i,
            }
            for i, (_, page_number) in enumerate(chunks)
        ]

        # Chroma embeds these via embedding_fn automatically on add().
        # Batch in groups to avoid one giant call for the larger PDF.
        BATCH = 100
        for i in range(0, len(ids), BATCH):
            collection.add(
                ids=ids[i:i + BATCH],
                documents=documents[i:i + BATCH],
                metadatas=metadatas[i:i + BATCH],
            )
        total_chunks += len(chunks)

    print(f"\nDone. {total_chunks} chunks indexed into collection '{COLLECTION_NAME}'")
    print(f"Persisted to: {POLICY_INDEX_DIR}")


if __name__ == "__main__":
    build_index()
