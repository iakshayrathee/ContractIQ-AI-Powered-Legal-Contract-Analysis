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
        # New aggregates
        assert data["total_analyses"] == 1
        assert data["high_risk_count"] == 0  # medium risk only
        assert data["flagged_count"] == 0
        # Timeline covers a 14-day window with one analysis logged today
        assert len(data["analyses_timeline"]) == 14
        assert sum(p["count"] for p in data["analyses_timeline"]) == 1
        # trends keys always present (values may be null without prior history)
        assert set(data["trends"].keys()) == {"projects", "analyses", "risk"}
        # Risk-category + contract-type breakdowns from the seeded analysis
        assert data["risk_category_counts"]["missing_clause"] == 1
        assert data["contract_type_counts"]["NDA"] == 1
        assert data["range"] == "all"

    async def test_stats_range_filter(self, client, seed_project, seed_analysis):
        # The seeded analysis is created "now", so it is inside every window.
        resp = await client.get("/dashboard/stats?range=7d")
        assert resp.status_code == 200
        data = resp.json()
        assert data["range"] == "7d"
        assert data["total_analyses"] == 1
        assert len(data["analyses_timeline"]) == 7  # window shrinks to 7 days

    async def test_stats_invalid_range_falls_back_to_all(self, client, seed_project):
        resp = await client.get("/dashboard/stats?range=bogus")
        assert resp.status_code == 200
        data = resp.json()
        assert data["range"] == "all"
        assert len(data["analyses_timeline"]) == 14

    async def test_stats_empty_has_new_fields(self, client):
        resp = await client.get("/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_analyses"] == 0
        assert data["high_risk_count"] == 0
        assert data["avg_quality_score"] == 0.0
        assert len(data["analyses_timeline"]) == 14
