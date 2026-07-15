"""Unit tests for JobService (in-memory, no async needed)."""

import pytest

from app.services.job_service import JobService


class TestJobService:
    def test_create_job(self, job_service: JobService):
        job = job_service.create_job("proj", "doc.pdf")
        assert job.status == "pending"
        assert len(job.steps) == 4
        assert all(s.status == "pending" for s in job.steps)

    def test_get_nonexistent_returns_none(self, job_service: JobService):
        assert job_service.get_job("no-such-id") is None

    def test_start_step(self, job_service: JobService):
        job = job_service.create_job("proj", "doc.pdf")
        job_service.start_step(job.job_id, "Parsing")
        updated = job_service.get_job(job.job_id)
        assert updated.status == "running"
        assert updated.steps[0].status == "running"
        assert updated.steps[0].started_at is not None

    def test_complete_step(self, job_service: JobService):
        job = job_service.create_job("proj", "doc.pdf")
        job_service.start_step(job.job_id, "Parsing")
        job_service.complete_step(job.job_id, "Parsing")
        updated = job_service.get_job(job.job_id)
        assert updated.steps[0].status == "completed"
        assert updated.steps[0].completed_at is not None

    def test_complete_job(self, job_service: JobService):
        job = job_service.create_job("proj", "doc.pdf")
        job_service.complete_job(job.job_id, 42)
        updated = job_service.get_job(job.job_id)
        assert updated.status == "completed"
        assert updated.chunk_count == 42

    def test_fail_job(self, job_service: JobService):
        job = job_service.create_job("proj", "doc.pdf")
        job_service.start_step(job.job_id, "Chunking")
        job_service.fail_job(job.job_id, "something broke")
        updated = job_service.get_job(job.job_id)
        assert updated.status == "failed"
        assert updated.error == "something broke"
        # Running step should be marked failed
        chunking_step = [s for s in updated.steps if s.name == "Chunking"][0]
        assert chunking_step.status == "failed"

    def test_update_step_details(self, job_service: JobService):
        job = job_service.create_job("proj", "doc.pdf")
        job_service.start_step(job.job_id, "Embedding Prep")
        job_service.update_step_details(job.job_id, "Embedding Prep", {"total_chunks": 10})
        updated = job_service.get_job(job.job_id)
        step = [s for s in updated.steps if s.name == "Embedding Prep"][0]
        assert step.details["total_chunks"] == 10
