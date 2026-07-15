"""Tests for API authorization, tenancy isolation, and database cascade deletion."""

import pytest
from fastapi import HTTPException, status
from app.auth.dependencies import get_current_user
from app.db.models import ProjectRow, QueryCacheRow
from sqlalchemy import select


class TestAPIAuthorization:
    async def test_endpoints_return_401_without_token(self, app, client):
        # Override get_current_user to raise 401 (simulating missing/invalid token)
        def fake_failing_user():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials.",
            )
        app.dependency_overrides[get_current_user] = fake_failing_user

        endpoints = [
            ("GET", "/projects"),
            ("POST", "/projects"),
            ("GET", "/projects/some-project"),
            ("DELETE", "/projects/some-project"),
            ("GET", "/projects/some-project/chunks"),
            ("GET", "/projects/some-project/documents/doc.pdf"),
            ("GET", "/projects/some-project/chat"),
            ("DELETE", "/projects/some-project/chat"),
            ("POST", "/query"),
            ("POST", "/projects/some-project/analyze"),
            ("GET", "/projects/some-project/analysis"),
            ("GET", "/projects/some-project/analysis/clauses"),
            ("GET", "/projects/some-project/risks"),
            ("GET", "/projects/some-project/summary"),
            ("GET", "/projects/some-project/quality"),
            ("GET", "/dashboard/stats"),
        ]

        for method, path in endpoints:
            if method == "GET":
                resp = await client.get(path)
            elif method == "POST":
                resp = await client.post(path, json={})
            elif method == "DELETE":
                resp = await client.delete(path)
            
            assert resp.status_code == 401, f"{method} {path} did not return 401: {resp.status_code}"


class TestTenancyIsolation:
    async def test_user_projects_isolation(self, app, client, session_factory):
        # Create Project 1 owned by User A
        async with session_factory() as session:
            project_a = ProjectRow(
                id="proj-a",
                name="project-user-a",
                collection_name="project-user-a",
                user_id="user-a",
            )
            session.add(project_a)
            await session.commit()

        # Call API as User B
        app.dependency_overrides[get_current_user] = lambda: "user-b"

        # User B lists projects — should not see User A's project
        resp = await client.get("/projects")
        assert resp.status_code == 200
        projects = resp.json()
        assert len(projects) == 0

        # User B gets User A's project — should return 404
        resp = await client.get("/projects/project-user-a")
        assert resp.status_code == 404

        # User B deletes User A's project — should return 404
        resp = await client.delete("/projects/project-user-a")
        assert resp.status_code == 404


class TestDatabaseCascades:
    async def test_project_deletion_cascades_query_cache(self, app, client, session_factory):
        app.dependency_overrides[get_current_user] = lambda: "user-a"

        # Create project and cache entries
        async with session_factory() as session:
            project = ProjectRow(
                id="proj-cache-test",
                name="proj-cache",
                collection_name="proj-cache",
                user_id="user-a",
            )
            session.add(project)
            await session.commit()

            cache = QueryCacheRow(
                cache_key="test-key-123",
                project_id="proj-cache-test",
                question="What is this?",
                answer="Answer",
            )
            session.add(cache)
            await session.commit()

        # Delete project via API
        resp = await client.delete("/projects/proj-cache")
        assert resp.status_code == 204

        # Verify cache row is deleted from the DB due to foreign key cascade
        async with session_factory() as session:
            result = await session.execute(
                select(QueryCacheRow).where(QueryCacheRow.project_id == "proj-cache-test")
            )
            row = result.scalar_one_or_none()
            assert row is None, "Query cache entry was not cascade-deleted"
