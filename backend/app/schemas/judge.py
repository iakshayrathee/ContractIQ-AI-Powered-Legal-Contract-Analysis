"""Pydantic schemas for LLM-as-Judge evaluation outputs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class JudgeClauseExtraction(BaseModel):
    """Evaluation of clause extraction quality."""

    recall: float = Field(
        ge=0.0, le=1.0,
        description="Did we find all the important clauses? 0.0 = missed everything, 1.0 = perfect recall."
    )
    precision: float = Field(
        ge=0.0, le=1.0,
        description="Are extracted clauses accurate? 0.0 = all wrong, 1.0 = all correct."
    )
    notes: str = Field(
        default="",
        description="Qualitative notes on clause extraction quality."
    )


class JudgeRiskAssessment(BaseModel):
    """Evaluation of risk assessment quality."""

    accuracy: float = Field(
        ge=0.0, le=1.0,
        description="Are identified risks substantive and properly calibrated?"
    )
    severity_calibration: float = Field(
        ge=0.0, le=1.0,
        description="Are severity levels appropriate? 1.0 = perfectly calibrated."
    )
    notes: str = Field(default="", description="Qualitative notes on risk assessment.")


class JudgeSummaryFaithfulness(BaseModel):
    """Evaluation of plain-English summary quality."""

    faithfulness: float = Field(
        ge=0.0, le=1.0,
        description="Does the summary accurately represent the contract? 1.0 = perfectly faithful."
    )
    completeness: float = Field(
        ge=0.0, le=1.0,
        description="Does the summary cover all important aspects? 1.0 = complete."
    )
    notes: str = Field(default="", description="Qualitative notes on summary quality.")


class JudgeHallucinationDetails(BaseModel):
    """Details about hallucinated content detected."""

    clause_hallucinations: list[str] = Field(
        default_factory=list,
        description="Specific clause hallucinations detected."
    )
    summary_hallucinations: list[str] = Field(
        default_factory=list,
        description="Specific summary hallucinations detected."
    )
    risk_hallucinations: list[str] = Field(
        default_factory=list,
        description="Specific risk item hallucinations detected."
    )


class JudgeMissingContent(BaseModel):
    """Content that was missed during analysis."""

    missing_critical_clauses: list[str] = Field(
        default_factory=list,
        description="Critical clause types that were not identified."
    )
    missing_obligations: list[str] = Field(
        default_factory=list,
        description="Important obligations not captured."
    )
    missing_dates: list[str] = Field(
        default_factory=list,
        description="Important dates not captured."
    )


class JudgeUnsafeStatements(BaseModel):
    """Statements that may be legally unsafe or harmful."""

    statements: list[str] = Field(
        default_factory=list,
        description="Potentially unsafe or misleading statements found."
    )
    severity: str = Field(
        default="none",
        description="Overall severity: 'none', 'low', 'medium', 'high', 'critical'."
    )


class JudgeOutput(BaseModel):
    """
    Complete judge evaluation for a contract analysis.

    Produced by the LLM-as-Judge after reviewing:
    - Source document
    - Extracted clauses
    - Risk report
    - Plain-English summary
    """

    # Overall quality score
    overall_score: float = Field(
        ge=0.0, le=1.0,
        description="Overall quality of the analysis. 1.0 = perfect, 0.0 = completely unacceptable."
    )
    overall_reasoning: str = Field(
        default="",
        description="Free-text reasoning for the overall score."
    )

    # Dimension scores
    clause_extraction: JudgeClauseExtraction = Field(
        default_factory=JudgeClauseExtraction,
        description="Clause extraction evaluation."
    )
    risk_assessment: JudgeRiskAssessment = Field(
        default_factory=JudgeRiskAssessment,
        description="Risk assessment evaluation."
    )
    summary_faithfulness: JudgeSummaryFaithfulness = Field(
        default_factory=JudgeSummaryFaithfulness,
        description="Summary faithfulness evaluation."
    )

    # Problem detection
    hallucinations: JudgeHallucinationDetails = Field(
        default_factory=JudgeHallucinationDetails,
        description="Hallucinated content detected by the judge."
    )
    missing_content: JudgeMissingContent = Field(
        default_factory=JudgeMissingContent,
        description="Critical content that was missed."
    )
    unsafe_statements: JudgeUnsafeStatements = Field(
        default_factory=JudgeUnsafeStatements,
        description="Potentially unsafe statements detected."
    )

    # Metadata
    judge_model: str = Field(
        default="gpt-4o",
        description="Which model was used for judging."
    )
    judged_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="ISO timestamp when evaluation was performed."
    )
    analysis_id: Optional[str] = Field(
        default=None,
        description="ID of the analysis being judged."
    )

    def is_acceptable(self, threshold: float = 0.7) -> bool:
        """Returns True if overall score meets the minimum quality threshold."""
        return self.overall_score >= threshold

    def flagged_for_review(self) -> bool:
        """Returns True if any critical issues were found that require human review."""
        return (
            self.overall_score < 0.7
            or len(self.hallucinations.clause_hallucinations) > 0
            or self.unsafe_statements.severity in ("high", "critical")
            or len(self.missing_content.missing_critical_clauses) > 2
        )


class JudgeScores(BaseModel):
    """
    Flattened judge scores stored alongside analysis results.

    Extracted from JudgeOutput for easy querying and trending.
    """

    analysis_id: str
    overall_score: float
    clause_recall: float
    clause_precision: float
    risk_accuracy: float
    risk_severity_calibration: float
    summary_faithfulness: float
    summary_completeness: float
    hallucination_count: int
    missing_critical_clause_count: int
    unsafe_statement_severity: str
    flagged_for_review: bool
    judge_model: str
    judged_at: str

    @classmethod
    def from_judge_output(cls, output: JudgeOutput, analysis_id: str) -> "JudgeScores":
        """Create a flattened score row from a full JudgeOutput."""
        return cls(
            analysis_id=analysis_id,
            overall_score=output.overall_score,
            clause_recall=output.clause_extraction.recall,
            clause_precision=output.clause_extraction.precision,
            risk_accuracy=output.risk_assessment.accuracy,
            risk_severity_calibration=output.risk_assessment.severity_calibration,
            summary_faithfulness=output.summary_faithfulness.faithfulness,
            summary_completeness=output.summary_faithfulness.completeness,
            hallucination_count=(
                len(output.hallucinations.clause_hallucinations)
                + len(output.hallucinations.summary_hallucinations)
                + len(output.hallucinations.risk_hallucinations)
            ),
            missing_critical_clause_count=len(output.missing_content.missing_critical_clauses),
            unsafe_statement_severity=output.unsafe_statements.severity,
            flagged_for_review=output.flagged_for_review(),
            judge_model=output.judge_model,
            judged_at=output.judged_at,
        )
