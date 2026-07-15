"""
app/utils/pdf_utils.py
======================
Document utility helpers.

separate_content_types() has been removed (was Unstructured-specific).
build_document_from_chunk() is the new helper for the custom pipeline.
export_chunks_to_json() is kept for debugging and offline exports.
"""

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def build_document_from_chunk(chunk: dict[str, Any]) -> Document:
    """
    Build a LangChain Document from a chunk dict produced by
    ingestion.chunker.chunk_text().

    The chunk dict must contain:
        text            str         chunk text
        page_number     int         1-indexed page number
        chunk_index     int         zero-indexed position in document
        source_filename str         originating file basename
        clause_type     str | None  detected clause type or None

    Returns a Document whose:
        page_content = chunk["text"]
        metadata = {
            "original_content": JSON string with full chunk provenance,
            "source_file":      chunk["source_filename"],
            "page_number":      int,
            "chunk_index":      int,
            "clause_type":      str | None,
        }
    """
    metadata_payload = json.dumps({
        "raw_text": chunk["text"],
        "page_numbers": [chunk["page_number"]],
        "chunk_index": chunk["chunk_index"],
        "source_filename": chunk["source_filename"],
        "clause_type": chunk.get("clause_type"),
        # Backward-compat fields for existing vector store payload readers
        "tables_html": [],
        "images_base64": [],
    })

    return Document(
        page_content=chunk["text"],
        metadata={
            "original_content": metadata_payload,
            "source_file": chunk["source_filename"],
            "page_number": chunk["page_number"],
            "chunk_index": chunk["chunk_index"],
            "clause_type": chunk.get("clause_type"),
        },
    )


def export_chunks_to_json(
    chunks: list[Document],
    filepath: str | Path,
) -> list[dict]:
    """
    Serialize a list of LangChain Documents to a JSON file.

    Args:
        chunks:   List of LangChain Document objects.
        filepath: Destination path (string or Path).

    Returns:
        The serialized list of dicts (same data written to disk).
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    export_data = [
        {
            "chunk_id": i + 1,
            "enhanced_content": doc.page_content,
            "metadata": {
                "original_content": json.loads(
                    doc.metadata.get("original_content", "{}")
                )
            },
        }
        for i, doc in enumerate(chunks)
    ]

    with filepath.open("w", encoding="utf-8") as fh:
        json.dump(export_data, fh, indent=2, ensure_ascii=False)

    logger.info("Exported %d chunks to %s", len(export_data), filepath)
    return export_data
