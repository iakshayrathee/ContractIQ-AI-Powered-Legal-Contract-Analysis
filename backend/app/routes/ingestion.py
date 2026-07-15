import asyncio
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status

from app.auth.dependencies import get_current_user
from app.schemas.responses import IngestJobResponse
from app.services.ingestion_service import IngestionService
from app.services.job_service import JobService
from app.services.project_service import ProjectService
from app.services.vector_store_service import VectorStoreService
from app.utils.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

# Accepted MIME types and extensions
_ACCEPTED_EXTENSIONS = {".pdf", ".docx", ".doc"}
_ACCEPTED_MIME_PREFIXES = ("application/pdf", "application/vnd.openxmlformats", "application/msword")


def _is_accepted_file(filename: str, content_type: str) -> bool:
    """Return True if the file extension or MIME type is accepted."""
    suffix = Path(filename).suffix.lower()
    if suffix in _ACCEPTED_EXTENSIONS:
        return True
    return any(content_type.startswith(p) for p in _ACCEPTED_MIME_PREFIXES)


async def _run_ingestion_background(
    *,
    job_id: str,
    tmp_path: Path,
    filename: str,
    source_file: str,
    collection_name: str,
    overwrite: bool,
    ingestion_service: IngestionService,
    vector_store_service: VectorStoreService,
    job_service: JobService,
) -> None:
    """
    Background coroutine: runs the full 4-stage pipeline and updates job status.
    Deletes the temp file when done (success or failure).
    """
    def on_step_start(step_name: str) -> None:
        job_service.start_step(job_id, step_name)

    def on_step_done(step_name: str) -> None:
        job_service.complete_step(job_id, step_name)

    def on_step_details(step_name: str, details: dict[str, Any]) -> None:
        job_service.update_step_details(job_id, step_name, details)

    def on_summarise_progress(processed: int, total: int) -> None:
        job_service.update_step_details(job_id, "Embedding Prep", {
            "total_chunks": total,
            "processed_chunks": processed,
        })

    try:
        # Stages 1-3 (parse → chunk → embedding prep)
        documents = await ingestion_service.run_pipeline_with_steps(
            tmp_path,
            on_step_start,
            on_step_done,
            on_step_details=on_step_details,
            on_summarise_progress=on_summarise_progress,
        )

        # Tag each document with the source filename so the frontend can link to the file
        for doc in documents:
            doc.metadata["source_file"] = source_file

        # Stage 4: Embedding + storage
        job_service.start_step(job_id, "Embedding")
        loop = asyncio.get_event_loop()
        if overwrite:
            await loop.run_in_executor(
                None,
                vector_store_service.create_or_replace,
                documents,
                collection_name,
            )
        else:
            await loop.run_in_executor(
                None,
                vector_store_service.append_documents,
                documents,
                collection_name,
            )
        job_service.update_step_details(job_id, "Embedding", {
            "vectors_stored": len(documents),
            "collection_name": collection_name,
        })
        job_service.complete_step(job_id, "Embedding")

        job_service.complete_job(job_id, len(documents))
        logger.info("Background ingestion job %s completed (%d docs).", job_id, len(documents))

    except Exception as exc:
        logger.error("Background ingestion job %s failed: %s", job_id, exc, exc_info=True)
        job_service.fail_job(job_id, str(exc))
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
            logger.debug("Deleted temp file '%s'.", tmp_path)


@router.post(
    "/ingest",
    response_model=IngestJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a PDF or DOCX document (async)",
)
@limiter.limit("10/minute")
async def ingest_document(
    request: Request,
    file: UploadFile,
    project_name: str,
    overwrite: bool = True,
    user_id: str = Depends(get_current_user),
) -> IngestJobResponse:
    """
    Upload a PDF or DOCX and start the ingestion pipeline in the background.
    Returns immediately with a `job_id` — poll `GET /jobs/{job_id}` for progress.

    Pipeline stages: Parsing → Chunking → Embedding Prep → Embedding
    """
    filename = file.filename or ""
    content_type = file.content_type or ""

    if not _is_accepted_file(filename, content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Only PDF and DOCX files are accepted. "
                f"Got content_type='{content_type}', filename='{filename}'."
            ),
        )

    project_service: ProjectService = request.app.state.project_service
    project = await project_service.get_project(project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found. Create it first via POST /projects.",
        )

    job_service: JobService = request.app.state.job_service
    ingestion_service: IngestionService = request.app.state.ingestion_service
    vector_store_service: VectorStoreService = request.app.state.vector_store_service

    try:
        file_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {exc}",
        ) from exc

    # Determine file suffix for the temp file
    suffix = Path(filename).suffix.lower() or ".pdf"

    # Persist a copy of the file for source-citation download links
    safe_filename = re.sub(r"[^\w\-.]", "_", filename).strip("_") or f"document{suffix}"
    uploads_dir = Path("uploads") / project.collection_name
    uploads_dir.mkdir(parents=True, exist_ok=True)
    (uploads_dir / safe_filename).write_bytes(file_bytes)

    # Write to temp file (the background task deletes it)
    with tempfile.NamedTemporaryFile(
        suffix=suffix, delete=False, prefix="rag_upload_"
    ) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    logger.info(
        "[Ingestion] Upload received: '%s' (%d bytes) for project '%s' → saved to '%s'.",
        filename, len(file_bytes), project_name, tmp_path,
    )

    job = job_service.create_job(project_name=project_name, document_name=filename)

    asyncio.create_task(
        _run_ingestion_background(
            job_id=job.job_id,
            tmp_path=tmp_path,
            filename=filename,
            source_file=safe_filename,
            collection_name=project.collection_name,
            overwrite=overwrite,
            ingestion_service=ingestion_service,
            vector_store_service=vector_store_service,
            job_service=job_service,
        )
    )

    return IngestJobResponse(
        job_id=job.job_id,
        message="Ingestion started. Poll GET /jobs/{job_id} for progress.",
        project_name=project_name,
        document_name=filename,
    )
