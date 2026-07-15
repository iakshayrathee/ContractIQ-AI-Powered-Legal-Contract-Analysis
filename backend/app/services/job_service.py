import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

PIPELINE_STEPS = ["Parsing", "Chunking", "Embedding Prep", "Embedding"]

StepStatus = Literal["pending", "running", "completed", "failed"]
JobStatus = Literal["pending", "running", "completed", "failed"]


@dataclass
class JobStep:
    name: str
    status: StepStatus = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    details: dict[str, Any] | None = None


@dataclass
class Job:
    job_id: str
    project_name: str
    document_name: str
    status: JobStatus
    steps: list[JobStep]
    chunk_count: int | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class JobService:
    """
    In-memory job tracker for the ingestion pipeline.
    Jobs are lost when the server restarts — acceptable for a dev/single-user setup.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create_job(self, project_name: str, document_name: str) -> Job:
        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            project_name=project_name,
            document_name=document_name,
            status="pending",
            steps=[JobStep(name=step) for step in PIPELINE_STEPS],
        )
        self._jobs[job_id] = job
        logger.info("Created job %s for project '%s', file '%s'.", job_id, project_name, document_name)
        return job

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def start_step(self, job_id: str, step_name: str) -> None:
        job = self._get_or_raise(job_id)
        job.status = "running"
        for step in job.steps:
            if step.name == step_name:
                step.status = "running"
                step.started_at = datetime.now(timezone.utc).isoformat()
                logger.debug("Job %s: step '%s' started.", job_id, step_name)
                return
        logger.warning("Job %s: unknown step '%s'.", job_id, step_name)

    def complete_step(self, job_id: str, step_name: str) -> None:
        job = self._get_or_raise(job_id)
        for step in job.steps:
            if step.name == step_name:
                step.status = "completed"
                step.completed_at = datetime.now(timezone.utc).isoformat()
                logger.debug("Job %s: step '%s' completed.", job_id, step_name)
                return
        logger.warning("Job %s: unknown step '%s'.", job_id, step_name)

    def update_step_details(self, job_id: str, step_name: str, details: dict[str, Any]) -> None:
        """Update the details dict for a specific step (e.g. element counts, chunk stats)."""
        job = self._get_or_raise(job_id)
        for step in job.steps:
            if step.name == step_name:
                if step.details is None:
                    step.details = {}
                step.details.update(details)
                return

    def complete_job(self, job_id: str, chunk_count: int) -> None:
        job = self._get_or_raise(job_id)
        job.status = "completed"
        job.chunk_count = chunk_count
        # Mark any still-pending steps as completed (safety net)
        for step in job.steps:
            if step.status not in ("completed", "failed"):
                step.status = "completed"
                step.completed_at = datetime.now(timezone.utc).isoformat()
        logger.info("Job %s completed with %d chunks.", job_id, chunk_count)

    def fail_job(self, job_id: str, error: str) -> None:
        job = self._get_or_raise(job_id)
        job.status = "failed"
        job.error = error
        for step in job.steps:
            if step.status == "running":
                step.status = "failed"
                step.completed_at = datetime.now(timezone.utc).isoformat()
        logger.error("Job %s failed: %s", job_id, error)

    def _get_or_raise(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Job '{job_id}' not found.")
        return job
