"""Eval case dataset schemas and loaders for contract analysis quality measurement."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class ContractType(str, Enum):
    NDA = "NDA"
    MSA = "MSA"
    SLA = "SLA"
    EMPLOYMENT = "Employment"
    LEASE = "Lease"
    SaaS = "SaaS"
    CONSULTING = "Consulting"
    PURCHASE = "Purchase"
    LICENSE = "License"
    OTHER = "Other"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class EvalCase(BaseModel):
    """
    A single test case for evaluating contract analysis quality.

    Contains:
    - Ground truth about what clauses/risks are actually present
    - Source text to analyze
    - Metadata for categorizing results
    """

    id: str = Field(description="Unique identifier for this test case.")
    contract_type: ContractType = Field(description="Type of contract.")
    difficulty: Difficulty = Field(description="Expected analysis difficulty.")
    source_text: str = Field(description="Full text of the contract or excerpt.")
    expected_clauses: list[str] = Field(
        default_factory=list,
        description="Clause types that SHOULD be found in this contract."
    )
    unexpected_clauses: list[str] = Field(
        default_factory=list,
        description="Clause types that should NOT be found (to test precision)."
    )
    expected_risks: list[str] = Field(
        default_factory=list,
        description="Risk titles or categories that are genuinely present."
    )
    expected_parties: list[str] = Field(
        default_factory=list,
        description="Party names that should appear in the analysis."
    )
    expected_summary_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords that should appear in the plain-English summary."
    )
    excluded_summary_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords that should NOT appear in the summary (hallucination test)."
    )
    notes: str = Field(default="", description="Human notes about this test case.")
    source_file: str = Field(default="", description="Original source file name if applicable.")
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="When this test case was created."
    )
    tags: list[str] = Field(default_factory=list, description="Searchable tags.")


class EvalResult(BaseModel):
    """
    Result of running a single eval case through the analysis pipeline.
    """

    case_id: str = Field(description="ID of the EvalCase that was tested.")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="When the eval was run."
    )
    model_version: str = Field(default="unknown", description="Model used for analysis.")
    pipeline_version: str = Field(default="unknown", description="Pipeline/prompt version.")

    # Clause extraction metrics
    clauses_extracted: list[str] = Field(
        default_factory=list,
        description="Clause types actually extracted."
    )
    clause_true_positives: list[str] = Field(
        default_factory=list,
        description="Expected clauses that were correctly found."
    )
    clause_false_positives: list[str] = Field(
        default_factory=list,
        description="Extracted clauses that were not in expected set."
    )
    clause_false_negatives: list[str] = Field(
        default_factory=list,
        description="Expected clauses that were not found."
    )

    # Clause metric scores (0.0-1.0)
    clause_recall: float = Field(ge=0.0, le=1.0, default=0.0)
    clause_precision: float = Field(ge=0.0, le=1.0, default=0.0)
    clause_f1: float = Field(ge=0.0, le=1.0, default=0.0)

    # Risk metrics
    risks_extracted: list[str] = Field(default_factory=list)
    risk_recall: float = Field(ge=0.0, le=1.0, default=0.0)
    risk_precision: float = Field(ge=0.0, le=1.0, default=0.0)

    # Summary metrics
    summary_contains_keywords: bool = Field(default=False)
    summary_has_excluded_keywords: bool = Field(default=False)
    summary_keyword_match_ratio: float = Field(ge=0.0, le=1.0, default=0.0)

    # Judge scores (from LLM-as-Judge)
    judge_overall: float = Field(ge=0.0, le=1.0, default=0.0)
    judge_clause_recall: float = Field(ge=0.0, le=1.0, default=0.0)
    judge_clause_precision: float = Field(ge=0.0, le=1.0, default=0.0)
    judge_risk_accuracy: float = Field(ge=0.0, le=1.0, default=0.0)
    judge_summary_faithfulness: float = Field(ge=0.0, le=1.0, default=0.0)
    hallucination_count: int = Field(default=0)
    missing_clause_count: int = Field(default=0)
    unsafe_statement_severity: str = Field(default="none")

    # Guardrail results
    guardrail_passed: bool = Field(default=True)
    guardrail_confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    guardrail_hallucinations: list[str] = Field(default_factory=list)
    guardrail_unsafe_statements: list[str] = Field(default_factory=list)

    # Overall pass/fail
    passed: bool = Field(default=False, description="Did this eval pass overall?")
    pass_reason: str = Field(default="", description="Why it passed or failed.")
    error: Optional[str] = Field(default=None, description="Error message if eval failed.")


class EvalDataset(BaseModel):
    """A collection of eval cases with metadata."""

    name: str = Field(description="Descriptive name for this dataset.")
    version: str = Field(description="Dataset version for tracking changes.")
    description: str = Field(default="", description="What this dataset covers.")
    cases: list[EvalCase] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def filter_by_contract_type(self, contract_type: ContractType) -> "EvalDataset":
        """Return a new dataset with only cases of the given contract type."""
        filtered = [c for c in self.cases if c.contract_type == contract_type]
        return EvalDataset(name=self.name, version=self.version, cases=filtered)

    def filter_by_difficulty(self, difficulty: Difficulty) -> "EvalDataset":
        """Return a new dataset with only cases of the given difficulty."""
        filtered = [c for c in self.cases if c.difficulty == difficulty]
        return EvalDataset(name=self.name, version=self.version, cases=filtered)

    def get_case(self, case_id: str) -> Optional[EvalCase]:
        """Get a specific case by ID."""
        for c in self.cases:
            if c.id == case_id:
                return c
        return None

    @classmethod
    def load_from_directory(cls, directory: Path) -> "EvalDataset":
        """Load all eval cases from a directory of JSON files."""
        cases = []
        for file_path in sorted(directory.glob("*.json")):
            import json
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        cases.append(EvalCase(**item))
                else:
                    cases.append(EvalCase(**data))
        return cls(name=directory.name, version="1.0.0", cases=cases)
