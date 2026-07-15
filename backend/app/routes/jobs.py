import logging
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.responses import JobResponse, JobStepResponse
from app.services.job_service import JobService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/{job_id}", response_model=JobResponse, summary="Get job status")
async def get_job(job_id: str, request: Request) -> JobResponse:
    """Poll this endpoint to track ingestion pipeline progress."""
    job_service: JobService = request.app.state.job_service
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return JobResponse(
        job_id=job.job_id,
        project_name=job.project_name,
        document_name=job.document_name,
        status=job.status,
        steps=[
            JobStepResponse(
                name=s.name,
                status=s.status,
                started_at=s.started_at,
                completed_at=s.completed_at,
                details=s.details,
            )
            for s in job.steps
        ],
        chunk_count=job.chunk_count,
        error=job.error,
        created_at=job.created_at,
    )
