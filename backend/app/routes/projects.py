import json
import logging
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import insert

from app.auth.dependencies import get_current_user
from app.db.models import ChatMessageRow, ProjectRow
from app.schemas.requests import CreateProjectRequest
from app.schemas.responses import ChatMessageResponse, ChunkItem, ChunksResponse, ProjectResponse, SourceChunk
from app.services.project_service import ProjectService
from app.services.vector_store_service import VectorStoreService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


def _count_documents_on_disk(collection_name: str) -> int:
    """Count actual files in the uploads directory for a collection."""
    uploads_dir = Path("uploads") / collection_name
    if not uploads_dir.exists() or not uploads_dir.is_dir():
        return 0
    return len([f for f in uploads_dir.iterdir() if f.is_file()])


def _to_response(project, doc_count: int) -> ProjectResponse:
    return ProjectResponse(
        name=project.name,
        description=project.description,
        collection_name=project.collection_name,
        created_at=project.created_at,
        document_count=doc_count,
    )


@router.get("", response_model=list[ProjectResponse], summary="List all projects")
async def list_projects(
    request: Request,
    user_id: str = Depends(get_current_user),
) -> list[ProjectResponse]:
    ps: ProjectService = request.app.state.project_service
    projects = await ps.list_projects(user_id=user_id)
    return [_to_response(p, _count_documents_on_disk(p.collection_name)) for p in projects]


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
async def create_project(
    request: Request,
    body: CreateProjectRequest,
    user_id: str = Depends(get_current_user),
) -> ProjectResponse:
    ps: ProjectService = request.app.state.project_service
    try:
        project = await ps.create_project(name=body.name, description=body.description, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_response(project, 0)


@router.get("/{project_name}", response_model=ProjectResponse, summary="Get a project")
async def get_project(
    project_name: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> ProjectResponse:
    ps: ProjectService = request.app.state.project_service
    project = await ps.get_project(project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found.",
        )
    return _to_response(project, _count_documents_on_disk(project.collection_name))


@router.delete(
    "/{project_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project and its vector store",
)
async def delete_project(
    project_name: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> None:
    ps: ProjectService = request.app.state.project_service
    vs: VectorStoreService = request.app.state.vector_store_service

    project = await ps.get_project(project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found.",
        )

    # Delete vector collection
    vs.delete_collection(project.collection_name)
    
    # Clean up uploads directory
    uploads_dir = Path("uploads") / project.collection_name
    if uploads_dir.exists() and uploads_dir.is_dir():
        try:
            shutil.rmtree(uploads_dir)
            logger.info("Deleted uploads directory for collection '%s'", project.collection_name)
        except Exception as exc:
            logger.warning("Failed to delete uploads directory: %s", exc)
    
    try:
        await ps.delete_project(project_name, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{project_name}/chunks/stats",
    summary="Get chunk statistics for a project",
)
async def get_chunk_stats(
    project_name: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Returns lightweight chunk statistics without fetching full content.
    Provides total count and breakdown by type (text/table/image).
    """
    ps: ProjectService = request.app.state.project_service
    vs: VectorStoreService = request.app.state.vector_store_service

    project = await ps.get_project(project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found.",
        )

    stats = vs.chunk_stats(project.collection_name)
    
    return {
        "project_name": project_name,
        "total": stats["total"],
        "by_type": {
            "text": stats["text"],
            "table": stats["table"],
            "image": stats["image"],
        },
    }


@router.get(
    "/{project_name}/chunks",
    response_model=ChunksResponse,
    summary="List chunks stored in a project",
)
async def list_chunks(
    project_name: str,
    request: Request,
    type: str | None = None,
    user_id: str = Depends(get_current_user),
) -> ChunksResponse:
    """
    Returns all stored chunks for a project.
    Optional query param: `?type=text|table|image`
    """
    ps: ProjectService = request.app.state.project_service
    vs: VectorStoreService = request.app.state.vector_store_service

    project = await ps.get_project(project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found.",
        )

    valid_types = {"text", "table", "image", None}
    if type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid type filter '{type}'. Must be one of: text, table, image.",
        )

    raw_chunks = vs.list_chunks(project.collection_name, type_filter=type)

    chunks = [
        ChunkItem(
            chunk_id=c["chunk_id"],
            content=c["content"],
            content_types=c["content_types"],
            raw_text=c["raw_text"],
            tables_html=c["tables_html"],
            images_base64=c["images_base64"],
            source_file=c.get("source_file", ""),
            page_number=c.get("page_number"),
            chunk_index=c.get("chunk_index"),
            clause_type=c.get("clause_type"),
            chunk_type=c.get("chunk_type"),
            source_type=c.get("source_type"),
            section_reference=c.get("section_reference"),
            image_dimensions=c.get("image_dimensions"),
        )
        for c in raw_chunks
    ]

    return ChunksResponse(
        project_name=project_name,
        total=len(chunks),
        chunks=chunks,
    )


@router.get(
    "/{project_name}/documents/{filename}",
    summary="Download an uploaded PDF document",
)
async def get_document(
    project_name: str,
    filename: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> FileResponse:
    """Serve a stored PDF file so the frontend can open it for source citation."""
    ps: ProjectService = request.app.state.project_service
    project = await ps.get_project(project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found.",
        )

    # Strip directory components to prevent path traversal
    safe_name = Path(filename).name
    if not safe_name or re.search(r"[^\w\-.]", safe_name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename.")

    file_path = Path("uploads") / project.collection_name / safe_name
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found. Re-upload the PDF to enable source links.",
        )

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=safe_name,
    )


@router.get(
    "/{project_name}/documents",
    summary="List all uploaded documents in a project",
)
async def list_documents(
    project_name: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> dict:
    """Return a list of all document filenames uploaded to this project."""
    ps: ProjectService = request.app.state.project_service
    project = await ps.get_project(project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found.",
        )
    
    uploads_dir = Path("uploads") / project.collection_name
    documents = []
    
    if uploads_dir.exists() and uploads_dir.is_dir():
        for file_path in uploads_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                documents.append({
                    "filename": file_path.name,
                    "size_bytes": stat.st_size,
                    "uploaded_at": stat.st_mtime,  # Unix timestamp
                })
    
    return {
        "project_name": project_name,
        "total": len(documents),
        "documents": documents,
    }


@router.delete(
    "/{project_name}/documents/{filename}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and its vector chunks",
)
async def delete_document(
    project_name: str,
    filename: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> None:
    """
    Delete a document from disk and remove all its chunks from the vector store.
    This invalidates the analysis cache (document hash changes).
    """
    ps: ProjectService = request.app.state.project_service
    vs: VectorStoreService = request.app.state.vector_store_service
    
    project = await ps.get_project(project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found.",
        )
    
    # Sanitize filename to prevent path traversal
    safe_name = Path(filename).name
    if not safe_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename.")
    
    file_path = Path("uploads") / project.collection_name / safe_name
    
    # Delete from disk
    if file_path.exists() and file_path.is_file():
        try:
            file_path.unlink()
            logger.info("Deleted document file: %s", file_path)
        except Exception as exc:
            logger.error("Failed to delete file %s: %s", file_path, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete document file.",
            ) from exc
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{safe_name}' not found.",
        )
    
    # Delete vector chunks
    vs.delete_document_points(safe_name, project.collection_name)
    
    logger.info(
        "Deleted document '%s' from project '%s' (user=%s)",
        safe_name, project_name, user_id,
    )


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------


@router.get(
    "/{project_name}/chat",
    response_model=list[ChatMessageResponse],
    summary="Get all chat messages for a project",
)
async def get_chat_history(
    project_name: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> list[ChatMessageResponse]:
    ps: ProjectService = request.app.state.project_service
    project = await ps.get_project(project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found.",
        )

    rows = await ps.get_chat_history(project_name, user_id=user_id)
    result = []
    for row in rows:
        sources: list[SourceChunk] = []
        if row.sources_json:
            try:
                raw = json.loads(row.sources_json)
                sources = [SourceChunk(**s) for s in raw]
            except Exception:
                sources = []
        result.append(
            ChatMessageResponse(
                id=row.id,
                role=row.role,
                content=row.content,
                sources=sources,
                created_at=row.created_at.isoformat(),
            )
        )
    return result


@router.delete(
    "/{project_name}/chat",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear all chat messages for a project",
)
async def clear_chat_history(
    project_name: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> None:
    ps: ProjectService = request.app.state.project_service
    project = await ps.get_project(project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found.",
        )
    await ps.clear_chat_history(project_name, user_id=user_id)


async def save_chat_pair(
    session_factory,
    project_name: str,
    question: str,
    answer: str,
    sources_json: str = "[]",
    user_id: str | None = None,
) -> None:
    """Persist a user question + assistant answer pair to the chat_messages table."""
    try:
        from sqlalchemy import select as sa_select
        async with session_factory() as session:
            # Build query with user_id filter to prevent cross-user data leakage
            query = sa_select(ProjectRow.id).where(ProjectRow.name.ilike(project_name))
            if user_id is not None:
                query = query.where(ProjectRow.user_id == user_id)
            
            project_result = await session.execute(query)
            project_id = project_result.scalar_one_or_none()
            if not project_id:
                logger.warning(
                    "Cannot save chat pair: Project '%s' not found for user '%s'",
                    project_name,
                    user_id or "anonymous"
                )
                return
            session.add_all([
                ChatMessageRow(project_id=project_id, role="user", content=question, sources_json="[]"),
                ChatMessageRow(project_id=project_id, role="assistant", content=answer, sources_json=sources_json),
            ])
            await session.commit()
    except Exception as exc:
        logger.warning("Failed to persist chat pair: %s", exc)
