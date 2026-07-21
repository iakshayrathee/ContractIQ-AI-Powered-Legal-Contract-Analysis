"""
Versioned prompt registry.

All LLM prompts are stored here with explicit version tags so:
  - Every AnalysisRow records which prompt version it used.
  - Eval delta reports can be attributed to prompt changes.
  - A/B testing is possible by changing ACTIVE_VERSIONS.

Naming convention:  <purpose>_v<N>
  e.g. chunk_extraction_v2, risk_analysis_v3, summary_v2, merge_v2

To add a new version:
  1. Add the constant below.
  2. Bump the version key in ACTIVE_VERSIONS.
  3. The old version stays in the file so history is preserved.

Integration with Langfuse (optional):
  If langfuse_enabled=True, get_prompt() will attempt to pull the prompt
  from Langfuse prompt management first, falling back to the local constant
  on miss. This allows hot-swapping prompts without a deploy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt version catalogue
# ---------------------------------------------------------------------------

# ── Pass 1: per-chunk clause extraction ─────────────────────────────────────
CHUNK_EXTRACTION_V1 = """You are a legal contract analyst. Analyze this contract chunk and extract structured information.

IMPORTANT: This is a partial excerpt from a larger contract — do NOT infer clauses that are not explicitly present in this text.

CHUNK TEXT:
{chunk_text}

Return a JSON object with these fields:
{{
  "clauses": [
    {{
      "clause_type": "<MUST be exactly one of: confidentiality, termination, indemnification, liability, non_compete, non_solicitation, intellectual_property, payment, governing_law, dispute_resolution, force_majeure, data_privacy, warranty, insurance, assignment, amendment, entire_agreement, severability, auto_renewal, other>",
      "title": "<short descriptive title>",
      "text": "<quote the exact relevant text verbatim from the chunk — do not paraphrase>",
      "section_reference": "<section or article number if visible in the text, else null>",
      "obligations": [
        {{
          "party": "<party name exactly as written>",
          "description": "<what they must/may/must not do — include monetary amounts, notice periods, and deadlines if mentioned>",
          "deadline": "<deadline if explicitly stated, else null>",
          "type": "<must|must_not|may>"
        }}
      ]
    }}
  ],
  "metadata_fragments": {{
    "contract_type": "<type if clearly identifiable from this chunk, else null>",
    "parties": ["<party names found in this chunk>"],
    "effective_date": "<date if explicitly stated, else null>",
    "expiration_date": "<date if explicitly stated, else null>",
    "governing_law": "<jurisdiction if explicitly stated, else null>",
    "jurisdiction": "<jurisdiction if explicitly stated, else null>"
  }},
  "key_dates": ["<any important dates explicitly mentioned>"],
  "financial_terms": ["<any monetary amounts, caps, penalties, fees, or payment schedules explicitly stated>"]
}}

Rules:
- Extract ONLY what is explicitly stated — never fabricate, infer, or extrapolate
- If a field is not present in this chunk, use null or empty array
- Use clause_type "other" if no specific type fits
- Pay special attention to: liability caps, indemnification scope, notice periods, renewal terms, and payment obligations
- Return ONLY valid JSON, no markdown fences, no extra text"""


# ── Pass 2: merge + metadata resolution ─────────────────────────────────────
MERGE_V1 = """You are a legal contract analyst. Given these extracted fragments from different parts of a contract, produce a unified contract analysis.

METADATA FRAGMENTS (parties, dates, governing law from each chunk):
{fragments_json}

IDENTIFIED CLAUSES (type and title only — for context):
{clauses_summary}

Produce a single JSON object:
{{
  "metadata": {{
    "contract_type": "<most likely type based on clauses and metadata>",
    "parties": ["<deduplicated list of all parties — merge name variants>"],
    "effective_date": "<resolved date or null>",
    "expiration_date": "<resolved date or null>",
    "governing_law": "<resolved or null>",
    "jurisdiction": "<resolved or null>"
  }}
}}

Rules:
- Deduplicate party names (merge variants like 'ACME Corp' and 'Acme Corporation' → pick the most formal)
- Pick the most specific contract_type
- Resolve conflicting dates by picking the most credible occurrence
- Return ONLY valid JSON, no markdown fences"""


# ── Risk analysis v1 (legacy, no evidence requirement) ──────────────────────
RISK_ANALYSIS_V1 = """You are a senior legal risk analyst reviewing a contract for potential issues.

CONTRACT ANALYSIS SUMMARY:
{analysis_json}

Identify genuine risks and concerns. Pay particular attention to:
1. UNLIMITED LIABILITY — Is there a liability cap?
2. ONE-SIDED INDEMNIFICATION — Does only one party bear indemnification obligations?
3. VAGUE OR UNDEFINED TERMS — Are key terms left undefined or overly broad?
4. INADEQUATE NOTICE PERIODS — Are notice periods too short (< 15 days) or absent?
5. MISSING LIQUIDATED DAMAGES — For contracts with delivery obligations, no penalty for non-performance?
6. UNILATERAL MODIFICATION RIGHTS — Can one party change terms without consent?
7. IP OWNERSHIP AMBIGUITY — Is ownership of work product clearly assigned?

Return a JSON object:
{{
  "risks": [
    {{
      "category": "<missing_clause|unfavorable_terms|ambiguous_language|compliance|financial|operational|data_privacy>",
      "severity": "<low|medium|high|critical>",
      "title": "<short specific risk title>",
      "description": "<what the risk is and why it matters>",
      "clause_reference": "<title of the related clause, or null>",
      "recommendation": "<concrete, actionable step to mitigate>"
    }}
  ],
  "summary": "<3-4 sentence overall risk assessment>"
}}

Return ONLY valid JSON, no markdown fences"""


# ── Risk analysis v2 — Phase 1+4: evidence quotes + party perspective ────────
RISK_ANALYSIS_V2 = """You are a senior legal risk analyst reviewing a contract for potential issues.

PARTY PERSPECTIVE: {perspective}
(Assess risks FROM THE PERSPECTIVE of: {perspective}. If "neutral", assess for both parties.)

CONTRACT ANALYSIS — FULL CLAUSE TEXT:
{analysis_json}

RETRIEVED SOURCE PASSAGES (verbatim from the contract — use these for evidence):
{evidence_passages}

Identify genuine risks. Pay particular attention to:
1. UNLIMITED LIABILITY — Is there a liability cap? If absent or vague → critical/high.
2. ONE-SIDED INDEMNIFICATION — Does only one party bear indemnification? Flag if asymmetric.
3. VAGUE OR UNDEFINED TERMS — Key terms like 'reasonable', 'material breach' left undefined?
4. INADEQUATE NOTICE PERIODS — Notice periods < 15 days or absent for termination/renewal opt-out?
5. MISSING LIQUIDATED DAMAGES — No penalty for non-performance on delivery obligations?
6. UNILATERAL MODIFICATION RIGHTS — One party can change terms without consent?
7. IP OWNERSHIP AMBIGUITY — Ownership of work product, inventions, or data clearly assigned?
8. AUTO-RENEWAL TRAP — Auto-renewal without a clear, reasonable opt-out window?
9. PAYMENT SUSPENSION — Can service be suspended on short notice for non-payment?
10. DATA PRIVACY GAPS — GDPR/CCPA compliance obligations present but vague?

For EACH risk, you MUST provide an evidence quote — a verbatim excerpt from the source passages
above that directly supports your finding. If you cannot find a verbatim quote supporting a risk,
do NOT include that risk.

Return a JSON object:
{{
  "risks": [
    {{
      "category": "<missing_clause|unfavorable_terms|ambiguous_language|compliance|financial|operational|data_privacy>",
      "severity": "<low|medium|high|critical>",
      "title": "<short specific risk title>",
      "description": "<what the risk is, why it matters for {perspective}, and what specific language causes it>",
      "clause_reference": "<title of the related clause, or null if missing clause>",
      "recommendation": "<concrete, actionable step — be specific>",
      "evidence": [
        {{
          "quote": "<verbatim excerpt from the source passages that proves this risk>",
          "page_number": <integer or null>,
          "section_reference": "<e.g. Section 6.1 or null>"
        }}
      ],
      "confidence": <float 0.0-1.0 — how strongly the evidence supports this risk>
    }}
  ],
  "summary": "<3-4 sentence overall risk assessment from the perspective of {perspective}: state overall risk level, 2-3 most significant risks, and a clear recommendation>"
}}

Severity guidelines:
- critical: Exposes {perspective} to unlimited liability, regulatory penalties, or fundamental failure
- high: Significant commercial or legal exposure requiring attention before signing
- medium: Suboptimal terms that pose moderate risk if a dispute arises
- low: Minor gaps or standard imprecisions with limited practical impact

IMPORTANT:
- Only include risks with verbatim evidence quotes from the passages above
- Do NOT fabricate risks for categories that have no evidence
- Return ONLY valid JSON, no markdown fences"""


# ── Summary v1 (legacy) ──────────────────────────────────────────────────────
SUMMARY_V1 = """You are a legal assistant explaining a contract in plain English to a non-lawyer.

CONTRACT DETAILS:
{analysis_json}

RISK FINDINGS:
{risk_json}

Return a JSON object with EXACTLY these sections:
{{
  "executive_summary": "<2-3 sentence overview>",
  "what_this_does": "<3-4 sentence plain-English explanation>",
  "obligations_by_party": {{
    "<party name>": ["<obligation 1>", "<obligation 2>"]
  }},
  "key_dates": ["<important dates with full context>"],
  "watch_out_for": ["<[Clause Name]: plain-English concern>"],
  "action_items": ["<[URGENT/BEFORE SIGNING/WITHIN 30 DAYS/ONGOING]: action>"],
  "key_risks_plain": ["<HIGH/CRITICAL risk in plain English>"]
}}

Return ONLY valid JSON, no markdown fences"""


# ── Summary v2 — Phase 1+6: evidence-grounded, adaptive depth ────────────────
SUMMARY_V2 = """You are a legal assistant explaining a contract in plain English to a non-lawyer.

SUMMARY DEPTH: {complexity_tier}
(brief = NDA/simple contracts: 2-3 items per section; standard = most contracts; detailed = complex MSA/SaaS)

CONTRACT DETAILS:
{analysis_json}

RISK FINDINGS (with evidence quotes):
{risk_json}

VERBATIM SOURCE PASSAGES (for grounding obligations and dates):
{evidence_passages}

OBLIGATIONS ALREADY EXTRACTED (use these directly — do not re-derive):
{obligations_json}

Return a JSON object:
{{
  "executive_summary": "<2-3 sentence overview anyone can understand — state what the contract is, who signed it, and the most important thing to know>",
  "what_this_does": "<plain-English explanation: purpose, what each party gets, main commitments, duration ({complexity_tier} depth)>",
  "obligations_by_party": {{
    "<party name>": ["<obligation — specific, include amounts/deadlines if present>"]
  }},
  "key_dates": ["<date with full context — e.g. 'Contract expires Dec 31 2025 — 30 days notice to renew'>"],
  "watch_out_for": [
    "<[Clause Name]: plain-English concern. Reference the actual clause causing it.>"
  ],
  "action_items": [
    "<[URGENT|BEFORE SIGNING|WITHIN 30 DAYS|ONGOING]: specific action>"
  ],
  "key_risks_plain": [
    "<HIGH or CRITICAL risk in plain English with zero legal jargon — what could go wrong, why it matters, what to do>"
  ],
  "complexity_tier": "{complexity_tier}"
}}

Rules:
- Use simple language — explain to a friend, not a lawyer
- Be specific: reference actual clause names, dollar amounts, and deadlines
- Base everything on the content provided — do not fabricate terms
- key_risks_plain: include only HIGH and CRITICAL severity risks
- Return ONLY valid JSON, no markdown fences"""


# ── Evidence verification pass — Phase 5 ────────────────────────────────────
EVIDENCE_VERIFICATION_V1 = """You are a legal quality reviewer. For each risk finding below, verify whether the provided evidence quote actually supports the stated severity and description.

RISK FINDINGS TO VERIFY:
{risks_json}

SOURCE DOCUMENT (verbatim):
{source_text}

For each risk, return one of:
- "keep": evidence clearly supports the finding at stated severity
- "downgrade": evidence exists but supports lower severity (specify new severity)
- "drop": evidence does not support the finding or is fabricated

Return a JSON array:
[
  {{
    "risk_title": "<exact title from input>",
    "verdict": "<keep|downgrade|drop>",
    "new_severity": "<low|medium|high|critical or null if keep/drop>",
    "reason": "<one sentence explaining the verdict>"
  }}
]

Return ONLY valid JSON, no markdown fences."""


# ── Judge-informed regeneration — Phase 5 ───────────────────────────────────
RISK_REGENERATION_V1 = """You are a senior legal risk analyst. A previous risk analysis received a low quality score.

JUDGE CRITIQUE:
{judge_critique}

ORIGINAL RISK OUTPUT (to improve):
{original_risks_json}

CONTRACT ANALYSIS:
{analysis_json}

RETRIEVED SOURCE PASSAGES:
{evidence_passages}

Regenerate the risk analysis addressing ALL issues raised in the judge critique.
Pay special attention to: {critique_focus}

Return corrected JSON in the same format as the original risk output.
Return ONLY valid JSON, no markdown fences."""


SUMMARY_REGENERATION_V1 = """You are a legal assistant. A previous plain-English summary received a low quality score.

JUDGE CRITIQUE:
{judge_critique}

ORIGINAL SUMMARY (to improve):
{original_summary_json}

CONTRACT DETAILS:
{analysis_json}

Regenerate the summary addressing ALL issues raised in the judge critique.
Pay special attention to: {critique_focus}

Return corrected JSON in the same format as the original summary.
Return ONLY valid JSON, no markdown fences."""


# ---------------------------------------------------------------------------
# Active version registry — change these to upgrade the pipeline
# ---------------------------------------------------------------------------

ACTIVE_VERSIONS: dict[str, str] = {
    "chunk_extraction": "v1",
    "merge": "v1",
    "risk_analysis": "v2",   # Phase 1+4: evidence + perspective
    "summary": "v2",          # Phase 1+6: evidence-grounded + adaptive
    "evidence_verification": "v1",
    "risk_regeneration": "v1",
    "summary_regeneration": "v1",
}

_PROMPT_CATALOGUE: dict[str, str] = {
    "chunk_extraction_v1": CHUNK_EXTRACTION_V1,
    "merge_v1": MERGE_V1,
    "risk_analysis_v1": RISK_ANALYSIS_V1,
    "risk_analysis_v2": RISK_ANALYSIS_V2,
    "summary_v1": SUMMARY_V1,
    "summary_v2": SUMMARY_V2,
    "evidence_verification_v1": EVIDENCE_VERIFICATION_V1,
    "risk_regeneration_v1": RISK_REGENERATION_V1,
    "summary_regeneration_v1": SUMMARY_REGENERATION_V1,
}


@dataclass
class PromptRegistry:
    """Centralised access to versioned prompts with optional Langfuse pull."""

    langfuse_enabled: bool = False
    _langfuse_client: object = field(default=None, init=False, repr=False)

    def _try_langfuse(self, key: str) -> Optional[str]:
        """
        Attempt to pull a prompt from Langfuse prompt management.
        Returns the prompt string if found, None otherwise.
        """
        if not self.langfuse_enabled:
            return None
        try:
            if self._langfuse_client is None:
                from langfuse import Langfuse
                self._langfuse_client = Langfuse()
            prompt_obj = self._langfuse_client.get_prompt(key)
            return prompt_obj.compile()
        except Exception as exc:
            logger.debug("Langfuse prompt pull failed for '%s': %s — using local", key, exc)
            return None

    def get(self, purpose: str) -> tuple[str, str]:
        """
        Retrieve the active prompt for a pipeline stage.

        Args:
            purpose: Pipeline stage name (matches ACTIVE_VERSIONS keys).

        Returns:
            (prompt_text, version_tag) — version_tag is e.g. "risk_analysis_v2"

        Raises:
            KeyError: if purpose is not in ACTIVE_VERSIONS.
        """
        version = ACTIVE_VERSIONS[purpose]
        key = f"{purpose}_{version}"

        # 1. Try Langfuse hot-swap
        lf_prompt = self._try_langfuse(key)
        if lf_prompt:
            logger.debug("Using Langfuse prompt: %s", key)
            return lf_prompt, key

        # 2. Fall back to local catalogue
        prompt = _PROMPT_CATALOGUE.get(key)
        if prompt is None:
            raise KeyError(
                f"Prompt '{key}' not found in catalogue. "
                f"Check ACTIVE_VERSIONS and _PROMPT_CATALOGUE."
            )
        return prompt, key

    def list_active(self) -> dict[str, str]:
        """Return {purpose: version_key} for all active prompts."""
        return {p: f"{p}_{v}" for p, v in ACTIVE_VERSIONS.items()}


# Module-level singleton — import this for direct use
_registry: Optional[PromptRegistry] = None


def get_prompt(purpose: str, langfuse_enabled: bool = False) -> tuple[str, str]:
    """
    Convenience wrapper around the module-level PromptRegistry singleton.

    Returns:
        (prompt_text, version_key)
    """
    global _registry
    if _registry is None or _registry.langfuse_enabled != langfuse_enabled:
        _registry = PromptRegistry(langfuse_enabled=langfuse_enabled)
    return _registry.get(purpose)
