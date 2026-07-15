from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request body for POST /query."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language question to answer from the ingested documents.",
        examples=["How many attention heads does the Transformer use?"],
    )
    project_name: str = Field(
        ...,
        min_length=1,
        description="Name of the project (knowledge base) to query.",
    )
    k: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Number of chunks to retrieve. Falls back to RETRIEVAL_TOP_K from config.",
    )


class CreateProjectRequest(BaseModel):
    """Request body for POST /projects."""

    name: str = Field(..., min_length=1, max_length=50, description="Project display name.")
    description: str = Field(default="", max_length=200, description="Optional project description.")
