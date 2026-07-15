"""Unit tests for QueryService (retrieval, generation, multimodal)."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.documents import Document

from app.services.query_service import QueryService
from app.services.vector_store_service import VectorStoreService
from app.config import Settings


@pytest.fixture
def query_service(settings: Settings, mock_vector_store) -> QueryService:
    """Create a QueryService with mocked VectorStoreService."""
    return QueryService(settings, mock_vector_store)


class TestQueryServiceLLMIntegration:
    """Test LLM property and lazy initialization."""

    def test_llm_lazy_initialization(self, query_service):
        """LLM should be lazily initialized on first access."""
        assert query_service._llm is None
        llm = query_service.llm
        assert llm is not None
        assert query_service._llm is not None

    def test_llm_reuses_instance(self, query_service):
        """Multiple accesses should return same LLM instance."""
        llm1 = query_service.llm
        llm2 = query_service.llm
        assert llm1 is llm2


class TestQueryServicePromptBuilding:
    """Test multimodal prompt construction."""

    def test_build_prompt_text_only(self, query_service):
        """Should build prompt with text-only content."""
        docs = [
            Document(
                page_content="This is a test document.",
                metadata={"original_content": "{}", "source_file": "test.pdf"}
            )
        ]
        
        prompt = query_service._build_prompt(docs, "What is this?")
        
        assert isinstance(prompt, list)
        assert len(prompt) > 0
        assert prompt[0]["type"] == "text"
        assert "What is this?" in prompt[0]["text"]
        assert "This is a test document." in prompt[0]["text"]

    def test_build_prompt_with_tables(self, query_service):
        """Should include table HTML in prompt."""
        original_content = {
            "raw_text": "Document text",
            "tables_html": ["<table><tr><td>Data</td></tr></table>"],
            "images_base64": []
        }
        docs = [
            Document(
                page_content="Document text",
                metadata={"original_content": json.dumps(original_content), "source_file": "test.pdf"}
            )
        ]
        
        prompt = query_service._build_prompt(docs, "What data is in the table?")
        
        prompt_text = prompt[0]["text"]
        assert "Table" in prompt_text
        assert "<table>" in prompt_text

    def test_build_prompt_with_images(self, query_service):
        """Should include images as separate message content items."""
        original_content = {
            "raw_text": "Document with image",
            "tables_html": [],
            "images_base64": ["iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="]
        }
        docs = [
            Document(
                page_content="Document with image",
                metadata={"original_content": json.dumps(original_content), "source_file": "test.pdf"}
            )
        ]
        
        prompt = query_service._build_prompt(docs, "What is in the image?")
        
        # Should have text + image content items
        assert len(prompt) >= 2
        image_items = [p for p in prompt if p.get("type") == "image_url"]
        assert len(image_items) > 0

    def test_build_prompt_invalid_json_metadata(self, query_service):
        """Should handle invalid JSON in metadata gracefully."""
        docs = [
            Document(
                page_content="Document text",
                metadata={"original_content": "invalid json", "source_file": "test.pdf"}
            )
        ]
        
        prompt = query_service._build_prompt(docs, "What is this?")
        
        assert isinstance(prompt, list)
        assert len(prompt) > 0


class TestQueryServiceSourceExtraction:
    """Test source chunk extraction."""

    def test_extract_sources_text_only(self, query_service):
        """Should extract text-only sources."""
        docs = [
            Document(
                page_content="Source text",
                metadata={"original_content": "{}", "source_file": "doc.pdf"}
            )
        ]
        
        sources = query_service._extract_sources(docs)
        
        assert len(sources) == 1
        assert sources[0]["content"] == "Source text"
        assert sources[0]["source_file"] == "doc.pdf"
        assert "text" in sources[0]["content_types"]

    def test_extract_sources_with_tables_and_images(self, query_service):
        """Should identify content types correctly."""
        original_content = {
            "raw_text": "Text",
            "tables_html": ["<table></table>"],
            "images_base64": ["base64data"],
            "page_numbers": [1, 2]
        }
        docs = [
            Document(
                page_content="Text",
                metadata={"original_content": json.dumps(original_content), "source_file": "doc.pdf"}
            )
        ]
        
        sources = query_service._extract_sources(docs)
        
        assert len(sources) == 1
        assert "text" in sources[0]["content_types"]
        assert "table" in sources[0]["content_types"]
        assert "image" in sources[0]["content_types"]
        assert sources[0]["page_numbers"] == [1, 2]

    def test_extract_sources_invalid_json(self, query_service):
        """Should handle invalid JSON gracefully."""
        docs = [
            Document(
                page_content="Text",
                metadata={"original_content": "not json", "source_file": "doc.pdf"}
            )
        ]
        
        sources = query_service._extract_sources(docs)
        
        assert len(sources) == 1
        assert sources[0]["content"] == "Text"


class TestQueryServiceAnswerGeneration:
    """Test answer generation (non-streaming)."""

    def test_generate_final_answer_no_chunks(self, query_service):
        """Should return fallback message when no chunks provided."""
        answer = query_service.generate_final_answer([], "What is this?")
        
        assert "couldn't find" in answer.lower()
        assert "relevant content" in answer.lower()

    def test_generate_final_answer_with_chunks(self, query_service):
        """Should call LLM with chunks."""
        docs = [
            Document(
                page_content="Relevant content",
                metadata={"original_content": "{}", "source_file": "test.pdf"}
            )
        ]
        
        mock_response = MagicMock()
        mock_response.content = "This is the answer."
        
        with patch.object(query_service, '_llm', MagicMock()):
            query_service._llm.invoke = MagicMock(return_value=mock_response)
            
            answer = query_service.generate_final_answer(docs, "What is this?")
            
            assert answer == "This is the answer."
            query_service._llm.invoke.assert_called_once()

    def test_generate_final_answer_error_handling(self, query_service):
        """Should raise RuntimeError on LLM failure."""
        docs = [
            Document(
                page_content="Content",
                metadata={"original_content": "{}", "source_file": "test.pdf"}
            )
        ]
        
        with patch.object(query_service, '_llm', MagicMock()):
            query_service._llm.invoke = MagicMock(side_effect=Exception("LLM error"))
            
            with pytest.raises(RuntimeError, match="Failed to generate answer"):
                query_service.generate_final_answer(docs, "What is this?")


class TestQueryServiceStreaming:
    """Test streaming answer generation."""

    @pytest.mark.asyncio
    async def test_stream_answer_no_chunks(self, query_service):
        """Should yield fallback message when no chunks provided."""
        result = []
        async for chunk in query_service.stream_answer([], "What is this?"):
            result.append(chunk)
        
        answer = "".join(result)
        assert "couldn't find" in answer.lower()

    @pytest.mark.asyncio
    async def test_stream_answer_with_chunks(self, query_service):
        """Should stream tokens from LLM."""
        docs = [
            Document(
                page_content="Content",
                metadata={"original_content": "{}", "source_file": "test.pdf"}
            )
        ]
        
        async def mock_astream(*args, **kwargs):
            for token in ["Hello", " ", "world", "."]:
                yield MagicMock(content=token)
        
        with patch.object(query_service, '_streaming_llm', MagicMock()):
            query_service._streaming_llm.astream = mock_astream
            
            result = []
            async for chunk in query_service.stream_answer(docs, "What is this?"):
                result.append(chunk)
            
            answer = "".join(result)
            assert answer == "Hello world."


class TestQueryServiceFullPipeline:
    """Test complete retrieve-then-generate pipeline."""

    def test_answer_pipeline(self, query_service):
        """Should execute full retrieve-then-generate pipeline."""
        with patch.object(query_service._vs, 'similarity_search') as mock_search:
            mock_docs = [
                Document(
                    page_content="Relevant content",
                    metadata={"original_content": "{}", "source_file": "test.pdf"}
                )
            ]
            mock_search.return_value = mock_docs
            
            with patch.object(query_service, 'generate_final_answer') as mock_generate:
                mock_generate.return_value = "Answer text"
                
                answer, count, sources = query_service.answer("What?", k=3, collection_name="test")
                
                assert answer == "Answer text"
                assert count == 1
                assert len(sources) == 1
                mock_search.assert_called_once_with("What?", k=3, collection_name="test", page_filter=None)

    def test_retrieve_only(self, query_service):
        """Should retrieve chunks without generating answer."""
        with patch.object(query_service._vs, 'similarity_search') as mock_search:
            mock_docs = [
                Document(
                    page_content="Content",
                    metadata={"original_content": "{}", "source_file": "test.pdf"}
                )
            ]
            mock_search.return_value = mock_docs
            
            result = query_service.retrieve("What?", k=3, collection_name="test")
            
            assert result == mock_docs
            mock_search.assert_called_once_with("What?", k=3, collection_name="test", page_filter=None)
