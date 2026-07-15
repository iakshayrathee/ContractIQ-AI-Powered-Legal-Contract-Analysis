"""
tests/test_retrieval.py
========================
Unit tests for the hybrid search implementation (Task 2).

Tests cover:
  - _encode_sparse() produces correct SparseVector structure
  - _is_hybrid_collection() correctly identifies collection type
  - similarity_search() dispatches to hybrid or semantic based on settings
  - RRF fusion path is called when both search_mode=hybrid and collection is hybrid
  - Hybrid search wraps sparse query in NamedSparseVector (fixes 400 Bad Request)
  - Fallback to semantic when sparse encoding fails
  - Fallback to semantic when collection is legacy (dense-only)
  - Score threshold filtering in _postprocess_results (semantic mode)
  - threshold=None skips all filtering (hybrid/RRF mode)
  - Top-1 fallback when all results are below threshold (semantic mode only)
"""

from unittest.mock import MagicMock, patch, call
import pytest

from langchain_core.documents import Document

from app.config import Settings
from app.services.vector_store_service import VectorStoreService, _encode_sparse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hybrid_settings(settings: Settings) -> Settings:
    """Settings with search_mode=hybrid."""
    settings.search_mode = "hybrid"
    settings.retrieval_score_threshold = 0.0  # don't filter in most tests
    return settings


@pytest.fixture
def semantic_settings(settings: Settings) -> Settings:
    """Settings with search_mode=semantic."""
    settings.search_mode = "semantic"
    settings.retrieval_score_threshold = 0.0
    return settings


@pytest.fixture
def vector_service(hybrid_settings: Settings) -> VectorStoreService:
    return VectorStoreService(hybrid_settings)


@pytest.fixture
def semantic_service(semantic_settings: Settings) -> VectorStoreService:
    return VectorStoreService(semantic_settings)


def _make_point(score=0.9, page_content="test content"):
    """Helper: create a mock Qdrant ScoredPoint."""
    point = MagicMock()
    point.score = score
    point.payload = {
        "page_content": page_content,
        "original_content": "{}",
        "source_file": "test.pdf",
    }
    return point


# ---------------------------------------------------------------------------
# _encode_sparse tests
# ---------------------------------------------------------------------------

class TestEncodeSparse:

    def test_encode_sparse_returns_none_when_fastembed_missing(self):
        """If fastembed is not available, encode_sparse should return list of None."""
        with patch("app.services.vector_store_service._get_bm25_encoder", return_value=None):
            result = _encode_sparse(["hello world"])
        assert result == [None]

    def test_encode_sparse_returns_sparse_vector(self):
        """When fastembed is available, should return SparseVector objects."""
        from qdrant_client.models import SparseVector

        mock_embedding = MagicMock()
        mock_embedding.indices.tolist.return_value = [1, 5, 10]
        mock_embedding.values.tolist.return_value = [0.5, 0.3, 0.8]

        mock_encoder = MagicMock()
        mock_encoder.embed.return_value = [mock_embedding]

        with patch("app.services.vector_store_service._get_bm25_encoder", return_value=mock_encoder):
            result = _encode_sparse(["test text"])

        assert len(result) == 1
        sv = result[0]
        assert isinstance(sv, SparseVector)
        assert sv.indices == [1, 5, 10]
        assert sv.values == [0.5, 0.3, 0.8]

    def test_encode_sparse_multiple_texts(self):
        """Should return one SparseVector per input text."""
        from qdrant_client.models import SparseVector

        def make_embedding(indices, values):
            emb = MagicMock()
            emb.indices.tolist.return_value = indices
            emb.values.tolist.return_value = values
            return emb

        mock_encoder = MagicMock()
        mock_encoder.embed.return_value = [
            make_embedding([1, 2], [0.5, 0.3]),
            make_embedding([3, 4], [0.7, 0.2]),
        ]

        with patch("app.services.vector_store_service._get_bm25_encoder", return_value=mock_encoder):
            result = _encode_sparse(["text one", "text two"])

        assert len(result) == 2
        assert all(isinstance(r, SparseVector) for r in result)

    def test_encode_sparse_handles_encoding_error(self):
        """If encoder.embed raises, should return list of None."""
        mock_encoder = MagicMock()
        mock_encoder.embed.side_effect = RuntimeError("encoding failed")

        with patch("app.services.vector_store_service._get_bm25_encoder", return_value=mock_encoder):
            result = _encode_sparse(["bad text"])

        assert result == [None]


# ---------------------------------------------------------------------------
# _is_hybrid_collection tests
# ---------------------------------------------------------------------------

class TestIsHybridCollection:

    def test_returns_true_for_named_vectors(self, vector_service: VectorStoreService):
        """Named vector config (dict) and sparse vector config present → hybrid collection."""
        mock_info = MagicMock()
        mock_info.config.params.vectors = {"dense": MagicMock()}
        mock_info.config.params.sparse_vectors = {"sparse": MagicMock()}
        vector_service._client = MagicMock()
        vector_service._client.get_collection.return_value = mock_info

        assert vector_service._is_hybrid_collection("test_col") is True

    def test_returns_false_for_named_dense_but_no_sparse_config(self, vector_service: VectorStoreService):
        """Named vector config (dict) but no sparse_vectors config → legacy/not hybrid collection."""
        mock_info = MagicMock()
        mock_info.config.params.vectors = {"dense": MagicMock()}
        mock_info.config.params.sparse_vectors = None
        vector_service._client = MagicMock()
        vector_service._client.get_collection.return_value = mock_info

        assert vector_service._is_hybrid_collection("test_col") is False

    def test_returns_false_for_unnamed_vectors(self, vector_service: VectorStoreService):
        """Single VectorParams object (not a dict) → legacy collection."""
        from qdrant_client.models import VectorParams, Distance
        mock_info = MagicMock()
        mock_info.config.params.vectors = VectorParams(size=1536, distance=Distance.COSINE)
        mock_info.config.params.sparse_vectors = None
        vector_service._client = MagicMock()
        vector_service._client.get_collection.return_value = mock_info

        assert vector_service._is_hybrid_collection("test_col") is False

    def test_returns_false_on_exception(self, vector_service: VectorStoreService):
        """If get_collection raises, should return False (safe default)."""
        vector_service._client = MagicMock()
        vector_service._client.get_collection.side_effect = Exception("connection error")

        assert vector_service._is_hybrid_collection("test_col") is False


# ---------------------------------------------------------------------------
# similarity_search dispatch tests
# ---------------------------------------------------------------------------

class TestSimilaritySearchDispatch:

    def test_dispatches_to_hybrid_when_mode_hybrid_and_collection_hybrid(
        self, vector_service: VectorStoreService
    ):
        """hybrid mode + hybrid collection → _hybrid_search called."""
        vector_service._collection_exists = MagicMock(return_value=True)
        vector_service._is_hybrid_collection = MagicMock(return_value=True)
        vector_service._hybrid_search = MagicMock(return_value=[])

        vector_service.similarity_search("query", k=5, collection_name="col")
        vector_service._hybrid_search.assert_called_once_with("query", 5, "col", None)

    def test_dispatches_to_semantic_when_mode_semantic(
        self, semantic_service: VectorStoreService
    ):
        """semantic mode → _semantic_search always called."""
        semantic_service._collection_exists = MagicMock(return_value=True)
        semantic_service._is_hybrid_collection = MagicMock(return_value=True)
        semantic_service._semantic_search = MagicMock(return_value=[])

        semantic_service.similarity_search("query", k=5, collection_name="col")
        semantic_service._semantic_search.assert_called_once_with("query", 5, "col", None)

    def test_falls_back_to_semantic_for_legacy_collection(
        self, vector_service: VectorStoreService
    ):
        """hybrid mode + legacy (dense-only) collection → _semantic_search with warning."""
        vector_service._collection_exists = MagicMock(return_value=True)
        vector_service._is_hybrid_collection = MagicMock(return_value=False)
        vector_service._semantic_search = MagicMock(return_value=[])

        vector_service.similarity_search("query", k=5, collection_name="col")
        vector_service._semantic_search.assert_called_once_with("query", 5, "col", None)

    def test_raises_runtime_error_if_collection_missing(
        self, vector_service: VectorStoreService
    ):
        """Missing collection → RuntimeError."""
        vector_service._collection_exists = MagicMock(return_value=False)

        with pytest.raises(RuntimeError, match="No documents ingested"):
            vector_service.similarity_search("query", k=5, collection_name="missing_col")


# ---------------------------------------------------------------------------
# _semantic_search query param tests
# ---------------------------------------------------------------------------

class TestSemanticSearch:

    def test_semantic_search_uses_dense_vector_name_for_hybrid_collection(
        self, vector_service: VectorStoreService
    ):
        """When collection is hybrid, _semantic_search should query using="dense"."""
        mock_result = MagicMock()
        mock_result.points = []
        vector_service._client = MagicMock()
        vector_service._client.query_points.return_value = mock_result
        vector_service._embeddings = MagicMock()
        vector_service._embeddings.embed_query.return_value = [0.1] * 1536
        vector_service._is_hybrid_collection = MagicMock(return_value=True)

        vector_service._semantic_search("query", k=3, collection_name="col")

        vector_service._client.query_points.assert_called_once()
        call_kwargs = vector_service._client.query_points.call_args.kwargs
        assert call_kwargs["using"] == "dense"

    def test_semantic_search_uses_none_for_legacy_collection(
        self, vector_service: VectorStoreService
    ):
        """When collection is legacy/not hybrid, _semantic_search should query using=None."""
        mock_result = MagicMock()
        mock_result.points = []
        vector_service._client = MagicMock()
        vector_service._client.query_points.return_value = mock_result
        vector_service._embeddings = MagicMock()
        vector_service._embeddings.embed_query.return_value = [0.1] * 1536
        vector_service._is_hybrid_collection = MagicMock(return_value=False)

        vector_service._semantic_search("query", k=3, collection_name="col")

        vector_service._client.query_points.assert_called_once()
        call_kwargs = vector_service._client.query_points.call_args.kwargs
        assert call_kwargs["using"] is None


# ---------------------------------------------------------------------------
# _hybrid_search tests
# ---------------------------------------------------------------------------

class TestHybridSearch:

    def test_hybrid_search_calls_rrf_fusion(self, vector_service: VectorStoreService):
        """_hybrid_search should call client.query_points with FusionQuery(RRF)."""
        from qdrant_client.models import SparseVector, Fusion, FusionQuery

        mock_sparse = SparseVector(indices=[1, 2], values=[0.5, 0.3])
        mock_result = MagicMock()
        mock_result.points = [_make_point(score=0.85)]

        vector_service._client = MagicMock()
        vector_service._client.query_points.return_value = mock_result
        vector_service._embeddings = MagicMock()
        vector_service._embeddings.embed_query.return_value = [0.1] * 1536

        with patch(
            "app.services.vector_store_service._encode_sparse",
            return_value=[mock_sparse],
        ):
            docs = vector_service._hybrid_search("query", k=3, collection_name="col")

        vector_service._client.query_points.assert_called_once()
        call_kwargs = vector_service._client.query_points.call_args.kwargs
        assert call_kwargs["query"] == FusionQuery(fusion=Fusion.RRF)
        assert len(docs) == 1

    def test_hybrid_search_uses_fusion_query_not_plain_fusion(
        self, vector_service: VectorStoreService
    ):
        """
        The outer RRF query must be FusionQuery(fusion=Fusion.RRF), NOT Fusion.RRF.

        Using `query=Fusion.RRF` directly serialises to the bare JSON string "rrf",
        which Qdrant server rejects with:
            400 Bad Request: "Expected some form of vector, id, or a type of query"
        The correct format is `{"fusion": "rrf"}`, achieved via FusionQuery.
        """
        from qdrant_client.models import SparseVector, Fusion, FusionQuery

        mock_sparse = SparseVector(indices=[1, 2], values=[0.5, 0.3])
        mock_result = MagicMock()
        mock_result.points = [_make_point(score=0.05)]

        vector_service._client = MagicMock()
        vector_service._client.query_points.return_value = mock_result
        vector_service._embeddings = MagicMock()
        vector_service._embeddings.embed_query.return_value = [0.1] * 1536

        with patch(
            "app.services.vector_store_service._encode_sparse",
            return_value=[mock_sparse],
        ):
            vector_service._hybrid_search("query", k=3, collection_name="col")

        call_kwargs = vector_service._client.query_points.call_args.kwargs
        outer_query = call_kwargs["query"]

        # Must be FusionQuery, not the raw Fusion enum
        assert isinstance(outer_query, FusionQuery), (
            f"Outer RRF query must be FusionQuery(fusion=Fusion.RRF) to serialise "
            f"to {{\"fusion\": \"rrf\"}}. Got: {type(outer_query).__name__!r} = {outer_query!r}"
        )
        assert outer_query.fusion == Fusion.RRF

        from qdrant_client.models import NearestQuery

        # The dense and sparse prefetch queries must be wrapped in NearestQuery for Qdrant server compatibility
        prefetches = call_kwargs["prefetch"]
        assert len(prefetches) == 2
        
        dense_prefetch = prefetches[0]
        assert isinstance(dense_prefetch.query, NearestQuery)
        assert isinstance(dense_prefetch.query.nearest, list)

        sparse_prefetch = prefetches[1]
        assert isinstance(sparse_prefetch.query, NearestQuery), (
            f"Sparse prefetch query must be a NearestQuery. "
            f"Got: {type(sparse_prefetch.query).__name__!r}"
        )
        assert isinstance(sparse_prefetch.query.nearest, SparseVector), (
            f"NearestQuery must wrap a SparseVector. Got: {type(sparse_prefetch.query.nearest).__name__!r}"
        )

    def test_hybrid_search_skips_threshold_for_rrf_scores(
        self, vector_service: VectorStoreService
    ):
        """
        RRF fusion scores are rank-based (0.01-0.06), not cosine similarities.
        _hybrid_search must pass threshold=None to _postprocess_results so that
        low-but-valid RRF scores are not incorrectly filtered out.
        """
        from qdrant_client.models import SparseVector

        mock_sparse = SparseVector(indices=[1, 2], values=[0.5, 0.3])
        # RRF scores are tiny — would all be below a 0.20 or 0.35 cosine threshold
        mock_result = MagicMock()
        mock_result.points = [
            _make_point(score=0.016),
            _make_point(score=0.014),
            _make_point(score=0.012),
        ]

        vector_service._client = MagicMock()
        vector_service._client.query_points.return_value = mock_result
        vector_service._embeddings = MagicMock()
        vector_service._embeddings.embed_query.return_value = [0.1] * 1536
        # Even with a high cosine threshold, hybrid should return all 3 results
        vector_service._settings.retrieval_score_threshold = 0.35

        with patch(
            "app.services.vector_store_service._encode_sparse",
            return_value=[mock_sparse],
        ):
            docs = vector_service._hybrid_search("query", k=3, collection_name="col")

        # All 3 RRF results must be returned despite being below the cosine threshold
        assert len(docs) == 3, (
            f"Expected 3 results from hybrid search (RRF scores should not be "
            f"filtered by cosine threshold), got {len(docs)}"
        )

    def test_hybrid_search_falls_back_when_sparse_unavailable(
        self, vector_service: VectorStoreService
    ):
        """If sparse encoding returns None, fall back to _semantic_search."""
        vector_service._embeddings = MagicMock()
        vector_service._embeddings.embed_query.return_value = [0.1] * 1536
        vector_service._semantic_search = MagicMock(return_value=[])

        with patch(
            "app.services.vector_store_service._encode_sparse",
            return_value=[None],
        ):
            vector_service._hybrid_search("query", k=3, collection_name="col")

        vector_service._semantic_search.assert_called_once_with("query", 3, "col", None)

    def test_hybrid_search_falls_back_on_query_exception(
        self, vector_service: VectorStoreService
    ):
        """If client.query_points raises, fall back to semantic search."""
        from qdrant_client.models import SparseVector

        mock_sparse = SparseVector(indices=[1], values=[0.5])
        vector_service._client = MagicMock()
        vector_service._client.query_points.side_effect = Exception("Qdrant error")
        vector_service._embeddings = MagicMock()
        vector_service._embeddings.embed_query.return_value = [0.1] * 1536
        vector_service._semantic_search = MagicMock(return_value=[])

        with patch(
            "app.services.vector_store_service._encode_sparse",
            return_value=[mock_sparse],
        ):
            vector_service._hybrid_search("query", k=3, collection_name="col")

        vector_service._semantic_search.assert_called_once()


# ---------------------------------------------------------------------------
# _postprocess_results tests
# ---------------------------------------------------------------------------

class TestPostprocessResults:

    def test_score_threshold_filters_low_scores(self, vector_service: VectorStoreService):
        """Points with score below threshold should be excluded (semantic mode)."""
        vector_service._settings.retrieval_score_threshold = 0.5
        points = [
            _make_point(score=0.8, page_content="high score"),
            _make_point(score=0.3, page_content="low score"),
        ]
        docs = vector_service._postprocess_results(points, threshold=0.5, collection_name="col")
        assert len(docs) == 1
        assert docs[0].page_content == "high score"

    def test_top1_fallback_when_all_below_threshold(self, vector_service: VectorStoreService):
        """If all points fail threshold, top-1 should be returned (semantic mode)."""
        points = [_make_point(score=0.1, page_content="only result")]
        docs = vector_service._postprocess_results(points, threshold=0.9, collection_name="col")
        assert len(docs) == 1
        assert docs[0].page_content == "only result"

    def test_empty_results_returns_empty_list(self, vector_service: VectorStoreService):
        """No points → empty list (no fallback needed)."""
        docs = vector_service._postprocess_results([], threshold=0.5, collection_name="col")
        assert docs == []

    def test_rrf_results_with_none_score_are_included(self, vector_service: VectorStoreService):
        """RRF fusion results may have None score — they should pass through."""
        point = _make_point(score=None, page_content="rrf result")
        docs = vector_service._postprocess_results([point], threshold=0.5, collection_name="col")
        assert len(docs) == 1
        assert docs[0].page_content == "rrf result"

    def test_threshold_none_returns_all_results(self, vector_service: VectorStoreService):
        """
        threshold=None (hybrid/RRF mode) must return ALL results regardless of score.
        This is critical because RRF scores (0.01-0.06) would always be wiped out
        by a cosine-similarity threshold like 0.20 or 0.35.
        """
        points = [
            _make_point(score=0.016, page_content="rrf rank 1"),
            _make_point(score=0.014, page_content="rrf rank 2"),
            _make_point(score=0.001, page_content="rrf rank 3"),
        ]
        # Even with a high cosine threshold set on settings, threshold=None bypasses it
        docs = vector_service._postprocess_results(points, threshold=None, collection_name="col")
        assert len(docs) == 3, (
            "threshold=None must return all results; no score-based filtering for hybrid mode"
        )

    def test_threshold_none_no_top1_fallback(self, vector_service: VectorStoreService):
        """
        When threshold=None, the top-1 fallback must NOT fire (it only applies
        when a threshold actually filtered everything out in semantic mode).
        """
        # threshold=None with one result — it should just come through normally,
        # no warning logged about 'falling back to top-1'
        points = [_make_point(score=0.005, page_content="sole rrf result")]
        docs = vector_service._postprocess_results(points, threshold=None, collection_name="col")
        assert len(docs) == 1

    def test_returns_correct_document_structure(self, vector_service: VectorStoreService):
        """Each returned Document must have page_content, original_content, source_file."""
        point = _make_point(score=0.9, page_content="contract clause text")
        docs = vector_service._postprocess_results([point], threshold=0.0, collection_name="col")
        assert len(docs) == 1
        doc = docs[0]
        assert isinstance(doc, Document)
        assert doc.page_content == "contract clause text"
        assert "original_content" in doc.metadata
        assert "source_file" in doc.metadata
