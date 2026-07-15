"""
Guardrails: input validation and output safety checks.

Input Guardrails (pre-processing):
  - Prompt injection detection
  - Content size limits
  - Repetitive/abusive content detection

Output Guardrails (post-processing):
  - Hallucination detection (low source overlap)
  - Unsafe legal statement detection
  - Confidence scoring
"""

import collections
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input Guardrails
# ---------------------------------------------------------------------------

# Maximum accepted content size (10MB of text)
MAX_CONTENT_CHARS = 10_000_000

# Patterns that indicate prompt injection attempts
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|all)\s+(instructions?|prompts?|rules?)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+)?(you\s+)?(are|cAN)\s+(a\s+)?different", re.IGNORECASE),
    re.compile(r"disregard\s+(your\s+)?(system|previous)\s+(instructions?|config)", re.IGNORECASE),
    re.compile(r"//\s*USER\s*INSTRUCTIONS", re.IGNORECASE),
    re.compile(r"<\|.*\|>"),  # Malicious role-play tokens
    re.compile(r"{{\s*.*?\s*}}"),  # Template injection attempt
    re.compile(r"\[INST\]\s*.*?\s*\[/INST\]", re.IGNORECASE),  # Llama instruction injection
]


@dataclass
class InputGuardrailResult:
    passed: bool
    reason: Optional[str] = None
    sanitized_content: Optional[str] = None


def validate_contract_input(content: str) -> InputGuardrailResult:
    """
    Validate contract content before ingestion.

    Checks:
    1. Content length is within acceptable bounds
    2. No prompt injection patterns detected
    3. No repetitive/abusive content patterns
    """
    # 1. Length check — prevent resource exhaustion
    if len(content) > MAX_CONTENT_CHARS:
        logger.warning("Content rejected: too large (%d chars, max %d)", len(content), MAX_CONTENT_CHARS)
        return InputGuardrailResult(
            passed=False,
            reason=f"Content too large: {len(content):,} chars (max: {MAX_CONTENT_CHARS:,})",
        )

    if len(content) == 0:
        return InputGuardrailResult(
            passed=False,
            reason="Content is empty",
        )

    # 2. Prompt injection detection
    for pattern in INJECTION_PATTERNS:
        match = pattern.search(content)
        if match:
            logger.warning("Content rejected: prompt injection pattern detected (%s)", pattern.pattern)
            return InputGuardrailResult(
                passed=False,
                reason="Content contains suspicious patterns that are not permitted.",
            )

    # 3. Repetitive/abusive content check
    if _has_repetitive_pattern(content):
        logger.warning("Content rejected: repetitive pattern detected")
        return InputGuardrailResult(
            passed=False,
            reason="Content appears to be repetitive or abusive.",
        )

    return InputGuardrailResult(passed=True, sanitized_content=content)


def validate_query_input(query: str) -> InputGuardrailResult:
    """
    Validate user chat queries to prevent jailbreaks and off-topic prompts.
    """
    # 1. Prompt injection detection
    for pattern in INJECTION_PATTERNS:
        if pattern.search(query):
            logger.warning("Query rejected: prompt injection pattern detected (%s)", pattern.pattern)
            return InputGuardrailResult(
                passed=False,
                reason="I cannot process this request as it contains restricted instructional patterns.",
            )
            
    # 2. Semantic topic restriction heuristic
    off_topic_keywords = [
        "recipe", "poem", "code", "python", "javascript", "html", 
        "tell me a joke", "story about", "write a song", "ignore context"
    ]
    query_lower = query.lower()
    if any(kw in query_lower for kw in off_topic_keywords):
        if not any(legal_kw in query_lower for legal_kw in ["contract", "legal", "clause", "agreement", "law"]):
            logger.warning("Query rejected: off-topic detected")
            return InputGuardrailResult(
                passed=False,
                reason="This system is restricted to legal contract analysis. Please ask questions related to the contract.",
            )
            
    return InputGuardrailResult(passed=True, sanitized_content=query)


def _has_repetitive_pattern(content: str, threshold: float = 0.85) -> bool:
    """Detect if content is >threshold% the same character repeated."""
    if len(content) < 1000:
        return False
    counts = collections.Counter(content.lower())
    most_common_ratio = counts.most_common(1)[0][1] / len(content)
    return most_common_ratio > threshold


# ---------------------------------------------------------------------------
# Output Guardrails — hallucination + unsafe statement detection
# ---------------------------------------------------------------------------

# Legal statements that require strict source verification
UNSAFE_LEGAL_PATTERNS = [
    (
        re.compile(r"you\s+hereby\s+waive\s+(all\s+)?(your\s+)?rights?", re.IGNORECASE),
        "Waiver claim",
    ),
    (
        re.compile(r"this\s+contract\s+(is|constitutes)\s+(a\s+)?(\w+\s+)?settlement", re.IGNORECASE),
        "Settlement claim",
    ),
    (
        re.compile(r"party\s+\w+\s+irrevocably\s+agrees", re.IGNORECASE),
        "Irrevocable agreement",
    ),
    (
        re.compile(r"this\s+agreement\s+(is\s+)?void\s+((under| pursuant to)\s+)?", re.IGNORECASE),
        "Voidness claim",
    ),
    (
        re.compile(r"(party\s+\w+\s+)?hereby\s+(grants?|conveys?|assigns?)\s+.+\s+(all\s+)?rights", re.IGNORECASE),
        "Rights grant claim",
    ),
]


@dataclass
class OutputGuardrailResult:
    passed: bool
    hallucinations: list[str] = None
    unsafe_statements: list[str] = None
    confidence: float = 1.0
    warnings: list[str] = None

    def __post_init__(self):
        if self.hallucinations is None:
            self.hallucinations = []
        if self.unsafe_statements is None:
            self.unsafe_statements = []
        if self.warnings is None:
            self.warnings = []


class OutputGuardrails:
    """
    Post-processing guardrails that validate LLM outputs against source content.

    Detects:
    - Hallucinated clauses (low overlap with source)
    - Unsafe legal statements (requires verification)
    - Summary claims not grounded in source
    """

    # Minimum word-level overlap between extracted clause and source text
    MIN_CLAUSE_SOURCE_OVERLAP = 0.25

    # Minimum entity overlap for summary claims
    MIN_SUMMARY_ENTITY_OVERLAP = 0.4

    def __init__(self, settings: Settings):
        self._settings = settings

    def validate_clauses(
        self,
        clauses: list[dict],
        source_chunks: list[str],
        user_query: Optional[str] = None,
    ) -> OutputGuardrailResult:
        """
        Validate extracted clauses against source text.

        Checks:
        1. Each clause's text has sufficient word overlap with source
        2. No unsafe legal statements without clear source backing
        """
        hallucinations = []
        unsafe_statements = []

        if not source_chunks:
            # No source to validate against — flag all clauses as unverified
            for clause in clauses:
                hallucinations.append(
                    f"Clause '{clause.get('clause_type', 'unknown')}: {clause.get('title', 'untitled')}' "
                    f"cannot be verified — no source content available."
                )
            return OutputGuardrailResult(
                passed=len(hallucinations) == 0,
                hallucinations=hallucinations,
                confidence=0.5,
                warnings=["No source content available for verification."],
            )

        # Build a combined source text (lowercased for matching)
        source_text = " ".join(source_chunks).lower()
        source_words = set(re.findall(r"\b[a-z]{3,}\b", source_text))

        for clause in clauses:
            clause_text = clause.get("text", "").lower()
            clause_type = clause.get("clause_type", "unknown")
            clause_title = clause.get("title", "untitled")

            # Skip empty clauses
            if not clause_text.strip():
                continue

            # Check 1: N-gram (bigram) overlap with source to prevent hallucination
            clause_words = re.findall(r"\b[a-z]{3,}\b", clause_text)
            clause_bigrams = set(zip(clause_words, clause_words[1:])) if len(clause_words) > 1 else set(clause_words)
            
            source_words_list = re.findall(r"\b[a-z]{3,}\b", source_text)
            source_bigrams = set(zip(source_words_list, source_words_list[1:])) if len(source_words_list) > 1 else set(source_words_list)
            
            if clause_bigrams:
                overlap = len(clause_bigrams & source_bigrams) / len(clause_bigrams)
            else:
                overlap = 0.0

            if overlap < self.MIN_CLAUSE_SOURCE_OVERLAP:
                hallucinations.append(
                    f"Clause '{clause_type}: {clause_title}' has low source overlap ({overlap:.0%}). "
                    f"The extracted text may be hallucinated or significantly misrepresented. "
                    f"(extracted: {clause_text[:100]}...)"
                )

            # Check 2: Unsafe legal statement patterns
            for pattern, label in UNSAFE_LEGAL_PATTERNS:
                if pattern.search(clause_text):
                    # Only flag if this is NOT clearly backed by source
                    pattern_words = set(re.findall(r"\b[a-z]{3,}\b", pattern.pattern))
                    pattern_in_source = any(
                        re.search(pattern, chunk.lower()) for chunk in source_chunks
                    )
                    if not pattern_in_source:
                        unsafe_statements.append(
                            f"'{label}' detected in clause '{clause_title}' — "
                            f"this is a significant legal claim that should be verified against the source document."
                        )

        passed = len(hallucinations) == 0 and len(unsafe_statements) == 0
        confidence = 1.0 - (len(hallucinations) * 0.1 + len(unsafe_statements) * 0.2)
        confidence = max(0.0, min(1.0, confidence))

        return OutputGuardrailResult(
            passed=passed,
            hallucinations=hallucinations,
            unsafe_statements=unsafe_statements,
            confidence=confidence,
            warnings=[],
        )

    def validate_summary(
        self,
        summary: dict,
        source_chunks: list[str],
    ) -> OutputGuardrailResult:
        """
        Validate plain-English summary claims against source.

        Checks:
        1. Key entities mentioned in summary appear in source
        2. No fabricated dates, parties, or obligations
        """
        hallucinations = []
        warnings = []

        if not source_chunks:
            return OutputGuardrailResult(
                passed=True,
                confidence=0.5,
                warnings=["No source content available for summary validation."],
            )

        source_text = " ".join(source_chunks).lower()
        source_words = set(re.findall(r"\b[a-z]{3,}\b", source_text))

        # Check executive summary
        exec_summary = summary.get("executive_summary", "")
        summary_claims = _extract_claims(exec_summary)

        for claim in summary_claims:
            entities = _extract_key_entities(claim)
            if entities:
                entity_overlap = sum(
                    1 for e in entities if e.lower() in source_words
                ) / len(entities)
                if entity_overlap < self.MIN_SUMMARY_ENTITY_OVERLAP:
                    hallucinations.append(
                        f"Summary claim may not be grounded in source: '{claim}' "
                        f"(entity overlap: {entity_overlap:.0%})"
                    )

        # Check obligations_by_party
        obligations = summary.get("obligations_by_party", {})
        for party, obligations_list in obligations.items():
            if party.lower() not in source_text and party != "Unknown":
                # Party name not in source — flag but don't fail
                warnings.append(
                    f"Party '{party}' mentioned in summary obligations not found in source text."
                )

        # Check key_dates
        key_dates = summary.get("key_dates", [])
        for date_entry in key_dates:
            # Extract date patterns and verify they appear in source
            date_patterns = re.findall(r"\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}", date_entry)
            for dp in date_patterns:
                if dp not in source_text:
                    warnings.append(
                        f"Date '{dp}' mentioned in summary key dates not found in source."
                    )

        passed = len(hallucinations) == 0
        confidence = 1.0 - (len(hallucinations) * 0.15)
        confidence = max(0.0, min(1.0, confidence))

        return OutputGuardrailResult(
            passed=passed,
            hallucinations=hallucinations,
            confidence=confidence,
            warnings=warnings,
        )

    def validate_risk_items(
        self,
        risk_items: list[dict],
        source_chunks: list[str],
    ) -> OutputGuardrailResult:
        """
        Validate risk items are grounded in actual contract content.
        """
        hallucinations = []

        if not source_chunks:
            return OutputGuardrailResult(
                passed=True,
                confidence=0.5,
                warnings=["No source content available for risk validation."],
            )

        source_text = " ".join(source_chunks).lower()

        for item in risk_items:
            title = item.get("title", "")
            description = item.get("description", "")
            combined_text = f"{title} {description}".lower()

            # Extract key terms
            key_terms = set(re.findall(r"\b[a-z]{4,}\b", combined_text))
            source_terms = set(re.findall(r"\b[a-z]{4,}\b", source_text))

            if key_terms:
                overlap = len(key_terms & source_terms) / len(key_terms)
                if overlap < 0.20:
                    hallucinations.append(
                        f"Risk item '{title}' appears to have low connection to source content "
                        f"(term overlap: {overlap:.0%}). Verify this risk is actually present."
                    )

        passed = len(hallucinations) == 0
        confidence = 1.0 - (len(hallucinations) * 0.1)
        confidence = max(0.0, min(1.0, confidence))

        return OutputGuardrailResult(
            passed=passed,
            hallucinations=hallucinations,
            confidence=confidence,
            warnings=[],
            unsafe_statements=[],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_claims(text: str) -> list[str]:
    """Extract declarative sentences that make factual claims."""
    if not text:
        return []
    sentences = re.split(r"[.!?]+", text)
    claims = []
    for s in sentences:
        s = s.strip()
        if len(s) < 20:
            continue
        # Sentences with modal verbs, numbers, or party references make claims
        if any(modal in s.lower() for modal in ["must", "shall", "will", "may", "cannot"]):
            claims.append(s)
        elif re.search(r"\d{4}", s):  # Contains a year — likely a date claim
            claims.append(s)
    return claims


def _extract_key_entities(text: str) -> list[str]:
    """Extract capitalized terms and quoted phrases that look like entities."""
    entities = []

    # Capitalized multi-word terms (likely parties, clauses, etc.)
    capitalized = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text)
    entities.extend(capitalized)

    # Quoted phrases
    quoted = re.findall(r'"([^"]+)"', text)
    entities.extend(quoted)

    # Terms in all-caps (likely defined terms)
    all_caps = re.findall(r"\b[A-Z]{2,}\b", text)
    entities.extend(all_caps)

    return entities
