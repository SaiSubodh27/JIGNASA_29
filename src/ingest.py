"""
ingest.py - Parse, clean, chunk and tag official ethics documents.
Reads PDFs listed in data/manifest.json, extracts text, chunks by paragraph,
and saves chunks with rich metadata to data/processed/chunks.json.
"""

import json
import os
import re
from pathlib import Path

# Try pypdf first, fall back to pymupdf (fitz)
try:
    from pypdf import PdfReader as _PdfReader

    def extract_text_from_pdf(pdf_path: str) -> str:
        reader = _PdfReader(pdf_path)
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
        return "\n".join(pages)

except ImportError:
    try:
        import fitz  # pymupdf

        def extract_text_from_pdf(pdf_path: str) -> str:
            doc = fitz.open(pdf_path)
            return "\n".join(page.get_text() for page in doc)

    except ImportError:
        raise ImportError("Install either pypdf or pymupdf: pip install pypdf")

# ── Topic keyword rules ─────────────────────────────────────────────────────
TOPIC_KEYWORDS = {
    "consent": [
        "consent", "assent", "volunteer", "participant", "informed",
        "voluntary", "withdraw", "refusal", "waiver",
    ],
    "data_handling": [
        "data", "privacy", "confidentiality", "anonymi", "pseudonym",
        "storage", "security", "breach", "record", "protect",
    ],
    "authorship": [
        "author", "contribution", "credit", "ghost", "guest", "honorary",
        "corresponding", "acknowledgement",
    ],
    "publication_ethics": [
        "duplicate", "plagiari", "conflict of interest", "disclosure",
        "retract", "correction", "peer review", "salami", "misconduct",
    ],
}


def tag_topics(text: str) -> list[str]:
    """Return a list of matched topic labels for a chunk of text."""
    text_lower = text.lower()
    return [
        topic
        for topic, keywords in TOPIC_KEYWORDS.items()
        if any(kw in text_lower for kw in keywords)
    ] or ["general"]


# ── Text cleaning ────────────────────────────────────────────────────────────
def clean_text(text: str) -> str:
    """Strip headers/footers artefacts and normalise whitespace."""
    # Remove page numbers (standalone digits on a line)
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)
    # Collapse runs of blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Normalise whitespace within a line
    text = re.sub(r"[^\S\n]+", " ", text)
    return text.strip()


# ── Chunking ─────────────────────────────────────────────────────────────────
def chunk_text(text: str, max_words: int = 300, overlap_words: int = 50) -> list[str]:
    """
    Split text into overlapping chunks of ~max_words words.
    Tries to split on paragraph boundaries first, then falls back to word count.
    """
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    current_words: list[str] = []

    for para in paragraphs:
        para_words = para.split()
        
        # If adding this paragraph exceeds the limit, and we already have words
        if current_words and len(current_words) + len(para_words) > max_words:
            chunks.append(" ".join(current_words))
            current_words = current_words[-overlap_words:]
            
        # If the paragraph itself is huge, we need to chunk it directly
        if len(para_words) > max_words:
            # Process the large paragraph in pieces
            for i in range(0, len(para_words), max_words - overlap_words):
                piece = para_words[i:i + max_words]
                if current_words and len(current_words) + len(piece) > max_words:
                    chunks.append(" ".join(current_words))
                    current_words = current_words[-overlap_words:]
                current_words.extend(piece)
                if len(current_words) >= max_words:
                    chunks.append(" ".join(current_words))
                    current_words = current_words[-overlap_words:]
        else:
            current_words.extend(para_words)

    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


# ── Section heuristic ────────────────────────────────────────────────────────
def guess_section(chunk_text: str) -> str:
    """Heuristically extract a section title from the chunk text."""
    first_line = chunk_text.split("\n")[0][:80]
    if re.match(r"^[A-Z0-9\s:\.]{5,60}$", first_line):
        return first_line.strip()
    return "General"


# ── Main pipeline ────────────────────────────────────────────────────────────
def ingest(
    manifest_path: str = "data/manifest.json",
    output_path: str = "data/processed/chunks.json",
) -> list[dict]:
    manifest_path = Path(manifest_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    all_chunks: list[dict] = []

    for doc in manifest:
        pdf_path = Path(doc["file"])
        if not pdf_path.exists():
            print(f"[WARN] PDF not found: {pdf_path} — skipping '{doc['title']}'")
            continue

        print(f"[INFO] Ingesting: {doc['title']}")
        raw_text = extract_text_from_pdf(str(pdf_path))
        clean = clean_text(raw_text)
        chunks = chunk_text(clean)

        for idx, chunk in enumerate(chunks):
            chunk_id = f"{doc['doc_id']}_c{idx:04d}"
            topics = tag_topics(chunk)
            all_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc["doc_id"],
                    "doc_title": doc["title"],
                    "publisher": doc["publisher"],
                    "version": doc["version"],
                    "section": guess_section(chunk),
                    "page": -1,  # page-level mapping skipped for simplicity
                    "topic": topics[0],
                    "all_topics": topics,
                    "authority": doc["authority"],
                    "text": chunk,
                }
            )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Saved {len(all_chunks)} chunks to {output_path}")
    return all_chunks


if __name__ == "__main__":
    ingest()
