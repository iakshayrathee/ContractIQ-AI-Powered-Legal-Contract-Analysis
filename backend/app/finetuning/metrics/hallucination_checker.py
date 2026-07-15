"""
Hallucination checker for fine-tuning evaluation.

Computes source overlap scores and fabrication rates for extracted clauses.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.schemas.contract import Clause

logger = logging.getLogger(__name__)


@dataclass
class HallucinationReport:
    """Report of hallucination metrics for a batch of clauses."""
    source_overlap_scores: list[float]
    mean_overlap: float
    p25_overlap: float
    p75_overlap: float
    p95_overlap: float
    fabrication_rate: float
    fabrications: list[dict]


def _extract_entities(text: str) -> set[str]:
    """Extract party names, dates, and dollar amounts from text."""
    entities = set()

    # Dollar amounts
    dollar_pattern = r'\$[\d,]+(?:\.\d{2})?'
    entities.update(re.findall(dollar_pattern, text))

    # Dates (various formats)
    date_patterns = [
        r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
        r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}',
    ]
    for pattern in date_patterns:
        entities.update(re.findall(pattern, text, re.IGNORECASE))

    # Party names (capitalized multi-word terms)
    party_pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b'
    entities.update(re.findall(party_pattern, text))

    return entities


def _compute_source_overlap(clause_text: str, source_text: str) -> float:
    """Compute word-level overlap between clause and source."""
    clause_words = set(re.findall(r'\b[a-z]{3,}\b', clause_text.lower()))
    source_words = set(re.findall(r'\b[a-z]{3,}\b', source_text.lower()))

    if not clause_words:
        return 0.0

    overlap = len(clause_words & source_words) / len(clause_words)
    return overlap


def _check_fabrication(clause: Clause, source_text: str) -> Optional[dict]:
    """
    Check if clause contains fabricated entities not in source.

    Returns fabrication details if found, None otherwise.
    """
    clause_entities = _extract_entities(clause.text)
    source_entities = _extract_entities(source_text)

    fabrications = []
    for entity in clause_entities:
        if entity not in source_entities:
            fabrications.append(entity)

    if fabrications:
        return {
            "clause_title": clause.title,
            "clause_type": clause.clause_type.value,
            "fabricated_entities": fabrications,
        }

    return None


def check_batch(
    clauses: list[Clause],
    source_chunks: list[str],
) -> HallucinationReport:
    """
    Check hallucination metrics for a batch of clauses.

    Args:
        clauses: List of extracted Clause objects
        source_chunks: List of source text chunks

    Returns:
        HallucinationReport with overlap scores and fabrication metrics
    """
    combined_source = " ".join(source_chunks).lower()

    overlap_scores = []
    fabrications = []

    for clause in clauses:
        # Compute source overlap
        overlap = _compute_source_overlap(clause.text, combined_source)
        overlap_scores.append(overlap)

        # Check for fabrications
        fabrication = _check_fabrication(clause, combined_source)
        if fabrication:
            fabrications.append(fabrication)

    # Compute statistics
    if overlap_scores:
        sorted_scores = sorted(overlap_scores)
        mean_overlap = sum(overlap_scores) / len(overlap_scores)
        p25_overlap = sorted_scores[int(len(sorted_scores) * 0.25)]
        p75_overlap = sorted_scores[int(len(sorted_scores) * 0.75)]
        p95_overlap = sorted_scores[int(len(sorted_scores) * 0.95)]
    else:
        mean_overlap = 0.0
        p25_overlap = 0.0
        p75_overlap = 0.0
        p95_overlap = 0.0

    fabrication_rate = len(fabrications) / len(clauses) if clauses else 0.0

    return HallucinationReport(
        source_overlap_scores=overlap_scores,
        mean_overlap=mean_overlap,
        p25_overlap=p25_overlap,
        p75_overlap=p75_overlap,
        p95_overlap=p95_overlap,
        fabrication_rate=fabrication_rate,
        fabrications=fabrications,
    )


if __name__ == "__main__":
    # Test the checker
    from app.schemas.contract import Clause, ClauseType

    test_clauses = [
        Clause(
            clause_type=ClauseType.TERMINATION,
            title="Termination",
            text="Either party may terminate this agreement upon 30 days written notice.",
            section_reference="Section 5",
            obligations=[],
        )
    ]

    test_source = ["This agreement may be terminated by either party with 30 days notice."]

    report = check_batch(test_clauses, test_source)
    print(f"Mean overlap: {report.mean_overlap:.2%}")
    print(f"Fabrication rate: {report.fabrication_rate:.2%}")
