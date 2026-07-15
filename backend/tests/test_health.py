"""Tests for /health endpoint."""

import pytest


class TestHealthEndpoint:
    async def test_health_returns_200(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data

    async def test_health_includes_vectorstore_status(self, client):
        resp = await client.get("/health")
        data = resp.json()
        assert "vectorstore_loaded" in data
        assert isinstance(data["vectorstore_loaded"], bool)
