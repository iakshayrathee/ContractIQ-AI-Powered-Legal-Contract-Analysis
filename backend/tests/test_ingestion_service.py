"""Unit tests for IngestionService (parsing, chunking, embedding prep)."""

import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.documents import Document

from app.services.ingestion_service import IngestionService
from app.config import Settings


@pytest.fixture
def ingestion_service(settings: Settings) -> IngestionService:
    """Create an IngestionService with test settings."""
    return IngestionService(settings)


class TestIngestionServiceElementStats:
    """Test element statistics computation (legacy shims)."""

    def test_get_element_stats_empty(self, ingestion_service):
        """Empty element list should return zeros."""
        stats = ingestion_service.get_element_stats([])
        assert stats["total_elements"] == 0
        assert stats["text_sections"] == 0
        assert stats["tables"] == 0
        assert stats["images"] == 0

    def test_get_element_stats_with_elements(self, ingestion_service):
        """Should count elements by type according to legacy shim."""
        mock_elements = [MagicMock(), MagicMock(), MagicMock()]
        stats = ingestion_service.get_element_stats(mock_elements)
        assert stats["total_elements"] == 3
        assert stats["text_sections"] == 3
        assert stats["tables"] == 0
        assert stats["images"] == 0

    def test_get_element_stats_mixed_text_types(self, ingestion_service):
        """Should aggregate different text element types according to legacy shim."""
        mock_elements = [MagicMock(), MagicMock(), MagicMock()]
        stats = ingestion_service.get_element_stats(mock_elements)
        assert stats["text_sections"] == 3


class TestIngestionServiceChunkStats:
    """Test chunk statistics computation."""

    def test_get_chunk_stats_empty(self, ingestion_service):
        """Empty chunks should return zeros."""
        stats = ingestion_service.get_chunk_stats([], [])
        assert stats["chunks_count"] == 0
        assert stats["avg_chunk_size"] == 0

    def test_get_chunk_stats_with_chunks(self, ingestion_service):
        """Should compute chunk statistics."""
        mock_pages = [MagicMock() for _ in range(5)]
        mock_chunks = [
            {"text": "a" * 100},
            {"text": "b" * 200},
            {"text": "c" * 300},
        ]

        stats = ingestion_service.get_chunk_stats(mock_pages, mock_chunks)
        assert stats["pages_count"] == 5
        assert stats["chunks_count"] == 3
        assert stats["avg_chunk_size"] == 200  # (100 + 200 + 300) / 3

    def test_get_chunk_stats_single_chunk(self, ingestion_service):
        """Should handle single chunk correctly."""
        mock_chunks = [{"text": "x" * 500}]
        stats = ingestion_service.get_chunk_stats([], mock_chunks)
        assert stats["chunks_count"] == 1
        assert stats["avg_chunk_size"] == 500


class TestIngestionServiceParsing:
    """Test document parsing (Stage 1)."""

    @pytest.mark.asyncio
    async def test_parse_document_calls_parser_pdf(self, ingestion_service):
        """Should call parse_pdf for PDF files."""
        mock_pages = [{"page_number": 1, "text": "pdf content"}]
        
        with patch("app.services.ingestion_service.parse_pdf") as mock_parse:
            mock_parse.return_value = mock_pages
            
            result = await ingestion_service.parse_document(Path("test.pdf"))
            
            assert result == mock_pages
            mock_parse.assert_called_once_with("test.pdf")

    @pytest.mark.asyncio
    async def test_parse_document_calls_parser_docx(self, ingestion_service):
        """Should call parse_docx for DOCX files."""
        mock_pages = [{"page_number": 1, "text": "docx content"}]
        
        with patch("app.services.ingestion_service.parse_docx") as mock_parse:
            mock_parse.return_value = mock_pages
            
            result = await ingestion_service.parse_document(Path("test.docx"))
            
            assert result == mock_pages
            mock_parse.assert_called_once_with("test.docx")

    @pytest.mark.asyncio
    async def test_parse_document_unsupported_type(self, ingestion_service):
        """Should raise ValueError for unsupported suffix."""
        with pytest.raises(ValueError, match="Unsupported file type"):
            await ingestion_service.parse_document(Path("test.txt"))


class TestIngestionServiceLLMIntegration:
    """Test LLM property and lazy initialization."""

    def test_llm_lazy_initialization(self, ingestion_service):
        """LLM should be lazily initialized on first access."""
        assert ingestion_service._llm is None
        llm = ingestion_service.llm
        assert llm is not None
        assert ingestion_service._llm is not None

    def test_llm_reuses_instance(self, ingestion_service):
        """Multiple accesses should return same LLM instance."""
        llm1 = ingestion_service.llm
        llm2 = ingestion_service.llm
        assert llm1 is llm2


class TestIngestionServiceChunking:
    """Test Stage 2: Chunker wrapper."""

    def test_create_chunks_basic(self, ingestion_service):
        """Should chunk pages using chunk_text."""
        mock_pages = [{"page_number": 1, "text": "Some text content here"}]
        
        with patch("app.services.ingestion_service.chunk_text") as mock_chunk:
            mock_chunks = [{"text": "chunk1"}]
            mock_chunk.return_value = mock_chunks
            
            result = ingestion_service.create_chunks(mock_pages, source_filename="test.pdf")
            
            assert result == mock_chunks
            mock_chunk.assert_called_once()

    def test_create_chunks_empty_list(self, ingestion_service):
        """Should handle empty pages list."""
        with patch("app.services.ingestion_service.chunk_text") as mock_chunk:
            mock_chunk.return_value = []
            
            result = ingestion_service.create_chunks([], source_filename="test.pdf")
            
            assert result == []

    def test_create_chunks_respects_settings(self, ingestion_service):
        """Should use settings for chunk parameters."""
        mock_pages = [{"page_number": 1, "text": "text"}]
        
        with patch("app.services.ingestion_service.chunk_text") as mock_chunk:
            mock_chunk.return_value = []
            
            ingestion_service.create_chunks(mock_pages, source_filename="test.pdf")
            
            # Verify settings were passed
            call_kwargs = mock_chunk.call_args[1]
            assert "chunk_size" in call_kwargs
            assert "chunk_overlap" in call_kwargs
            assert call_kwargs["chunk_size"] == ingestion_service._settings.chunk_size
            assert call_kwargs["chunk_overlap"] == ingestion_service._settings.chunk_overlap


class TestIngestionServiceEmbeddingPrep:
    """Test Stage 3: Embedding Prep."""

    def test_prepare_documents_basic(self, ingestion_service):
        """Should build LangChain Documents from chunk dicts."""
        mock_chunks = [
            {
                "text": "This is a confidentiality clause.",
                "page_number": 2,
                "chunk_index": 0,
                "source_filename": "test.pdf",
                "clause_type": "confidentiality"
            }
        ]
        
        result = ingestion_service.prepare_documents(mock_chunks)
        
        assert len(result) == 1
        doc = result[0]
        assert isinstance(doc, Document)
        assert doc.page_content == "This is a confidentiality clause."
        assert doc.metadata["source_file"] == "test.pdf"
        assert doc.metadata["page_number"] == 2
        assert doc.metadata["chunk_index"] == 0
        assert doc.metadata["clause_type"] == "confidentiality"
        
        # Verify original_content contains expected keys
        original_content = json.loads(doc.metadata["original_content"])
        assert original_content["raw_text"] == "This is a confidentiality clause."
        assert original_content["page_numbers"] == [2]
        assert original_content["chunk_index"] == 0
        assert original_content["source_filename"] == "test.pdf"
        assert original_content["clause_type"] == "confidentiality"

    def test_prepare_documents_with_progress_callback(self, ingestion_service):
        """Should call progress callback during preparation."""
        mock_chunks = [
            {
                "text": "Chunk 1",
                "page_number": 1,
                "chunk_index": 0,
                "source_filename": "test.pdf",
                "clause_type": None
            },
            {
                "text": "Chunk 2",
                "page_number": 1,
                "chunk_index": 1,
                "source_filename": "test.pdf",
                "clause_type": None
            }
        ]
        progress_calls = []
        
        def progress_callback(current, total):
            progress_calls.append((current, total))
        
        ingestion_service.prepare_documents(mock_chunks, on_progress=progress_callback)
        
        assert len(progress_calls) == 2
        assert progress_calls[0] == (1, 2)
        assert progress_calls[1] == (2, 2)


class TestIngestionServiceFullPipeline:
    """Test full RAG pipeline stages 1-3."""

    @pytest.mark.asyncio
    async def test_run_pipeline_with_steps_success(self, ingestion_service):
        """Should execute all pipeline stages with callbacks."""
        mock_pages = [{"page_number": 1, "text": "text"}]
        mock_chunks = [{"text": "chunk"}]
        mock_documents = [Document(page_content="doc")]
        
        step_starts = []
        step_dones = []
        step_details = []
        
        def on_start(step):
            step_starts.append(step)
        
        def on_done(step):
            step_dones.append(step)
        
        def on_details(step, details):
            step_details.append((step, details))
        
        with patch.object(ingestion_service, 'parse_document', new_callable=AsyncMock) as mock_parse:
            with patch.object(ingestion_service, 'create_chunks') as mock_chunk:
                with patch.object(ingestion_service, 'prepare_documents') as mock_prep:
                    mock_parse.return_value = mock_pages
                    mock_chunk.return_value = mock_chunks
                    mock_prep.return_value = mock_documents
                    
                    result = await ingestion_service.run_pipeline_with_steps(
                        Path("test.pdf"),
                        on_step_start=on_start,
                        on_step_done=on_done,
                        on_step_details=on_details,
                    )
                    
                    # Verify all stages were called
                    assert "Parsing" in step_starts
                    assert "Chunking" in step_starts
                    assert "Embedding Prep" in step_starts
                    
                    assert "Parsing" in step_dones
                    assert "Chunking" in step_dones
                    assert "Embedding Prep" in step_dones
                    
                    assert result == mock_documents

    @pytest.mark.asyncio
    async def test_run_pipeline_without_callbacks(self, ingestion_service):
        """Should run pipeline without callbacks."""
        mock_pages = [{"page_number": 1, "text": "text"}]
        mock_chunks = [{"text": "chunk"}]
        mock_documents = [Document(page_content="doc")]
        
        with patch.object(ingestion_service, 'parse_document', new_callable=AsyncMock) as mock_parse:
            with patch.object(ingestion_service, 'create_chunks') as mock_chunk:
                with patch.object(ingestion_service, 'prepare_documents') as mock_prep:
                    mock_parse.return_value = mock_pages
                    mock_chunk.return_value = mock_chunks
                    mock_prep.return_value = mock_documents
                    
                    result = await ingestion_service.run_pipeline(Path("test.pdf"))
                    
                    assert result == mock_documents

    @pytest.mark.asyncio
    async def test_pipeline_stage_order(self, ingestion_service):
        """Should execute stages in correct order: Parsing → Chunking → Embedding Prep."""
        call_order = []
        
        async def mock_parse(*args, **kwargs):
            call_order.append("parse")
            return [{"page_number": 1, "text": "text"}]
        
        def mock_chunk(*args, **kwargs):
            call_order.append("chunk")
            return [{"text": "chunk"}]
        
        def mock_prep(*args, **kwargs):
            call_order.append("prepare")
            return [Document(page_content="doc")]
        
        with patch.object(ingestion_service, 'parse_document', side_effect=mock_parse):
            with patch.object(ingestion_service, 'create_chunks', side_effect=mock_chunk):
                with patch.object(ingestion_service, 'prepare_documents', side_effect=mock_prep):
                    await ingestion_service.run_pipeline(Path("test.pdf"))
                    
                    assert call_order == ["parse", "chunk", "prepare"]


class TestIngestionServiceErrorHandling:
    """Test error handling across pipeline stages."""

    @pytest.mark.asyncio
    async def test_pipeline_parse_failure(self, ingestion_service):
        """Should propagate parse errors."""
        with patch.object(ingestion_service, 'parse_document', new_callable=AsyncMock) as mock_parse:
            mock_parse.side_effect = RuntimeError("Parse failed")
            
            with pytest.raises(RuntimeError, match="Parse failed"):
                await ingestion_service.run_pipeline(Path("test.pdf"))

    @pytest.mark.asyncio
    async def test_pipeline_chunking_failure(self, ingestion_service):
        """Should propagate chunking errors."""
        with patch.object(ingestion_service, 'parse_document', new_callable=AsyncMock) as mock_parse:
            with patch.object(ingestion_service, 'create_chunks') as mock_chunk:
                mock_parse.return_value = [{"page_number": 1, "text": "text"}]
                mock_chunk.side_effect = ValueError("Invalid chunk config")
                
                with pytest.raises(ValueError, match="Invalid chunk config"):
                    await ingestion_service.run_pipeline(Path("test.pdf"))

    @pytest.mark.asyncio
    async def test_pipeline_embedding_prep_failure(self, ingestion_service):
        """Should propagate preparation errors."""
        with patch.object(ingestion_service, 'parse_document', new_callable=AsyncMock) as mock_parse:
            with patch.object(ingestion_service, 'create_chunks') as mock_chunk:
                with patch.object(ingestion_service, 'prepare_documents') as mock_prep:
                    mock_parse.return_value = [{"page_number": 1, "text": "text"}]
                    mock_chunk.return_value = [{"text": "chunk"}]
                    mock_prep.side_effect = RuntimeError("Prep error")
                    
                    with pytest.raises(RuntimeError, match="Prep error"):
                        await ingestion_service.run_pipeline(Path("test.pdf"))
