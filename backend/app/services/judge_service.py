"""
LLM-as-Judge service for evaluating contract analysis quality.

Uses a structured output LLM (GPT-4o) to review:
  - Clause extraction (recall, precision)
  - Risk assessment (accuracy, severity calibration)
  - Summary faithfulness (accuracy, completeness)
  - Hallucinations, missing content, unsafe statements
"""

import json
import logging
from typing import Optional

from langchain_openai import ChatOpenAI

from app.config import Settings
from app.schemas.contract import ContractAnalysis, PlainSummary, RiskReport
from app.schemas.judge import JudgeOutput
from app.utils.langfuse_utils import get_langfuse_callback

logger = logging.getLogger(__name__)

# Maximum source text length sent to judge (prevent context overflow)
MAX_SOURCE_CHARS = 15000

# Judge system prompt
JUDGE_SYSTEM_PROMPT = """You are a senior legal contracts expert serving as an AI Quality Judge.
Your role is to rigorously evaluate contract analysis outputs for accuracy, completeness, and safety.

EVALUATION DIMENSIONS:

1. CLAUSE EXTRACTION RECALL (0.0-1.0)
   - Are all legally significant clauses identified?
   - Critical clause types: confidentiality, termination, indemnification, liability,
     governing_law, dispute_resolution, force_majeure, data_privacy, payment, non_compete
   - Score 0.0 = missed all important clauses, 1.0 = found everything

2. CLAUSE EXTRACTION PRECISION (0.0-1.0)
   - Are extracted clause texts accurate excerpts from the source?
   - Are clause type classifications correct?
   - Score 0.0 = all wrong, 1.0 = all correct

3. RISK ASSESSMENT ACCURACY (0.0-1.0)
   - Are identified risks genuine issues present in the contract?
   - Are severity levels appropriately calibrated?
   - Score 0.0 = no real risks found, 1.0 = all risks are genuine and well-calibrated

4. SUMMARY FAITHFULNESS (0.0-1.0)
   - Does the plain-English summary accurately represent the contract?
   - Are parties, obligations, dates, and terms faithfully conveyed?
   - Score 0.0 = completely inaccurate, 1.0 = perfectly faithful

5. SUMMARY COMPLETENESS (0.0-1.0)
   - Are all significant aspects of the contract covered?
   - Are key obligations by party captured?
   - Score 0.0 = missing everything important, 1.0 = comprehensive

HALLUCINATION DETECTION:
- Check if extracted clause text appears verbatim (or nearly) in source
- Check if summary claims are backed by source content
- Check if parties/dates/terms in summary exist in source

MISSING CONTENT:
- Identify critical clause types that were NOT found but should be present
- Note important obligations that were missed
- Note significant dates that were not captured

UNSAFE STATEMENTS:
- Flag any legally significant claims that contradict the source
- Flag any high-stakes legal conclusions that lack source support
- Mark severity: 'none', 'low', 'medium', 'high', 'critical'

Respond with a JSON object exactly matching the provided schema.
IMPORTANT: Return ONLY valid JSON, no markdown fences, no extra text."""

RAG_JUDGE_SYSTEM_PROMPT = """You are an AI Quality Judge evaluating a RAG (Retrieve-and-Generate) system.
Given a user Question, the retrieved Context, and the generated Answer, evaluate the following metrics on a scale of 0.0 to 1.0:

1. FAITHFULNESS (0.0-1.0)
   - Is the Answer entirely supported by the Context?
   - 1.0 = All claims can be inferred from Context. 0.0 = Entirely hallucinated.

2. ANSWER RELEVANCE (0.0-1.0)
   - Does the Answer directly address the Question?
   - 1.0 = Directly and fully answers. 0.0 = Completely off-topic or evasive.

3. CONTEXT PRECISION (0.0-1.0)
   - Are the provided Context chunks actually useful for answering the Question?
   - 1.0 = All chunks are highly relevant. 0.0 = No chunks are relevant.

4. CONTEXT RECALL (0.0-1.0)
   - Does the Context contain all the necessary information to fully answer the Question?
   - 1.0 = Complete information present. 0.0 = Missing essential information.

Return a JSON object exactly matching the schema requested.
IMPORTANT: Return ONLY valid JSON, no markdown fences, no extra text."""


JUDGE_USER_PROMPT_TEMPLATE = """Evaluate the following contract analysis:

## SOURCE DOCUMENT (excerpt):
{source_text}

---

## EXTRACTED CLAUSES:
{clauses_json}

---

## RISK REPORT:
{risk_json}

---

## PLAIN-ENGLISH SUMMARY:
{summary_json}

---

Provide your evaluation as a JSON object with this exact structure:
{{
  "overall_score": <float 0.0-1.0>,
  "overall_reasoning": "<2-3 sentence explanation of overall quality>",
  "clause_extraction": {{
    "recall": <float 0.0-1.0>,
    "precision": <float 0.0-1.0>,
    "notes": "<qualitative notes>"
  }},
  "risk_assessment": {{
    "accuracy": <float 0.0-1.0>,
    "severity_calibration": <float 0.0-1.0>,
    "notes": "<qualitative notes>"
  }},
  "summary_faithfulness": {{
    "faithfulness": <float 0.0-1.0>,
    "completeness": <float 0.0-1.0>,
    "notes": "<qualitative notes>"
  }},
  "hallucinations": {{
    "clause_hallucinations": ["<list of specific clause hallucinations>"],
    "summary_hallucinations": ["<list of specific summary hallucinations>"],
    "risk_hallucinations": ["<list of specific risk hallucinations>"]
  }},
  "missing_content": {{
    "missing_critical_clauses": ["<list of critical clause types not found>"],
    "missing_obligations": ["<list of important obligations not captured>"],
    "missing_dates": ["<list of important dates not captured>"]
  }},
  "unsafe_statements": {{
    "statements": ["<list of potentially unsafe statements>"],
    "severity": "<none|low|medium|high|critical>"
  }},
  "judge_model": "<model used>",
  "judged_at": "<ISO timestamp>"
}}"""

RAG_JUDGE_USER_PROMPT = """Evaluate this RAG interaction:

## QUESTION:
{question}

## CONTEXT:
{context}

## ANSWER:
{answer}

Provide your evaluation as a JSON object with this exact structure:
{{
  "faithfulness": <float 0.0-1.0>,
  "answer_relevance": <float 0.0-1.0>,
  "context_precision": <float 0.0-1.0>,
  "context_recall": <float 0.0-1.0>,
  "reasoning": "<2-3 sentence explanation of the scores>"
}}"""


class JudgeService:
    """
    LLM-as-Judge service that evaluates contract analysis quality.

    Runs after a full analysis is complete, producing:
    - Overall quality score (0.0-1.0)
    - Per-dimension scores (clause extraction, risk, summary)
    - Hallucination and missing content flags
    - Unsafe statement warnings
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._llm: Optional[ChatOpenAI] = None

    @property
    def llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=self._settings.openai_model_judge,
                temperature=0.0,
                api_key=self._settings.openai_api_key,
            )
        return self._llm

    def _build_source_text(self, source_chunks: list[str]) -> str:
        """Truncate source text to prevent context overflow."""
        combined = "\n\n---\n\n".join(source_chunks)
        if len(combined) <= MAX_SOURCE_CHARS:
            return combined
        return combined[:MAX_SOURCE_CHARS] + f"\n\n[... truncated {len(combined) - MAX_SOURCE_CHARS:,} remaining chars ...]"

    def _build_clauses_json(self, analysis: ContractAnalysis) -> str:
        """Build a compact JSON representation of clauses for the judge."""
        clauses = []
        for c in analysis.clauses:
            clauses.append({
                "clause_type": c.clause_type.value,
                "title": c.title,
                "text": c.text[:500],  # Truncate long texts
                "section_reference": c.section_reference,
                "obligation_count": len(c.obligations),
            })
        return json.dumps({"clauses": clauses}, indent=2)

    def _build_risk_json(self, risk_report: RiskReport) -> str:
        """Build a compact JSON representation of the risk report."""
        return json.dumps({
            "overall_score": risk_report.overall_score,
            "risk_level": risk_report.risk_level,
            "items": [
                {
                    "severity": r.severity.value,
                    "category": r.category.value,
                    "title": r.title,
                    "description": r.description[:200],
                }
                for r in risk_report.items
            ],
            "missing_clauses": risk_report.missing_clauses,
        }, indent=2)

    def _build_summary_json(self, summary: PlainSummary) -> str:
        """Build a compact JSON representation of the plain-English summary."""
        return json.dumps({
            "executive_summary": summary.executive_summary,
            "what_this_does": summary.what_this_does,
            "obligations_by_party": summary.obligations_by_party,
            "key_dates": summary.key_dates,
            "watch_out_for": summary.watch_out_for,
            "action_items": summary.action_items,
        }, indent=2)

    def _parse_judge_response(self, text: str) -> JudgeOutput:
        """Parse the judge's JSON response into a JudgeOutput."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        data = None
        try:
            data = json.loads(cleaned)
            return JudgeOutput(**data)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse judge JSON: %s\nResponse: %s...", e, cleaned[:500])
            return JudgeOutput(
                overall_score=0.0,
                overall_reasoning=f"Failed to parse judge response: {e}",
            )
        except Exception as e:
            logger.error("Failed to construct JudgeOutput: %s\nData: %s", e, str(data)[:500] if data else "N/A")
            return JudgeOutput(
                overall_score=0.0,
                overall_reasoning=f"Failed to construct judge output: {e}",
            )

    async def judge_analysis(
        self,
        source_chunks: list[str],
        analysis: ContractAnalysis,
        risk_report: RiskReport,
        plain_summary: PlainSummary,
        analysis_id: Optional[str] = None,
    ) -> JudgeOutput:
        """
        Run the judge evaluation on a completed contract analysis.

        Args:
            source_chunks: Raw text chunks from the source document
            analysis: The ContractAnalysis result
            risk_report: The RiskReport result
            plain_summary: The PlainSummary result
            analysis_id: Optional ID for tracking

        Returns:
            JudgeOutput with quality scores and flagged issues
        """
        source_text = self._build_source_text(source_chunks)
        clauses_json = self._build_clauses_json(analysis)
        risk_json = self._build_risk_json(risk_report)
        summary_json = self._build_summary_json(plain_summary)

        user_prompt = JUDGE_USER_PROMPT_TEMPLATE.format(
            source_text=source_text,
            clauses_json=clauses_json,
            risk_json=risk_json,
            summary_json=summary_json,
        )

        cb = get_langfuse_callback(trace_name="judge-evaluation")
        config = {"callbacks": [cb]} if cb else {}

        try:
            response = await self.llm.ainvoke(
                [{"role": "system", "content": JUDGE_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
                config=config,
            )
            judge_output = self._parse_judge_response(response.content)
            judge_output.judge_model = self._settings.openai_model_judge
            if analysis_id:
                judge_output.analysis_id = analysis_id

            logger.info(
                "Judge evaluation complete: analysis_id=%s, overall_score=%.2f, flagged=%s",
                analysis_id, judge_output.overall_score, judge_output.flagged_for_review(),
            )
            return judge_output

        except Exception as e:
            logger.error("Judge evaluation failed: %s", e, exc_info=True)
            return JudgeOutput(
                overall_score=0.0,
                overall_reasoning=f"Judge evaluation failed with error: {e}",
                judge_model=self._settings.openai_model_judge,
                analysis_id=analysis_id,
            )

    async def judge_rag_query(self, question: str, context_chunks: list[str], answer: str) -> dict:
        """
        Evaluate a single RAG query interaction for custom metrics:
        Faithfulness, Answer Relevance, Context Precision, and Context Recall.
        """
        context_text = "\n\n".join([f"Chunk {i+1}:\n{c}" for i, c in enumerate(context_chunks)])
        if len(context_text) > MAX_SOURCE_CHARS:
            context_text = context_text[:MAX_SOURCE_CHARS] + "\n\n[... truncated ...]"
            
        user_prompt = RAG_JUDGE_USER_PROMPT.format(
            question=question,
            context=context_text,
            answer=answer
        )
        
        cb = get_langfuse_callback(trace_name="judge-rag")
        config = {"callbacks": [cb]} if cb else {}
        
        try:
            response = await self.llm.ainvoke(
                [{"role": "system", "content": RAG_JUDGE_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
                config=config,
            )
            cleaned = response.content.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines)
                
            result = json.loads(cleaned)
            logger.info("RAG evaluation complete: faithfulness=%.2f, relevance=%.2f", 
                        result.get("faithfulness", 0), result.get("answer_relevance", 0))
            return result
        except Exception as e:
            logger.error("RAG judge evaluation failed: %s", e)
            return {
                "faithfulness": 0.0,
                "answer_relevance": 0.0,
                "context_precision": 0.0,
                "context_recall": 0.0,
                "reasoning": f"Evaluation failed: {str(e)}"
            }
