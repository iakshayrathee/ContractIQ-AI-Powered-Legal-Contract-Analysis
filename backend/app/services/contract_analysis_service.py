"""
Two-pass contract analysis service.

Pass 1 (per-chunk, parallel): Extract local clauses + metadata fragments from each chunk.
Pass 2 (merge + meta-analysis): Deduplicate, resolve conflicts, produce contract-level output.

Also generates plain-english summaries and risk analysis.
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import AnalysisRow, ProjectRow
from app.llm.provider import get_analysis_llm, get_llm
from app.schemas.contract import (
    Clause,
    ClauseType,
    ContractAnalysis,
    ContractMetadata,
    Obligation,
    ObligationType,
    PlainSummary,
    RiskCategory,
    RiskItem,
    RiskReport,
    RiskSeverity,
    ScoringExplanation,
)
from app.schemas.judge import JudgeOutput
from app.services.guardrails import OutputGuardrails, validate_contract_input
from app.services.vector_store_service import VectorStoreService
from app.utils.langfuse_utils import get_langfuse_callback

logger = structlog.get_logger()

# Max simultaneous GPT-4o calls during Pass 1 to avoid rate-limit 429s.
_PASS1_CONCURRENCY = 5

# --- Prompt templates ---

CHUNK_EXTRACTION_PROMPT = """You are a legal contract analyst. Analyze this contract chunk and extract structured information.

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
          "description": "<what they must/may/must not do — include monetary amounts, notice periods, and deadlines if mentioned (e.g., '$500,000 cap', '30 days written notice', 'within 60 days')>",
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
  "financial_terms": ["<any monetary amounts, caps, penalties, fees, or payment schedules explicitly stated — e.g., '$1M liability cap', '2% monthly late fee', '$50,000 deposit'>"]
}}

Rules:
- Extract ONLY what is explicitly stated — never fabricate, infer, or extrapolate
- If a field is not present in this chunk, use null or empty array
- Use clause_type "other" if no specific type fits
- If uncertain about a clause_type classification, use "other"
- Pay special attention to: liability caps, indemnification scope, notice periods, renewal terms, and payment obligations
- Return ONLY valid JSON, no markdown fences, no extra text"""

MERGE_PROMPT = """You are a legal contract analyst. Given these extracted fragments from different parts of a contract, produce a unified contract analysis.

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
  }},
  "summary": "<4-5 sentence executive summary that covers ALL of the following: (1) what this contract does and its primary purpose, (2) who the parties are and their roles, (3) the key financial terms or obligations if present, (4) the contract duration and how it can be terminated, (5) the governing law/jurisdiction. If any element is absent from the contract, state that explicitly.>"
}}

Rules:
- Deduplicate party names (merge variants like 'ACME Corp' and 'Acme Corporation' → pick the most formal)
- Pick the most specific contract_type
- Resolve conflicting dates by picking the most credible occurrence
- Base the summary on the actual clause types and metadata present — do not fabricate terms not evidenced
- The summary must be substantive and complete — avoid vague phrases like 'various obligations'
- Return ONLY valid JSON, no markdown fences"""

RISK_ANALYSIS_PROMPT = """You are a senior legal risk analyst reviewing a contract for potential issues.

CONTRACT ANALYSIS SUMMARY:
{analysis_json}

Identify genuine risks and concerns. Pay particular attention to:
1. UNLIMITED LIABILITY — Is there a liability cap? If the contract has no liability limitation clause or the cap is absent/vague, flag as critical/high.
2. ONE-SIDED INDEMNIFICATION — Does only one party bear indemnification obligations? Flag if asymmetric.
3. VAGUE OR UNDEFINED TERMS — Are key terms like 'reasonable', 'material breach', or 'confidential information' left undefined or overly broad?
4. INADEQUATE NOTICE PERIODS — Are notice periods for termination, renewal opt-out, or dispute escalation too short (< 15 days) or absent?
5. MISSING LIQUIDATED DAMAGES — For contracts with delivery obligations, is there no penalty for non-performance?
6. UNILATERAL MODIFICATION RIGHTS — Can one party change terms without the other's consent?
7. IP OWNERSHIP AMBIGUITY — Is ownership of work product, inventions, or data clearly assigned?

Return a JSON object:
{{
  "risks": [
    {{
      "category": "<MUST be exactly one of: missing_clause, unfavorable_terms, ambiguous_language, compliance, financial, operational, data_privacy>",
      "severity": "<low|medium|high|critical>",
      "title": "<short specific risk title>",
      "description": "<what the risk is, why it matters, and what specific language (or absence of language) causes it>",
      "clause_reference": "<title of the related clause, or null if it is a missing clause>",
      "recommendation": "<concrete, actionable step to mitigate this risk — be specific>"
    }}
  ],
  "summary": "<3-4 sentence overall risk assessment: state the overall risk level, identify the 2-3 most significant risks, and give a clear recommendation on whether the contract is ready to sign or needs renegotiation>"
}}

Severity guidelines:
- critical: Exposes a party to unlimited liability, regulatory penalties, or fundamental agreement failure
- high: Significant commercial or legal exposure requiring attention before signing
- medium: Suboptimal terms that pose moderate risk if a dispute arises
- low: Minor gaps or standard imprecisions with limited practical impact

IMPORTANT:
- Only include risks that are genuinely present based on the contract content above
- If the contract is professionally drafted and a category has no real issue, do NOT fabricate a risk for it
- Return an empty "risks" array if the contract is well-drafted and no genuine issues are present
- Do not report the same issue under multiple categories
- Return ONLY valid JSON, no markdown fences"""

SUMMARY_PROMPT = """You are a legal assistant explaining a contract in plain English to a non-lawyer.

CONTRACT DETAILS:
{analysis_json}

RISK FINDINGS:
{risk_json}

Return a JSON object with EXACTLY these sections:
{{
  "executive_summary": "<2-3 sentence overview that anyone can understand — state what the contract is, who signed it, and what the most important thing to know is>",
  "what_this_does": "<3-4 sentence plain-English explanation: what is the purpose of this agreement, what does each party get, what are the main commitments, and how long does it last>",
  "obligations_by_party": {{
    "<party name>": ["<obligation 1 — be specific, include amounts/deadlines if present>", "<obligation 2>"]
  }},
  "key_dates": ["<important dates with full context — e.g., 'Contract expires on Dec 31, 2025 — must give 30 days notice to renew'>"],
  "watch_out_for": [
    "<IMPORTANT: Each item MUST reference the specific clause causing the concern. Format: '[Clause Name]: explanation in plain English that a non-lawyer understands. Example: '[Liability Cap Clause]: Your financial exposure is limited to $50,000 — even if you suffer much greater losses.'>"
  ],
  "action_items": [
    "<Each action item MUST start with one of: [URGENT], [BEFORE SIGNING], [WITHIN 30 DAYS], or [ONGOING]. Example: '[BEFORE SIGNING]: Negotiate the liability cap — the current $10,000 limit may not cover your actual losses.'>"
  ],
  "key_risks_plain": [
    "<Rewrite each HIGH or CRITICAL risk finding in plain English with zero legal jargon. Explain what could go wrong, why it matters to the person reading this, and what they can do about it. Example: 'The contract automatically renews every year — if you forget to cancel 30 days before the end date, you are locked in for another year and cannot get a refund.'>"
  ]
}}

Rules:
- Use simple, clear language — pretend you are explaining this to a friend, not a lawyer
- Be specific: reference actual clause names, dollar amounts, and deadlines from the contract
- Base everything on the content provided — do not fabricate terms or obligations not mentioned
- The key_risks_plain list should contain only HIGH and CRITICAL severity risks, rewritten accessibly
- If the answer cannot be found in the provided content, omit that item rather than guess
- Return ONLY valid JSON, no markdown fences"""


def _parse_json_response(text: str) -> dict:
    """Parse LLM response text as JSON, stripping markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove markdown code fences
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON from LLM response: %s...", cleaned[:200])
        return {}


class ContractAnalysisService:
    """Orchestrates two-pass contract extraction, risk analysis, and summaries."""

    def __init__(
        self,
        settings: Settings,
        vector_store_service: VectorStoreService,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._vs = vector_store_service
        self._session_factory = session_factory
        # Pass 1: clause extraction — uses LoRA (LocalLoRAProvider) when LLM_PROVIDER=local_lora,
        #         otherwise ChatOpenAI(gpt-4o-mini). Lazy-loaded on first use.
        self._analysis_llm = None
        # Pass 2: merge, risk, summary — always ChatOpenAI(gpt-4o-mini) for quality reasoning.
        self._merge_llm = None
        # Shared semaphore — limits Pass 1 to _PASS1_CONCURRENCY simultaneous LLM calls.
        self._pass1_semaphore = asyncio.Semaphore(_PASS1_CONCURRENCY)
        # Local concurrency semaphore — serialises local PEFT model inference to prevent GPU OOM/CPU thrashing.
        self._local_concurrency_semaphore = asyncio.Semaphore(1)

    @property
    def analysis_llm(self):
        """Pass 1 LLM: LoRA (local_lora provider) or ChatOpenAI(gpt-4o-mini)."""
        if self._analysis_llm is None:
            self._analysis_llm = get_analysis_llm(self._settings)
        return self._analysis_llm

    @property
    def llm(self):
        """Pass 2 LLM: always ChatOpenAI(gpt-4o-mini) for merge/risk/summary reasoning."""
        if self._merge_llm is None:
            self._merge_llm = get_llm(self._settings, json_mode=False)
        return self._merge_llm

    def _get_config(self, trace_name: str, metadata: dict | None = None) -> dict:
        cb = get_langfuse_callback(trace_name=trace_name, metadata=metadata or {})
        return {"callbacks": [cb]} if cb else {}

    async def _call_llm_with_retry(
        self,
        prompt: str,
        config: dict,
        max_retries: int = 3,
    ) -> str:
        """
        Invoke the LLM with exponential backoff on transient errors.

        Retries on openai.RateLimitError and openai.APITimeoutError (imported
        lazily to avoid a hard dependency at module load). Any other exception
        propagates immediately so callers can handle it.
        """
        import openai  # lazy import; available via langchain-openai

        last_exc: Exception = RuntimeError("LLM call did not execute")
        for attempt in range(max_retries):
            try:
                response = await self.llm.ainvoke(prompt, config=config)
                return response.content
            except (openai.RateLimitError, openai.APITimeoutError) as exc:
                wait = 2 ** attempt
                logger.warning(
                    "LLM transient error (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1, max_retries, wait, exc,
                )
                last_exc = exc
                await asyncio.sleep(wait)
            except Exception:
                raise
        raise last_exc

    # ------------------------------------------------------------------
    # Pass 1: Per-chunk extraction (parallel, rate-limited)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_document_hash(chunks: list[dict]) -> str:
        """
        Compute a stable SHA-256 content hash over all chunk raw_text values.

        Chunks are sorted by their text before hashing so insertion-order
        differences (e.g. re-ingesting in a different order) do not bust the
        cache incorrectly.  The hash covers content only — metadata changes
        (source_file rename) do not invalidate existing analyses.
        """
        texts = sorted(chunk.get("raw_text", chunk.get("content", "")) for chunk in chunks)
        digest = hashlib.sha256("\n---\n".join(texts).encode("utf-8")).hexdigest()
        return digest[:32]

    async def _extract_chunk(
        self, chunk_text: str, chunk_idx: int, project_name: str = ""
    ) -> dict:
        """
        Extract clauses and metadata from a single chunk (with rate-limit guard).

        Pass 1 uses get_analysis_llm():
          - LLM_PROVIDER=local_lora  → iakshayrathee/contractiq-lora-llama3 via LocalLoRAProvider
          - LLM_PROVIDER=openai      → ChatOpenAI(gpt-4o-mini)
        Pass 2 (merge/risk/summary) always uses ChatOpenAI via self.llm.
        """
        from app.llm.provider import LocalLoRAProvider

        async with self._pass1_semaphore:
            try:
                # --- Local LoRA path ---
                if isinstance(self.analysis_llm, LocalLoRAProvider):
                    async with self._local_concurrency_semaphore:
                        clauses = await self.analysis_llm.extract_clauses(chunk_text[:4000])
                    # Wrap in the same structure as the OpenAI path returns
                    return {"clauses": clauses, "metadata_fragments": {}, "key_dates": []}

                # --- OpenAI / Gemini path ---
                prompt = CHUNK_EXTRACTION_PROMPT.format(chunk_text=chunk_text[:4000])
                content = await self._call_llm_with_retry(
                    prompt,
                    self._get_config(
                        f"extract-chunk-{chunk_idx}",
                        metadata={"project": project_name, "chunk_index": chunk_idx},
                    ),
                )
                return _parse_json_response(content)
            except Exception as e:
                logger.error("Chunk %d extraction failed after retries: %s", chunk_idx, e)
                return {}

    async def _pass1_extract(self, collection_name: str, project_name: str = "") -> list[dict]:
        """Run pass 1 on all chunks in parallel (max _PASS1_CONCURRENCY at a time)."""
        # Eagerly load the analysis LLM model/adapter in a background thread to prevent blocking event loop
        if self._analysis_llm is None:
            from app.llm.provider import get_analysis_llm
            loop = asyncio.get_event_loop()
            self._analysis_llm = await loop.run_in_executor(None, get_analysis_llm, self._settings)

        # Wrap vector store list_chunks in thread executor
        loop = asyncio.get_event_loop()
        chunks = await loop.run_in_executor(None, self._vs.list_chunks, collection_name)
        if not chunks:
            return []

        tasks = [
            self._extract_chunk(chunk.get("raw_text", chunk.get("content", "")), i, project_name)
            for i, chunk in enumerate(chunks)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = []
        for r in results:
            if isinstance(r, dict) and r:
                valid.append(r)
            elif isinstance(r, Exception):
                logger.warning("Chunk extraction exception: %s", r)
        return valid

    # ------------------------------------------------------------------
    # Pass 2: Merge + meta-analysis
    # ------------------------------------------------------------------

    async def _pass2_merge(self, fragments: list[dict]) -> ContractAnalysis:
        """Merge per-chunk extractions into a unified analysis."""
        all_clauses: list[Clause] = []
        all_key_dates: list[str] = []

        for frag in fragments:
            for raw_clause in frag.get("clauses", []):
                try:
                    clause_type = raw_clause.get("clause_type", "other")
                    try:
                        ct = ClauseType(clause_type)
                    except ValueError:
                        ct = ClauseType.OTHER

                    obligations = []
                    for raw_ob in raw_clause.get("obligations", []):
                        try:
                            ob_type = ObligationType(raw_ob.get("type", "must"))
                        except ValueError:
                            ob_type = ObligationType.MUST
                        obligations.append(Obligation(
                            party=raw_ob.get("party", "Unknown"),
                            description=raw_ob.get("description", ""),
                            deadline=raw_ob.get("deadline"),
                            type=ob_type,
                        ))

                    all_clauses.append(Clause(
                        clause_type=ct,
                        title=raw_clause.get("title", "Untitled"),
                        text=raw_clause.get("text", ""),
                        section_reference=raw_clause.get("section_reference"),
                        obligations=obligations,
                    ))
                except Exception as e:
                    logger.warning("Failed to parse clause: %s", e)

            all_key_dates.extend(frag.get("key_dates", []))

        # Deduplicate clauses: primary key is clause_type (keep the longest text per
        # type so we preserve the most complete version). For OTHER clauses, fall
        # through to title-string deduplication so distinct "other" clauses are kept.
        best_by_type: dict[ClauseType, Clause] = {}
        other_clauses: list[Clause] = []
        for clause in all_clauses:
            if clause.clause_type == ClauseType.OTHER:
                other_clauses.append(clause)
            else:
                existing = best_by_type.get(clause.clause_type)
                if existing is None or len(clause.text) > len(existing.text):
                    best_by_type[clause.clause_type] = clause

        # Deduplicate OTHER clauses by title string
        seen_titles: set[str] = set()
        deduped_other: list[Clause] = []
        for clause in other_clauses:
            key = clause.title.lower().strip()
            if key not in seen_titles:
                seen_titles.add(key)
                deduped_other.append(clause)

        deduped_clauses: list[Clause] = list(best_by_type.values()) + deduped_other
        logger.debug(
            "Clause dedup: %d raw → %d unique (by type: %d, other: %d)",
            len(all_clauses), len(deduped_clauses), len(best_by_type), len(deduped_other),
        )

        # LLM merge for metadata + summary
        fragments_for_merge = [
            frag.get("metadata_fragments", {})
            for frag in fragments
            if frag.get("metadata_fragments")
        ]

        # Build a compact clause summary for context (type + title only — no full text)
        clauses_summary = "\n".join(
            f"- {c.clause_type.value}: {c.title}" for c in deduped_clauses
        ) or "(no clauses identified)"

        metadata = ContractMetadata()
        summary = ""

        if fragments_for_merge:
            prompt = MERGE_PROMPT.format(
                fragments_json=json.dumps(fragments_for_merge, indent=2),
                clauses_summary=clauses_summary,
            )
            try:
                content = await self._call_llm_with_retry(
                    prompt, self._get_config("merge-analysis")
                )
                merged = _parse_json_response(content)
                meta_raw = merged.get("metadata", {})
                metadata = ContractMetadata(
                    contract_type=meta_raw.get("contract_type", "unknown"),
                    parties=meta_raw.get("parties", []),
                    effective_date=meta_raw.get("effective_date"),
                    expiration_date=meta_raw.get("expiration_date"),
                    governing_law=meta_raw.get("governing_law"),
                    jurisdiction=meta_raw.get("jurisdiction"),
                )
                summary = merged.get("summary", "")
            except Exception as e:
                logger.error("Merge pass failed: %s", e)

        return ContractAnalysis(
            metadata=metadata,
            clauses=deduped_clauses,
            key_dates=list(set(all_key_dates)),
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Risk Analysis (hybrid: rules + LLM)
    # ------------------------------------------------------------------

    def _rule_based_risks(self, analysis: ContractAnalysis) -> tuple[list[RiskItem], list[str]]:
        """Deterministic rule-based risk checks."""
        risks: list[RiskItem] = []
        missing: list[str] = []
        clause_types_found = {c.clause_type for c in analysis.clauses}
        contract_type_lower = (analysis.metadata.contract_type or "").lower()

        # --- Core standard clauses (expected in virtually all contracts) ---
        core_expected = {
            ClauseType.CONFIDENTIALITY: ("Confidentiality clause", RiskSeverity.MEDIUM),
            ClauseType.TERMINATION: ("Termination clause", RiskSeverity.MEDIUM),
            ClauseType.GOVERNING_LAW: ("Governing law clause", RiskSeverity.MEDIUM),
            ClauseType.LIABILITY: ("Liability limitation clause", RiskSeverity.HIGH),
            ClauseType.DISPUTE_RESOLUTION: ("Dispute resolution clause", RiskSeverity.MEDIUM),
            ClauseType.INDEMNIFICATION: ("Indemnification clause", RiskSeverity.MEDIUM),
        }
        for ct, (label, severity) in core_expected.items():
            if ct not in clause_types_found:
                missing.append(label)
                risks.append(RiskItem(
                    category=RiskCategory.MISSING_CLAUSE,
                    severity=severity,
                    title=f"Missing {label}",
                    description=f"The contract does not contain a {label.lower()}. This is standard in most agreements and its absence creates legal exposure.",
                    recommendation=f"Add a {label.lower()} to clearly define each party's rights and limit exposure.",
                ))

        # --- Conditional clauses: IP ownership (tech/services contracts) ---
        tech_keywords = {"software", "saas", "technology", "service", "development", "consulting", "app", "platform"}
        is_tech_contract = any(kw in contract_type_lower for kw in tech_keywords)
        if is_tech_contract and ClauseType.INTELLECTUAL_PROPERTY not in clause_types_found:
            label = "Intellectual Property ownership clause"
            missing.append(label)
            risks.append(RiskItem(
                category=RiskCategory.MISSING_CLAUSE,
                severity=RiskSeverity.HIGH,
                title=f"Missing {label}",
                description=(
                    "This appears to be a technology or services contract but it lacks an explicit clause "
                    "defining who owns the work product, inventions, or developed software. "
                    "Without this, IP ownership defaults to the creator — which may not match the parties' intent."
                ),
                recommendation="Add an IP ownership and assignment clause specifying who owns all work product created under this contract.",
            ))

        # --- Conditional clauses: Payment terms (service/commercial contracts) ---
        commercial_keywords = {"service", "saas", "supply", "vendor", "purchase", "sale", "agreement", "consulting"}
        is_commercial = any(kw in contract_type_lower for kw in commercial_keywords)
        if is_commercial and ClauseType.PAYMENT not in clause_types_found:
            label = "Payment terms clause"
            missing.append(label)
            risks.append(RiskItem(
                category=RiskCategory.MISSING_CLAUSE,
                severity=RiskSeverity.HIGH,
                title=f"Missing {label}",
                description=(
                    "This appears to be a commercial or services contract but it contains no explicit payment "
                    "terms clause. The absence of payment schedules, amounts, and late-payment consequences "
                    "creates significant financial and enforcement risk."
                ),
                recommendation="Add a payment clause specifying amounts, due dates, payment method, and late-payment penalties.",
            ))

        # --- No expiration date AND no termination clause ---
        has_termination = ClauseType.TERMINATION in clause_types_found
        if not analysis.metadata.expiration_date and not has_termination:
            risks.append(RiskItem(
                category=RiskCategory.OPERATIONAL,
                severity=RiskSeverity.MEDIUM,
                title="No expiration date and no termination clause",
                description=(
                    "The contract specifies neither an end date nor a termination mechanism, "
                    "which may create indefinite obligations with no clear exit path."
                ),
                recommendation="Add an expiration date or a clear termination-for-convenience clause.",
            ))

        # --- Auto-renewal without notice period ---
        if ClauseType.AUTO_RENEWAL in clause_types_found:
            renewal_clauses = [c for c in analysis.clauses if c.clause_type == ClauseType.AUTO_RENEWAL]
            for rc in renewal_clauses:
                if "notice" not in rc.text.lower():
                    risks.append(RiskItem(
                        category=RiskCategory.UNFAVORABLE_TERMS,
                        severity=RiskSeverity.HIGH,
                        title="Auto-renewal without notice period",
                        description="An auto-renewal clause exists without a clear notice period for opting out. This can trap parties in unwanted contract extensions.",
                        clause_reference=rc.title,
                        recommendation="Add a minimum opt-out notice period (e.g., 30 days before renewal date) and require written notice.",
                    ))

        # --- Liability clause present but no cap amount detectable ---
        if ClauseType.LIABILITY in clause_types_found:
            liability_clauses = [c for c in analysis.clauses if c.clause_type == ClauseType.LIABILITY]
            cap_keywords = ["cap", "limit", "maximum", "aggregate", "shall not exceed", "not exceed"]
            for lc in liability_clauses:
                text_lower = lc.text.lower()
                has_cap = any(kw in text_lower for kw in cap_keywords)
                if not has_cap:
                    risks.append(RiskItem(
                        category=RiskCategory.FINANCIAL,
                        severity=RiskSeverity.HIGH,
                        title="Liability clause lacks a monetary cap",
                        description=(
                            "A liability clause exists but does not appear to specify a monetary cap or limit. "
                            "Without an explicit cap, one party may face unlimited financial exposure."
                        ),
                        clause_reference=lc.title,
                        recommendation="Add a specific monetary cap (e.g., 'liability shall not exceed the fees paid in the prior 12 months') to limit financial exposure.",
                    ))

        return risks, missing

    @staticmethod
    def _build_slim_analysis_json(analysis: ContractAnalysis) -> str:
        """
        Build a compact JSON representation of the analysis for LLM prompts.

        Sends metadata in full and truncates each clause's text to 500 characters
        (increased from 200) so the risk LLM has enough context to detect ambiguous
        language, unfavorable terms, and missing caps/notice periods.
        """
        slim = {
            "metadata": analysis.metadata.model_dump(),
            "summary": analysis.summary,
            "clauses": [
                {
                    "clause_type": c.clause_type.value,
                    "title": c.title,
                    "text_excerpt": c.text[:500],  # increased from 200 → 500
                    "section_reference": c.section_reference,
                    "obligations": [
                        {
                            "party": o.party,
                            "description": o.description,
                            "type": o.type.value,
                            "deadline": o.deadline,
                        }
                        for o in c.obligations
                    ],
                }
                for c in analysis.clauses
            ],
            "key_dates": analysis.key_dates,
        }
        return json.dumps(slim, indent=2)

    @staticmethod
    def _build_slim_risk_json(risk_report: RiskReport) -> str:
        """Build a compact risk summary for the summary prompt."""
        slim = {
            "overall_score": risk_report.overall_score,
            "risk_level": risk_report.risk_level,
            "missing_clauses": risk_report.missing_clauses,
            "risks": [
                {
                    "severity": r.severity.value,
                    "title": r.title,
                    "description": r.description[:200],
                }
                for r in risk_report.items
            ],
        }
        return json.dumps(slim, indent=2)

    async def _llm_risk_analysis(self, analysis: ContractAnalysis) -> list[RiskItem]:
        """LLM-based risk checks for nuanced issues."""
        prompt = RISK_ANALYSIS_PROMPT.format(
            analysis_json=self._build_slim_analysis_json(analysis)
        )
        try:
            content = await self._call_llm_with_retry(
                prompt, self._get_config("risk-analysis")
            )
            parsed = _parse_json_response(content)
            items = []
            for raw in parsed.get("risks", []):
                try:
                    items.append(RiskItem(
                        category=RiskCategory(raw.get("category", "unfavorable_terms")),
                        severity=RiskSeverity(raw.get("severity", "medium")),
                        title=raw.get("title", "Unknown Risk"),
                        description=raw.get("description", ""),
                        clause_reference=raw.get("clause_reference"),
                        recommendation=raw.get("recommendation", ""),
                    ))
                except (ValueError, Exception) as e:
                    logger.warning("Skipping invalid risk item: %s", e)
            return items
        except Exception as e:
            logger.error("LLM risk analysis failed: %s", e)
            return []

    async def _compute_risk_report(self, analysis: ContractAnalysis) -> RiskReport:
        """
        Hybrid risk scoring: rule-based (40%) + LLM (60%).

        Rule score (0–100):
          - Each missing standard clause (of 5): +16 pts
          - No expiration date AND no termination clause: +10 pts
          - Auto-renewal without notice: +20 pts
          (capped at 100)

        LLM score (0–100):
          - Uses severity distribution, not additive sum:
            LOW=10, MEDIUM=35, HIGH=65, CRITICAL=90
          - llm_score = max_severity * 0.6 + avg_severity * 0.4
          - Prevents score explosion: 5 MEDIUMs → score 35, not 75

        Floor guards:
          - ≥2 HIGH items  → final_score = max(final_score, 76)
          - ≥1 CRITICAL AND ≥2 HIGH → final_score = max(final_score, 91)
        """
        rule_risks, missing = self._rule_based_risks(analysis)
        llm_risks = await self._llm_risk_analysis(analysis)

        # Merge and deduplicate by title
        all_risks = rule_risks + llm_risks
        seen: set[str] = set()
        deduped: list[RiskItem] = []
        for r in all_risks:
            key = r.title.lower().strip()
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        # --- Rule-based score (normalized, not per-item additive) ---
        clause_types_found = {c.clause_type for c in analysis.clauses}
        expected_clause_types = {
            ClauseType.CONFIDENTIALITY,
            ClauseType.TERMINATION,
            ClauseType.GOVERNING_LAW,
            ClauseType.LIABILITY,
            ClauseType.DISPUTE_RESOLUTION,
        }
        missing_count = len(expected_clause_types - clause_types_found)
        missing_clause_penalty = missing_count * 16  # max 80 for all 5 missing

        has_termination = ClauseType.TERMINATION in clause_types_found
        no_exit_penalty = 10 if (not analysis.metadata.expiration_date and not has_termination) else 0

        auto_renewal_penalty = 0
        if ClauseType.AUTO_RENEWAL in clause_types_found:
            bad_renewals = [
                c for c in analysis.clauses
                if c.clause_type == ClauseType.AUTO_RENEWAL and "notice" not in c.text.lower()
            ]
            auto_renewal_penalty = 20 if bad_renewals else 0

        rule_score = min(100, missing_clause_penalty + no_exit_penalty + auto_renewal_penalty)
        logger.debug(
            "Rule score: missing_clauses=%d (penalty=%d), no_exit=%d, auto_renewal=%d → %d",
            missing_count, missing_clause_penalty, no_exit_penalty, auto_renewal_penalty, rule_score,
        )

        # --- LLM score (distribution-based) ---
        severity_values = {
            RiskSeverity.LOW: 10,
            RiskSeverity.MEDIUM: 35,
            RiskSeverity.HIGH: 65,
            RiskSeverity.CRITICAL: 90,
        }
        llm_severity_vals = [
            severity_values.get(r.severity, 10)
            for r in deduped
            if r not in rule_risks  # only LLM-sourced items drive the LLM score
        ]

        if llm_severity_vals:
            max_sev = max(llm_severity_vals)
            avg_sev = sum(llm_severity_vals) / len(llm_severity_vals)
            llm_score = int(max_sev * 0.6 + avg_sev * 0.4)
        else:
            llm_score = 0

        logger.debug(
            "LLM score: %d items, max_sev=%s, avg_sev=%.1f → %d",
            len(llm_severity_vals),
            max(llm_severity_vals) if llm_severity_vals else 0,
            sum(llm_severity_vals) / len(llm_severity_vals) if llm_severity_vals else 0.0,
            llm_score,
        )

        # --- Weighted blend ---
        # Use the max of: the blend, or the dominant single component.
        # This prevents the 40% near-zero rule_score from dragging down a real LLM score
        # (e.g., rule=0 + LLM finds MEDIUM → blend=21, but llm_score alone=30 → use 30).
        blended = round(0.4 * rule_score + 0.6 * llm_score)
        combined = max(rule_score, llm_score, blended)

        # --- Floor guards for severe contracts ---
        high_count = sum(1 for r in deduped if r.severity == RiskSeverity.HIGH)
        critical_count = sum(1 for r in deduped if r.severity == RiskSeverity.CRITICAL)
        if critical_count >= 1 and high_count >= 2:
            combined = max(combined, 91)
        elif high_count >= 2:
            combined = max(combined, 76)

        overall_score = min(100, max(0, combined))

        if overall_score <= 30:
            risk_level = "low"
        elif overall_score <= 55:
            risk_level = "medium"
        elif overall_score <= 75:
            risk_level = "high"
        else:
            risk_level = "critical"

        # Determine overall highest severity
        all_severities = [r.severity for r in deduped]
        if RiskSeverity.CRITICAL in all_severities:
            highest_sev = "critical"
        elif RiskSeverity.HIGH in all_severities:
            highest_sev = "high"
        elif RiskSeverity.MEDIUM in all_severities:
            highest_sev = "medium"
        elif RiskSeverity.LOW in all_severities:
            highest_sev = "low"
        else:
            highest_sev = "none"

        # Top contributors: highest-severity items first, capped at 5
        sorted_risks = sorted(
            deduped,
            key=lambda r: severity_values.get(r.severity, 0),
            reverse=True,
        )
        top_contributors = [r.title for r in sorted_risks[:5]]

        scoring_explanation = ScoringExplanation(
            rule_based_score=rule_score,
            llm_score=llm_score,
            combined_score=overall_score,
            missing_clause_penalty=missing_clause_penalty,
            highest_severity=highest_sev,
            top_contributors=top_contributors,
        )

        logger.info(
            "Risk score for analysis: rule=%d, llm=%d, combined=%d, level=%s",
            rule_score, llm_score, overall_score, risk_level,
        )

        return RiskReport(
            overall_score=overall_score,
            risk_level=risk_level,
            items=deduped,
            missing_clauses=missing,
            summary=f"Found {len(deduped)} risk items across {missing_count} missing clauses and {len(llm_risks)} LLM-identified issues. Overall risk level: {risk_level}.",
            scoring_explanation=scoring_explanation,
        )

    # ------------------------------------------------------------------
    # Plain-English Summary
    # ------------------------------------------------------------------

    async def _generate_summary(self, analysis: ContractAnalysis, risk_report: RiskReport) -> PlainSummary:
        """Generate a plain-english summary from structured analysis."""
        prompt = SUMMARY_PROMPT.format(
            analysis_json=self._build_slim_analysis_json(analysis),
            risk_json=self._build_slim_risk_json(risk_report),
        )
        try:
            content = await self._call_llm_with_retry(
                prompt, self._get_config("plain-summary")
            )
            parsed = _parse_json_response(content)
            return PlainSummary(
                executive_summary=parsed.get("executive_summary", ""),
                what_this_does=parsed.get("what_this_does", ""),
                obligations_by_party=parsed.get("obligations_by_party", {}),
                key_dates=parsed.get("key_dates", []),
                watch_out_for=parsed.get("watch_out_for", []),
                action_items=parsed.get("action_items", []),
                key_risks_plain=parsed.get("key_risks_plain", []),
            )
        except Exception as e:
            logger.error("Summary generation failed: %s", e)
            return PlainSummary(executive_summary="Summary generation failed.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_analysis(self, project_name: str, user_id: str | None = None) -> Optional[AnalysisRow]:
        """Get the latest analysis for a project."""
        async with self._session_factory() as session:
            query = (
                select(AnalysisRow)
                .join(ProjectRow)
                .where(ProjectRow.name.ilike(project_name))
            )
            if user_id is not None:
                # Only return analysis for projects owned by this user
                query = query.where(ProjectRow.user_id == user_id)
            
            result = await session.execute(
                query.order_by(AnalysisRow.created_at.desc()).limit(1)
            )
            return result.scalar_one_or_none()

    async def prepare_analysis(
        self, project_name: str, collection_name: str, project_id: str
    ) -> tuple[str, str]:
        """
        Prepare analysis by checking cache, validating input, and creating DB row.
        
        Returns:
            tuple[row_id, status]: The analysis row ID and initial status
                                   ("completed" if cached, "running" if new, "failed" if rejected)
        """
        loop = asyncio.get_event_loop()
        all_chunks = await loop.run_in_executor(None, self._vs.list_chunks, collection_name)
        doc_hash = self._compute_document_hash(all_chunks) if all_chunks else ""

        # Check cache
        if doc_hash:
            async with self._session_factory() as session:
                cached_result = await session.execute(
                    select(AnalysisRow)
                    .where(
                        AnalysisRow.project_id == project_id,
                        AnalysisRow.document_hash == doc_hash,
                        AnalysisRow.status == "completed",
                    )
                    .order_by(AnalysisRow.created_at.desc())
                    .limit(1)
                )
                cached_row = cached_result.scalar_one_or_none()

            if cached_row is not None:
                logger.info(
                    "Analysis cache HIT for project '%s' (hash=%s). "
                    "Returning existing row %s — no LLM calls made.",
                    project_name, doc_hash, cached_row.id,
                )
                return cached_row.id, "completed"

        # Input guardrails validation
        if self._settings.guardrails_enabled:
            combined_text = "\n".join(
                c.get("raw_text", c.get("content", "")) for c in all_chunks
            ) if all_chunks else ""
            input_check = validate_contract_input(combined_text)
            if not input_check.passed:
                logger.warning(
                    "Input guardrail rejected content for project '%s': %s",
                    project_name, input_check.reason,
                )
                # Store failure in a new row
                analysis_row = AnalysisRow(
                    project_id=project_id,
                    status="failed",
                    document_hash=doc_hash or None,
                    error=f"Input validation failed: {input_check.reason}",
                )
                async with self._session_factory() as session:
                    session.add(analysis_row)
                    await session.commit()
                    await session.refresh(analysis_row)
                return analysis_row.id, "failed"

        # Create running analysis row
        analysis_row = AnalysisRow(
            project_id=project_id,
            status="running",
            document_hash=doc_hash or None,
        )
        async with self._session_factory() as session:
            session.add(analysis_row)
            await session.commit()
            await session.refresh(analysis_row)
            row_id = analysis_row.id

        return row_id, "running"

    async def run_analysis_pipeline_from_row(
        self, row_id: str, project_name: str, collection_name: str
    ) -> None:
        """
        Execute the analysis pipeline for an existing row with status="running".
        
        This includes Pass 1, Pass 2, Risk, Summary, Guardrails, Judge, and DB updates.
        """
        loop = asyncio.get_event_loop()
        all_chunks = await loop.run_in_executor(None, self._vs.list_chunks, collection_name)

        guardrail_warnings: dict = {}
        judge_output: Optional[JudgeOutput] = None

        try:
            # Pass 1
            logger.info("Analysis pass 1: extracting from chunks in '%s'", collection_name)
            fragments = await self._pass1_extract(collection_name, project_name)
            chunk_count = len(all_chunks)

            if not fragments:
                raise RuntimeError("No content could be extracted from the document chunks.")

            # Pass 2
            logger.info("Analysis pass 2: merging %d fragments", len(fragments))
            analysis = await self._pass2_merge(fragments)

            # Risk analysis
            logger.info("Running risk analysis")
            risk_report = await self._compute_risk_report(analysis)

            # Plain-english summary
            logger.info("Generating plain-english summary")
            plain_summary = await self._generate_summary(analysis, risk_report)

            # --- Output guardrails: validate before storing ---
            if self._settings.guardrails_enabled:
                logger.info("Running output guardrails")
                source_chunks = [c.get("raw_text", c.get("content", "")) for c in all_chunks]
                output_guardrails = OutputGuardrails(self._settings)

                clause_guardrail = output_guardrails.validate_clauses(
                    clauses=[c.model_dump() for c in analysis.clauses],
                    source_chunks=source_chunks,
                )
                summary_guardrail = output_guardrails.validate_summary(
                    summary=plain_summary.model_dump(),
                    source_chunks=source_chunks,
                )
                risk_guardrail = output_guardrails.validate_risk_items(
                    risk_items=[r.model_dump() for r in risk_report.items],
                    source_chunks=source_chunks,
                )

                guardrail_warnings = {
                    "clauses": {
                        "passed": clause_guardrail.passed,
                        "confidence": clause_guardrail.confidence,
                        "hallucinations": clause_guardrail.hallucinations,
                        "unsafe_statements": clause_guardrail.unsafe_statements,
                    },
                    "summary": {
                        "passed": summary_guardrail.passed,
                        "confidence": summary_guardrail.confidence,
                        "hallucinations": summary_guardrail.hallucinations,
                        "warnings": summary_guardrail.warnings,
                    },
                    "risks": {
                        "passed": risk_guardrail.passed,
                        "confidence": risk_guardrail.confidence,
                        "hallucinations": risk_guardrail.hallucinations,
                    },
                    "overall_passed": clause_guardrail.passed and summary_guardrail.passed and risk_guardrail.passed,
                }

                if not guardrail_warnings["overall_passed"]:
                    logger.warning(
                        "Output guardrails flagged issues for project '%s': "
                        "clauses_passed=%s, summary_passed=%s, risks_passed=%s",
                        project_name,
                        guardrail_warnings["clauses"]["passed"],
                        guardrail_warnings["summary"]["passed"],
                        guardrail_warnings["risks"]["passed"],
                    )

            # --- LLM-as-Judge evaluation ---
            if self._settings.judge_enabled:
                logger.info("Running LLM-as-Judge evaluation")
                from app.services.judge_service import JudgeService
                judge_service = JudgeService(self._settings)
                source_chunks = [c.get("raw_text", c.get("content", "")) for c in all_chunks]
                judge_output = await judge_service.judge_analysis(
                    source_chunks=source_chunks,
                    analysis=analysis,
                    risk_report=risk_report,
                    plain_summary=plain_summary,
                    analysis_id=row_id,
                )

                if judge_output.flagged_for_review():
                    logger.warning(
                        "Analysis %s flagged for human review: judge_score=%.2f",
                        row_id, judge_output.overall_score,
                    )

            # Persist
            doc_hash = self._compute_document_hash(all_chunks) if all_chunks else ""
            async with self._session_factory() as session:
                row = await session.get(AnalysisRow, row_id)
                if row:
                    row.status = "completed"
                    row.analysis_json = analysis.model_dump_json()
                    row.risk_json = risk_report.model_dump_json()
                    row.summary_json = plain_summary.model_dump_json()
                    row.overall_risk_score = risk_report.overall_score
                    row.document_hash = doc_hash or None
                    row.completed_at = datetime.now(timezone.utc)

                    # Store judge / guardrail results
                    if judge_output is not None:
                        row.judge_json = judge_output.model_dump_json()
                        row.quality_score = judge_output.overall_score
                        row.flagged_for_review = judge_output.flagged_for_review()

                    if guardrail_warnings:
                        row.guardrail_warnings_json = json.dumps(guardrail_warnings)

                    await session.commit()

            # --- Per-run cost estimate log ---
            pass1_in = chunk_count * 1100
            pass1_out = chunk_count * 400
            fixed_in = 2950
            fixed_out = 1150
            total_in = pass1_in + fixed_in
            total_out = pass1_out + fixed_out
            est_cost = (total_in / 1_000_000 * 5.0) + (total_out / 1_000_000 * 15.0)
            model = self._settings.openai_model_analysis
            logger.info(
                "Analysis run complete: project=%s, chunks=%d, "
                "est_tokens_in=%d, est_tokens_out=%d, est_cost=$%.4f, "
                "model=%s (P1×%d + P2/Risk/Summary×3), risk_score=%d",
                project_name, chunk_count,
                total_in, total_out, est_cost,
                model, chunk_count,
                risk_report.overall_score,
            )

        except Exception as exc:
            logger.error("Analysis failed for '%s': %s", project_name, exc, exc_info=True)
            async with self._session_factory() as session:
                row = await session.get(AnalysisRow, row_id)
                if row:
                    row.status = "failed"
                    row.error = str(exc)
                    await session.commit()

    async def run_full_analysis(self, project_name: str, collection_name: str, project_id: str) -> str:
        """
        Run the full analysis pipeline (backwards-compatible method).
        
        Calls prepare_analysis, then if status is "running", executes run_analysis_pipeline_from_row synchronously.
        Returns the analysis row ID.
        """
        row_id, status = await self.prepare_analysis(project_name, collection_name, project_id)
        
        if status == "running":
            await self.run_analysis_pipeline_from_row(row_id, project_name, collection_name)
        
        return row_id
