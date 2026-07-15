from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class ProjectResponse(BaseModel):
    name: str
    description: str
    collection_name: str
    created_at: str
    document_count: int


# ---------------------------------------------------------------------------
# Jobs (async ingestion)
# ---------------------------------------------------------------------------

class JobStepResponse(BaseModel):
    name: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    details: dict[str, Any] | None = None


class JobResponse(BaseModel):
    job_id: str
    project_name: str
    document_name: str
    status: str
    steps: list[JobStepResponse]
    chunk_count: int | None = None
    error: str | None = None
    created_at: str


class IngestJobResponse(BaseModel):
    """Immediate 202 response returned when ingestion is accepted."""

    job_id: str
    message: str
    project_name: str
    document_name: str


# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------

class ChunkItem(BaseModel):
    chunk_id: str
    content: str
    content_types: list[str]
    raw_text: str
    tables_html: list[str]
    images_base64: list[str]
    source_file: str = Field(default="", description="Filename of the source PDF.")
    # Rich metadata fields
    page_number: int | None = Field(default=None, description="Page number where chunk originates (1-indexed).")
    chunk_index: int | None = Field(default=None, description="Sequential index of chunk within document.")
    clause_type: str | None = Field(default=None, description="Detected legal clause type (e.g., 'indemnification').")
    chunk_type: str | None = Field(default=None, description="Type of chunk: 'text', 'table', or 'image_description'.")
    source_type: str | None = Field(default=None, description="Source type: 'text', 'table', or 'image'.")
    section_reference: str | None = Field(default=None, description="Section/clause reference (e.g., 'Section 6.1').")
    image_dimensions: str | None = Field(default=None, description="Image dimensions (e.g., '640x480') for image chunks.")


class ChunksResponse(BaseModel):
    project_name: str
    total: int
    chunks: list[ChunkItem]


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

class SourceChunk(BaseModel):
    content: str = Field(description="AI-enhanced summary of the chunk.")
    raw_text: str = Field(description="Original raw text extracted from the document.")
    tables_html: list[str] = Field(default_factory=list)
    images_base64: list[str] = Field(default_factory=list)
    content_types: list[str] = Field(default_factory=list)
    page_numbers: list[int] = Field(default_factory=list, description="Page numbers this chunk spans.")
    source_file: str = Field(default="", description="Filename of the source PDF (empty for legacy chunks).")


class QueryResponse(BaseModel):
    question: str = Field(description="The original question as received.")
    answer: str = Field(description="GPT-4o generated answer using retrieved multimodal context.")
    chunks_retrieved: int = Field(description="Number of chunks actually used.")
    project_name: str = Field(description="Project that was queried.")
    sources: list[SourceChunk] = Field(default_factory=list, description="Retrieved source chunks.")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = Field(description="'healthy' or 'degraded'.")
    version: str
    vectorstore_loaded: bool
    qdrant_url: str | None = None
    collection_document_count: int | None = None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sources: list[SourceChunk] = Field(default_factory=list)
    created_at: str
