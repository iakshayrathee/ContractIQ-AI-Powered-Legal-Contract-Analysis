"""Tests for /projects endpoints."""

import pytest


class TestProjectsCRUD:
    async def test_create_project(self, client):
        resp = await client.post("/projects", json={"name": "My NDA", "description": "Test"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My NDA"
        assert data["description"] == "Test"
        assert data["document_count"] == 0
        assert "collection_name" in data
        assert "created_at" in data

    async def test_create_duplicate_returns_409(self, client):
        await client.post("/projects", json={"name": "dup-test"})
        resp = await client.post("/projects", json={"name": "dup-test"})
        assert resp.status_code == 409

    async def test_list_projects_empty(self, client):
        resp = await client.get("/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_projects_after_create(self, client):
        await client.post("/projects", json={"name": "proj-1"})
        await client.post("/projects", json={"name": "proj-2"})
        resp = await client.get("/projects")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "proj-1" in names
        assert "proj-2" in names

    async def test_get_project(self, client, seed_project):
        resp = await client.get(f"/projects/{seed_project.name}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-project"

    async def test_get_nonexistent_returns_404(self, client):
        resp = await client.get("/projects/no-such-project")
        assert resp.status_code == 404

    async def test_delete_project(self, client, seed_project):
        resp = await client.delete(f"/projects/{seed_project.name}")
        assert resp.status_code == 204

        # Verify it's gone
        resp = await client.get(f"/projects/{seed_project.name}")
        assert resp.status_code == 404

    async def test_delete_nonexistent_returns_404(self, client):
        resp = await client.delete("/projects/ghost-project")
        assert resp.status_code == 404


class TestProjectChunks:
    async def test_chunks_returns_list(self, client, seed_project):
        resp = await client.get(f"/projects/{seed_project.name}/chunks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_name"] == "test-project"
        assert "total" in data
        assert isinstance(data["chunks"], list)

    async def test_chunks_nonexistent_project_404(self, client):
        resp = await client.get("/projects/nope/chunks")
        assert resp.status_code == 404

    async def test_chunks_invalid_type_filter_400(self, client, seed_project):
        resp = await client.get(f"/projects/{seed_project.name}/chunks?type=invalid")
        assert resp.status_code == 400


class TestProjectValidation:
    async def test_create_empty_name_422(self, client):
        resp = await client.post("/projects", json={"name": ""})
        assert resp.status_code == 422

    async def test_create_long_name_422(self, client):
        resp = await client.post("/projects", json={"name": "x" * 100})
        assert resp.status_code == 422
