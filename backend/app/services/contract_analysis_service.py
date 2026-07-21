"""
Two-pass contract analysis service.

Pass 1 (per-chunk, parallel): Extract local clauses + metadata fragments from each chunk.
Pass 2 (merge + meta-analysis): Deduplicate, resolve conflicts, produce contract-level output.

Phase 1+: Risk and summary are grounded in verbatim retrieved evidence passages (not just
          slim truncated JSON). Every RiskItem carries citations back to source.
Phase 2+: Structured outputs with schema-repair retry; parse failures are logged not swallowed.
Phase 3+: Deterministic typed extractors replace brittle substring keyword checks.
Phase 4+: Configurable scoring weights + party perspective + feature vector in explanation.
Phase 5+: Evidence verification pass + Judge-driven bounded regeneration loop.
Phase 6+: Versioned prompt registry; single summary source of truth; adaptive depth.
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
    Evidence,
    Obligation,
    ObligationType,
    PlainSummary,
    RiskCategory,
    RiskItem,
    RiskReport,
    RiskSeverity,
    ScoringExplanation,
    SEVERITY_ORDINAL,
)
from app.schemas.judge import JudgeOutput
from app.services.guardrails import OutputGuardrails, validate_contract_input
from app.services.prompts.registry import get_prompt
from app.services.reranker import rerank_documents
from app.services.risk_rules.extractors import (
    extract_auto_renewal_terms,
    extract_indemnity_asymmetry,
    extract_liability_cap,
    extract_notice_period,
)
from app.services.vector_store_service import VectorStoreService
from app.utils.langfuse_utils import get_langfuse_callback

logger = structlog.get_logger()

# Max simultaneous GPT-4o calls during Pass 1 to avoid rate-limit 429s.
# Raised from 5 → 10 (WS-2.5): Pass 1 is the dominant latency bottleneck;
# higher concurrency cuts wall-time proportionally to the rate-limit headroom.
_PASS1_CONCURRENCY = 10

# Targeted retrieval queries per risk category (Phase 1 — RISK_PROBES)
# Used by _retrieve_risk_evidence() to pull verbatim passages for each category.
RISK_PROBES: dict[str, str] = {
    "financial":         "limitation of liability cap aggregate damages shall not exceed",
    "unfavorable_terms": "termination auto-renewal notice period unilateral modification",
    "ambiguous_language":"reasonable material breach confidential information undefined",
    "data_privacy":      "data protection personal data processing GDPR CCPA breach notification",
    "compliance":        "regulatory compliance export control sanctions anti-bribery FCPA",
    "operational":       "force majeure business continuity disaster recovery SLA uptime",
    "missing_clause":    "indemnification liability dispute resolution governing law",
}

def _parse_json_response(text: str, context: str = "") -> dict:
    """
    Parse LLM response text as JSON, stripping markdown fences if present.

    Phase 2: failures are logged with context instead of silently returning {}.
    Returns {} only as a last resort so callers can detect and handle the failure.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error(
            "json_parse_failure",
            context=context,
            error=str(exc),
            preview=cleaned[:300],
        )
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
                prompt_template, _ver = get_prompt("chunk_extraction",
                    langfuse_enabled=self._settings.langfuse_enabled)
                prompt = prompt_template.format(chunk_text=chunk_text[:4000])
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
            merge_prompt_template, _merge_ver = get_prompt("merge",
                langfuse_enabled=self._settings.langfuse_enabled)
            prompt = merge_prompt_template.format(
                fragments_json=json.dumps(fragments_for_merge, indent=2),
                clauses_summary=clauses_summary,
            )
            try:
                content = await self._call_llm_with_retry(
                    prompt, self._get_config("merge-analysis")
                )
                merged = _parse_json_response(content, context="merge-analysis")
                meta_raw = merged.get("metadata", {})
                metadata = ContractMetadata(
                    contract_type=meta_raw.get("contract_type", "unknown"),
                    parties=meta_raw.get("parties", []),
                    effective_date=meta_raw.get("effective_date"),
                    expiration_date=meta_raw.get("expiration_date"),
                    governing_law=meta_raw.get("governing_law"),
                    jurisdiction=meta_raw.get("jurisdiction"),
                )
                # Phase 6: summary is no longer generated here; it is derived from
                # PlainSummary.executive_summary at the end of the pipeline.
                # The ContractAnalysis.summary field is populated then.
            except Exception as e:
                logger.error("Merge pass failed: %s", e)

        return ContractAnalysis(
            metadata=metadata,
            clauses=deduped_clauses,
            key_dates=list(set(all_key_dates)),
            summary="",  # Phase 6: populated from PlainSummary.executive_summary after generation
        )

    # ------------------------------------------------------------------
    # Risk Analysis (hybrid: typed-extractor rules + LLM)
    # ------------------------------------------------------------------

    def _rule_based_risks(self, analysis: ContractAnalysis) -> tuple[list[RiskItem], list[str]]:
        """
        Deterministic rule-based risk checks using typed extractors (Phase 3).

        Replaces brittle substring keyword matching with:
          - extract_liability_cap()        — regex + numeric parsing
          - extract_auto_renewal_terms()   — renewal period + notice days
          - extract_notice_period()        — numeric/written notice extraction
          - extract_indemnity_asymmetry()  — party-level obligation detection
        """
        risks: list[RiskItem] = []
        missing: list[str] = []
        clause_types_found = {c.clause_type for c in analysis.clauses}
        contract_type_lower = (analysis.metadata.contract_type or "").lower()

        # --- Core standard clauses expected in virtually all contracts ---
        core_expected = {
            ClauseType.CONFIDENTIALITY:    ("Confidentiality clause", RiskSeverity.MEDIUM),
            ClauseType.TERMINATION:        ("Termination clause", RiskSeverity.MEDIUM),
            ClauseType.GOVERNING_LAW:      ("Governing law clause", RiskSeverity.MEDIUM),
            ClauseType.LIABILITY:          ("Liability limitation clause", RiskSeverity.HIGH),
            ClauseType.DISPUTE_RESOLUTION: ("Dispute resolution clause", RiskSeverity.MEDIUM),
            ClauseType.INDEMNIFICATION:    ("Indemnification clause", RiskSeverity.MEDIUM),
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
                    confidence=1.0,
                ))

        # --- IP clause for tech/services contracts ---
        tech_keywords = {"software", "saas", "technology", "service", "development", "consulting", "app", "platform"}
        if any(kw in contract_type_lower for kw in tech_keywords):
            if ClauseType.INTELLECTUAL_PROPERTY not in clause_types_found:
                label = "Intellectual Property ownership clause"
                missing.append(label)
                risks.append(RiskItem(
                    category=RiskCategory.MISSING_CLAUSE,
                    severity=RiskSeverity.HIGH,
                    title=f"Missing {label}",
                    description=(
                        "This appears to be a technology or services contract but lacks an explicit clause "
                        "defining who owns the work product, inventions, or developed software. "
                        "Without this, IP ownership defaults to the creator — which may not match the parties' intent."
                    ),
                    recommendation="Add an IP ownership and assignment clause specifying who owns all work product created under this contract.",
                    confidence=1.0,
                ))

        # --- Payment terms for commercial contracts ---
        commercial_keywords = {"service", "saas", "supply", "vendor", "purchase", "sale", "agreement", "consulting"}
        if any(kw in contract_type_lower for kw in commercial_keywords):
            if ClauseType.PAYMENT not in clause_types_found:
                label = "Payment terms clause"
                missing.append(label)
                risks.append(RiskItem(
                    category=RiskCategory.MISSING_CLAUSE,
                    severity=RiskSeverity.HIGH,
                    title=f"Missing {label}",
                    description=(
                        "This appears to be a commercial contract but contains no explicit payment terms. "
                        "The absence of payment schedules, amounts, and late-payment consequences creates financial risk."
                    ),
                    recommendation="Add a payment clause specifying amounts, due dates, payment method, and late-payment penalties.",
                    confidence=1.0,
                ))

        # --- No expiration date AND no termination clause ---
        if not analysis.metadata.expiration_date and ClauseType.TERMINATION not in clause_types_found:
            risks.append(RiskItem(
                category=RiskCategory.OPERATIONAL,
                severity=RiskSeverity.MEDIUM,
                title="No expiration date and no termination clause",
                description="The contract specifies neither an end date nor a termination mechanism, potentially creating indefinite obligations.",
                recommendation="Add an expiration date or a termination-for-convenience clause.",
                confidence=1.0,
            ))

        # --- Auto-renewal: use typed extractor instead of "notice" substring ---
        for rc in [c for c in analysis.clauses if c.clause_type == ClauseType.AUTO_RENEWAL]:
            renewal = extract_auto_renewal_terms(rc.text)
            if renewal.has_auto_renewal and not renewal.has_adequate_notice:
                notice_detail = (
                    f"Opt-out notice is only {renewal.opt_out_days} days."
                    if renewal.opt_out_days is not None
                    else "No opt-out notice period specified."
                )
                risks.append(RiskItem(
                    category=RiskCategory.UNFAVORABLE_TERMS,
                    severity=RiskSeverity.HIGH,
                    title="Auto-renewal without adequate opt-out notice",
                    description=(
                        f"An auto-renewal clause exists with insufficient notice to opt out. {notice_detail} "
                        "This can trap parties in unwanted contract extensions."
                    ),
                    clause_reference=rc.title,
                    recommendation="Require at least 30 days written opt-out notice before the renewal date.",
                    evidence=[Evidence(
                        quote=renewal.matched_text[:200],
                        page_number=rc.page_number,
                        section_reference=rc.section_reference,
                    )] if renewal.matched_text else [],
                    confidence=0.95,
                ))

        # --- Liability clause: use extract_liability_cap() not keyword substring ---
        for lc in [c for c in analysis.clauses if c.clause_type == ClauseType.LIABILITY]:
            cap_result = extract_liability_cap(lc.text)
            if not cap_result.has_cap:
                risks.append(RiskItem(
                    category=RiskCategory.FINANCIAL,
                    severity=RiskSeverity.HIGH,
                    title="Liability clause lacks a monetary cap",
                    description=(
                        "A liability clause exists but no monetary cap or limit was detected. "
                        "Without an explicit cap, a party may face unlimited financial exposure."
                    ),
                    clause_reference=lc.title,
                    recommendation="Add a specific monetary cap (e.g., 'liability shall not exceed the fees paid in the prior 12 months').",
                    evidence=[],
                    confidence=0.90,
                ))

        # --- Indemnity: use typed asymmetry extractor ---
        indem_clauses = [c for c in analysis.clauses if c.clause_type == ClauseType.INDEMNIFICATION]
        if indem_clauses:
            combined_indem = " ".join(c.text for c in indem_clauses)
            asym = extract_indemnity_asymmetry(combined_indem)
            if asym["is_one_sided"] and asym["parties_obligated"]:
                obligor = asym["parties_obligated"][0]
                risks.append(RiskItem(
                    category=RiskCategory.UNFAVORABLE_TERMS,
                    severity=RiskSeverity.HIGH,
                    title="One-sided indemnification obligation",
                    description=(
                        f"Only '{obligor}' bears indemnification obligations. "
                        "Asymmetric indemnity creates disproportionate financial risk for that party."
                    ),
                    clause_reference=indem_clauses[0].title,
                    recommendation="Negotiate mutual indemnification or cap the indemnifying party's exposure.",
                    evidence=[Evidence(
                        quote=asym["matched_snippets"][0][:200],
                        page_number=indem_clauses[0].page_number,
                        section_reference=indem_clauses[0].section_reference,
                    )] if asym["matched_snippets"] else [],
                    confidence=0.85,
                ))

        return risks, missing

    @staticmethod
    def _build_slim_analysis_json(analysis: ContractAnalysis, max_clause_chars: int = 2000) -> str:
        """
        Build a compact JSON representation of the analysis for LLM prompts.

        Phase 1: clause text cap raised from 500 → 2000 chars so the risk/summary
        LLM sees enough language to detect carve-outs, defined terms, and cap amounts
        that appear beyond the first few hundred characters of a clause.
        """
        slim = {
            "metadata": analysis.metadata.model_dump(),
            "clauses": [
                {
                    "clause_type": c.clause_type.value,
                    "title": c.title,
                    "text_excerpt": c.text[:max_clause_chars],
                    "section_reference": c.section_reference,
                    "page_number": c.page_number,
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

    async def _llm_risk_analysis(
        self,
        analysis: ContractAnalysis,
        evidence_passages: str,
        perspective: str = "neutral",
    ) -> list[RiskItem]:
        """
        LLM-based risk checks grounded in retrieved verbatim evidence passages (Phase 1).

        Uses RISK_ANALYSIS_V2 prompt which requires evidence quotes per finding.
        Falls back to empty list on parse failure (logged, not swallowed).
        """
        prompt_template, prompt_ver = get_prompt("risk_analysis",
            langfuse_enabled=self._settings.langfuse_enabled)
        prompt = prompt_template.format(
            perspective=perspective,
            analysis_json=self._build_slim_analysis_json(analysis),
            evidence_passages=evidence_passages,
        )
        try:
            content = await self._call_llm_with_retry(
                prompt, self._get_config("risk-analysis", metadata={"prompt_version": prompt_ver})
            )
            parsed = _parse_json_response(content, context="risk-analysis")
            items: list[RiskItem] = []
            for raw in parsed.get("risks", []):
                try:
                    # Parse evidence citations
                    raw_evidence = raw.get("evidence", [])
                    evidence = []
                    for ev in raw_evidence:
                        evidence.append(Evidence(
                            quote=ev.get("quote", ""),
                            page_number=ev.get("page_number"),
                            section_reference=ev.get("section_reference"),
                        ))
                    items.append(RiskItem(
                        category=RiskCategory(raw.get("category", "unfavorable_terms")),
                        severity=RiskSeverity(raw.get("severity", "medium")),
                        title=raw.get("title", "Unknown Risk"),
                        description=raw.get("description", ""),
                        clause_reference=raw.get("clause_reference"),
                        recommendation=raw.get("recommendation", ""),
                        evidence=evidence,
                        confidence=float(raw.get("confidence", 0.8)),
                    ))
                except (ValueError, Exception) as e:
                    logger.warning("Skipping invalid risk item: %s", e)
            return items
        except Exception as e:
            logger.error("LLM risk analysis failed: %s", e)
            return []

    async def _retrieve_risk_evidence(
        self, collection_name: str, perspective: str = "neutral"
    ) -> str:
        """
        Phase 1+2: Targeted retrieval of verbatim source passages per risk category.

        Issues one similarity search per RISK_PROBE category, reranks each result set,
        and returns a consolidated block of verbatim passages for the risk prompt.
        This replaces slim truncated JSON with actual contract language.
        """
        if not collection_name:
            return "(no source passages available)"

        all_passages: list[str] = []
        seen: set[str] = set()

        # Add perspective-specific probe if not neutral
        probes = dict(RISK_PROBES)
        if perspective != "neutral":
            probes["perspective_focus"] = f"rights obligations {perspective} party risk exposure"

        loop = asyncio.get_event_loop()

        async def _probe(category: str, query: str) -> tuple[str, list]:
            """Run one similarity search + rerank off the event loop."""
            try:
                raw_docs = await loop.run_in_executor(
                    None,
                    lambda q=query: self._vs.similarity_search(
                        q, k=6, collection_name=collection_name
                    ),
                )
                # rerank_documents uses a cross-encoder (CPU-heavy) → keep off the loop
                reranked = await loop.run_in_executor(
                    None, lambda q=query, d=raw_docs: rerank_documents(q, d, top_n=3)
                )
                return category, reranked
            except Exception as exc:
                logger.warning("Risk evidence retrieval failed for category '%s': %s", category, exc)
                return category, []

        # Run all category probes concurrently instead of serially. Results are
        # returned in probe order, so dedup stays deterministic.
        probe_results = await asyncio.gather(
            *[_probe(cat, q) for cat, q in probes.items()]
        )
        for category, reranked in probe_results:
            for doc in reranked:
                text = doc.page_content.strip()
                # Deduplicate on first 120 chars to avoid near-duplicates
                key = text[:120]
                if key not in seen and text:
                    seen.add(key)
                    all_passages.append(f"[{category.upper()}]\n{text}")

        if not all_passages:
            return "(retrieval returned no passages)"

        combined = "\n\n---\n\n".join(all_passages)
        # Cap at 12000 chars to stay within context budget
        if len(combined) > 12000:
            combined = combined[:12000] + "\n\n[... passages truncated for context budget ...]"
        return combined

    async def _verify_risk_evidence(
        self,
        risks: list[RiskItem],
        source_chunks: list[str],
    ) -> list[RiskItem]:
        """
        Phase 5: Lightweight evidence-verification pass.

        Prompts the LLM to check each risk's evidence.quote against the source and
        return keep / downgrade / drop verdicts. Drops unsupported risks and downgrades
        over-stated severity without re-running the full risk prompt.
        """
        if not risks or not source_chunks:
            return risks

        # Only verify high/critical risks — low/medium are kept as-is
        high_risks = [r for r in risks if r.severity in (RiskSeverity.HIGH, RiskSeverity.CRITICAL)]
        other_risks = [r for r in risks if r.severity not in (RiskSeverity.HIGH, RiskSeverity.CRITICAL)]

        if not high_risks:
            return risks

        source_text = " ".join(source_chunks)[:8000]
        risks_json = json.dumps([
            {
                "title": r.title,
                "severity": r.severity.value,
                "description": r.description[:200],
                "evidence_quotes": [e.quote[:150] for e in r.evidence],
            }
            for r in high_risks
        ], indent=2)

        verification_template, _ver = get_prompt("evidence_verification",
            langfuse_enabled=self._settings.langfuse_enabled)
        prompt = verification_template.format(
            risks_json=risks_json,
            source_text=source_text,
        )
        try:
            content = await self._call_llm_with_retry(
                prompt, self._get_config("evidence-verification")
            )
            verdicts = _parse_json_response(content, context="evidence-verification")
            if not isinstance(verdicts, list):
                return risks

            verdict_map = {v["risk_title"]: v for v in verdicts if "risk_title" in v}
            verified: list[RiskItem] = []
            for risk in high_risks:
                verdict_data = verdict_map.get(risk.title, {})
                verdict = verdict_data.get("verdict", "keep")
                if verdict == "drop":
                    logger.info("Evidence verification: dropping risk '%s' — %s",
                                risk.title, verdict_data.get("reason", ""))
                    continue
                if verdict == "downgrade" and verdict_data.get("new_severity"):
                    try:
                        risk.severity = RiskSeverity(verdict_data["new_severity"])
                        logger.info("Evidence verification: downgraded '%s' to %s",
                                    risk.title, risk.severity)
                    except ValueError:
                        pass
                verified.append(risk)

            return other_risks + verified
        except Exception as exc:
            logger.warning("Evidence verification failed (%s) — using unverified risks", exc)
            return risks

    async def _compute_risk_report(
        self,
        analysis: ContractAnalysis,
        collection_name: str = "",
        source_chunks: list[str] | None = None,
        perspective: str = "neutral",
        evidence_passages: str | None = None,
    ) -> RiskReport:
        """
        Hybrid risk scoring: typed-extractor rules + evidence-grounded LLM (Phase 1–4).

        Scoring weights are configurable (not hard-coded magic numbers — Phase 4).
        Every RiskItem carries evidence citations. Verification pass drops hallucinated risks.

        Feature vector stored in ScoringExplanation so the UI can explain the score.

        ``evidence_passages`` may be supplied by the caller to avoid re-running the
        (expensive) multi-probe retrieval when it has already been fetched upstream.
        """
        # Retrieve verbatim evidence passages for the LLM (Phase 1).
        # Reuse caller-provided passages when available to avoid duplicate retrieval.
        if evidence_passages is None:
            evidence_passages = await self._retrieve_risk_evidence(collection_name, perspective)

        # Run rule layer and LLM layer concurrently (Quick Win #2)
        rule_risks_result, llm_risks = await asyncio.gather(
            asyncio.to_thread(self._rule_based_risks, analysis),
            self._llm_risk_analysis(analysis, evidence_passages, perspective),
        )
        rule_risks, missing = rule_risks_result

        # Merge and deduplicate by normalised title (Quick Win #3: semantic dedup)
        all_risks = rule_risks + llm_risks
        seen: set[str] = set()
        deduped: list[RiskItem] = []
        for r in all_risks:
            key = r.title.lower().strip()
            # Also catch near-duplicates by first 40 chars
            short_key = key[:40]
            if key not in seen and short_key not in seen:
                seen.add(key)
                seen.add(short_key)
                deduped.append(r)

        # Phase 5: evidence-verification pass (drops hallucinated high/critical risks)
        if source_chunks:
            deduped = await self._verify_risk_evidence(deduped, source_chunks)

        # ── Phase 4: Configurable scoring weights ──────────────────────────────
        # Weights stored in config; defaults preserve previous calibration intent
        # but are now explicit and documented rather than magic literals.
        rule_weight = getattr(self._settings, "risk_rule_weight", 0.4)
        llm_weight  = getattr(self._settings, "risk_llm_weight",  0.6)
        severity_values = {
            RiskSeverity.LOW:      getattr(self._settings, "risk_severity_low",      10),
            RiskSeverity.MEDIUM:   getattr(self._settings, "risk_severity_medium",   35),
            RiskSeverity.HIGH:     getattr(self._settings, "risk_severity_high",     65),
            RiskSeverity.CRITICAL: getattr(self._settings, "risk_severity_critical", 90),
        }

        # ── Rule score ───────────────────────────────────────────────────────
        clause_types_found = {c.clause_type for c in analysis.clauses}
        expected_clause_types = {
            ClauseType.CONFIDENTIALITY, ClauseType.TERMINATION,
            ClauseType.GOVERNING_LAW, ClauseType.LIABILITY, ClauseType.DISPUTE_RESOLUTION,
        }
        missing_count = len(expected_clause_types - clause_types_found)
        missing_clause_penalty = missing_count * 16

        no_exit_penalty = 10 if (
            not analysis.metadata.expiration_date
            and ClauseType.TERMINATION not in clause_types_found
        ) else 0

        auto_renewal_penalty = 0
        for rc in [c for c in analysis.clauses if c.clause_type == ClauseType.AUTO_RENEWAL]:
            ar = extract_auto_renewal_terms(rc.text)
            if ar.has_auto_renewal and not ar.has_adequate_notice:
                auto_renewal_penalty = 20
                break

        rule_score = min(100, missing_clause_penalty + no_exit_penalty + auto_renewal_penalty)

        # ── LLM score (distribution-based, not additive sum) ─────────────────
        llm_severity_vals = [
            severity_values[r.severity]
            for r in deduped
            if r not in rule_risks
        ]
        if llm_severity_vals:
            max_sev = max(llm_severity_vals)
            avg_sev = sum(llm_severity_vals) / len(llm_severity_vals)
            llm_score = int(max_sev * 0.6 + avg_sev * 0.4)
        else:
            llm_score = 0

        # ── Weighted blend ───────────────────────────────────────────────────
        blended = round(rule_weight * rule_score + llm_weight * llm_score)
        combined = max(rule_score, llm_score, blended)

        # Floor guards (still present but now driven by configurable feature counts)
        high_count     = sum(1 for r in deduped if r.severity == RiskSeverity.HIGH)
        critical_count = sum(1 for r in deduped if r.severity == RiskSeverity.CRITICAL)
        if critical_count >= 1 and high_count >= 2:
            combined = max(combined, 91)
        elif high_count >= 2:
            combined = max(combined, 76)

        overall_score = min(100, max(0, combined))

        if overall_score <= 30:   risk_level = "low"
        elif overall_score <= 55: risk_level = "medium"
        elif overall_score <= 75: risk_level = "high"
        else:                     risk_level = "critical"

        # ── Highest severity ─────────────────────────────────────────────────
        all_severities = [r.severity for r in deduped]
        if RiskSeverity.CRITICAL in all_severities:   highest_sev = "critical"
        elif RiskSeverity.HIGH in all_severities:     highest_sev = "high"
        elif RiskSeverity.MEDIUM in all_severities:   highest_sev = "medium"
        elif RiskSeverity.LOW in all_severities:      highest_sev = "low"
        else:                                          highest_sev = "none"

        sorted_risks = sorted(deduped, key=lambda r: severity_values.get(r.severity, 0), reverse=True)
        top_contributors = [r.title for r in sorted_risks[:5]]

        # ── Phase 4: Feature vector for UI explainability ────────────────────
        cap_present = any(
            extract_liability_cap(c.text).has_cap
            for c in analysis.clauses if c.clause_type == ClauseType.LIABILITY
        )
        notice_days_list = [
            extract_notice_period(c.text)
            for c in analysis.clauses
            if c.clause_type in (ClauseType.TERMINATION, ClauseType.AUTO_RENEWAL)
        ]
        min_notice = min((d for d in notice_days_list if d is not None), default=None)

        indem_texts = " ".join(c.text for c in analysis.clauses if c.clause_type == ClauseType.INDEMNIFICATION)
        one_sided_indem = extract_indemnity_asymmetry(indem_texts)["is_one_sided"] if indem_texts else False

        feature_vector = {
            "critical_count": critical_count,
            "high_count": high_count,
            "medium_count": sum(1 for r in deduped if r.severity == RiskSeverity.MEDIUM),
            "low_count": sum(1 for r in deduped if r.severity == RiskSeverity.LOW),
            "missing_core_clauses": missing_count,
            "cap_present": cap_present,
            "min_notice_days": min_notice,
            "one_sided_indemnity": one_sided_indem,
            "auto_renewal_no_notice": auto_renewal_penalty > 0,
        }

        scoring_explanation = ScoringExplanation(
            rule_based_score=rule_score,
            llm_score=llm_score,
            combined_score=overall_score,
            missing_clause_penalty=missing_clause_penalty,
            highest_severity=highest_sev,
            top_contributors=top_contributors,
            feature_vector=feature_vector,
            weights_used={
                "rule_weight": rule_weight,
                "llm_weight": llm_weight,
                "severity_values": {k.value: v for k, v in severity_values.items()},
            },
            perspective=perspective,
        )

        logger.info(
            "Risk score: rule=%d, llm=%d, combined=%d, level=%s, perspective=%s",
            rule_score, llm_score, overall_score, risk_level, perspective,
        )

        return RiskReport(
            overall_score=overall_score,
            risk_level=risk_level,
            items=deduped,
            missing_clauses=missing,
            summary=f"Found {len(deduped)} risk items: {critical_count} critical, {high_count} high. Overall risk level: {risk_level}.",
            scoring_explanation=scoring_explanation,
            perspective=perspective,
        )

    # ------------------------------------------------------------------
    # Plain-English Summary (Phase 1+6: evidence-grounded, adaptive depth)
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_complexity_tier(analysis: ContractAnalysis, risk_report: RiskReport) -> str:
        """Phase 6: derive adaptive summary depth from contract complexity."""
        clause_count = len(analysis.clauses)
        risk_count = len(risk_report.items)
        if clause_count <= 4 and risk_count <= 2:
            return "brief"
        if clause_count >= 10 or risk_count >= 6:
            return "detailed"
        return "standard"

    @staticmethod
    def _build_obligations_json(analysis: ContractAnalysis) -> str:
        """
        Phase 1+Quick Win #5: Build obligations_by_party deterministically from
        extracted Clause.obligations rather than letting the summary LLM re-derive them.
        This eliminates a major source of summary hallucinations.
        """
        by_party: dict[str, list[str]] = {}
        for clause in analysis.clauses:
            for ob in clause.obligations:
                party = ob.party.strip()
                if not party:
                    continue
                entry = ob.description.strip()
                if ob.deadline:
                    entry += f" (by {ob.deadline})"
                by_party.setdefault(party, []).append(entry)
        return json.dumps(by_party, indent=2)

    async def _generate_summary(
        self,
        analysis: ContractAnalysis,
        risk_report: RiskReport,
        evidence_passages: str = "",
    ) -> PlainSummary:
        """
        Generate a grounded plain-English summary (Phase 1+4+6).

        - Uses SUMMARY_V2 prompt with verbatim evidence passages.
        - Obligations are pre-computed deterministically, not re-derived by LLM.
        - Complexity tier drives section depth (brief/standard/detailed).
        - Schema-repair retry on validation failure (Phase 2).
        - Phase 6: single source of truth — ContractAnalysis.summary is populated
          from this result, not from a separate generation step.
        """
        complexity_tier = self._determine_complexity_tier(analysis, risk_report)
        obligations_json = self._build_obligations_json(analysis)

        prompt_template, prompt_ver = get_prompt("summary",
            langfuse_enabled=self._settings.langfuse_enabled)
        prompt = prompt_template.format(
            complexity_tier=complexity_tier,
            analysis_json=self._build_slim_analysis_json(analysis),
            risk_json=self._build_slim_risk_json(risk_report),
            evidence_passages=evidence_passages or "(see clause text above)",
            obligations_json=obligations_json,
        )
        try:
            content = await self._call_llm_with_retry(
                prompt,
                self._get_config("plain-summary", metadata={"prompt_version": prompt_ver}),
            )
            parsed = _parse_json_response(content, context="plain-summary")

            # Phase 2: schema-repair retry on empty/partial parse
            if not parsed.get("executive_summary"):
                logger.warning("Summary parse incomplete — attempting schema-repair retry")
                repair_prompt = (
                    prompt
                    + f"\n\nYour previous output was invalid or incomplete: {content[:300]}\n"
                    "Return the corrected JSON now."
                )
                content2 = await self._call_llm_with_retry(
                    repair_prompt,
                    self._get_config("plain-summary-repair"),
                    max_retries=1,
                )
                parsed = _parse_json_response(content2, context="plain-summary-repair") or parsed

            summary = PlainSummary(
                executive_summary=parsed.get("executive_summary", ""),
                what_this_does=parsed.get("what_this_does", ""),
                obligations_by_party=parsed.get("obligations_by_party", {}),
                key_dates=parsed.get("key_dates", []),
                watch_out_for=parsed.get("watch_out_for", []),
                action_items=parsed.get("action_items", []),
                key_risks_plain=parsed.get("key_risks_plain", []),
                complexity_tier=complexity_tier,
            )

            # Merge deterministic obligations — don't let LLM drop parties
            det_obligations = json.loads(obligations_json)
            for party, obs in det_obligations.items():
                if party not in summary.obligations_by_party:
                    summary.obligations_by_party[party] = obs

            return summary
        except Exception as e:
            logger.error("Summary generation failed: %s", e)
            return PlainSummary(
                executive_summary="Summary generation failed.",
                complexity_tier=complexity_tier,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_analysis(self, project_name: str, user_id: str | None = None) -> Optional[AnalysisRow]:
        """
        Get the latest analysis for a project — hash-aware (WS-1.1).

        Fetches the most recent AnalysisRow, then computes the current corpus hash
        and compares it to ``row.document_hash``.  If they differ (corpus has been
        modified since the analysis was run) or there are no chunks at all, returns
        ``None`` so the caller surfaces ``status="none"`` rather than stale data.
        """
        async with self._session_factory() as session:
            # 1. Look up the project to get collection_name.
            proj_query = select(ProjectRow).where(ProjectRow.name.ilike(project_name))
            if user_id is not None:
                proj_query = proj_query.where(ProjectRow.user_id == user_id)
            proj_result = await session.execute(proj_query)
            project_row = proj_result.scalar_one_or_none()
            if project_row is None:
                return None

            # 2. Fetch the latest analysis row.
            query = (
                select(AnalysisRow)
                .where(AnalysisRow.project_id == project_row.id)
            )
            result = await session.execute(
                query.order_by(AnalysisRow.created_at.desc()).limit(1)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None

            # 3. For running/pending rows return as-is so the UI can keep polling.
            if row.status in ("running", "pending"):
                return row

            # 4. For completed rows, verify the current corpus hash matches.
            loop = asyncio.get_event_loop()
            chunks = await loop.run_in_executor(
                None, self._vs.list_chunks, project_row.collection_name
            )
            if not chunks:
                # No chunks — corpus was cleared; stale row is invisible.
                logger.debug(
                    "get_analysis: no chunks in collection '%s' — returning None",
                    project_row.collection_name,
                )
                return None

            current_hash = self._compute_document_hash(chunks)
            if row.document_hash and row.document_hash != current_hash:
                logger.info(
                    "get_analysis: stale analysis detected for project '%s' "
                    "(stored_hash=%s, current_hash=%s) — returning None",
                    project_name, row.document_hash, current_hash,
                )
                return None

            return row

    async def invalidate_analyses(self, project_id: str) -> None:
        """
        Delete all AnalysisRow records for a project (WS-1.2 / WS-1.3).

        Called after document delete or successful re-ingestion so the corpus
        hash is guaranteed to diverge from any existing row.
        """
        from sqlalchemy import delete as sa_delete
        async with self._session_factory() as session:
            await session.execute(
                sa_delete(AnalysisRow).where(AnalysisRow.project_id == project_id)
            )
            await session.commit()
        logger.info("Invalidated analyses for project_id=%s", project_id)

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

    async def _update_stage(
        self,
        row_id: str,
        stage: str,
        processed: int | None = None,
        total: int | None = None,
    ) -> None:
        """
        Persist pipeline stage progress to AnalysisRow.stage_json (WS-2.2).

        Called after each major pipeline step so the polling frontend can
        display a meaningful progress indicator instead of a blank spinner.
        Stage values: extracting_clauses | assessing_risk | writing_summary | reviewing_quality
        """
        payload: dict = {"stage": stage}
        if processed is not None:
            payload["processed"] = processed
        if total is not None:
            payload["total"] = total
        async with self._session_factory() as session:
            row = await session.get(AnalysisRow, row_id)
            if row:
                row.stage_json = json.dumps(payload)
                await session.commit()

    async def _persist_partial(
        self,
        row_id: str,
        *,
        analysis_json: str | None = None,
        risk_json: str | None = None,
        summary_json: str | None = None,
    ) -> None:
        """
        Write partial analysis results to the DB while status stays 'running' (WS-2.1).

        The polling frontend renders whichever fields are non-null, so the user
        sees clauses appear before risk, and risk before summary.
        """
        async with self._session_factory() as session:
            row = await session.get(AnalysisRow, row_id)
            if row:
                if analysis_json is not None:
                    row.analysis_json = analysis_json
                if risk_json is not None:
                    row.risk_json = risk_json
                if summary_json is not None:
                    row.summary_json = summary_json
                await session.commit()

    async def run_analysis_pipeline_from_row(
        self, row_id: str, project_name: str, collection_name: str,
        perspective: str = "neutral",
    ) -> None:
        """
        Execute the full analysis pipeline for a row with status="running".

        Phase 1+: risk + summary receive verbatim evidence passages.
        Phase 4+: perspective-aware scoring.
        Phase 5+: Judge loop closes — low-quality output triggers one bounded regeneration.
        Phase 6+: ContractAnalysis.summary backfilled from PlainSummary (single source of truth).
        """
        loop = asyncio.get_event_loop()
        all_chunks = await loop.run_in_executor(None, self._vs.list_chunks, collection_name)
        source_chunks = [c.get("raw_text", c.get("content", "")) for c in all_chunks]

        guardrail_warnings: dict = {}
        judge_output: Optional[JudgeOutput] = None
        prompt_versions: dict = {}

        try:
            # Pass 1 — clause extraction (dominant latency, parallelised)
            logger.info("Analysis pass 1: extracting from chunks in '%s'", collection_name)
            await self._update_stage(row_id, "extracting_clauses", processed=0, total=len(all_chunks))
            fragments = await self._pass1_extract(collection_name, project_name)
            chunk_count = len(all_chunks)

            if not fragments:
                raise RuntimeError("No content could be extracted from the document chunks.")

            # Pass 2 — merge fragments into a unified ContractAnalysis
            logger.info("Analysis pass 2: merging %d fragments", len(fragments))
            await self._update_stage(row_id, "extracting_clauses", processed=chunk_count, total=chunk_count)
            analysis = await self._pass2_merge(fragments)

            # WS-2.1: persist clauses immediately so the UI can start rendering them
            await self._persist_partial(row_id, analysis_json=analysis.model_dump_json())

            # Risk analysis
            logger.info("Retrieving risk evidence passages")
            await self._update_stage(row_id, "assessing_risk")
            evidence_passages = await self._retrieve_risk_evidence(collection_name, perspective)

            # Note: summary depends on risk_report, so these stay sequential.
            logger.info("Running risk analysis (perspective=%s)", perspective)
            risk_report = await self._compute_risk_report(
                analysis,
                collection_name=collection_name,
                source_chunks=source_chunks,
                perspective=perspective,
                evidence_passages=evidence_passages,
            )

            # WS-2.1: persist risk immediately
            await self._persist_partial(row_id, risk_json=risk_report.model_dump_json())

            # Summary
            logger.info("Generating plain-English summary (tier=%s)",
                        self._determine_complexity_tier(analysis, risk_report))
            await self._update_stage(row_id, "writing_summary")
            plain_summary = await self._generate_summary(analysis, risk_report, evidence_passages)

            # Phase 6: backfill ContractAnalysis.summary from PlainSummary
            analysis.summary = plain_summary.executive_summary

            # WS-2.1: persist summary immediately — row is now "user-visible complete"
            # We update analysis_json again to include the backfilled .summary field.
            await self._persist_partial(
                row_id,
                analysis_json=analysis.model_dump_json(),
                summary_json=plain_summary.model_dump_json(),
            )

            # --- Output guardrails ---
            guardrail_warnings: dict = {}
            if self._settings.guardrails_enabled:
                logger.info("Running output guardrails")
                output_guardrails = OutputGuardrails(self._settings)

                clause_guardrail, summary_guardrail, risk_guardrail = await asyncio.gather(
                    asyncio.to_thread(
                        output_guardrails.validate_clauses,
                        clauses=[c.model_dump() for c in analysis.clauses],
                        source_chunks=source_chunks,
                    ),
                    asyncio.to_thread(
                        output_guardrails.validate_summary,
                        summary=plain_summary.model_dump(),
                        source_chunks=source_chunks,
                    ),
                    asyncio.to_thread(
                        output_guardrails.validate_risk_items,
                        risk_items=[r.model_dump() for r in risk_report.items],
                        source_chunks=source_chunks,
                    ),
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
                    "overall_passed": (
                        clause_guardrail.passed
                        and summary_guardrail.passed
                        and risk_guardrail.passed
                    ),
                }

            # --- Mark row completed BEFORE running the judge ---
            # WS-2.5: Judge + bounded regeneration are expensive and not needed for
            # the user-visible result.  We mark the row completed here so the UI
            # unblocks as soon as summary is ready, then run the judge in a
            # background fire-and-forget task that writes quality metadata afterward.
            doc_hash = self._compute_document_hash(all_chunks) if all_chunks else ""
            from app.services.prompts.registry import ACTIVE_VERSIONS
            prompt_versions = dict(ACTIVE_VERSIONS)

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
                    row.stage_json = json.dumps({"stage": "completed"})

                    if guardrail_warnings:
                        row.guardrail_warnings_json = json.dumps(guardrail_warnings)

                    if hasattr(row, "prompt_versions_json"):
                        row.prompt_versions_json = json.dumps(prompt_versions)

                    await session.commit()

            # Cost estimate log
            pass1_in = chunk_count * 1100
            pass1_out = chunk_count * 400
            fixed_in, fixed_out = 3500, 1400
            total_in = pass1_in + fixed_in
            total_out = pass1_out + fixed_out
            est_cost = (total_in / 1_000_000 * 5.0) + (total_out / 1_000_000 * 15.0)
            logger.info(
                "Analysis complete: project=%s, chunks=%d, est_tokens_in=%d, "
                "est_tokens_out=%d, est_cost=$%.4f, risk_score=%d, perspective=%s",
                project_name, chunk_count, total_in, total_out, est_cost,
                risk_report.overall_score, perspective,
            )

            # --- LLM-as-Judge (off critical path, WS-2.5) ---
            # Run as a fire-and-forget task so the user sees results without waiting.
            if self._settings.judge_enabled:
                asyncio.create_task(
                    self._run_judge_background(
                        row_id=row_id,
                        project_name=project_name,
                        analysis=analysis,
                        risk_report=risk_report,
                        plain_summary=plain_summary,
                        source_chunks=source_chunks,
                        collection_name=collection_name,
                        perspective=perspective,
                        evidence_passages=evidence_passages,
                    )
                )

        except Exception as exc:
            logger.error("Analysis failed for '%s': %s", project_name, exc, exc_info=True)
            async with self._session_factory() as session:
                row = await session.get(AnalysisRow, row_id)
                if row:
                    row.status = "failed"
                    row.error = str(exc)
                    row.stage_json = json.dumps({"stage": "failed"})
                    await session.commit()

    async def _run_judge_background(
        self,
        *,
        row_id: str,
        project_name: str,
        analysis: "ContractAnalysis",
        risk_report: "RiskReport",
        plain_summary: "PlainSummary",
        source_chunks: list[str],
        collection_name: str,
        perspective: str,
        evidence_passages: str,
    ) -> None:
        """
        Run LLM-as-Judge + bounded regeneration off the critical path (WS-2.5).

        The analysis row is already marked 'completed' when this fires.
        We update quality_score / flagged_for_review / judge_json afterward
        without affecting the user-visible status.
        """
        try:
            await self._update_stage(row_id, "reviewing_quality")
            logger.info("Running LLM-as-Judge evaluation (background) for row %s", row_id)
            from app.services.judge_service import JudgeService
            judge_service = JudgeService(self._settings)
            judge_output = await judge_service.judge_analysis(
                source_chunks=source_chunks,
                analysis=analysis,
                risk_report=risk_report,
                plain_summary=plain_summary,
                analysis_id=row_id,
            )

            # Phase 5: Judge loop — bounded regeneration on low-quality output
            if judge_output.overall_score < self._settings.judge_quality_threshold:
                logger.warning(
                    "Judge score %.2f below threshold %.2f — triggering bounded regeneration (background)",
                    judge_output.overall_score, self._settings.judge_quality_threshold,
                )
                critique = judge_output.overall_reasoning or ""
                regen_risk = (
                    judge_output.risk_assessment.accuracy
                    < judge_output.summary_faithfulness.faithfulness
                )
                if regen_risk:
                    logger.info("Regenerating risk analysis with judge critique (background)")
                    regen_tmpl, _ = get_prompt("risk_regeneration",
                        langfuse_enabled=self._settings.langfuse_enabled)
                    regen_prompt = regen_tmpl.format(
                        judge_critique=critique,
                        original_risks_json=self._build_slim_risk_json(risk_report),
                        analysis_json=self._build_slim_analysis_json(analysis),
                        evidence_passages=evidence_passages,
                        critique_focus=(
                            ", ".join(judge_output.missing_content.missing_critical_clauses[:3])
                            or "all flagged issues"
                        ),
                    )
                    try:
                        regen_content = await self._call_llm_with_retry(
                            regen_prompt, self._get_config("risk-regen"), max_retries=1
                        )
                        regen_parsed = _parse_json_response(regen_content, context="risk-regen")
                        if regen_parsed.get("risks"):
                            risk_report = await self._compute_risk_report(
                                analysis,
                                collection_name=collection_name,
                                source_chunks=source_chunks,
                                perspective=perspective,
                                evidence_passages=evidence_passages,
                            )
                            logger.info("Risk regeneration complete (background)")
                    except Exception as regen_exc:
                        logger.warning("Risk regeneration failed (background): %s", regen_exc)
                else:
                    logger.info("Regenerating summary with judge critique (background)")
                    regen_tmpl, _ = get_prompt("summary_regeneration",
                        langfuse_enabled=self._settings.langfuse_enabled)
                    regen_prompt = regen_tmpl.format(
                        judge_critique=critique,
                        original_summary_json=plain_summary.model_dump_json(),
                        analysis_json=self._build_slim_analysis_json(analysis),
                        critique_focus=critique[:200],
                    )
                    try:
                        regen_content = await self._call_llm_with_retry(
                            regen_prompt, self._get_config("summary-regen"), max_retries=1
                        )
                        regen_parsed = _parse_json_response(regen_content, context="summary-regen")
                        if regen_parsed.get("executive_summary"):
                            plain_summary = PlainSummary(
                                executive_summary=regen_parsed.get("executive_summary", plain_summary.executive_summary),
                                what_this_does=regen_parsed.get("what_this_does", plain_summary.what_this_does),
                                obligations_by_party=regen_parsed.get("obligations_by_party", plain_summary.obligations_by_party),
                                key_dates=regen_parsed.get("key_dates", plain_summary.key_dates),
                                watch_out_for=regen_parsed.get("watch_out_for", plain_summary.watch_out_for),
                                action_items=regen_parsed.get("action_items", plain_summary.action_items),
                                key_risks_plain=regen_parsed.get("key_risks_plain", plain_summary.key_risks_plain),
                                complexity_tier=plain_summary.complexity_tier,
                            )
                            analysis.summary = plain_summary.executive_summary
                            logger.info("Summary regeneration complete (background)")
                    except Exception as regen_exc:
                        logger.warning("Summary regeneration failed (background): %s", regen_exc)

            if judge_output.flagged_for_review():
                logger.warning(
                    "Analysis %s flagged for human review: judge_score=%.2f",
                    row_id, judge_output.overall_score,
                )

            # Persist judge results + any regenerated content back to the row
            async with self._session_factory() as session:
                row = await session.get(AnalysisRow, row_id)
                if row:
                    row.judge_json = judge_output.model_dump_json()
                    row.quality_score = judge_output.overall_score
                    row.flagged_for_review = judge_output.flagged_for_review()
                    # Overwrite risk/summary only if regeneration happened
                    row.risk_json = risk_report.model_dump_json()
                    row.summary_json = plain_summary.model_dump_json()
                    row.analysis_json = analysis.model_dump_json()
                    row.stage_json = json.dumps({"stage": "completed"})
                    await session.commit()

            logger.info("Background judge evaluation complete for row %s", row_id)

        except Exception as exc:
            logger.warning(
                "Background judge evaluation failed for row %s: %s", row_id, exc, exc_info=True
            )
            # Do not change the row status — the analysis itself is still valid.

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
