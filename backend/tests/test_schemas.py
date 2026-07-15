"""Unit tests for Pydantic schemas — validates serialization and constraints."""

import pytest
from pydantic import ValidationError

from app.schemas.contract import (
    AnalysisResponse,
    Clause,
    ClauseType,
    ContractAnalysis,
    ContractMetadata,
    DashboardStats,
    Obligation,
    ObligationType,
    PlainSummary,
    RiskItem,
    RiskCategory,
    RiskReport,
    RiskSeverity,
)
from app.schemas.requests import CreateProjectRequest, QueryRequest
from app.schemas.responses import HealthResponse, ProjectResponse


class TestQueryRequestSchema:
    def test_valid(self):
        req = QueryRequest(question="What?", project_name="proj")
        assert req.question == "What?"

    def test_empty_question_invalid(self):
        with pytest.raises(ValidationError):
            QueryRequest(question="", project_name="proj")

    def test_k_range(self):
        with pytest.raises(ValidationError):
            QueryRequest(question="x", project_name="p", k=0)
        with pytest.raises(ValidationError):
            QueryRequest(question="x", project_name="p", k=51)

    def test_k_optional(self):
        req = QueryRequest(question="x", project_name="p")
        assert req.k is None


class TestCreateProjectSchema:
    def test_valid(self):
        req = CreateProjectRequest(name="My Project")
        assert req.description == ""

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            CreateProjectRequest(name="x" * 100)

    def test_name_empty(self):
        with pytest.raises(ValidationError):
            CreateProjectRequest(name="")


class TestContractSchemas:
    def test_clause_serialization(self):
        clause = Clause(
            clause_type=ClauseType.CONFIDENTIALITY,
            title="NDA Section",
            text="Both parties agree...",
        )
        d = clause.model_dump()
        assert d["clause_type"] == "confidentiality"

    def test_obligation(self):
        ob = Obligation(party="Acme", description="Must pay", type=ObligationType.MUST)
        assert ob.type == ObligationType.MUST

    def test_risk_report_score_range(self):
        with pytest.raises(ValidationError):
            RiskReport(overall_score=101, risk_level="critical")
        with pytest.raises(ValidationError):
            RiskReport(overall_score=-1, risk_level="low")

    def test_risk_item(self):
        item = RiskItem(
            category=RiskCategory.MISSING_CLAUSE,
            severity=RiskSeverity.HIGH,
            title="Missing clause",
            description="No indemnification",
        )
        assert item.severity == RiskSeverity.HIGH

    def test_analysis_response_defaults(self):
        resp = AnalysisResponse(project_name="x", status="none")
        assert resp.analysis is None

    def test_dashboard_stats_defaults(self):
        stats = DashboardStats()
        assert stats.total_projects == 0
        assert stats.avg_risk_score == 0.0

    def test_contract_analysis_round_trip(self):
        analysis = ContractAnalysis(
            metadata=ContractMetadata(contract_type="NDA", parties=["A", "B"]),
            clauses=[
                Clause(clause_type=ClauseType.TERMINATION, title="Term", text="..."),
            ],
            summary="Short summary",
        )
        json_str = analysis.model_dump_json()
        restored = ContractAnalysis.model_validate_json(json_str)
        assert restored.metadata.contract_type == "NDA"
        assert len(restored.clauses) == 1
