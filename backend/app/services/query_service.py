import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Optional

import structlog
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from app.config import Settings
from app.llm.provider import get_llm, get_streaming_llm
from app.services.vector_store_service import VectorStoreService
from app.utils.langfuse_utils import get_langfuse_callback
from app.core.agents import ContractAgent
from app.services.reranker import rerank_documents

logger = structlog.get_logger()


def _detect_page_query(query: str) -> int | None:
    """
    Phase 4 Fix: Detect if the query explicitly asks about a specific page.
    
    Returns the page number if found, None otherwise.
    
    Examples:
        "what is on page 1" -> 1
        "show me page 5" -> 5
        "first page" -> 1
    """
    query_lower = query.lower()
    
    # 1. Check for ordinals and spelled-out numbers
    word_to_num = {
        "first": 1, "1st": 1, "one": 1,
        "second": 2, "2nd": 2, "two": 2,
        "third": 3, "3rd": 3, "three": 3,
        "fourth": 4, "4th": 4, "four": 4,
        "fifth": 5, "5th": 5, "five": 5,
        "sixth": 6, "6th": 6, "six": 6,
        "seventh": 7, "7th": 7, "seven": 7,
        "eighth": 8, "8th": 8, "eight": 8,
        "ninth": 9, "9th": 9, "nine": 9,
        "tenth": 10, "10th": 10, "ten": 10,
    }
    
    for word, num in word_to_num.items():
        if re.search(rf'\b{word}\s+page\b', query_lower) or re.search(rf'\bpage\s+{word}\b', query_lower):
            return num

    # 2. Check for numeric digits
    patterns = [
        r'\bpage\s+(\d+)\b',
        r'\bp\.?\s*(\d+)\b',
        r'\bpg\.?\s*(\d+)\b',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query_lower)
        if match:
            return int(match.group(1))
    
    return None


class QueryService:
    """
    Handles the two-phase query pipeline:
        1. Retrieve — similarity search against Qdrant (~100ms)
        2. Generate — multimodal GPT-4o call with raw text + tables + images (~3-10s)
    """

    def __init__(
        self,
        settings: Settings,
        vector_store_service: VectorStoreService,
    ) -> None:
        self._settings = settings
        self._vs = vector_store_service
        self._llm = None
        self._streaming_llm = None
        self.agent = ContractAgent(settings, vector_store_service)

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(self._settings)
        return self._llm

    @property
    def streaming_llm(self):
        if self._streaming_llm is None:
            self._streaming_llm = get_streaming_llm(self._settings)
        return self._streaming_llm

    def _build_prompt(self, chunks: list[Document], query: str) -> list[dict]:
        """Build the multimodal message content list for GPT-4o."""
        # Simplified citation instruction - sources will be displayed separately in the UI
        citation_instruction = (
            "\n\nCITATION RULES:\n"
            "- Answer naturally without inline citations\n"
            "- Do NOT include source references like [document_name, page X] in your response\n"
            "- The system will automatically display source documents to the user\n"
            "- Focus on providing a clear, direct answer to the question"
        )

        prompt_text = (
            f"Answer the following question based on the provided document content.\n\n"
            f"QUESTION: {query}\n\n"
            "RELEVANT DOCUMENT CONTENT:\n"
        )

        message_content: list[dict] = []

        for i, doc in enumerate(chunks):
            try:
                original = json.loads(doc.metadata.get("original_content", "{}"))
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("Chunk %d: failed to parse original_content: %s", i, e)
                original = {}
            raw_text = original.get("raw_text", doc.page_content)
            tables_html = original.get("tables_html", [])
            images_base64 = original.get("images_base64", [])

            # Extract metadata for citation header
            source_file = doc.metadata.get("source_file", "unknown")
            clause_type = original.get("clause_type") or doc.metadata.get("clause_type")
            section_ref = original.get("section_reference")
            page_num = (
                original.get("page_numbers", [None])[0]
                if original.get("page_numbers")
                else doc.metadata.get("page_number")
            )

            # Build metadata header with document name first
            meta_parts = [f"document={source_file}"]
            if clause_type:
                meta_parts.append(f"clause_type={clause_type}")
            if section_ref:
                meta_parts.append(f"section={section_ref}")
            if page_num is not None:
                meta_parts.append(f"page={page_num}")
            meta_header = f" [{', '.join(meta_parts)}]"

            chunk_text = f"\n--- Chunk {i + 1}{meta_header} ---\n{raw_text}\n"
            if tables_html:
                for j, table in enumerate(tables_html):
                    chunk_text += f"\nTable {j + 1}:\n{table}\n"
            prompt_text += chunk_text

            for image_base64 in images_base64:
                message_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                })

        prompt_text += (
            "\nINSTRUCTIONS:\n"
            "- Provide a COMPREHENSIVE and COMPLETE answer using ALL relevant content above.\n"
            "- For summarization requests: cover every section, clause, or page mentioned — "
            "do NOT stop after the first point.\n"
            "- For specific questions: give a thorough, well-structured answer with all relevant details.\n"
            "- If a piece of information is explicitly present in the context, ALWAYS include it.\n"
            "- Only say 'I cannot find that information' if the topic is genuinely absent from ALL chunks above.\n"
            "- Do NOT truncate or abbreviate your response."
            + citation_instruction
        )

        message_content.insert(0, {"type": "text", "text": prompt_text})
        return message_content

    def _extract_sources(self, chunks: list[Document]) -> list[dict]:
        """Convert retrieved Documents into serializable source dicts."""
        source_chunks = []
        for doc in chunks:
            try:
                original = json.loads(doc.metadata.get("original_content", "{}"))
            except (json.JSONDecodeError, Exception):
                original = {}
            
            chunk_data = {
                "content": doc.page_content,
                "raw_text": original.get("raw_text", doc.page_content),
                "tables_html": original.get("tables_html", []),
                "images_base64": original.get("images_base64", []),
                "page_numbers": original.get("page_numbers", []),
                "source_file": doc.metadata.get("source_file", ""),
                "content_types": sorted(
                    {t for t in ["text"]
                     + (["table"] if original.get("tables_html") else [])
                     + (["image"] if original.get("images_base64") else [])}
                ),
            }
            
            # Include relevance score if available
            relevance_score = doc.metadata.get("relevance_score")
            if relevance_score is not None:
                chunk_data["relevance_score"] = relevance_score
            
            source_chunks.append(chunk_data)
        
        return source_chunks

    def _sort_sources_by_page(self, chunks: list[Document], target_page: int | None) -> list[Document]:
        """
        Phase 4 Fix: Sort sources by page number when a specific page is queried.
        
        Prioritizes chunks from the target page, then sorts remaining by page number.
        
        Args:
            chunks: Retrieved document chunks
            target_page: The page number to prioritize, or None
            
        Returns:
            Sorted list of chunks
        """
        if target_page is None:
            return chunks
        
        # Extract page numbers and sort
        def get_page_number(doc: Document) -> int:
            try:
                original = json.loads(doc.metadata.get("original_content", "{}"))
                page_num = original.get("page_number")
                if page_num is not None:
                    return int(page_num)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
            return float('inf')  # Put chunks without page numbers at the end
        
        # Sort: target page first, then by page number
        def sort_key(doc: Document) -> tuple:
            page = get_page_number(doc)
            is_target = (page == target_page)
            return (not is_target, page)  # False sorts before True, so target page comes first
        
        sorted_chunks = sorted(chunks, key=sort_key)
        
        logger.info(
            "Sorted %d chunks for page %d query. Top 3 pages: %s",
            len(sorted_chunks),
            target_page,
            [get_page_number(c) for c in sorted_chunks[:3]]
        )
        
        return sorted_chunks

    def generate_final_answer(self, chunks: list[Document], query: str, intent: str = "technical") -> str:
        """Build a multimodal prompt and call GPT-4o (non-streaming)."""
        if intent == "greeting":
            prompt = f"You are a helpful legal AI assistant. Respond conversationally to this greeting/pleasantry: {query}"
            message_content = [{"type": "text", "text": prompt}]
        elif intent == "off_topic":
            return "I am a strict legal AI assistant. I can only answer questions related to your legal documents and contracts. Please ask me something relevant to the uploaded documents."
        else:
            if not chunks:
                return (
                    "I couldn't find any relevant content in your documents to answer that question. "
                    "Try rephrasing, or check that the document was ingested successfully."
                )
            message_content = self._build_prompt(chunks, query)
            
        try:
            cb = get_langfuse_callback(trace_name="query-generate")
            config = {"callbacks": [cb]} if cb else {}
            response = self.llm.invoke([HumanMessage(content=message_content)], config=config)
            return response.content
        except Exception as exc:
            logger.error("Answer generation failed: %s", exc, exc_info=True)
            raise RuntimeError(f"Failed to generate answer: {exc}") from exc

    async def stream_answer(
        self, chunks: list[Document], query: str, intent: str = "technical"
    ) -> AsyncGenerator[str, None]:
        """Build a multimodal prompt and stream GPT-4o response tokens."""
        if intent == "greeting":
            prompt = f"You are a helpful legal AI assistant. Respond politely to this greeting/pleasantry: {query}"
            message_content = [{"type": "text", "text": prompt}]
        elif intent == "off_topic":
            yield "I am a strict legal AI assistant. I can only answer questions related to your legal documents and contracts. Please ask me something relevant to the uploaded documents."
            return
        else:
            if not chunks:
                yield (
                    "I couldn't find any relevant content in your documents to answer that question. "
                    "Try rephrasing, or check that the document was ingested successfully."
                )
                return
            message_content = self._build_prompt(chunks, query)
        cb = get_langfuse_callback(trace_name="query-stream")
        config = {"callbacks": [cb]} if cb else {}

        async for chunk in self.streaming_llm.astream([HumanMessage(content=message_content)], config=config):
            token = chunk.content
            if token:
                yield token

    def answer(self, question: str, k: int, collection_name: str) -> tuple[str, int, list[dict]]:
        """
        Execute the full retrieve-then-generate pipeline (non-streaming).

        Returns:
            Tuple of (answer_string, chunks_retrieved_count, source_chunks).
        """
        logger.info("Query (k=%d, collection=%s): %s", k, collection_name, question[:80])
        
        # Phase 4 Fix: Detect page-specific queries
        target_page = _detect_page_query(question)
        if target_page:
            logger.info("Detected page-specific query for page %d", target_page)
        
        chunks, intent = self.retrieve(question, k, collection_name)
        logger.info("Retrieved %d chunks after filtering.", len(chunks))
        
        answer_text = self.generate_final_answer(chunks, question, intent)
        source_chunks = self._extract_sources(chunks)
        return answer_text, len(chunks), source_chunks

    def retrieve(self, question: str, k: int | None, collection_name: str) -> tuple[list[Document], str]:
        """
        Retrieve phase only — used by the streaming endpoint.
        Uses LangGraph to classify intent and retrieve, then applies FlashRank
        semantic reranking for higher-precision context selection.
        Returns a tuple of (chunks, intent).
        """
        target_page = _detect_page_query(question)
        if target_page:
            logger.info("Detected page-specific query for page %d", target_page)
            
        state = {
            "question": question,
            "k": k,
            "collection_name": collection_name,
            "target_page": target_page,
        }
        
        logger.info("Invoking LangGraph agent for plan and retrieve")
        result = self.agent.graph.invoke(state)
        
        intent = result.get("intent", "technical")
        chunks = result.get("chunks", [])
        
        # Phase 4 Fix: Sort by page number if page-specific query
        if target_page and chunks:
            chunks = self._sort_sources_by_page(chunks, target_page)

        # Semantic reranking: use FlashRank cross-encoder to select the most
        # relevant chunks from the expanded Qdrant candidate pool.
        # Only applies to technical queries that have retrieved chunks.
        if intent == "technical" and chunks:
            # For page-specific queries keep top_n higher to cover whole page
            top_n = 10 if target_page else 8
            logger.info(
                "Reranking %d candidates with FlashRank (top_n=%d)...",
                len(chunks), top_n
            )
            chunks = rerank_documents(question, chunks, top_n=top_n)
            logger.info("After reranking: %d chunks sent to LLM.", len(chunks))
            
        return chunks, intent
