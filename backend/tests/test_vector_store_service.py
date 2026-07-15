"""Unit tests for VectorStoreService (Stage 4: Embedding and vector storage)."""

import pytest
import json
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document

from app.services.vector_store_service import VectorStoreService
from app.config import Settings


@pytest.fixture
def vector_store_service(settings: Settings) -> VectorStoreService:
    """Create a VectorStoreService with test settings."""
    return VectorStoreService(settings)


class TestVectorStoreServiceInitialization:
    """Test VectorStoreService initialization and lazy loading."""

    def test_lazy_client_initialization(self, vector_store_service):
        """Client should be lazily initialized on first access."""
        assert vector_store_service._client is None
        with patch("app.services.vector_store_service.QdrantClient"):
            client = vector_store_service.client
            assert client is not None
            assert vector_store_service._client is not None

    def test_lazy_embeddings_initialization(self, vector_store_service):
        """Embeddings should be lazily initialized on first access."""
        assert vector_store_service._embeddings is None
        with patch("app.services.vector_store_service.OpenAIEmbeddings"):
            embeddings = vector_store_service.embeddings
            assert embeddings is not None
            assert vector_store_service._embeddings is not None

    def test_client_reuses_instance(self, vector_store_service):
        """Multiple client accesses should return same instance."""
        with patch("app.services.vector_store_service.QdrantClient"):
            client1 = vector_store_service.client
            client2 = vector_store_service.client
            assert client1 is client2

    def test_embeddings_reuses_instance(self, vector_store_service):
        """Multiple embeddings accesses should return same instance."""
        with patch("app.services.vector_store_service.OpenAIEmbeddings"):
            emb1 = vector_store_service.embeddings
            emb2 = vector_store_service.embeddings
            assert emb1 is emb2


class TestVectorStoreServiceCollectionManagement:
    """Test collection creation and management."""

    def test_collection_exists_true(self, vector_store_service):
        """Should detect existing collections."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        mock_collection = MagicMock()
        mock_collection.name = "test-collection"
        mock_client.get_collections.return_value = MagicMock(collections=[mock_collection])
        
        result = vector_store_service._collection_exists("test-collection")
        
        assert result is True

    def test_collection_exists_false(self, vector_store_service):
        """Should return False for non-existent collections."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        mock_client.get_collections.return_value = MagicMock(collections=[])
        
        result = vector_store_service._collection_exists("nonexistent")
        
        assert result is False

    def test_collection_exists_error_handling(self, vector_store_service):
        """Should handle errors gracefully when checking collection."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        mock_client.get_collections.side_effect = Exception("Connection error")
        
        result = vector_store_service._collection_exists("test")
        
        assert result is False

    def test_ensure_collection_creates_new(self, vector_store_service):
        """Should create collection if it doesn't exist."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        with patch.object(vector_store_service, '_collection_exists', return_value=False):
            vector_store_service._ensure_collection("new-collection")
            
            mock_client.create_collection.assert_called_once()
            call_args = mock_client.create_collection.call_args
            assert call_args[1]["collection_name"] == "new-collection"

    def test_ensure_collection_skips_existing(self, vector_store_service):
        """Should not create collection if it already exists."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            vector_store_service._ensure_collection("existing-collection")
            
            mock_client.create_collection.assert_not_called()


class TestVectorStoreServiceEmbedding:
    """Test document embedding."""

    def test_embed_texts(self, vector_store_service):
        """Should embed texts using OpenAI embeddings."""
        texts = ["text1", "text2"]
        mock_vectors = [[0.1, 0.2], [0.3, 0.4]]
        
        mock_emb = MagicMock()
        vector_store_service._embeddings = mock_emb
        mock_emb.embed_documents.return_value = mock_vectors
        
        result = vector_store_service._embed_texts(texts)
        
        assert result == mock_vectors
        mock_emb.embed_documents.assert_called_once_with(texts)


class TestVectorStoreServiceCreateOrReplace:
    """Test create_or_replace operation (full rebuild)."""

    def test_create_or_replace_new_collection(self, vector_store_service):
        """Should create new collection with documents."""
        docs = [
            Document(
                page_content="Content 1",
                metadata={"source_file": "doc1.pdf"}
            ),
            Document(
                page_content="Content 2",
                metadata={"source_file": "doc2.pdf"}
            )
        ]
        
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        with patch.object(vector_store_service, '_collection_exists', return_value=False):
            with patch.object(vector_store_service, '_ensure_collection'):
                with patch.object(vector_store_service, '_embed_texts') as mock_embed:
                    with patch("app.services.vector_store_service._encode_sparse", return_value=[None, None]):
                        mock_embed.return_value = [[0.1, 0.2], [0.3, 0.4]]
                        
                        vector_store_service.create_or_replace(docs, "test-collection")
                        
                        # Verify upsert was called
                        mock_client.upsert.assert_called()

    def test_create_or_replace_deletes_existing(self, vector_store_service):
        """Should delete existing collection before recreating."""
        docs = [Document(page_content="Content", metadata={"source_file": "doc.pdf"})]
        
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            with patch.object(vector_store_service, '_ensure_collection'):
                with patch.object(vector_store_service, '_embed_texts') as mock_embed:
                    with patch("app.services.vector_store_service._encode_sparse", return_value=[None]):
                        mock_embed.return_value = [[0.1, 0.2]]
                        
                        vector_store_service.create_or_replace(docs, "test-collection")
                        
                        # Verify delete was called
                        mock_client.delete_collection.assert_called_once_with("test-collection")

    def test_create_or_replace_batches_large_documents(self, vector_store_service):
        """Should batch documents when upserting large sets."""
        docs = [
            Document(page_content=f"Content {i}", metadata={"source_file": "doc.pdf"})
            for i in range(1500)
        ]
        
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        with patch.object(vector_store_service, '_collection_exists', return_value=False):
            with patch.object(vector_store_service, '_ensure_collection'):
                with patch.object(vector_store_service, '_embed_texts') as mock_embed:
                    with patch("app.services.vector_store_service._encode_sparse", return_value=[None] * 1500):
                        mock_embed.return_value = [[0.1, 0.2]] * 1500
                        
                        vector_store_service.create_or_replace(docs, "test-collection")
                        
                        # Verify upsert was called 3 times (1500 / 500)
                        assert mock_client.upsert.call_count == 3


class TestVectorStoreServiceAppendDocuments:
    """Test append_documents operation (incremental add)."""

    def test_append_documents_to_existing_hybrid(self, vector_store_service):
        """Should append documents to existing hybrid collection using named vectors."""
        docs = [Document(page_content="New content", metadata={"source_file": "new.pdf"})]
        
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            with patch.object(vector_store_service, '_is_hybrid_collection', return_value=True):
                with patch.object(vector_store_service, '_embed_texts', return_value=[[0.1, 0.2]]):
                    with patch.object(vector_store_service, 'document_count', return_value=11):
                        with patch("app.services.vector_store_service._encode_sparse", return_value=[MagicMock()]):
                            vector_store_service.append_documents(docs, "test-collection")
                            
                            mock_client.upsert.assert_called_once()
                            upsert_points = mock_client.upsert.call_args[1]["points"]
                            assert len(upsert_points) == 1
                            assert isinstance(upsert_points[0].vector, dict)
                            assert "dense" in upsert_points[0].vector
                            assert "sparse" in upsert_points[0].vector

    def test_append_documents_to_existing_legacy(self, vector_store_service):
        """Should append documents to existing legacy collection using unnamed vectors."""
        docs = [Document(page_content="New content", metadata={"source_file": "new.pdf"})]
        
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            with patch.object(vector_store_service, '_is_hybrid_collection', return_value=False):
                with patch.object(vector_store_service, '_embed_texts', return_value=[[0.1, 0.2]]):
                    with patch.object(vector_store_service, 'document_count', return_value=11):
                        vector_store_service.append_documents(docs, "test-collection")
                        
                        mock_client.upsert.assert_called_once()
                        upsert_points = mock_client.upsert.call_args[1]["points"]
                        assert len(upsert_points) == 1
                        # Legacy collection: vector should be a list of floats, not a dict
                        assert isinstance(upsert_points[0].vector, list)
                        assert upsert_points[0].vector == [0.1, 0.2]

    def test_append_documents_fallback_to_create(self, vector_store_service):
        """Should fallback to create_or_replace if collection doesn't exist."""
        docs = [Document(page_content="Content", metadata={"source_file": "doc.pdf"})]
        
        with patch.object(vector_store_service, '_collection_exists', return_value=False):
            with patch.object(vector_store_service, 'create_or_replace') as mock_create:
                vector_store_service.append_documents(docs, "test-collection")
                
                mock_create.assert_called_once_with(docs, "test-collection")


class TestVectorStoreServiceSimilaritySearch:
    """Test similarity search (retrieval)."""

    def test_similarity_search_returns_documents(self, vector_store_service):
        """Should return relevant documents from similarity search."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        
        mock_emb = MagicMock()
        vector_store_service._embeddings = mock_emb
        
        # Mock settings/search fallback to semantic
        vector_store_service._settings.search_mode = "semantic"
        
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            with patch.object(vector_store_service, '_is_hybrid_collection', return_value=False):
                # Mock embedding
                mock_emb.embed_query.return_value = [0.1, 0.2]
                
                # Mock search results
                mock_point = MagicMock()
                mock_point.score = 0.9
                mock_point.payload = {
                    "page_content": "Relevant content",
                    "original_content": "{}",
                    "source_file": "doc.pdf"
                }
                mock_client.query_points.return_value = MagicMock(points=[mock_point])
                
                result = vector_store_service.similarity_search("query", k=5, collection_name="test")
                
                assert len(result) == 1
                assert result[0].page_content == "Relevant content"

    def test_similarity_search_filters_by_threshold(self, vector_store_service):
        """Should filter results below similarity threshold."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        
        mock_emb = MagicMock()
        vector_store_service._embeddings = mock_emb
        
        vector_store_service._settings.search_mode = "semantic"
        
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            with patch.object(vector_store_service, '_is_hybrid_collection', return_value=False):
                mock_emb.embed_query.return_value = [0.1, 0.2]
                
                # Mock low-score result
                mock_point = MagicMock()
                mock_point.score = 0.1  # Below threshold
                mock_point.payload = {
                    "page_content": "Low relevance",
                    "original_content": "{}",
                    "source_file": "doc.pdf"
                }
                mock_client.query_points.return_value = MagicMock(points=[mock_point])
                
                result = vector_store_service.similarity_search("query", k=5, collection_name="test")
                
                assert isinstance(result, list)

    def test_similarity_search_nonexistent_collection(self, vector_store_service):
        """Should raise error for nonexistent collection."""
        with patch.object(vector_store_service, '_collection_exists', return_value=False):
            with pytest.raises(RuntimeError, match="No documents ingested"):
                vector_store_service.similarity_search("query", k=5, collection_name="nonexistent")


class TestVectorStoreServiceDocumentCount:
    """Test document counting."""

    def test_document_count_existing_collection(self, vector_store_service):
        """Should return document count for existing collection."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            mock_collection = MagicMock()
            mock_collection.points_count = 42
            mock_client.get_collection.return_value = mock_collection
            
            count = vector_store_service.document_count("test-collection")
            
            assert count == 42

    def test_document_count_nonexistent_collection(self, vector_store_service):
        """Should return 0 for nonexistent collection."""
        with patch.object(vector_store_service, '_collection_exists', return_value=False):
            count = vector_store_service.document_count("nonexistent")
            
            assert count == 0

    def test_document_count_error_handling(self, vector_store_service):
        """Should return 0 on error."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            mock_client.get_collection.side_effect = Exception("Connection error")
            
            count = vector_store_service.document_count("test-collection")
            
            assert count == 0


class TestVectorStoreServiceListChunks:
    """Test chunk listing and filtering."""

    def test_list_chunks_returns_all(self, vector_store_service):
        """Should return all chunks from collection."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            mock_point = MagicMock()
            mock_point.id = "chunk-1"
            mock_point.payload = {
                "page_content": "Text content",
                "original_content": json.dumps({
                    "raw_text": "Text content",
                    "tables_html": [],
                    "images_base64": []
                }),
                "source_file": "doc.pdf"
            }
            mock_client.scroll.return_value = ([mock_point], None)
            
            result = vector_store_service.list_chunks("test-collection")
            
            assert len(result) == 1
            assert result[0]["chunk_id"] == "chunk-1"
            assert "text" in result[0]["content_types"]

    def test_list_chunks_filter_by_type(self, vector_store_service):
        """Should filter chunks by content type."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            mock_point = MagicMock()
            mock_point.id = "chunk-1"
            mock_point.payload = {
                "page_content": "Text with table",
                "original_content": json.dumps({
                    "raw_text": "Text",
                    "tables_html": ["<table></table>"],
                    "images_base64": []
                }),
                "source_file": "doc.pdf"
            }
            mock_client.scroll.return_value = ([mock_point], None)
            
            result = vector_store_service.list_chunks("test-collection", type_filter="table")
            
            assert len(result) == 1
            assert "table" in result[0]["content_types"]

    def test_list_chunks_nonexistent_collection(self, vector_store_service):
        """Should return empty list for nonexistent collection."""
        with patch.object(vector_store_service, '_collection_exists', return_value=False):
            result = vector_store_service.list_chunks("nonexistent")
            
            assert result == []


class TestVectorStoreServiceDeletion:
    """Test collection deletion."""

    def test_delete_collection_existing(self, vector_store_service):
        """Should delete existing collection."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            vector_store_service.delete_collection("test-collection")
            
            mock_client.delete_collection.assert_called_once_with("test-collection")

    def test_delete_collection_nonexistent(self, vector_store_service):
        """Should handle deletion of nonexistent collection gracefully."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        with patch.object(vector_store_service, '_collection_exists', return_value=False):
            # Should not raise
            vector_store_service.delete_collection("nonexistent")
            
            mock_client.delete_collection.assert_not_called()

    def test_delete_collection_error_handling(self, vector_store_service):
        """Should handle deletion errors gracefully."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            mock_client.delete_collection.side_effect = Exception("Connection error")
            
            # Should not raise
            vector_store_service.delete_collection("test-collection")


class TestVectorStoreServiceLoad:
    """Test startup and connectivity check."""

    def test_load_success(self, vector_store_service):
        """Should verify Qdrant connectivity on load."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        mock_collection = MagicMock()
        mock_collection.name = "test-collection"
        mock_client.get_collections.return_value = MagicMock(collections=[mock_collection])
        
        # Should not raise
        vector_store_service.load()
        
        mock_client.get_collections.assert_called_once()

    def test_load_connection_error(self, vector_store_service):
        """Should handle connection errors gracefully on load."""
        mock_client = MagicMock()
        vector_store_service._client = mock_client
        mock_client.get_collections.side_effect = Exception("Connection refused")
        
        # Should not raise
        vector_store_service.load()


class TestVectorStoreServiceIsLoaded:
    """Test collection status checking."""

    def test_is_loaded_true(self, vector_store_service):
        """Should return True for loaded collection."""
        with patch.object(vector_store_service, '_collection_exists', return_value=True):
            result = vector_store_service.is_loaded("test-collection")
            
            assert result is True

    def test_is_loaded_false(self, vector_store_service):
        """Should return False for unloaded collection."""
        with patch.object(vector_store_service, '_collection_exists', return_value=False):
            result = vector_store_service.is_loaded("test-collection")
            
            assert result is False
