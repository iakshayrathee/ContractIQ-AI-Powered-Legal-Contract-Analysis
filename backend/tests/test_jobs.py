"""Tests for /jobs endpoint."""

import pytest


class TestJobEndpoint:
    async def test_get_nonexistent_job_404(self, client):
        resp = await client.get("/jobs/nonexistent-id")
        assert resp.status_code == 404

    async def test_get_existing_job(self, client, job_service):
        job = job_service.create_job("test-proj", "test.pdf")
        resp = await client.get(f"/jobs/{job.job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job.job_id
        assert data["status"] == "pending"
        assert len(data["steps"]) == 4
        step_names = [s["name"] for s in data["steps"]]
        assert "Parsing" in step_names
        assert "Embedding" in step_names
