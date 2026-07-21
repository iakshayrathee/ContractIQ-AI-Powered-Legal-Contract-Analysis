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


# Ordinal map for severity calibration metrics
SEVERITY_ORDINAL: dict[RiskSeverity, int] = {
    RiskSeverity.LOW: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.HIGH: 3,
    RiskSeverity.CRITICAL: 4,
}


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
    text: str = Field(description="Extracted clause text from the document (full, untruncated).")
    section_reference: Optional[str] = Field(default=None, description="Section number if present.")
    obligations: list[Obligation] = Field(default_factory=list)
    # Phase 1: source provenance — populated from chunker metadata
    page_number: Optional[int] = Field(
        default=None,
        description="Page number where this clause was found (1-indexed).",
    )
    char_span: Optional[tuple[int, int]] = Field(
        default=None,
        description="(start, end) character offsets within the source document, if available.",
    )


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
    # Phase 6: summary is derived from PlainSummary.executive_summary, not a separate LLM call.
    # Still kept for backwards-compatibility with existing API consumers; populated at the end
    # of the pipeline rather than as a standalone generation step.
    summary: str = Field(default="", description="Executive summary (copied from PlainSummary after generation).")


# ---------------------------------------------------------------------------
# Risk Analysis Schemas — Phase 1: Evidence citations
# ---------------------------------------------------------------------------

class Evidence(BaseModel):
    """
    A verifiable source span backing a risk finding or summary claim.

    The `quote` must be a verbatim excerpt from the source document that
    directly supports the associated risk or claim. Guardrails check that
    this quote is present (fuzzy-match ≥ 0.9) in the original text before
    the result is persisted.
    """
    quote: str = Field(description="Verbatim text from the contract that supports this finding.")
    page_number: Optional[int] = Field(
        default=None,
        description="Page number where the quote was found (1-indexed).",
    )
    section_reference: Optional[str] = Field(
        default=None,
        description="Section/clause identifier (e.g. 'Section 6.1') if determinable.",
    )


class RiskItem(BaseModel):
    category: RiskCategory
    severity: RiskSeverity
    title: str = Field(description="Short risk title.")
    description: str = Field(description="What the risk is and why it matters.")
    clause_reference: Optional[str] = Field(default=None, description="Related clause title.")
    recommendation: str = Field(default="", description="Suggested action to mitigate.")
    # Phase 1: grounded citations
    evidence: list[Evidence] = Field(
        default_factory=list,
        description="Verbatim source spans that support this risk finding.",
    )
    # Phase 1: per-item confidence (0–1) as reported by the LLM or rule engine
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in this risk finding (1.0 = fully grounded, 0.0 = speculative).",
    )


class ScoringExplanation(BaseModel):
    rule_based_score: int = Field(description="Rule-based component score (0–100).")
    llm_score: int = Field(description="LLM-based component score (0–100).")
    combined_score: int = Field(description="Final weighted score.")
    missing_clause_penalty: int = Field(description="Points added from missing standard clauses.")
    highest_severity: str = Field(description="Highest severity level found across all risk items.")
    top_contributors: list[str] = Field(
        default_factory=list,
        description="Titles of the risk items that contributed most to the score.",
    )
    # Phase 4: scoring feature vector — persisted so the UI can explain the score
    feature_vector: dict = Field(
        default_factory=dict,
        description=(
            "Raw feature values used for scoring: "
            "{'critical_count', 'high_count', 'medium_count', 'low_count', "
            "'missing_core_clauses', 'cap_present', 'notice_days', "
            "'one_sided_indemnity', 'auto_renewal_no_notice'}."
        ),
    )
    # Phase 4: scoring weights used (from config, not hard-coded)
    weights_used: dict = Field(
        default_factory=dict,
        description="Scoring weights applied: {'rule_weight', 'llm_weight', 'severity_values'}.",
    )
    # Phase 4: party perspective the score was computed for
    perspective: str = Field(
        default="neutral",
        description="Party perspective used for risk assessment: 'customer' | 'vendor' | 'neutral'.",
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
    # Phase 4: party perspective
    perspective: str = Field(
        default="neutral",
        description="Party perspective: 'customer' | 'vendor' | 'neutral'.",
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
    # Phase 6: adaptive — populated so the reporter can flag complexity
    complexity_tier: str = Field(
        default="standard",
        description="'brief' | 'standard' | 'detailed' — drives summary depth.",
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
    # WS-2.2: pipeline stage for progress display while status="running"
    # Values: extracting_clauses | assessing_risk | writing_summary | reviewing_quality | completed
    # JSON payload: {"stage": "extracting_clauses", "processed": 12, "total": 40}
    stage: Optional[dict] = None


class RiskResponse(BaseModel):
    project_name: str
    risk_report: Optional[RiskReport] = None


class SummaryResponse(BaseModel):
    project_name: str
    summary: Optional[PlainSummary] = None


class DashboardTrends(BaseModel):
    """Real period-over-period deltas (last 7 days vs the prior 7 days).

    Each value is a percentage change. ``None`` means there is not enough
    history to compute a meaningful delta, in which case the UI hides the badge.
    """

    projects: Optional[float] = None
    analyses: Optional[float] = None
    risk: Optional[float] = None


class TimelinePoint(BaseModel):
    date: str  # ISO date (YYYY-MM-DD)
    count: int = 0


class DashboardStats(BaseModel):
    total_projects: int = 0
    total_documents: int = 0
    total_analyses: int = 0
    avg_risk_score: float = 0.0
    high_risk_count: int = 0  # analyses scored high or critical
    flagged_count: int = 0  # analyses flagged for human review by the judge
    avg_quality_score: float = 0.0  # mean judge quality (0-100)
    risk_distribution: dict[str, int] = Field(default_factory=dict)
    clause_type_counts: dict[str, int] = Field(default_factory=dict)
    risk_category_counts: dict[str, int] = Field(default_factory=dict)
    contract_type_counts: dict[str, int] = Field(default_factory=dict)
    analyses_timeline: list[TimelinePoint] = Field(default_factory=list)
    trends: DashboardTrends = Field(default_factory=DashboardTrends)
    recent_analyses: list[dict] = Field(default_factory=list)
    range: str = "all"  # echoes the applied time-range filter
