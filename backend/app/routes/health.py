from fastapi import APIRouter, Request

from app.schemas.responses import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health_check(request: Request) -> HealthResponse:
    """Returns the current health status of the API and vector store state."""
    settings = request.app.state.settings
    vs: "VectorStoreService" = request.app.state.vector_store_service  # noqa: F821

    loaded = vs.is_loaded()
    doc_count = vs.document_count() if loaded else None

    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        vectorstore_loaded=loaded,
        qdrant_url=settings.qdrant_url if loaded else None,
        collection_document_count=doc_count,
    )
