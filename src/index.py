"""
index.py - Build BM25 and vector (FAISS + TF-IDF LSA) indices from chunks.json.
Uses scikit-learn TF-IDF + TruncatedSVD (LSA) instead of sentence-transformers
so the index builds on any CPU without AVX2 / PyTorch requirements.
Saves both indices to disk so they can be loaded quickly at runtime.
"""

import json
import pickle
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
import faiss


CHUNKS_PATH = "data/processed/chunks.json"
BM25_PATH = "data/processed/bm25.pkl"
FAISS_PATH = "data/processed/faiss.index"
TFIDF_PATH = "data/processed/tfidf.pkl"
SVD_PATH = "data/processed/svd.pkl"
META_PATH = "data/processed/chunk_meta.json"

# LSA dimensionality — lower = faster; higher = more semantic nuance
LSA_DIM = 64


def tokenize(text: str) -> list[str]:
    """Simple whitespace tokenizer for BM25."""
    return text.lower().split()


def build_indices(
    chunks_path: str = CHUNKS_PATH,
    bm25_path: str = BM25_PATH,
    faiss_path: str = FAISS_PATH,
    tfidf_path: str = TFIDF_PATH,
    svd_path: str = SVD_PATH,
    meta_path: str = META_PATH,
    lsa_dim: int = LSA_DIM,
) -> None:
    chunks_path = Path(chunks_path)
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"Chunks file not found: {chunks_path}\n"
            "Run  python src/ingest.py  first."
        )

    with open(chunks_path, encoding="utf-8") as f:
        chunks: list[dict] = json.load(f)

    texts = [c["text"] for c in chunks]
    print(f"[INFO] Building indices over {len(texts)} chunks …")

    # ── BM25 ──────────────────────────────────────────────────────────────────
    print("[INFO] Building BM25 index …")
    tokenized = [tokenize(t) for t in texts]
    bm25 = BM25Okapi(tokenized)
    with open(bm25_path, "wb") as f:
        pickle.dump(bm25, f)
    print(f"[INFO] BM25 index saved to {bm25_path}")

    # ── TF-IDF + LSA embeddings ────────────────────────────────────────────────
    print(f"[INFO] Building TF-IDF vectorizer …")
    tfidf = TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=20_000,
        sublinear_tf=True,
    )
    tfidf_matrix = tfidf.fit_transform(texts)  # sparse (n_docs, vocab)
    with open(tfidf_path, "wb") as f:
        pickle.dump(tfidf, f)
    print(f"[INFO] TF-IDF saved to {tfidf_path}")

    print(f"[INFO] Fitting TruncatedSVD (LSA) with {lsa_dim} components …")
    actual_dim = min(lsa_dim, len(texts) - 1)
    svd = TruncatedSVD(n_components=actual_dim, random_state=42)
    embeddings = svd.fit_transform(tfidf_matrix)  # dense (n_docs, lsa_dim)
    embeddings = normalize(embeddings, norm="l2").astype(np.float32)
    with open(svd_path, "wb") as f:
        pickle.dump(svd, f)
    print(f"[INFO] SVD saved to {svd_path}")

    # ── FAISS index ───────────────────────────────────────────────────────────
    dim = embeddings.shape[1]
    print(f"[INFO] Building FAISS IndexFlatIP (dim={dim}) …")
    index = faiss.IndexFlatIP(dim)  # inner-product on L2-normalised = cosine
    index.add(embeddings)
    faiss.write_index(index, faiss_path)
    print(f"[INFO] FAISS index saved to {faiss_path}")

    # ── Chunk ID order ─────────────────────────────────────────────────────────
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump([c["chunk_id"] for c in chunks], f)
    print(f"[INFO] Chunk ID list saved to {meta_path}")
    print(f"[INFO] Done. {len(texts)} chunks indexed.")


if __name__ == "__main__":
    build_indices()
