"""
Eval runner: executes test cases against the contract analysis pipeline
and produces structured EvalResult outputs.

Usage:
    # Run all cases in a dataset
    results = await run_evals(dataset, contract_service, judge_service, guardrails)

    # Run a single case
    result = await run_single_eval(case, contract_service, judge_service, guardrails)

    # Aggregate results
    summary = aggregate_results(results)
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.evals.dataset import ContractType, Difficulty, EvalCase, EvalDataset, EvalResult
from app.schemas.judge import JudgeOutput
from app.services.contract_analysis_service import ContractAnalysisService
from app.services.guardrails import OutputGuardrails
from app.services.judge_service import JudgeService

logger = logging.getLogger(__name__)

# Quality thresholds
JUDGE_SCORE_THRESHOLD = 0.7
CLAUSE_RECALL_THRESHOLD = 0.6
CLAUSE_PRECISION_THRESHOLD = 0.6


def _normalize_clause_type(clause_type_str: str) -> str:
    """Normalize a clause type string to match ClauseType enum values."""
    ct = clause_type_str.lower().strip().replace(" ", "_").replace("-", "_")
    return ct


def _compute_severity_calibration_error(
    predicted_risks: list,
    expected_severity: Optional[str],
) -> Optional[float]:
    """
    Phase 0: severity-calibration MAE.

    Computes the absolute ordinal difference between the predicted highest severity
    and the ground-truth expected_severity. Returns None if no ground truth available.
    Scale: 0 = perfect, 3 = maximum (e.g. predicted LOW vs actual CRITICAL).
    """
    from app.schemas.contract import RiskSeverity, SEVERITY_ORDINAL

    if not expected_severity:
        return None

    if not predicted_risks:
        # Predicted nothing → worst case MAE against the expected
        try:
            expected_ord = SEVERITY_ORDINAL[RiskSeverity(expected_severity)]
        except (ValueError, KeyError):
            return None
        return float(expected_ord - 1)  # distance from "low" (ordinal 1)

    # Find highest predicted severity
    highest_predicted = max(
        (r.severity if hasattr(r, "severity") else RiskSeverity(r) for r in predicted_risks),
        key=lambda s: SEVERITY_ORDINAL.get(s if isinstance(s, RiskSeverity) else RiskSeverity(s), 0),
        default=None,
    )
    if highest_predicted is None:
        return None

    try:
        pred_ord = SEVERITY_ORDINAL[highest_predicted if isinstance(highest_predicted, RiskSeverity)
                                    else RiskSeverity(highest_predicted)]
        exp_ord  = SEVERITY_ORDINAL[RiskSeverity(expected_severity)]
        return float(abs(pred_ord - exp_ord))
    except (ValueError, KeyError):
        return None


def _compute_citation_validity_rate(
    risk_items: list,
    source_text: str,
    min_overlap: float = 0.8,
) -> float:
    """
    Phase 1: citation-validity rate.

    For each HIGH/CRITICAL risk, checks that at least one evidence quote is found
    (fuzzy substring match with overlap >= min_overlap) in the source text.
    Returns fraction of high/critical risks that have a valid citation.
    """
    import re

    from app.schemas.contract import RiskSeverity

    high_critical = [
        r for r in risk_items
        if hasattr(r, "severity") and r.severity in (RiskSeverity.HIGH, RiskSeverity.CRITICAL)
    ]
    if not high_critical:
        return 1.0  # no high/critical risks to validate

    source_lower = source_text.lower()
    valid = 0
    for risk in high_critical:
        evidence = getattr(risk, "evidence", [])
        if not evidence:
            continue
        found_valid = False
        for ev in evidence:
            quote = getattr(ev, "quote", "") or ""
            if not quote:
                continue
            # Sliding-window word overlap check
            quote_words = set(re.findall(r"\b[a-z]{3,}\b", quote.lower()))
            if not quote_words:
                continue
            source_words = set(re.findall(r"\b[a-z]{3,}\b", source_lower))
            overlap = len(quote_words & source_words) / len(quote_words)
            if overlap >= min_overlap:
                found_valid = True
                break
        if found_valid:
            valid += 1

    return valid / len(high_critical)
    """
    Compute clause extraction metrics for a single eval case.

    Returns:
        (true_positives, false_positives, false_negatives, recall, precision, f1)
    """
    extracted = {_normalize_clause_type(c) for c in extracted_clauses}
    expected = {_normalize_clause_type(c) for c in expected_clauses}
    unexpected = {_normalize_clause_type(c) for c in unexpected_clauses}

    true_positives = list(extracted & expected)
    false_positives = list(extracted - expected - unexpected)
    false_negatives = list(expected - extracted)

    tp = len(true_positives)
    fp = len(false_positives)
    fn = len(false_negatives)

    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return true_positives, false_positives, false_negatives, recall, precision, f1


def _compute_risk_metrics(
    extracted_risks: list[str],
    expected_risks: list[str],
) -> tuple[float, float]:
    """Compute risk extraction metrics."""
    extracted = {r.lower().strip() for r in extracted_risks}
    expected = {r.lower().strip() for r in expected_risks}

    if not expected:
        # No expected risks — check we didn't find any (true negative for no-risk case)
        precision = 1.0 if len(extracted) == 0 else 0.0
        recall = 1.0  # Can't fail recall if nothing expected
    else:
        tp = len(extracted & expected)
        fp = len(extracted - expected)
        fn = len(expected - extracted)
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

    return recall, precision


def _compute_summary_metrics(
    summary_text: str,
    expected_keywords: list[str],
    excluded_keywords: list[str],
) -> tuple[bool, bool, float]:
    """Compute summary quality metrics based on keyword presence."""
    summary_lower = summary_text.lower()

    expected_found = sum(1 for kw in expected_keywords if kw.lower() in summary_lower)
    keyword_ratio = expected_found / len(expected_keywords) if expected_keywords else 1.0

    has_excluded = any(kw.lower() in summary_lower for kw in excluded_keywords)

    contains_keywords = expected_found >= len(expected_keywords) * 0.5 if expected_keywords else True

    return contains_keywords, has_excluded, keyword_ratio


async def run_single_eval(
    case: EvalCase,
    analysis_service: ContractAnalysisService,
    judge_service: Optional[JudgeService],
    guardrails: Optional[OutputGuardrails],
    source_chunks: list[str],
) -> EvalResult:
    """
    Run a single eval case through the full analysis + judge pipeline.

    Args:
        case: The eval case with ground truth
        analysis_service: Service to run contract analysis
        judge_service: Optional LLM-as-Judge service
        guardrails: Optional output guardrails
        source_chunks: Pre-extracted text chunks from the source document

    Returns:
        EvalResult with all metrics
    """
    model_version = os.getenv("MODEL_VERSION", "unknown")
    pipeline_version = os.getenv("PIPELINE_VERSION", "unknown")

    try:
        # Build a synthetic fragment from the eval case source text
        # for Pass 2 consumption. In production evals, chunks would come
        # from the vector store; here we simulate the Pass 1 output.
        chunk_text = case.source_text
        # Truncate to the same limit used in _extract_chunk
        chunk_text = chunk_text[:4000]

        # Run Pass 1 extraction on the single eval chunk
        fragment = await analysis_service._extract_chunk(chunk_text, 0, project_name=f"eval-{case.id}")

        if not fragment or not fragment.get("clauses"):
            # Analysis failed to extract anything
            return EvalResult(
                case_id=case.id,
                model_version=model_version,
                pipeline_version=pipeline_version,
                error="No clauses extracted from eval case",
                passed=False,
                pass_reason="Failed to extract any clauses from source text",
            )

        # Pass 2 merge
        analysis = await analysis_service._pass2_merge([fragment])

        # Risk analysis
        risk_report = await analysis_service._compute_risk_report(analysis)

        # Plain-English summary
        plain_summary = await analysis_service._generate_summary(analysis, risk_report)

        # --- Compute ground truth metrics ---
        extracted_clause_types = [c.clause_type.value for c in analysis.clauses]
        tp, fp, fn, recall, precision, f1 = _compute_clause_metrics(
            extracted_clause_types,
            case.expected_clauses,
            case.unexpected_clauses,
        )

        risk_titles = [r.title.lower() for r in risk_report.items]
        risk_recall, risk_precision = _compute_risk_metrics(risk_titles, case.expected_risks)

        # Phase 0: severity calibration
        sev_mae = _compute_severity_calibration_error(
            risk_report.items, case.expected_severity
        )
        risk_band_correct: Optional[bool] = None
        if case.expected_risk_level:
            risk_band_correct = (risk_report.risk_level == case.expected_risk_level)

        # Phase 1: citation validity rate
        citation_validity = _compute_citation_validity_rate(
            risk_report.items, case.source_text
        )

        # Predicted severity / band for reporting
        from app.schemas.contract import RiskSeverity
        predicted_severity: Optional[str] = None
        if risk_report.items:
            from app.schemas.contract import SEVERITY_ORDINAL
            highest = max(
                risk_report.items,
                key=lambda r: SEVERITY_ORDINAL.get(r.severity, 0),
                default=None,
            )
            if highest:
                predicted_severity = highest.severity.value

        # Summary metrics
        summary_text = plain_summary.executive_summary + " " + plain_summary.what_this_does
        sum_contains, sum_has_excluded, sum_kw_ratio = _compute_summary_metrics(
            summary_text,
            case.expected_summary_keywords,
            case.excluded_summary_keywords,
        )

        # Guardrail validation
        guardrail_passed = True
        guardrail_confidence = 1.0
        guardrail_hallucinations: list[str] = []
        guardrail_unsafe_statements: list[str] = []

        if guardrails is not None:
            clause_result = guardrails.validate_clauses(
                clauses=[c.model_dump() for c in analysis.clauses],
                source_chunks=source_chunks,
            )
            summary_result = guardrails.validate_summary(
                summary=plain_summary.model_dump(),
                source_chunks=source_chunks,
            )
            risk_result = guardrails.validate_risk_items(
                risk_items=[r.model_dump() for r in risk_report.items],
                source_chunks=source_chunks,
            )
            guardrail_passed = clause_result.passed and summary_result.passed and risk_result.passed
            guardrail_confidence = (
                clause_result.confidence + summary_result.confidence + risk_result.confidence
            ) / 3
            guardrail_hallucinations = (
                clause_result.hallucinations
                + summary_result.hallucinations
                + risk_result.hallucinations
            )
            guardrail_unsafe_statements = (
                clause_result.unsafe_statements
            )

        # Judge evaluation
        judge_overall = 0.0
        j_clause_recall = 0.0
        j_clause_precision = 0.0
        j_risk_accuracy = 0.0
        j_summary_faithfulness = 0.0
        hall_count = 0
        missing_count = 0
        unsafe_severity = "none"

        if judge_service is not None:
            judge_output = await judge_service.judge_analysis(
                source_chunks=source_chunks,
                analysis=analysis,
                risk_report=risk_report,
                plain_summary=plain_summary,
                analysis_id=None,
            )
            judge_overall = judge_output.overall_score
            j_clause_recall = judge_output.clause_extraction.recall
            j_clause_precision = judge_output.clause_extraction.precision
            j_risk_accuracy = judge_output.risk_assessment.accuracy
            j_summary_faithfulness = judge_output.summary_faithfulness.faithfulness
            hall_count = (
                len(judge_output.hallucinations.clause_hallucinations)
                + len(judge_output.hallucinations.summary_hallucinations)
                + len(judge_output.hallucinations.risk_hallucinations)
            )
            missing_count = len(judge_output.missing_content.missing_critical_clauses)
            unsafe_severity = judge_output.unsafe_statements.severity

        # Determine overall pass/fail
        passed = (
            judge_overall >= JUDGE_SCORE_THRESHOLD
            and recall >= CLAUSE_RECALL_THRESHOLD
            and precision >= CLAUSE_PRECISION_THRESHOLD
            and guardrail_passed
            and hall_count == 0
        )
        pass_reason = ""
        if passed:
            pass_reason = f"All checks passed (judge={judge_overall:.2f}, clause_f1={f1:.2f})"
        elif judge_overall < JUDGE_SCORE_THRESHOLD:
            pass_reason = f"Judge score {judge_overall:.2f} below threshold {JUDGE_SCORE_THRESHOLD}"
        elif recall < CLAUSE_RECALL_THRESHOLD:
            pass_reason = f"Clause recall {recall:.2f} below threshold {CLAUSE_RECALL_THRESHOLD}"
        elif guardrail_hallucinations:
            pass_reason = f"Guardrails detected {len(guardrail_hallucinations)} hallucination(s)"

        return EvalResult(
            case_id=case.id,
            model_version=model_version,
            pipeline_version=pipeline_version,
            # Clause metrics
            clauses_extracted=extracted_clause_types,
            clause_true_positives=tp,
            clause_false_positives=fp,
            clause_false_negatives=fn,
            clause_recall=recall,
            clause_precision=precision,
            clause_f1=f1,
            # Risk metrics
            risks_extracted=risk_titles,
            risk_recall=risk_recall,
            risk_precision=risk_precision,
            # Phase 0: severity calibration + band accuracy
            predicted_severity=predicted_severity,
            predicted_risk_level=risk_report.risk_level,
            severity_calibration_error=sev_mae,
            risk_band_correct=risk_band_correct,
            # Phase 1: citation validity
            citation_validity_rate=citation_validity,
            # Summary metrics
            summary_contains_keywords=sum_contains,
            summary_has_excluded_keywords=sum_has_excluded,
            summary_keyword_match_ratio=sum_kw_ratio,
            # Judge scores
            judge_overall=judge_overall,
            judge_clause_recall=j_clause_recall,
            judge_clause_precision=j_clause_precision,
            judge_risk_accuracy=j_risk_accuracy,
            judge_summary_faithfulness=j_summary_faithfulness,
            hallucination_count=hall_count,
            missing_clause_count=missing_count,
            unsafe_statement_severity=unsafe_severity,
            # Guardrail results
            guardrail_passed=guardrail_passed,
            guardrail_confidence=guardrail_confidence,
            guardrail_hallucinations=guardrail_hallucinations,
            guardrail_unsafe_statements=guardrail_unsafe_statements,
            # Overall
            passed=passed,
            pass_reason=pass_reason,
            error=None,
        )


async def run_evals(
    dataset: EvalDataset,
    analysis_service: ContractAnalysisService,
    judge_service: Optional[JudgeService] = None,
    guardrails: Optional[OutputGuardrails] = None,
) -> list[EvalResult]:
    """
    Run all eval cases in a dataset.

    Args:
        dataset: The EvalDataset to run
        analysis_service: ContractAnalysisService instance
        judge_service: Optional JudgeService for LLM-as-Judge evaluation
        guardrails: Optional OutputGuardrails for output validation

    Returns:
        List of EvalResult, one per case
    """
    results = []
    total = len(dataset.cases)

    logger.info("Starting evals: dataset=%s, cases=%d", dataset.name, total)

    for i, case in enumerate(dataset.cases):
        logger.info("Running eval %d/%d: case_id=%s", i + 1, total, case.id)

        # For eval mode, we need the source chunks from the case
        # In a real setup, the eval runner would have pre-extracted these
        source_chunks = [case.source_text]

        result = await run_single_eval(
            case=case,
            analysis_service=analysis_service,
            judge_service=judge_service,
            guardrails=guardrails,
            source_chunks=source_chunks,
        )
        results.append(result)

    logger.info("Evals complete: %d/%d passed", sum(1 for r in results if r.passed), total)
    return results


def aggregate_results(results: list[EvalResult]) -> dict:
    """
    Aggregate a list of EvalResults into summary statistics.

    Returns:
        Dictionary with aggregate metrics suitable for logging or reporting
    """
    total = len(results)
    if total == 0:
        return {"total": 0}

    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    # Compute averages over non-error results
    valid_results = [r for r in results if r.error is None]

    avg_judge_overall = sum(r.judge_overall for r in valid_results) / len(valid_results) if valid_results else 0.0
    avg_clause_recall = sum(r.clause_recall for r in valid_results) / len(valid_results) if valid_results else 0.0
    avg_clause_precision = sum(r.clause_precision for r in valid_results) / len(valid_results) if valid_results else 0.0
    avg_clause_f1 = sum(r.clause_f1 for r in valid_results) / len(valid_results) if valid_results else 0.0
    avg_risk_recall = sum(r.risk_recall for r in valid_results) / len(valid_results) if valid_results else 0.0
    avg_guardrail_confidence = sum(r.guardrail_confidence for r in valid_results) / len(valid_results) if valid_results else 0.0

    hallucination_total = sum(r.hallucination_count for r in valid_results)
    missing_clause_total = sum(r.missing_clause_count for r in valid_results)

    # Phase 0: new metrics
    sev_errors = [r.severity_calibration_error for r in valid_results if r.severity_calibration_error is not None]
    avg_severity_mae = sum(sev_errors) / len(sev_errors) if sev_errors else None

    band_results = [r.risk_band_correct for r in valid_results if r.risk_band_correct is not None]
    risk_band_accuracy = sum(band_results) / len(band_results) if band_results else None

    # Phase 1: citation validity
    avg_citation_validity = (
        sum(r.citation_validity_rate for r in valid_results) / len(valid_results)
        if valid_results else 1.0
    )

    # Per-contract-type breakdown
    by_contract_type: dict[str, dict] = {}
    for result in valid_results:
        case_id = result.case_id
        # Find the case to get contract type (would be better to store this in result)
        # For now, derive from case_id prefix
        contract_type = case_id.split("_")[0] if "_" in case_id else "unknown"
        if contract_type not in by_contract_type:
            by_contract_type[contract_type] = {"total": 0, "passed": 0, "avg_judge": 0.0}
        by_contract_type[contract_type]["total"] += 1
        if result.passed:
            by_contract_type[contract_type]["passed"] += 1
        by_contract_type[contract_type]["avg_judge"] += result.judge_overall

    for ct_data in by_contract_type.values():
        if ct_data["total"] > 0:
            ct_data["avg_judge"] /= ct_data["total"]
            ct_data["pass_rate"] = ct_data["passed"] / ct_data["total"]

    # Per-difficulty breakdown
    by_difficulty: dict[str, dict] = {}
    for result in valid_results:
        case_id = result.case_id
        difficulty = case_id.split("_")[1] if len(case_id.split("_")) > 1 else "unknown"
        if difficulty not in by_difficulty:
            by_difficulty[difficulty] = {"total": 0, "passed": 0, "avg_judge": 0.0}
        by_difficulty[difficulty]["total"] += 1
        if result.passed:
            by_difficulty[difficulty]["passed"] += 1
        by_difficulty[difficulty]["avg_judge"] += result.judge_overall

    for diff_data in by_difficulty.values():
        if diff_data["total"] > 0:
            diff_data["avg_judge"] /= diff_data["total"]
            diff_data["pass_rate"] = diff_data["passed"] / diff_data["total"]

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "total_cases": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / total if total > 0 else 0.0,
        "avg_judge_overall": round(avg_judge_overall, 3),
        "avg_clause_recall": round(avg_clause_recall, 3),
        "avg_clause_precision": round(avg_clause_precision, 3),
        "avg_clause_f1": round(avg_clause_f1, 3),
        "avg_risk_recall": round(avg_risk_recall, 3),
        "avg_guardrail_confidence": round(avg_guardrail_confidence, 3),
        "total_hallucinations": hallucination_total,
        "total_missing_clauses": missing_clause_total,
        # Phase 0 metrics
        "avg_severity_mae": round(avg_severity_mae, 3) if avg_severity_mae is not None else None,
        "risk_band_accuracy": round(risk_band_accuracy, 3) if risk_band_accuracy is not None else None,
        # Phase 1 metrics
        "avg_citation_validity_rate": round(avg_citation_validity, 3),
        "by_contract_type": by_contract_type,
        "by_difficulty": by_difficulty,
        "has_low_judge_scores": avg_judge_overall < JUDGE_SCORE_THRESHOLD,
        "has_poor_clause_recall": avg_clause_recall < CLAUSE_RECALL_THRESHOLD,
        "has_poor_clause_precision": avg_clause_precision < CLAUSE_PRECISION_THRESHOLD,
    }


def save_results(results: list[EvalResult], output_path: Path) -> None:
    """Save eval results to a JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([r.model_dump() for r in results], f, indent=2, ensure_ascii=False)
    logger.info("Saved %d eval results to %s", len(results), output_path)


def load_results(input_path: Path) -> list[EvalResult]:
    """Load eval results from a JSON file."""
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [EvalResult(**item) for item in data]
