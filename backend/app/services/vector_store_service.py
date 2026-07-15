import asyncio
import hashlib
import json
import logging
import re
import uuid
from typing import Optional

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
    SparseVector,
    SparseVectorParams,
    Prefetch,
    NearestQuery,
    Fusion,
    FusionQuery,
)

from app.config import Settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536  # text-embedding-3-small output dimension

_bm25_encoder = None

def _get_bm25_encoder():
    global _bm25_encoder
    if _bm25_encoder is None:
        try:
            from fastembed import SparseTextEmbedding
            _bm25_encoder = SparseTextEmbedding("Qdrant/bm25")
        except ImportError:
            logger.warning("fastembed not installed. Sparse embeddings will be disabled.")
            return None
    return _bm25_encoder

def _encode_sparse(texts: list[str]) -> list[Optional[SparseVector]]:
    encoder = _get_bm25_encoder()
    if not encoder:
        return [None] * len(texts)
    try:
        embeddings = list(encoder.embed(texts))
        result = []
        for emb in embeddings:
            result.append(
                SparseVector(
                    indices=emb.indices.tolist(),
                    values=emb.values.tolist(),
                )
            )
        return result
    except Exception as exc:
        logger.error("Error generating sparse embeddings: %s", exc)
        return [None] * len(texts)


class VectorStoreService:
    """
    Manages Qdrant vector stores across multiple named collections (one per project).
    Supports hybrid (dense + sparse) retrieval and semantic (dense-only) fallback.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._embeddings: Optional[OpenAIEmbeddings] = None
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(
                url=self._settings.qdrant_url,
                api_key=self._settings.qdrant_api_key,
            )
        return self._client

    @property
    def embeddings(self) -> OpenAIEmbeddings:
        if self._embeddings is None:
            self._embeddings = OpenAIEmbeddings(
                model=self._settings.openai_model_embedding,
                api_key=self._settings.openai_api_key,
            )
        return self._embeddings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collection_exists(self, collection_name: str) -> bool:
        try:
            collections = self.client.get_collections().collections
            return any(c.name == collection_name for c in collections)
        except Exception as exc:
            logger.warning("Could not inspect Qdrant collections: %s", exc)
            return False

    def _is_hybrid_collection(self, collection_name: str) -> bool:
        try:
            info = self.client.get_collection(collection_name)
            params = info.config.params
            has_dense = isinstance(params.vectors, dict) and "dense" in params.vectors
            has_sparse = getattr(params, "sparse_vectors", None) is not None
            return bool(has_dense and has_sparse)
        except Exception as exc:
            logger.warning("Error checking collection type for '%s': %s", collection_name, exc)
            return False

    def _ensure_collection(self, collection_name: str) -> None:
        if not self._collection_exists(collection_name):
            search_mode = getattr(self._settings, "search_mode", "semantic")
            if search_mode == "hybrid":
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        "dense": VectorParams(
                            size=EMBEDDING_DIM,
                            distance=Distance.COSINE,
                        )
                    },
                    sparse_vectors_config={
                        "sparse": SparseVectorParams()
                    }
                )
            else:
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=EMBEDDING_DIM,
                        distance=Distance.COSINE,
                    ),
                )
            logger.info("Created Qdrant collection '%s'.", collection_name)

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self.embeddings.embed_documents(texts)

    def _build_contextual_embedding_text(self, doc: Document) -> str:
        """
        Phase 3 Fix (Bug 5): Build contextual embedding text with metadata prefix.
        
        Prepends metadata context (source file, page number, clause type, section reference)
        to improve retrieval for queries that reference page numbers, clause types, or sections.
        
        The stored page_content stays as raw text for display, but the embedded text
        gets a contextual prefix for better semantic matching.
        
        Args:
            doc: Document with page_content and metadata
            
        Returns:
            Contextual text string ready for embedding
        """
        try:
            original = json.loads(doc.metadata.get("original_content", "{}"))
        except (json.JSONDecodeError, TypeError):
            original = {}
        
        # Extract metadata
        source_file = doc.metadata.get("source_file", "")
        page_number = original.get("page_number")
        clause_type = original.get("clause_type")
        section_reference = original.get("section_reference")
        
        # Build contextual prefix
        context_parts = []
        if source_file:
            context_parts.append(f"Document: {source_file}")
        if page_number is not None:
            context_parts.append(f"Page: {page_number}")
        if clause_type:
            context_parts.append(f"Clause: {clause_type}")
        if section_reference:
            context_parts.append(f"Section: {section_reference}")
        
        if context_parts:
            context_prefix = "[" + " | ".join(context_parts) + "]\n"
            return context_prefix + doc.page_content
        else:
            return doc.page_content

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Called at startup. Verify Qdrant connectivity."""
        try:
            collections = self.client.get_collections().collections
            names = [c.name for c in collections]
            logger.info("Qdrant connected. Existing collections: %s", names or "(none)")
        except Exception as exc:
            logger.warning("Could not connect to Qdrant: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_loaded(self, collection_name: str | None = None) -> bool:
        name = collection_name or self._settings.qdrant_collection_name
        return self._collection_exists(name)

    def create_or_replace(self, documents: list[Document], collection_name: str) -> None:
        """Delete the existing collection and rebuild from provided documents."""
        if self._collection_exists(collection_name):
            self.client.delete_collection(collection_name)
            logger.info("Deleted existing collection '%s'.", collection_name)

        self._ensure_collection(collection_name)

        # Phase 3 Fix (Bug 5): Use contextual embedding text
        contextual_texts = [self._build_contextual_embedding_text(doc) for doc in documents]
        vectors = self._embed_texts(contextual_texts)

        is_hybrid = self._is_hybrid_collection(collection_name)
        sparse_vectors = _encode_sparse(contextual_texts) if is_hybrid else None

        points = []
        for i, (doc, vector) in enumerate(zip(documents, vectors)):
            # Phase 2 Fix (Bug 4): Store metadata as top-level payload fields
            # This enables metadata-based filtering and ensures page numbers survive
            try:
                original = json.loads(doc.metadata.get("original_content", "{}"))
            except (json.JSONDecodeError, TypeError):
                original = {}
            
            payload = {
                "page_content": doc.page_content,
                "original_content": doc.metadata.get("original_content", "{}"),
                "source_file": doc.metadata.get("source_file", ""),
                # Top-level metadata fields for efficient filtering
                "page_number": original.get("page_number"),
                "chunk_index": original.get("chunk_index"),
                "clause_type": original.get("clause_type"),
                "section_reference": original.get("section_reference"),
            }
            
            if is_hybrid:
                sparse_vector = sparse_vectors[i] if sparse_vectors else None
                point_vector = {
                    "dense": vector,
                    "sparse": sparse_vector,
                }
            else:
                point_vector = vector

            points.append(
                PointStruct(id=str(uuid.uuid4()), vector=point_vector, payload=payload)
            )

        # Qdrant supports batch upsert up to ~1000 at a time
        batch_size = 500
        for i in range(0, len(points), batch_size):
            self.client.upsert(
                collection_name=collection_name,
                points=points[i : i + batch_size],
            )

        logger.info("Created collection '%s' with %d documents.", collection_name, len(documents))

    def append_documents(self, documents: list[Document], collection_name: str) -> None:
        """Add documents without wiping; falls back to create_or_replace if absent."""
        if not self._collection_exists(collection_name):
            logger.info("No existing collection '%s'; calling create_or_replace.", collection_name)
            return self.create_or_replace(documents, collection_name)

        # Phase 3 Fix (Bug 5): Use contextual embedding text
        contextual_texts = [self._build_contextual_embedding_text(doc) for doc in documents]
        vectors = self._embed_texts(contextual_texts)

        is_hybrid = self._is_hybrid_collection(collection_name)
        sparse_vectors = _encode_sparse(contextual_texts) if is_hybrid else None

        points = []
        for i, (doc, vector) in enumerate(zip(documents, vectors)):
            # Phase 2 Fix (Bug 4): Store metadata as top-level payload fields
            try:
                original = json.loads(doc.metadata.get("original_content", "{}"))
            except (json.JSONDecodeError, TypeError):
                original = {}
            
            payload = {
                "page_content": doc.page_content,
                "original_content": doc.metadata.get("original_content", "{}"),
                "source_file": doc.metadata.get("source_file", ""),
                # Top-level metadata fields for efficient filtering
                "page_number": original.get("page_number"),
                "chunk_index": original.get("chunk_index"),
                "clause_type": original.get("clause_type"),
                "section_reference": original.get("section_reference"),
            }
            
            if is_hybrid:
                sparse_vector = sparse_vectors[i] if sparse_vectors else None
                point_vector = {
                    "dense": vector,
                    "sparse": sparse_vector,
                }
            else:
                point_vector = vector

            points.append(
                PointStruct(id=str(uuid.uuid4()), vector=point_vector, payload=payload)
            )

        batch_size = 500
        for i in range(0, len(points), batch_size):
            self.client.upsert(
                collection_name=collection_name,
                points=points[i : i + batch_size],
            )

        count = self.document_count(collection_name)
        logger.info("Appended %d docs to '%s'. Total: %d.", len(documents), collection_name, count)

    def similarity_search(
        self, query: str, k: int, collection_name: str, page_filter: int | None = None
    ) -> list[Document]:
        """
        Perform similarity search with optional page filtering.
        
        Args:
            query: Search query string
            k: Number of results to return
            collection_name: Qdrant collection name
            page_filter: Optional page number to filter results (Phase 4 fix)
            
        Returns:
            List of retrieved Document objects
        """
        if not self._collection_exists(collection_name):
            raise RuntimeError(
                f"No documents ingested into project collection '{collection_name}' yet."
            )

        search_mode = getattr(self._settings, "search_mode", "semantic")
        if search_mode == "hybrid" and self._is_hybrid_collection(collection_name):
            return self._hybrid_search(query, k, collection_name, page_filter)
        else:
            return self._semantic_search(query, k, collection_name, page_filter)

    def _semantic_search(
        self, query: str, k: int, collection_name: str, page_filter: int | None = None
    ) -> list[Document]:
        query_vector = self.embeddings.embed_query(query)
        threshold = self._settings.retrieval_score_threshold

        using = "dense" if self._is_hybrid_collection(collection_name) else None

        # Phase 4 Fix: Add page filter if specified
        query_filter = None
        if page_filter is not None:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="page_number",
                        match=MatchValue(value=page_filter),
                    )
                ]
            )
            logger.info("Applying page filter for page %d", page_filter)

        results = self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            using=using,
            limit=k,
            with_payload=True,
            query_filter=query_filter,
        ).points

        return self._postprocess_results(results, threshold, collection_name, 
                                        query_vector=None, search_mode="semantic")

    def _hybrid_search(
        self, query: str, k: int, collection_name: str, page_filter: int | None = None
    ) -> list[Document]:
        """
        Hybrid search: prefetch dense + sparse, fuse with RRF.
        Falls back to semantic if sparse encoding fails.
        """
        query_vector = self.embeddings.embed_query(query)
        sparse_vecs = _encode_sparse([query])
        query_sparse = sparse_vecs[0] if sparse_vecs else None

        if query_sparse is None:
            logger.warning(
                "Sparse encoding unavailable for query; falling back to semantic search."
            )
            return self._semantic_search(query, k, collection_name, page_filter)

        dense_limit = 50
        sparse_limit = 50

        # Phase 4 Fix: Add page filter if specified
        query_filter = None
        if page_filter is not None:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="page_number",
                        match=MatchValue(value=page_filter),
                    )
                ]
            )
            logger.info("Applying page filter for page %d in hybrid search", page_filter)

        try:
            results = self.client.query_points(
                collection_name=collection_name,
                prefetch=[
                    Prefetch(
                        query=NearestQuery(nearest=query_vector),
                        using="dense",
                        limit=dense_limit,
                    ),
                    Prefetch(
                        query=NearestQuery(nearest=query_sparse),
                        using="sparse",
                        limit=sparse_limit,
                    ),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=k,
                with_payload=True,
                with_vectors=False,  # Don't fetch vectors for hybrid - we use rank-based scoring
                query_filter=query_filter,
            ).points
        except Exception as exc:
            logger.warning(
                "Hybrid query failed (%s); falling back to semantic search.", exc
            )
            return self._semantic_search(query, k, collection_name, page_filter)

        # RRF scores are rank-based and not filtered by similarity threshold in hybrid mode
        # Pass search_mode="hybrid" to use normalized rank-based scores
        return self._postprocess_results(
            results, threshold=None, collection_name=collection_name, 
            query_vector=None, search_mode="hybrid"
        )

    def _postprocess_results(
        self, results, threshold: float | None, collection_name: str, 
        query_vector: list[float] | None = None, search_mode: str = "semantic"
    ) -> list[Document]:
        """
        Apply score threshold and convert Qdrant points to Documents.
        
        For hybrid search (RRF): Uses normalized rank-based scores (1.0 - rank/total)
        For semantic search: Uses Qdrant's native cosine similarity scores
        
        Args:
            results: Qdrant query results
            threshold: Minimum score threshold (only applied to semantic mode)
            collection_name: Name of the collection
            query_vector: Query embedding vector (unused - kept for backward compatibility)
            search_mode: "hybrid" or "semantic" to determine scoring strategy
        """
        if not results:
            return []

        # For hybrid mode: convert RRF ranks to normalized confidence scores
        if search_mode == "hybrid":
            total_results = len(results)
            for rank, r in enumerate(results):
                # Normalized rank-based score: top result = 1.0, last result = ~0
                # This gives the UI a meaningful 0-1 confidence score
                r.score = 1.0 - (rank / max(total_results, 1))

        # For semantic mode: Qdrant's native cosine scores are already correct
        # (they're in [0,1] range for Distance.COSINE)
        # No modification needed - r.score is already set by Qdrant

        score_summary = ", ".join(
            f"{r.score:.3f}" for r in results if hasattr(r, "score") and r.score is not None
        )
        threshold_label = f"{threshold:.2f}" if threshold is not None else "N/A (RRF ranking)"
        logger.info(
            "Relevance scores for collection '%s' [%s mode] (threshold=%s): [%s]",
            collection_name, search_mode, threshold_label, score_summary,
        )

        filtered = []
        for r in results:
            score = getattr(r, "score", None)
            
            # Only apply threshold filtering in semantic mode
            if search_mode == "semantic" and threshold is not None and score is not None and score < threshold:
                logger.debug(
                    "Filtered out chunk with score %.3f (below threshold %.2f)",
                    score, threshold
                )
                continue
            
            payload = r.payload or {}
            doc = Document(
                page_content=payload.get("page_content", ""),
                metadata={
                    "original_content": payload.get("original_content", "{}"),
                    "source_file": payload.get("source_file", ""),
                    "relevance_score": float(score) if score is not None else None,
                },
            )
            filtered.append(doc)

        # Fallback to top-1 only in semantic mode when all results filtered out
        if not filtered and results and threshold is not None and search_mode == "semantic":
            logger.warning(
                "All %d chunks scored below threshold %.2f; falling back to top-1.",
                len(results), threshold,
            )
            r = results[0]
            score = getattr(r, "score", None)
            filtered = [Document(
                page_content=r.payload.get("page_content", ""),
                metadata={
                    "original_content": r.payload.get("original_content", "{}"),
                    "source_file": r.payload.get("source_file", ""),
                    "relevance_score": float(score) if score is not None else None,
                },
            )]

        logger.info(
            "Returning %d/%d chunks for collection '%s' [%s mode].",
            len(filtered), len(results), collection_name, search_mode,
        )
        return filtered

    def document_count(self, collection_name: str | None = None) -> int:
        name = collection_name or self._settings.qdrant_collection_name
        if not self._collection_exists(name):
            return 0
        try:
            info = self.client.get_collection(name)
            return info.points_count or 0
        except Exception:
            return 0

    def delete_document_points(self, source_file: str, collection_name: str) -> None:
        """
        Delete all vector points associated with a specific document from a collection.
        Filters by the 'source_file' field in the payload.
        """
        if not self._collection_exists(collection_name):
            logger.warning("Collection '%s' does not exist; nothing to delete.", collection_name)
            return

        try:
            # Delete all points where payload.source_file matches the given source_file
            self.client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="source_file",
                            match=MatchValue(value=source_file),
                        )
                    ]
                ),
            )
            logger.info(
                "Deleted all points with source_file='%s' from collection '%s'.",
                source_file, collection_name
            )
        except Exception as exc:
            logger.error(
                "Error deleting document points for '%s' in collection '%s': %s",
                source_file, collection_name, exc
            )
            raise

    def delete_collection(self, collection_name: str) -> None:
        if self._collection_exists(collection_name):
            try:
                self.client.delete_collection(collection_name)
                logger.info("Deleted collection '%s'.", collection_name)
            except Exception as exc:
                logger.warning("Error deleting collection '%s': %s", collection_name, exc)

    def chunk_stats(self, collection_name: str) -> dict:
        """
        Get lightweight statistics about chunks without fetching full content.
        Returns total count and breakdown by type (text/table/image).
        """
        if not self._collection_exists(collection_name):
            return {"total": 0, "text": 0, "table": 0, "image": 0}

        try:
            all_points = []
            offset = None
            while True:
                result = self.client.scroll(
                    collection_name=collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points, next_offset = result
                all_points.extend(points)
                if next_offset is None:
                    break
                offset = next_offset
        except Exception as exc:
            logger.error("Failed to get chunk stats from '%s': %s", collection_name, exc)
            return {"total": 0, "text": 0, "table": 0, "image": 0}

        text_count = 0
        table_count = 0
        image_count = 0

        for point in all_points:
            payload = point.payload or {}
            original: dict = {}
            if "original_content" in payload:
                try:
                    original = json.loads(payload["original_content"])
                except (json.JSONDecodeError, TypeError):
                    pass

            tables_html: list[str] = original.get("tables_html", [])
            images_base64: list[str] = original.get("images_base64", [])

            # Count chunk types based on content type
            # A chunk is categorized by its primary content type
            has_tables = bool(tables_html)
            has_images = bool(images_base64)
            
            if has_tables:
                table_count += 1
            if has_images:
                image_count += 1
            # Count as text only if it has neither tables nor images
            if not has_tables and not has_images:
                text_count += 1

        return {
            "total": len(all_points),
            "text": text_count,
            "table": table_count,
            "image": image_count,
        }

    def list_chunks(
        self, collection_name: str, type_filter: str | None = None
    ) -> list[dict]:
        """
        Retrieve all stored chunks; optionally filter by content type (text/table/image).
        """
        if not self._collection_exists(collection_name):
            return []

        try:
            all_points = []
            offset = None
            while True:
                result = self.client.scroll(
                    collection_name=collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points, next_offset = result
                all_points.extend(points)
                if next_offset is None:
                    break
                offset = next_offset
        except Exception as exc:
            logger.error("Failed to get chunks from '%s': %s", collection_name, exc)
            return []

        chunks = []
        for point in all_points:
            payload = point.payload or {}
            content = payload.get("page_content", "")
            original: dict = {}
            if "original_content" in payload:
                try:
                    original = json.loads(payload["original_content"])
                except (json.JSONDecodeError, TypeError):
                    pass

            raw_text: str = original.get("raw_text", content)
            tables_html: list[str] = original.get("tables_html", [])
            images_base64: list[str] = original.get("images_base64", [])

            content_types = ["text"]
            if tables_html:
                content_types.append("table")
            if images_base64:
                content_types.append("image")

            if type_filter and type_filter not in content_types:
                continue

            source_file: str = payload.get("source_file", "")

            chunks.append({
                "page_number": original.get("page_number") if isinstance(original, dict) else None,
                "clause_type": original.get("clause_type") if isinstance(original, dict) else None,
                "chunk_id": str(point.id),
                "content": content,
                "content_types": content_types,
                "raw_text": raw_text,
                "tables_html": tables_html,
                "images_base64": images_base64,
                "source_file": source_file,
            })

        return chunks
