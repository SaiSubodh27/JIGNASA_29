"""
retrieve.py - Hybrid BM25 + TF-IDF/LSA embedding retrieval with RRF.
Uses scikit-learn TF-IDF + TruncatedSVD instead of sentence-transformers
so it works on any CPU without PyTorch/AVX2 requirements.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.preprocessing import normalize
import faiss


# ── Paths (match index.py) ───────────────────────────────────────────────────
CHUNKS_PATH = "data/processed/chunks.json"
BM25_PATH = "data/processed/bm25.pkl"
FAISS_PATH = "data/processed/faiss.index"
TFIDF_PATH = "data/processed/tfidf.pkl"
SVD_PATH = "data/processed/svd.pkl"
META_PATH = "data/processed/chunk_meta.json"

# Similarity threshold: if the best chunk score is below this → "not found"
MIN_FAISS_SCORE = 0.05  # lower threshold since LSA scores are smaller than neural


def tokenize(text: str) -> list[str]:
    return text.lower().split()


def rrf(rank_lists: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion across multiple ranked lists of chunk IDs."""
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for pos, chunk_id in enumerate(ranks):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + pos + 1)
    return sorted(scores, key=lambda cid: scores[cid], reverse=True)


class HybridRetriever:
    """Load-once retriever that supports BM25, embedding, and hybrid search."""

    def __init__(
        self,
        chunks_path: str = CHUNKS_PATH,
        bm25_path: str = BM25_PATH,
        faiss_path: str = FAISS_PATH,
        tfidf_path: str = TFIDF_PATH,
        svd_path: str = SVD_PATH,
        meta_path: str = META_PATH,
    ):
        # Load chunks
        with open(chunks_path, encoding="utf-8") as f:
            chunks: list[dict] = json.load(f)
        self._chunk_map: dict[str, dict] = {c["chunk_id"]: c for c in chunks}
        self._chunk_list: list[dict] = chunks

        # Load BM25
        with open(bm25_path, "rb") as f:
            self._bm25: BM25Okapi = pickle.load(f)

        # Load FAISS
        self._faiss_index = faiss.read_index(faiss_path)

        # Chunk ID order (same order as FAISS rows)
        with open(meta_path, encoding="utf-8") as f:
            self._chunk_ids: list[str] = json.load(f)

        # TF-IDF + SVD for query encoding
        with open(tfidf_path, "rb") as f:
            self._tfidf = pickle.load(f)
        with open(svd_path, "rb") as f:
            self._svd = pickle.load(f)

        print("[INFO] HybridRetriever loaded.")

    def _encode(self, text: str) -> np.ndarray:
        """Encode a query string to an L2-normalised LSA vector."""
        tfidf_vec = self._tfidf.transform([text])       # sparse (1, vocab)
        lsa_vec = self._svd.transform(tfidf_vec)        # dense (1, lsa_dim)
        lsa_vec = normalize(lsa_vec, norm="l2").astype(np.float32)
        return lsa_vec

    # ── Individual retrievers ─────────────────────────────────────────────────
    def search_bm25(self, query: str, top_k: int = 20) -> list[str]:
        """Return top-k chunk IDs ranked by BM25."""
        scores = self._bm25.get_scores(tokenize(query))
        ranked = np.argsort(scores)[::-1][:top_k]
        return [self._chunk_ids[i] for i in ranked if scores[i] > 0]

    def search_embedding(
        self, query: str, top_k: int = 20
    ) -> tuple[list[str], float]:
        """Return (ranked chunk IDs, best cosine score) from FAISS."""
        qvec = self._encode(query)
        distances, indices = self._faiss_index.search(qvec, min(top_k, len(self._chunk_ids)))
        chunk_ids = [
            self._chunk_ids[i]
            for i in indices[0]
            if 0 <= i < len(self._chunk_ids)
        ]
        best_score = float(distances[0][0]) if len(distances[0]) > 0 else 0.0
        return chunk_ids, best_score

    # ── Hybrid search ─────────────────────────────────────────────────────────
    def search(
        self,
        query: str,
        top_k: int = 5,
        topic_filter: Optional[str] = None,
        mode: str = "hybrid",  # "hybrid" | "bm25" | "embedding"
    ) -> tuple[list[dict], bool]:
        """
        Returns (top_k chunks, confidence_ok).
        confidence_ok is False when no chunk passes MIN_FAISS_SCORE.
        """
        best_score = 1.0  # assume ok until measured

        if mode == "bm25":
            bm25_ids = self.search_bm25(query, top_k=top_k * 4)
            ranked_ids = bm25_ids
            best_score = 1.0  # BM25 doesn't give a normalised 0-1 score
        elif mode == "embedding":
            emb_ids, best_score = self.search_embedding(query, top_k=top_k * 4)
            ranked_ids = emb_ids
        else:  # hybrid (default)
            bm25_ids = self.search_bm25(query, top_k=top_k * 4)
            emb_ids, best_score = self.search_embedding(query, top_k=top_k * 4)
            ranked_ids = rrf([bm25_ids, emb_ids])

        # Optional topic filter
        if topic_filter:
            ranked_ids = [
                cid
                for cid in ranked_ids
                if topic_filter in self._chunk_map.get(cid, {}).get("all_topics", [])
            ]

        # Build result list, prefer lower authority number (more authoritative)
        chunks = [self._chunk_map[cid] for cid in ranked_ids if cid in self._chunk_map]
        chunks = sorted(chunks, key=lambda c: c.get("authority", 99))[:top_k]

        confidence_ok = best_score >= MIN_FAISS_SCORE or len(bm25_ids if mode == "bm25" else chunks) > 0
        return chunks, confidence_ok
