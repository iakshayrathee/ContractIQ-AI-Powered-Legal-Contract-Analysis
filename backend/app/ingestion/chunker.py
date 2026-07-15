"""
ingestion/chunker.py
====================
Text splitting and clause-type detection for the custom ingestion pipeline.

chunk_text() uses a RecursiveCharacterTextSplitter-style algorithm with:
  chunk_size   = 1024  (characters; configurable via CHUNK_SIZE env var)
  chunk_overlap= 200   (characters; configurable via CHUNK_OVERLAP env var)
  separators   = ["\n\n", "\n", ".", " "]

Each output chunk carries:
    {
        "text":            str,        # chunk text
        "page_number":     int,        # page the chunk starts on (1-indexed)
        "chunk_index":     int,        # zero-indexed position within document
        "source_filename": str,        # originating file basename
        "clause_type":     str | None, # detected legal clause type or None
    }
"""

import logging
import re
from typing import Any

import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

import os

# Fix 2 — Chunk size and overlap are now configurable via environment variables.
# CHUNK_SIZE increased from 512 → 1024: legal clauses routinely exceed 512 chars
# and were being split mid-clause, causing retrieval failures.
# CHUNK_OVERLAP increased from 64 → 200: wider overlap prevents clause text
# that spans a chunk boundary from being split mid-sentence (e.g. liability clause).
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "1024"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "200"))
SEPARATORS = ["\n\n", "\n", ".", " "]

# ---------------------------------------------------------------------------
# Section reference extraction (Fix 3 — C3)
# ---------------------------------------------------------------------------

SECTION_RE = re.compile(
    r"(?i)^(section|clause|article|exhibit|schedule|annex)\s+[\dA-Z\.]+[\.\d]*",
    re.MULTILINE
)

# ---------------------------------------------------------------------------
# Clause-type keyword heuristics
# ---------------------------------------------------------------------------

# Maps clause type name -> list of case-insensitive keywords that must appear
# in the chunk text for that clause type to be detected.
# Priority order: SIGNATURES → TERM_AND_RENEWAL → PAYMENT → INTELLECTUAL_PROPERTY →
# LIMITATION_OF_LIABILITY → INDEMNIFICATION → CONFIDENTIALITY → TERMINATION →
# DISPUTE_RESOLUTION → GOVERNING_LAW → WARRANTY → GENERAL (fallback to None)
_CLAUSE_KEYWORDS: dict[str, list[str]] = {
    "signatures": [
        "signature:", "signed by", "authorized representative", "chief technology officer",
        "chief operating officer", "chief executive",
    ],
    "term_and_renewal": [
        "shall automatically renew", "automatic renewal", "successive one-year",
        "non-renewal notice", "initial term",
    ],
    "payment": [
        "payment", "invoice", "fee", "price", "compensation", "remuneration",
        "billing", "payable",
    ],
    "intellectual_property": [
        "intellectual property", "work made for hire", "background ip", "work product",
        "irrevocably assigns", "copyright", "patent", "trademark",
        "proprietary rights", "ip rights",
    ],
    "liability": [
        "liabilit", "limitation of liability", "cap on liability",
        "not liable", "no liability", "indirect damages", "consequential damages",
    ],
    "indemnification": [
        "indemnif", "indemnity", "hold harmless", "defend and indemnify",
    ],
    "confidentiality": [
        "confidential", "non-disclosure", "nda", "proprietary information",
        "trade secret",
    ],
    "termination": [
        "terminat", "expir", "cancell", "cancel ", "end of term", "wind down",
    ],
    "dispute_resolution": [
        "arbitration", "mediation", "dispute resolution", "adr",
        "alternative dispute", "tribunal",
    ],
    "governing_law": [
        "governing law", "governed by", "applicable law", "choice of law",
        "laws of the state", "laws of",
    ],
    "warranty": [
        "warrant", "warranty", "representation", "as-is", "as is",
        "merchantability", "fitness for purpose",
    ],
    "force_majeure": [
        "force majeure", "act of god", "beyond reasonable control",
    ],
}


def detect_clause_type(text: str) -> str | None:
    """
    Identify the most likely legal clause type from chunk text using
    keyword heuristics.

    Returns the clause type string (e.g. "indemnification") if a match
    is found, or None if no known clause type is detected.

    Scoring: each clause type is scored by the number of distinct keywords
    matched.  The clause type with the highest score wins; ties are broken
    by the dict iteration order (more specific types listed first).
    """
    lower_text = text.lower()
    best_type: str | None = None
    best_score: int = 0

    for clause_type, keywords in _CLAUSE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower_text)
        if score > best_score:
            best_score = score
            best_type = clause_type

    return best_type  # None if no keyword matched (best_score == 0)


def extract_section_reference(text: str) -> str | None:
    """
    Extract section/clause reference from the beginning of chunk text.
    
    Uses regex to match patterns like "Section 6", "Clause 4.2", "Exhibit A".
    Scans the first 150 characters of the chunk to identify structured section
    headers common in legal documents.
    
    Args:
        text: Chunk text to scan for section headers.
        
    Returns:
        Matched section reference string (e.g. "Section 6.1") or None.
    """
    first_150 = text[:150]
    match = SECTION_RE.search(first_150)
    if match:
        return match.group(0)
    return None


# ---------------------------------------------------------------------------
# Core splitter logic
# ---------------------------------------------------------------------------

def _split_text_recursive(text: str, separators: list[str], chunk_size: int) -> list[str]:
    """
    Recursively split *text* using the first separator that creates
    splits shorter than *chunk_size*.  Falls back to the next separator
    if the current one doesn't help.
    """
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    # Try each separator in order
    for sep in separators:
        if sep in text:
            parts = text.split(sep)
            # Re-join parts that are below the chunk size
            result: list[str] = []
            current = ""
            for part in parts:
                candidate = (current + sep + part) if current else part
                if len(candidate) <= chunk_size:
                    current = candidate
                else:
                    if current:
                        result.append(current)
                    # The part itself might be over chunk_size — recurse
                    if len(part) > chunk_size:
                        result.extend(
                            _split_text_recursive(part, separators[separators.index(sep) + 1:] or [""], chunk_size)
                        )
                        current = ""
                    else:
                        current = part
            if current:
                result.append(current)
            return result

    # No separator worked — hard split at chunk_size
    return [text[i: i + chunk_size] for i in range(0, len(text), chunk_size)]


def chunk_text(
    pages: list[dict[str, Any]],
    source_filename: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    separators: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Split page-level text into overlapping chunks with rich metadata.

    Algorithm:
      1. Concatenate all pages into a stream of (text, page_number) segments.
      2. Recursively split each segment using the separator hierarchy.
      3. Apply overlap by prepending the tail of the previous chunk.
      4. Attach metadata: page_number, chunk_index, source_filename, clause_type.
      
    Phase 2 Fix: Track the origin page number for overlapping text to ensure
    accurate page attribution when overlap carries text across page boundaries.

    Args:
        pages:           Output of parse_pdf() or parse_docx() — list of
                         {"page_number": int, "text": str} dicts.
        source_filename: Basename of the source file (for metadata).
        chunk_size:      Max characters per chunk (default 1024).
        chunk_overlap:   Characters of overlap between consecutive chunks (default 200).
        separators:      Split hierarchy. Defaults to ["\n\n", "\n", ".", " "].

    Returns:
        List of chunk dicts with keys:
        text, page_number, chunk_index, source_filename, clause_type, chunk_type, source_type.
    """
    if separators is None:
        separators = SEPARATORS

    chunks: list[dict[str, Any]] = []
    chunk_index = 0
    prev_tail = ""  # trailing text carried over for overlap
    prev_page_number = None  # track which page the overlap came from

    for page in pages:
        page_number: int = page["page_number"]
        text: str = page["text"]

        if not text.strip():
            continue  # skip blank pages

        # Prepend overlap from previous page boundary
        working_text = (prev_tail + " " + text).strip() if prev_tail else text

        # Split the working text into raw pieces
        raw_pieces = _split_text_recursive(working_text, separators, chunk_size)

        for i, piece in enumerate(raw_pieces):
            piece = piece.strip()
            if not piece:
                continue

            # Phase 2 Fix: Determine the primary page number for this chunk
            # If this is the first chunk and we have overlap from previous page,
            # attribute it to the previous page if most content is from overlap
            chunk_page = page_number
            if i == 0 and prev_tail and len(prev_tail) > len(piece) / 2:
                # More than half the chunk is overlap from previous page
                chunk_page = prev_page_number if prev_page_number else page_number

            chunks.append({
                "text": piece,
                "page_number": chunk_page,
                "chunk_index": chunk_index,
                "source_filename": source_filename,
                "clause_type": detect_clause_type(piece),
                "section_reference": extract_section_reference(piece),
                "chunk_type": "text",
                "source_type": "text",
            })
            chunk_index += 1

        # Record the tail for cross-page overlap
        if raw_pieces:
            last_piece = raw_pieces[-1].strip()
            prev_tail = last_piece[-chunk_overlap:] if len(last_piece) > chunk_overlap else last_piece
            prev_page_number = page_number
        else:
            prev_tail = ""
            prev_page_number = None

    logger.info(
        "[Chunker] '%s' -> %d text chunks (chunk_size=%d, overlap=%d).",
        source_filename,
        len(chunks),
        chunk_size,
        chunk_overlap,
    )
    return chunks


def create_table_chunks(
    pages: list[dict[str, Any]],
    source_filename: str,
) -> list[dict[str, Any]]:
    """
    Create dedicated chunks for each table found in the parsed pages.
    
    Each table chunk contains:
        - text: Markdown representation for embedding
        - tables_html: List containing the HTML representation
        - chunk_type: "table"
        - source_type: "table"
        - page_number, source_filename, and other metadata
    
    Args:
        pages: Output of parse_pdf() or parse_docx() with "tables" field
        source_filename: Basename of source file
    
    Returns:
        List of table chunk dicts (chunk_index assigned later)
    """
    table_chunks: list[dict[str, Any]] = []
    
    for page in pages:
        page_number: int = page["page_number"]
        tables: list[dict[str, Any]] = page.get("tables", [])
        
        for table_idx, table_dict in enumerate(tables):
            text = table_dict.get("text", "")
            html = table_dict.get("html", "")
            
            if not text.strip():
                continue
            
            table_chunks.append({
                "text": text,  # Markdown representation for embedding
                "page_number": page_number,
                "chunk_index": None,  # Will be assigned during merge
                "source_filename": source_filename,
                "clause_type": detect_clause_type(text),
                "section_reference": extract_section_reference(text),
                "chunk_type": "table",
                "source_type": "table",
                "tables_html": [html],  # List to match schema
                "table_index": table_idx,
            })
    
    logger.info(
        "[Chunker] '%s' -> %d table chunks extracted.",
        source_filename,
        len(table_chunks),
    )
    return table_chunks
