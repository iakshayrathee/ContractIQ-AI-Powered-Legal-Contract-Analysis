"""Tests for the SSE /query endpoint with caching."""

import json

import pytest


class TestQueryEndpoint:
    async def test_query_nonexistent_project_404(self, client):
        resp = await client.post("/query", json={
            "project_name": "no-such-project",
            "question": "What is this?",
        })
        assert resp.status_code == 404

    async def test_query_returns_sse_stream(self, client, seed_project):
        resp = await client.post("/query", json={
            "project_name": seed_project.name,
            "question": "What is the confidentiality clause?",
            "k": 3,
        })
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        # Parse SSE events
        events = []
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        types = [e["type"] for e in events]
        assert "sources" in types
        assert "done" in types

    async def test_query_cache_hit(self, client, seed_project):
        """Second identical query should be served from cache."""
        payload = {
            "project_name": seed_project.name,
            "question": "cache test question",
            "k": 3,
        }
        # First call — populates cache
        resp1 = await client.post("/query", json=payload)
        assert resp1.status_code == 200

        # Second call — should hit cache
        resp2 = await client.post("/query", json=payload)
        assert resp2.status_code == 200

        events = []
        for line in resp2.text.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        types = [e["type"] for e in events]
        assert "sources" in types
        assert "done" in types


class TestQueryValidation:
    async def test_missing_question_422(self, client):
        resp = await client.post("/query", json={"project_name": "x"})
        assert resp.status_code == 422

    async def test_missing_project_name_422(self, client):
        resp = await client.post("/query", json={"question": "test"})
        assert resp.status_code == 422

    async def test_k_out_of_range_422(self, client):
        resp = await client.post("/query", json={
            "project_name": "x",
            "question": "test",
            "k": 0,
        })
        assert resp.status_code == 422
