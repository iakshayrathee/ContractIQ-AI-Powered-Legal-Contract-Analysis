"""Pydantic schemas for structured contract extraction and risk analysis."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ClauseType(str, Enum):
    CONFIDENTIALITY = "confidentiality"
    TERMINATION = "termination"
    INDEMNIFICATION = "indemnification"
    LIABILITY = "liability"
    NON_COMPETE = "non_compete"
    NON_SOLICITATION = "non_solicitation"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    PAYMENT = "payment"
    GOVERNING_LAW = "governing_law"
    DISPUTE_RESOLUTION = "dispute_resolution"
    FORCE_MAJEURE = "force_majeure"
    DATA_PRIVACY = "data_privacy"
    WARRANTY = "warranty"
    INSURANCE = "insurance"
    ASSIGNMENT = "assignment"
    AMENDMENT = "amendment"
    ENTIRE_AGREEMENT = "entire_agreement"
    SEVERABILITY = "severability"
    AUTO_RENEWAL = "auto_renewal"
    OTHER = "other"


class ObligationType(str, Enum):
    MUST = "must"
    MUST_NOT = "must_not"
    MAY = "may"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskCategory(str, Enum):
    MISSING_CLAUSE = "missing_clause"
    UNFAVORABLE_TERMS = "unfavorable_terms"
    AMBIGUOUS_LANGUAGE = "ambiguous_language"
    COMPLIANCE = "compliance"
    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    DATA_PRIVACY = "data_privacy"


# ---------------------------------------------------------------------------
# Contract Extraction Schemas
# ---------------------------------------------------------------------------

class Obligation(BaseModel):
    party: str = Field(description="Name of the party with this obligation.")
    description: str = Field(description="What the party must/may/must-not do.")
    deadline: Optional[str] = Field(default=None, description="Deadline if specified.")
    type: ObligationType = Field(default=ObligationType.MUST)


class Clause(BaseModel):
    clause_type: ClauseType = Field(description="Category of this clause.")
    title: str = Field(description="Short title summarizing the clause.")
    text: str = Field(description="Extracted clause text from the document.")
    section_reference: Optional[str] = Field(default=None, description="Section number if present.")
    obligations: list[Obligation] = Field(default_factory=list)


class ContractMetadata(BaseModel):
    contract_type: str = Field(default="unknown", description="E.g., NDA, MSA, SaaS Agreement.")
    parties: list[str] = Field(default_factory=list, description="Names of all contracting parties.")
    effective_date: Optional[str] = Field(default=None)
    expiration_date: Optional[str] = Field(default=None)
    governing_law: Optional[str] = Field(default=None, description="Jurisdiction / governing law.")
    jurisdiction: Optional[str] = Field(default=None)


class ContractAnalysis(BaseModel):
    metadata: ContractMetadata = Field(default_factory=ContractMetadata)
    clauses: list[Clause] = Field(default_factory=list)
    key_dates: list[str] = Field(default_factory=list, description="Important dates found.")
    summary: str = Field(default="", description="One-paragraph executive summary.")


# ---------------------------------------------------------------------------
# Risk Analysis Schemas
# ---------------------------------------------------------------------------

class RiskItem(BaseModel):
    category: RiskCategory
    severity: RiskSeverity
    title: str = Field(description="Short risk title.")
    description: str = Field(description="What the risk is and why it matters.")
    clause_reference: Optional[str] = Field(default=None, description="Related clause title.")
    recommendation: str = Field(default="", description="Suggested action to mitigate.")


class ScoringExplanation(BaseModel):
    rule_based_score: int = Field(description="Rule-based component score (0–100).")
    llm_score: int = Field(description="LLM-based component score (0–100).")
    combined_score: int = Field(description="Final weighted score: 40% rule + 60% LLM.")
    missing_clause_penalty: int = Field(description="Points added from missing standard clauses.")
    highest_severity: str = Field(description="Highest severity level found across all risk items.")
    top_contributors: list[str] = Field(
        default_factory=list,
        description="Titles of the risk items that contributed most to the score.",
    )


class RiskReport(BaseModel):
    overall_score: int = Field(ge=0, le=100, description="0 = no risk, 100 = maximum risk.")
    risk_level: str = Field(description="low / medium / high / critical")
    items: list[RiskItem] = Field(default_factory=list)
    missing_clauses: list[str] = Field(default_factory=list)
    summary: str = Field(default="", description="Plain-english risk summary.")
    scoring_explanation: Optional[ScoringExplanation] = Field(
        default=None, description="Breakdown of how the overall score was calculated."
    )


# ---------------------------------------------------------------------------
# Plain-English Summary Schema
# ---------------------------------------------------------------------------

class PlainSummary(BaseModel):
    executive_summary: str = Field(default="")
    what_this_does: str = Field(default="")
    obligations_by_party: dict[str, list[str]] = Field(default_factory=dict)
    key_dates: list[str] = Field(default_factory=list)
    watch_out_for: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    key_risks_plain: list[str] = Field(
        default_factory=list,
        description="Risk items rewritten in plain English with no legal jargon, for non-lawyers.",
    )


# ---------------------------------------------------------------------------
# API Response wrappers
# ---------------------------------------------------------------------------

class AnalysisResponse(BaseModel):
    project_name: str
    status: str = Field(description="pending | running | completed | failed")
    analysis: Optional[ContractAnalysis] = None
    risk_report: Optional[RiskReport] = None
    summary: Optional[PlainSummary] = None


class RiskResponse(BaseModel):
    project_name: str
    risk_report: Optional[RiskReport] = None


class SummaryResponse(BaseModel):
    project_name: str
    summary: Optional[PlainSummary] = None


class DashboardStats(BaseModel):
    total_projects: int = 0
    total_documents: int = 0
    avg_risk_score: float = 0.0
    risk_distribution: dict[str, int] = Field(default_factory=dict)
    clause_type_counts: dict[str, int] = Field(default_factory=dict)
    recent_analyses: list[dict] = Field(default_factory=list)
