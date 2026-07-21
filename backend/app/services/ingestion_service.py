"""
ingestion_service.py
====================
Custom document ingestion pipeline (PDF + DOCX).

Replaces the previous Unstructured Cloud API dependency entirely.

Stage 1  Parsing        → PyMuPDF (PDF) or python-docx (DOCX)
Stage 1b Image Desc.   → GPT-4o vision (optional; PDF only; async, rate-limited)
Stage 2  Chunking       → RecursiveCharacterTextSplitter (chunk_size=1024, overlap=200)
Stage 3  Embedding Prep → Build LangChain Documents, optionally AI-enhanced
Stage 4  Embedding      → Handled by VectorStoreService (caller)

Image extraction notes
----------------------
After parsing, for each PDF page that has at least one candidate image
(already filtered for size by the parser), we call GPT-4o vision to generate
a text description.  If the model returns "SKIP" or an empty string, the image
is discarded.  Otherwise a chunk is created with:

    chunk["text"] = "[Image on page N]: <description>"
    chunk["chunk_type"] = "image_description"
    chunk["source_type"] = "image"

These chunks flow through the existing Stage 2 (chunking) + Stage 3 (document
prep) pipeline unchanged.  The Qdrant collection schema is not modified — image
chunks use the same dense vector field as text chunks.

Rate limiting
-------------
Vision calls are guarded by an asyncio.Semaphore of size settings.vision_concurrency
(default 3, configurable via VISION_CONCURRENCY env var).  All vision calls for a
single ingestion job run concurrently up to the semaphore limit via asyncio.gather().
"""

import asyncio
import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

import structlog

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings
from app.utils.ai_utils import create_ai_enhanced_summary
from app.ingestion.chunker import chunk_text
from app.ingestion.parser import parse_docx, parse_pdf

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Vision system prompt
# ---------------------------------------------------------------------------

_VISION_SYSTEM_PROMPT = (
    "You are analysing an image extracted from a legal contract document. "
    "Describe what the image shows in precise detail. Focus on: any text visible "
    "in the image, any data (tables, charts, figures), any structural information "
    "(org charts, flowcharts, timelines). If the image appears to be a signature, "
    "stamp, logo, or decorative element with no informational content, respond with "
    "exactly: SKIP. Keep descriptions under 300 words."
)

_VISION_USER_PROMPT = (
    "Describe this image from a legal contract. Focus on informational content only."
)


class IngestionService:
    """
    Orchestrates the three-stage ingestion pipeline:
        Stage 1  Parsing        — PyMuPDF / python-docx → pages
        Stage 1b Image Desc.   — GPT-4o vision (PDF only, optional) → extra chunks
        Stage 2  Chunking       — RecursiveCharacterTextSplitter → chunks
        Stage 3  Embedding Prep — Build LangChain Documents
    Stage 4 (Embedding + vector storage) is handled by VectorStoreService.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._llm: Optional[ChatOpenAI] = None
        # Semaphore to rate-limit concurrent GPT-4o vision calls.
        # Created lazily inside the async context so it is always bound to the
        # running event loop (creating Semaphore at __init__ time on some
        # platforms binds it to whatever loop exists at construction, which can
        # mismatch the actual running loop in test/production setups).
        self._vision_semaphore: Optional[asyncio.Semaphore] = None

    def _get_vision_semaphore(self) -> asyncio.Semaphore:
        """Return (creating if necessary) the vision concurrency semaphore."""
        if self._vision_semaphore is None:
            self._vision_semaphore = asyncio.Semaphore(self._settings.vision_concurrency)
        return self._vision_semaphore

    @property
    def llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=self._settings.openai_model_vision,
                temperature=self._settings.openai_temperature,
                api_key=self._settings.openai_api_key,
            )
        return self._llm

    # ------------------------------------------------------------------
    # Stage 1 — Parsing
    # ------------------------------------------------------------------

    async def parse_document(self, file_path: Path) -> list[dict[str, Any]]:
        """
        Parse a PDF or DOCX file into a list of page dicts.

        Runs the synchronous parser in a thread pool so the asyncio event
        loop is not blocked.

        Returns:
            List of {"page_number": int, "text": str, "images": list} dicts.
        """
        suffix = file_path.suffix.lower()
        logger.info("[Stage 1/Parsing] Parsing '%s' (type=%s).", file_path.name, suffix)

        loop = asyncio.get_event_loop()

        if suffix == ".pdf":
            pages = await loop.run_in_executor(None, parse_pdf, str(file_path))
        elif suffix in (".docx", ".doc"):
            pages = await loop.run_in_executor(None, parse_docx, str(file_path))
        else:
            raise ValueError(
                f"Unsupported file type '{suffix}'. Accepted: .pdf, .docx"
            )

        logger.info(
            "[Stage 1/Parsing] Parsed %d pages from '%s'.",
            len(pages),
            file_path.name,
        )
        return pages

    @staticmethod
    def get_parse_stats(pages: list[dict[str, Any]]) -> dict[str, Any]:
        """Return parsing step details for the job status report."""
        total_chars = sum(len(p["text"]) for p in pages)
        non_empty = sum(1 for p in pages if p["text"].strip())
        total_images = sum(len(p.get("images", [])) for p in pages)
        total_tables = sum(len(p.get("tables", [])) for p in pages)
        return {
            "total_pages": len(pages),
            "non_empty_pages": non_empty,
            "total_characters": total_chars,
            "total_images": total_images,
            "total_tables": total_tables,
        }

    # ------------------------------------------------------------------
    # Stage 1b — GPT-4o Vision Image Description (PDF only)
    # ------------------------------------------------------------------

    async def _describe_image_with_vision(
        self,
        image_bytes: bytes,
        image_ext: str,
        page_num: int,
        img_index: int,
        source_filename: str,
    ) -> Optional[tuple[str, float, str]]:
        """
        Call the configured vision model to describe a single image extracted from a PDF.

        The call is wrapped in:
          - The shared vision semaphore (rate limiting).
          - A try/except so a single failed vision call never aborts ingestion.

        Args:
            image_bytes:     Raw image bytes (already filtered for size).
            image_ext:       Normalised extension — "png" or "jpeg".
            page_num:        1-based page number (for logging).
            img_index:       0-based image index within the page (for logging).
            source_filename: Originating file name (for logging context).

        Returns:
            A tuple of (description, est_cost_usd, b64_image) if successful, or None.
        """
        # Encode the raw bytes as a base64 data-URI for the vision payload.
        import base64
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        mime_type = f"image/{image_ext}"  # image_ext is already "jpeg" or "png"
        data_uri = f"data:{mime_type};base64,{b64_image}"

        sem = self._get_vision_semaphore()
        async with sem:
            try:
                # We call the underlying OpenAI client directly (not via LangChain
                # .invoke()) because LangChain's ChatOpenAI does not yet surface the
                # image_url message type transparently across all provider backends.
                # The openai package is a transitive dependency of langchain-openai,
                # so importing it here is safe and does not add a new requirement.
                import openai as _openai

                client = _openai.AsyncOpenAI(api_key=self._settings.openai_api_key)

                # Respect settings.openai_model_vision
                vision_model = self._settings.openai_model_vision or "gpt-4o-mini"

                response = await client.chat.completions.create(
                    model=vision_model,
                    max_tokens=400,
                    messages=[
                        {
                            "role": "system",
                            "content": _VISION_SYSTEM_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": data_uri},
                                },
                                {
                                    "type": "text",
                                    "text": _VISION_USER_PROMPT,
                                },
                            ],
                        },
                    ],
                )

                description: str = response.choices[0].message.content.strip()

                if not description or description.upper() == "SKIP":
                    logger.debug(
                        "[Stage 1b/Vision] Image %d on page %d of '%s' returned SKIP — discarded.",
                        img_index, page_num, source_filename,
                    )
                    return None

                # Log token usage and cost — gpt-4o-mini pricing: $0.15/1M input, $0.60/1M output
                # gpt-4o pricing: $2.50/1M input, $10.00/1M output
                usage = response.usage
                input_tokens = usage.prompt_tokens
                output_tokens = usage.completion_tokens
                if "gpt-4o-mini" in vision_model:
                    est_cost_usd = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000
                else:
                    est_cost_usd = (input_tokens * 2.50 + output_tokens * 10.00) / 1_000_000

                logger.info(
                    "[Stage 1b/Vision] Image %d on page %d: %d input + %d output tokens, est. $%.4f",
                    img_index, page_num, input_tokens, output_tokens, est_cost_usd,
                )
                logger.info(
                    "[Stage 1b/Vision] Image %d on page %d of '%s' described (%d chars).",
                    img_index, page_num, source_filename, len(description),
                )
                return description, est_cost_usd, b64_image

            except Exception as exc:
                logger.warning(
                    "[Stage 1b/Vision] Vision call failed for image %d on page %d of '%s': %s — skipping.",
                    img_index, page_num, source_filename, exc,
                )
                return None

    async def extract_image_chunks(
        self,
        pages: list[dict[str, Any]],
        source_filename: str,
    ) -> list[dict[str, Any]]:
        """
        Produce image-description chunks for all candidate images across all pages.

        Reads EXTRACT_IMAGES from settings.  If false, returns [] immediately
        without making any vision calls.

        All vision calls for this document are issued concurrently (up to the
        semaphore limit) via asyncio.gather(), so total latency is bounded by
        the slowest batch of vision_concurrency calls rather than the sum of all
        calls.

        Args:
            pages:           Output of parse_pdf() — list of page dicts, each
                             containing an "images" list of raw image dicts.
            source_filename: Originating file name for metadata on each chunk.

        Returns:
            List of image chunk dicts, one per successfully described image:
                {
                    "text":            "[Image on page N]: <description>",
                    "page_number":     int,    # 1-indexed
                    "chunk_index":     None,   # assigned later by chunker offset
                    "source_filename": str,
                    "clause_type":     None,   # image chunks have no clause type
                    "source_type":     "image",
                    "chunk_type":      "image_description",
                    "image_index":     int,    # 0-based within the page
                    "image_dimensions": str,  # e.g. "640x480"
                    "images_base64":   list,  # [base64_string]
                }
        """
        if not self._settings.extract_images:
            logger.info(
                "[Stage 1b/Vision] EXTRACT_IMAGES=false — image extraction disabled for '%s'.",
                source_filename,
            )
            return []

        # Build a flat list of (page_num, image_dict) tuples to describe.
        pending: list[tuple[int, dict[str, Any]]] = []
        for page in pages:
            page_num: int = page["page_number"]
            for img_dict in page.get("images", []):
                pending.append((page_num, img_dict))

        if not pending:
            logger.info(
                "[Stage 1b/Vision] No candidate images found in '%s' — nothing to describe.",
                source_filename,
            )
            return []

        logger.info(
            "[Stage 1b/Vision] Describing %d candidate image(s) from '%s' (concurrency=%d).",
            len(pending),
            source_filename,
            self._settings.vision_concurrency,
        )

        # Launch all vision calls concurrently; semaphore enforces the cap.
        # Track cost for each successful call.
        total_cost_usd = 0.0
        
        async def _describe(page_num: int, img_dict: dict[str, Any]) -> Optional[dict[str, Any]]:
            nonlocal total_cost_usd
            res = await self._describe_image_with_vision(
                image_bytes=img_dict["image_bytes"],
                image_ext=img_dict["image_ext"],
                page_num=page_num,
                img_index=img_dict["img_index"],
                source_filename=source_filename,
            )
            if res is None:
                return None
            description, est_cost_usd, b64_image = res
            total_cost_usd += est_cost_usd
            return {
                "text": f"[Image on page {page_num}]: {description}",
                "page_number": page_num,
                "chunk_index": None,   # will be offset-assigned in create_chunks()
                "source_filename": source_filename,
                "clause_type": None,   # image descriptions carry no clause type
                "source_type": "image",
                "chunk_type": "image_description",
                "image_index": img_dict["img_index"],
                "image_dimensions": f"{img_dict['width']}x{img_dict['height']}",
                "images_base64": [b64_image],
            }

        tasks = [_describe(pn, img) for pn, img in pending]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        image_chunks: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("[Stage 1b/Vision] Unexpected gather exception: %s", result)
            elif result is not None:
                image_chunks.append(result)

        # Log per-job vision summary
        logger.info(
            "[Stage 1b/Vision] Job complete — %d/%d image(s) described, est. total ~$%.4f",
            len(image_chunks), len(pending), total_cost_usd,
        )
        logger.info(
            "[Stage 1b/Vision] Detailed note: costs above are estimates only; actual charges depend on pricing tier and any volume discounts."
        )
        return image_chunks
    
    def extract_table_chunks(
        self,
        pages: list[dict[str, Any]],
        source_filename: str,
    ) -> list[dict[str, Any]]:
        """
        Extract dedicated table chunks from parsed pages.
        
        Calls the chunker's create_table_chunks() to produce one chunk per table,
        with HTML stored in tables_html and markdown text for embedding.
        
        Args:
            pages: Output of parse_pdf() or parse_docx() with "tables" field
            source_filename: Originating file name
        
        Returns:
            List of table chunk dicts (chunk_index will be assigned during merge)
        """
        from app.ingestion.chunker import create_table_chunks
        
        table_chunks = create_table_chunks(pages, source_filename)
        logger.info(
            "[Stage 1c/Table Extraction] Extracted %d table chunk(s) from '%s'.",
            len(table_chunks),
            source_filename,
        )
        return table_chunks

    # ------------------------------------------------------------------
    # Stage 2 — Chunking
    # ------------------------------------------------------------------

    def create_chunks(
        self, pages: list[dict[str, Any]], source_filename: str
    ) -> list[dict[str, Any]]:
        """Split page text into overlapping chunks with metadata."""
        logger.info("[Stage 2/Chunking] Chunking %d pages…", len(pages))
        chunks = chunk_text(
            pages,
            source_filename=source_filename,
            chunk_size=self._settings.chunk_size,
            chunk_overlap=self._settings.chunk_overlap,
        )
        logger.info("[Stage 2/Chunking] Created %d chunks.", len(chunks))
        return chunks

    def merge_multimodal_chunks(
        self,
        text_chunks: list[dict[str, Any]],
        table_chunks: list[dict[str, Any]],
        image_chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Merge text, table, and image chunks into a single list with contiguous chunk_index values.

        Text chunks arrive with chunk_index already assigned (0..N-1).
        Table and image chunks arrive with chunk_index=None.
        This method assigns sequential indices to table and image chunks.

        Args:
            text_chunks:  Chunks produced by create_chunks() (already indexed).
            table_chunks: Chunks produced by extract_table_chunks() (index=None).
            image_chunks: Chunks produced by extract_image_chunks() (index=None).

        Returns:
            Combined list with all chunk_index values set contiguously.
        """
        next_index = len(text_chunks)  # text chunks are 0..N-1
        
        # Assign indices to table chunks
        for tc in table_chunks:
            tc["chunk_index"] = next_index
            next_index += 1
        
        # Assign indices to image chunks
        for ic in image_chunks:
            ic["chunk_index"] = next_index
            next_index += 1

        merged = text_chunks + table_chunks + image_chunks
        
        if table_chunks or image_chunks:
            logger.info(
                "[Stage 2/Chunking] Merged %d text + %d table + %d image chunks = %d total.",
                len(text_chunks), len(table_chunks), len(image_chunks), len(merged),
            )
        
        return merged

    @staticmethod
    def get_chunk_stats(
        pages: list[dict[str, Any]], chunks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        total_chars = sum(len(c["text"]) for c in chunks)
        avg_size = total_chars // len(chunks) if chunks else 0
        image_chunks = sum(1 for c in chunks if c.get("chunk_type") == "image_description")
        table_chunks = sum(1 for c in chunks if c.get("chunk_type") == "table")
        text_chunks = sum(1 for c in chunks if c.get("chunk_type") == "text")
        return {
            "pages_count": len(pages),
            "chunks_count": len(chunks),
            "text_chunks": text_chunks,
            "table_chunks": table_chunks,
            "image_chunks": image_chunks,
            "avg_chunk_size": avg_size,
        }

    # ------------------------------------------------------------------
    # Stage 3 — Embedding Prep
    # ------------------------------------------------------------------

    def prepare_documents(
        self,
        chunks: list[dict[str, Any]],
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[Document]:
        """
        Build LangChain Documents from chunk dicts.

        Handles text, table, and image-description chunks. For table chunks,
        the tables_html field is populated. For image chunks, the extra metadata
        fields (source_type, chunk_type, image_index, image_dimensions) are stored
        inside original_content JSON so they are preserved in Qdrant payload without
        any schema changes.

        Metadata stored per Document:
          - original_content: JSON with raw_text, page_numbers, clause_type,
                              section_reference, chunk_index, source_filename,
                              tables_html (for table chunks),
                              images_base64 (for image chunks),
                              and (for image chunks) source_type, chunk_type,
                              image_index, image_dimensions
          - source_file: the originating filename
          - page_number: int
          - chunk_index: int
          - clause_type: str | None
          - section_reference: str | None
          - chunk_type:  str | None  ("text", "table", or "image_description")
          - source_type: str | None  ("text", "table", or "image")
        """
        logger.info("[Stage 3/Embedding Prep] Building %d documents…", len(chunks))
        documents: list[Document] = []
        total = len(chunks)

        for i, chunk in enumerate(chunks):
            page_content = chunk["text"]
            chunk_type = chunk.get("chunk_type", "text")
            is_image_chunk = chunk_type == "image_description"
            is_table_chunk = chunk_type == "table"

            # Build the original_content payload
            original_content_dict: dict[str, Any] = {
                "raw_text": chunk["text"],
                "page_numbers": [chunk["page_number"]],
                "chunk_index": chunk["chunk_index"],
                "source_filename": chunk["source_filename"],
                "clause_type": chunk.get("clause_type"),
                "section_reference": chunk.get("section_reference"),
                "chunk_type": chunk_type,
                "source_type": chunk.get("source_type", "text"),
            }

            # Add type-specific fields
            if is_table_chunk:
                original_content_dict["tables_html"] = chunk.get("tables_html", [])
            else:
                original_content_dict["tables_html"] = []
            
            if is_image_chunk:
                original_content_dict["images_base64"] = chunk.get("images_base64", [])
                original_content_dict["image_index"] = chunk.get("image_index")
                original_content_dict["image_dimensions"] = chunk.get("image_dimensions")
            else:
                original_content_dict["images_base64"] = []

            metadata_payload = json.dumps(original_content_dict)

            doc_metadata: dict[str, Any] = {
                "original_content": metadata_payload,
                "source_file": chunk["source_filename"],
                "page_number": chunk["page_number"],
                "chunk_index": chunk["chunk_index"],
                "clause_type": chunk.get("clause_type"),
                "section_reference": chunk.get("section_reference"),
                "chunk_type": chunk_type,
                "source_type": chunk.get("source_type", "text"),
            }

            doc = Document(
                page_content=page_content,
                metadata=doc_metadata,
            )
            documents.append(doc)

            if on_progress:
                on_progress(i + 1, total)

        logger.info("[Stage 3/Embedding Prep] %d documents ready.", len(documents))
        return documents

    # ------------------------------------------------------------------
    # Pipeline entry points
    # ------------------------------------------------------------------

    async def run_pipeline_with_steps(
        self,
        file_path: Path,
        on_step_start: Callable[[str], None],
        on_step_done: Callable[[str], None],
        on_step_details: Optional[Callable[[str, dict[str, Any]], None]] = None,
        on_summarise_progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[Document]:
        """
        Execute Stages 1–3 (+ 1b image extraction + 1c table extraction) with 
        step callbacks for real-time progress reporting.  Stage 4 (Embedding + storage) 
        is handled by VectorStoreService.

        Step names: "Parsing", "Table Extraction", "Image Extraction", "Chunking", "Embedding Prep"

        Image Extraction step is skipped (no callback, no timing) when
        EXTRACT_IMAGES=false or the file is a DOCX.
        """
        logger.info("=== Pipeline starting: %s ===", file_path.name)
        source_filename = file_path.name
        is_pdf = file_path.suffix.lower() == ".pdf"

        # Stage 1 — Parsing
        on_step_start("Parsing")
        t0 = time.monotonic()
        pages = await self.parse_document(file_path)
        if on_step_details:
            on_step_details("Parsing", self.get_parse_stats(pages))
        on_step_done("Parsing")
        logger.info(
            "[Pipeline] Parsing complete — %d pages in %.0fms.",
            len(pages),
            (time.monotonic() - t0) * 1000,
        )

        # Stage 1c — Table Extraction (always run if tables exist)
        on_step_start("Table Extraction")
        t_table = time.monotonic()
        table_chunks = self.extract_table_chunks(pages, source_filename)
        if on_step_details:
            on_step_details("Table Extraction", {
                "table_chunks_produced": len(table_chunks),
            })
        on_step_done("Table Extraction")
        logger.info(
            "[Pipeline] Table extraction complete — %d table chunk(s) in %.0fms.",
            len(table_chunks),
            (time.monotonic() - t_table) * 1000,
        )

        # Stage 1b — Image Extraction (PDF only, skipped if EXTRACT_IMAGES=false)
        image_chunks: list[dict[str, Any]] = []
        if is_pdf and self._settings.extract_images:
            on_step_start("Image Extraction")
            t_img = time.monotonic()
            image_chunks = await self.extract_image_chunks(pages, source_filename)
            if on_step_details:
                on_step_details("Image Extraction", {
                    "image_chunks_produced": len(image_chunks),
                })
            on_step_done("Image Extraction")
            logger.info(
                "[Pipeline] Image extraction complete — %d image chunk(s) in %.0fms.",
                len(image_chunks),
                (time.monotonic() - t_img) * 1000,
            )

        # Stage 2 — Chunking
        on_step_start("Chunking")
        t1 = time.monotonic()
        text_chunks = self.create_chunks(pages, source_filename=source_filename)
        chunks = self.merge_multimodal_chunks(text_chunks, table_chunks, image_chunks)
        if on_step_details:
            on_step_details("Chunking", self.get_chunk_stats(pages, chunks))
        on_step_done("Chunking")
        logger.info(
            "[Pipeline] Chunking complete — %d chunks in %.0fms.",
            len(chunks),
            (time.monotonic() - t1) * 1000,
        )

        # Stage 3 — Embedding Prep
        on_step_start("Embedding Prep")
        if on_step_details:
            on_step_details("Embedding Prep", {
                "total_chunks": len(chunks),
                "processed_chunks": 0,
            })
        documents = self.prepare_documents(
            chunks, on_progress=on_summarise_progress
        )
        if on_step_details:
            on_step_details("Embedding Prep", {
                "total_chunks": len(chunks),
                "processed_chunks": len(chunks),
            })
        on_step_done("Embedding Prep")

        logger.info(
            "=== Stages 1-3 complete: %d documents ready for embedding ===",
            len(documents),
        )
        return documents

    async def run_pipeline(self, file_path: Path) -> list[Document]:
        """Convenience wrapper without step callbacks."""
        return await self.run_pipeline_with_steps(
            file_path,
            on_step_start=lambda s: logger.info("[Pipeline] Step start: %s", s),
            on_step_done=lambda s: logger.info("[Pipeline] Step done: %s", s),
        )

    # ------------------------------------------------------------------
    # Legacy compatibility shims
    # ------------------------------------------------------------------

    @staticmethod
    def get_element_stats(elements: list) -> dict[str, Any]:
        """Legacy shim kept for test compatibility — maps to parse stats."""
        return {
            "total_elements": len(elements),
            "text_sections": len(elements),
            "tables": 0,
            "images": 0,
            "titles_headers": 0,
            "other_elements": 0,
        }

    @staticmethod
    def get_chunk_stats_legacy(elements: list, chunks: list) -> dict[str, Any]:
        """Legacy shim: mirrors old get_chunk_stats signature."""
        total_chars = sum(len(c.get("text", "")) if isinstance(c, dict) else len(getattr(c, "text", "")) for c in chunks)
        avg_size = total_chars // len(chunks) if chunks else 0
        return {
            "elements_count": len(elements),
            "chunks_count": len(chunks),
            "avg_chunk_size": avg_size,
        }
