"""
Semantic reranker using FlashRank (local cross-encoder ONNX model).

Why reranking?
  Vector similarity (cosine/BM25) retrieves candidates quickly but is "fuzzy" —
  it measures embedding distance, not true semantic relevance to the query.
  A cross-encoder (FlashRank) re-scores each candidate chunk by jointly encoding
  the (query, chunk) pair, giving much higher precision at the cost of more compute.
  FlashRank uses a quantized ONNX model locally — no API call, ~2-10ms per batch.

Flow:
  Qdrant vector search (large pool, low threshold)
    → FlashRank cross-encoder re-scores
      → top-N returned to LLM
"""

import logging
from typing import Optional

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# Lazy-initialized global ranker — avoids slowing app startup
_ranker = None


def _get_ranker():
    """Initialize FlashRank ranker lazily on first use."""
    global _ranker
    if _ranker is None:
        try:
            from flashrank import Ranker
            logger.info("Initializing FlashRank cross-encoder model (ms-marco-MiniLM-L-6-v2)...")
            _ranker = Ranker()
            logger.info("FlashRank reranker ready.")
        except ImportError:
            logger.warning(
                "flashrank not installed — reranking disabled. "
                "Run: pip install flashrank"
            )
            _ranker = False  # Sentinel: don't retry import
    return _ranker if _ranker is not False else None


def rerank_documents(
    query: str,
    documents: list[Document],
    top_n: int = 8,
) -> list[Document]:
    """
    Re-score retrieved documents against the query using FlashRank cross-encoder.

    Args:
        query:     The user's question.
        documents: Candidate chunks from Qdrant vector search.
        top_n:     How many top-scoring documents to return to the LLM.

    Returns:
        List of Documents sorted by cross-encoder relevance score (highest first),
        truncated to top_n. Falls back to original Qdrant order if FlashRank fails.
    """
    if not documents:
        return []

    ranker = _get_ranker()
    if ranker is None:
        logger.warning("FlashRank unavailable — returning original Qdrant order.")
        return documents[:top_n]

    try:
        from flashrank import RerankRequest

        passages = [
            {"id": i, "text": doc.page_content}
            for i, doc in enumerate(documents)
        ]

        request = RerankRequest(query=query, passages=passages)
        results = ranker.rerank(request)

        # Map reranked results back to original Document objects (preserving metadata)
        reranked_docs = []
        for res in results[:top_n]:
            original_idx = res["id"]
            doc = documents[original_idx]
            # Attach rerank score to metadata for observability
            doc.metadata["rerank_score"] = round(float(res["score"]), 4)
            reranked_docs.append(doc)

        top_score = results[0]["score"] if results else "N/A"
        logger.info(
            "FlashRank reranked %d → %d docs. Top score: %.4f",
            len(documents),
            len(reranked_docs),
            top_score if isinstance(top_score, float) else 0.0,
        )
        return reranked_docs

    except Exception as exc:
        logger.error("FlashRank reranking failed (%s) — falling back to Qdrant order.", exc)
        return documents[:top_n]
