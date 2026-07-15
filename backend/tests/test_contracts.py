"""Tests for contract analysis, risk, and summary endpoints."""

import json
from unittest.mock import AsyncMock

import pytest

from app.db.models import AnalysisRow


class TestAnalyzeEndpoint:
    async def test_analyze_nonexistent_project_404(self, client):
        resp = await client.post("/projects/nope/analyze")
        assert resp.status_code == 404

    async def test_analyze_returns_202(self, client, seed_project):
        import shutil
        from pathlib import Path
        uploads_dir = Path("uploads") / seed_project.collection_name
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "dummy.pdf").write_text("dummy content")
        try:
            resp = await client.post(f"/projects/{seed_project.name}/analyze")
            assert resp.status_code == 202
            data = resp.json()
            assert data["project_name"] == seed_project.name
            assert data["status"] == "running"
        finally:
            shutil.rmtree(uploads_dir, ignore_errors=True)


class TestAnalysisEndpoint:
    async def test_analysis_no_result(self, client, seed_project):
        resp = await client.get(f"/projects/{seed_project.name}/analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "none"
        assert data["analysis"] is None

    async def test_analysis_with_completed_result(
        self, client, seed_project, seed_analysis, mock_contract_analysis_service
    ):
        # Wire the mock to return the seed analysis
        mock_contract_analysis_service.get_analysis = AsyncMock(return_value=seed_analysis)

        resp = await client.get(f"/projects/{seed_project.name}/analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["analysis"] is not None
        assert data["analysis"]["metadata"]["contract_type"] == "NDA"
        assert len(data["analysis"]["clauses"]) == 1


class TestClausesEndpoint:
    async def test_clauses_no_analysis_404(self, client, seed_project):
        resp = await client.get(f"/projects/{seed_project.name}/analysis/clauses")
        assert resp.status_code == 404

    async def test_clauses_with_analysis(
        self, client, seed_project, seed_analysis, mock_contract_analysis_service
    ):
        mock_contract_analysis_service.get_analysis = AsyncMock(return_value=seed_analysis)
        resp = await client.get(f"/projects/{seed_project.name}/analysis/clauses")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["clauses"][0]["clause_type"] == "confidentiality"

    async def test_clauses_filter_by_type(
        self, client, seed_project, seed_analysis, mock_contract_analysis_service
    ):
        mock_contract_analysis_service.get_analysis = AsyncMock(return_value=seed_analysis)
        resp = await client.get(f"/projects/{seed_project.name}/analysis/clauses?type=termination")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestRisksEndpoint:
    async def test_risks_no_analysis(self, client, seed_project):
        resp = await client.get(f"/projects/{seed_project.name}/risks")
        assert resp.status_code == 200
        assert resp.json()["risk_report"] is None

    async def test_risks_with_analysis(
        self, client, seed_project, seed_analysis, mock_contract_analysis_service
    ):
        mock_contract_analysis_service.get_analysis = AsyncMock(return_value=seed_analysis)
        resp = await client.get(f"/projects/{seed_project.name}/risks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_report"]["overall_score"] == 35
        assert data["risk_report"]["risk_level"] == "medium"
        assert len(data["risk_report"]["items"]) == 1


class TestSummaryEndpoint:
    async def test_summary_no_analysis(self, client, seed_project):
        resp = await client.get(f"/projects/{seed_project.name}/summary")
        assert resp.status_code == 200
        assert resp.json()["summary"] is None

    async def test_summary_with_analysis(
        self, client, seed_project, seed_analysis, mock_contract_analysis_service
    ):
        mock_contract_analysis_service.get_analysis = AsyncMock(return_value=seed_analysis)
        resp = await client.get(f"/projects/{seed_project.name}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["executive_summary"] == "Standard NDA with moderate risk."
        assert len(data["summary"]["action_items"]) == 1
