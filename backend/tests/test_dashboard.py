"""Tests for /dashboard/stats endpoint."""

import pytest
from unittest.mock import AsyncMock

from app.db.models import AnalysisRow


class TestDashboardStats:
    async def test_stats_empty_db(self, client):
        resp = await client.get("/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_projects"] == 0
        assert data["total_documents"] == 0
        assert data["avg_risk_score"] == 0.0

    async def test_stats_with_project(self, client, seed_project):
        resp = await client.get("/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_projects"] == 1

    async def test_stats_with_analysis(self, client, seed_project, seed_analysis):
        resp = await client.get("/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["avg_risk_score"] == 35.0
        assert data["risk_distribution"]["medium"] == 1
        assert "recent_analyses" in data
        assert len(data["recent_analyses"]) == 1
