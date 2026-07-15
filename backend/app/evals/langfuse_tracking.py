"""
Langfuse integration for tracking eval metrics over time.

Provides:
- eval_result_logged: Log a completed eval result to Langfuse
- eval_run_logged: Log an entire eval run summary
- get_eval_trends: Retrieve historical eval metrics for trending

Langfuse Evaluation API:
https://langfuse.com/docs/evaluation
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from app.evals.dataset import EvalResult
from app.schemas.judge import JudgeOutput

logger = logging.getLogger(__name__)

# Lazily initialized Langfuse client
_langfuse_client: Optional[object] = None


def _get_langfuse_client():
    """Get or initialize the Langfuse client."""
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client

    try:
        from langfuse import Langfuse

        if os.getenv("LANGFUSE_ENABLED", "false").lower() != "true":
            logger.debug("Langfuse disabled via LANGFUSE_ENABLED env var")
            return None

        _langfuse_client = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
        return _langfuse_client
    except ImportError:
        logger.warning("langfuse not installed — eval tracking disabled")
        return None
    except Exception as e:
        logger.warning("Failed to initialize Langfuse: %s", e)
        return None


def log_eval_result(
    result: EvalResult,
    case_metadata: Optional[dict] = None,
    judge_output: Optional[JudgeOutput] = None,
) -> None:
    """
    Log a single eval result to Langfuse for tracking.

    This creates an evaluation observation in Langfuse that can be:
    - Queried for trends over time
    - Compared across model versions
    - Used to trigger alerts on regression

    Args:
        result: The EvalResult from running a single case
        case_metadata: Optional metadata about the eval case (contract_type, difficulty, etc.)
        judge_output: Optional full JudgeOutput for detailed tracking
    """
    client = _get_langfuse_client()
    if client is None:
        return

    try:
        # Build metadata for Langfuse
        metadata = {
            "case_id": result.case_id,
            "model_version": result.model_version,
            "pipeline_version": result.pipeline_version,
            "passed": result.passed,
            "pass_reason": result.pass_reason,
            # Clause metrics
            "clause_recall": result.clause_recall,
            "clause_precision": result.clause_precision,
            "clause_f1": result.clause_f1,
            "clause_tp_count": len(result.clause_true_positives),
            "clause_fp_count": len(result.clause_false_positives),
            "clause_fn_count": len(result.clause_false_negatives),
            # Risk metrics
            "risk_recall": result.risk_recall,
            "risk_precision": result.risk_precision,
            # Summary metrics
            "summary_keyword_match_ratio": result.summary_keyword_match_ratio,
            "summary_has_excluded_keywords": result.summary_has_excluded_keywords,
            # Judge scores
            "judge_overall": result.judge_overall,
            "hallucination_count": result.hallucination_count,
            "missing_clause_count": result.missing_clause_count,
            "unsafe_statement_severity": result.unsafe_statement_severity,
            # Guardrail results
            "guardrail_passed": result.guardrail_passed,
            "guardrail_confidence": result.guardrail_confidence,
        }

        if case_metadata:
            metadata.update(case_metadata)

        # Log a score observation
        client.log(
            name=f"eval-{result.case_id}",
            score=result.judge_overall,
            metadata=metadata,
        )

        # If we have judge output, log dimension-specific scores
        if judge_output:
            dimension_scores = [
                ("clause_recall", judge_output.clause_extraction.recall),
                ("clause_precision", judge_output.clause_extraction.precision),
                ("risk_accuracy", judge_output.risk_assessment.accuracy),
                ("risk_severity_calibration", judge_output.risk_assessment.severity_calibration),
                ("summary_faithfulness", judge_output.summary_faithfulness.faithfulness),
                ("summary_completeness", judge_output.summary_faithfulness.completeness),
            ]
            for name, score in dimension_scores:
                client.log(
                    name=f"eval-dimension-{name}",
                    score=score,
                    metadata={
                        "case_id": result.case_id,
                        "dimension": name,
                        "model_version": result.model_version,
                    },
                )

        logger.debug("Logged eval result to Langfuse: case_id=%s, score=%.3f", result.case_id, result.judge_overall)

    except Exception as e:
        logger.error("Failed to log eval result to Langfuse: %s", e)


def log_eval_run(
    dataset_name: str,
    total_cases: int,
    passed: int,
    failed: int,
    aggregate_metrics: dict,
    model_version: Optional[str] = None,
) -> None:
    """
    Log an entire eval run summary to Langfuse.

    Args:
        dataset_name: Name of the dataset evaluated
        total_cases: Total number of cases
        passed: Number of cases that passed
        failed: Number of cases that failed
        aggregate_metrics: Dict from aggregate_results()
        model_version: Optional model/pipeline version identifier
    """
    client = _get_langfuse_client()
    if client is None:
        return

    try:
        metadata = {
            "dataset": dataset_name,
            "total_cases": total_cases,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / total_cases if total_cases > 0 else 0.0,
            "model_version": model_version or os.getenv("MODEL_VERSION", "unknown"),
            "pipeline_version": os.getenv("PIPELINE_VERSION", "unknown"),
            # Aggregate metrics
            "avg_judge_overall": aggregate_metrics.get("avg_judge_overall", 0.0),
            "avg_clause_recall": aggregate_metrics.get("avg_clause_recall", 0.0),
            "avg_clause_precision": aggregate_metrics.get("avg_clause_precision", 0.0),
            "avg_clause_f1": aggregate_metrics.get("avg_clause_f1", 0.0),
            "avg_risk_recall": aggregate_metrics.get("avg_risk_recall", 0.0),
            "avg_guardrail_confidence": aggregate_metrics.get("avg_guardrail_confidence", 0.0),
            "total_hallucinations": aggregate_metrics.get("total_hallucinations", 0),
            "total_missing_clauses": aggregate_metrics.get("total_missing_clauses", 0),
            # Quality flags
            "has_low_judge_scores": aggregate_metrics.get("has_low_judge_scores", False),
            "has_poor_clause_recall": aggregate_metrics.get("has_poor_clause_recall", False),
            "has_poor_clause_precision": aggregate_metrics.get("has_poor_clause_precision", False),
            # Breakdown
            "by_contract_type": aggregate_metrics.get("by_contract_type", {}),
            "by_difficulty": aggregate_metrics.get("by_difficulty", {}),
        }

        client.log(
            name=f"eval-run-{dataset_name}",
            score=aggregate_metrics.get("avg_judge_overall", 0.0),
            metadata=metadata,
        )

        logger.info(
            "Logged eval run to Langfuse: dataset=%s, pass_rate=%.1f%%, avg_judge=%.3f",
            dataset_name,
            (passed / total_cases * 100) if total_cases > 0 else 0,
            aggregate_metrics.get("avg_judge_overall", 0.0),
        )

    except Exception as e:
        logger.error("Failed to log eval run to Langfuse: %s", e)


def get_eval_trends(
    dataset_name: Optional[str] = None,
    days: int = 30,
) -> dict:
    """
    Retrieve historical eval metrics from Langfuse for trending analysis.

    Args:
        dataset_name: Optional filter by dataset name
        days: Number of days to look back (default 30)

    Returns:
        Dict with trend data per metric
    """
    client = _get_langfuse_client()
    if client is None:
        return {"error": "Langfuse not available"}

    try:
        # Langfuse Python SDK — fetch observations for eval runs
        # This is a simplified version; actual API may vary
        from datetime import datetime, timedelta

        start_time = datetime.utcnow() - timedelta(days=days)

        observations = client.observations(
            name=f"eval-run-{dataset_name}" if dataset_name else "eval-run-*",
            start_time=start_time,
        )

        # Aggregate into trends
        trends: dict[str, list[dict]] = {
            "judge_overall": [],
            "clause_recall": [],
            "clause_precision": [],
            "pass_rate": [],
        }

        for obs in observations:
            metadata = obs.get("metadata", {})
            ts = obs.get("timestamp")

            if "avg_judge_overall" in metadata:
                trends["judge_overall"].append({
                    "timestamp": ts,
                    "value": metadata["avg_judge_overall"],
                    "dataset": metadata.get("dataset"),
                })
            if "avg_clause_recall" in metadata:
                trends["clause_recall"].append({
                    "timestamp": ts,
                    "value": metadata["avg_clause_recall"],
                    "dataset": metadata.get("dataset"),
                })
            if "avg_clause_precision" in metadata:
                trends["clause_precision"].append({
                    "timestamp": ts,
                    "value": metadata["avg_clause_precision"],
                    "dataset": metadata.get("dataset"),
                })
            if "pass_rate" in metadata:
                trends["pass_rate"].append({
                    "timestamp": ts,
                    "value": metadata["pass_rate"],
                    "dataset": metadata.get("dataset"),
                })

        return trends

    except Exception as e:
        logger.error("Failed to fetch eval trends from Langfuse: %s", e)
        return {"error": str(e)}


def check_regression(
    current_metrics: dict,
    baseline_metrics: dict,
    regression_threshold: float = 0.05,
) -> dict[str, bool]:
    """
    Check if current eval metrics have regressed vs a baseline.

    Args:
        current_metrics: Current aggregate_metrics from run_evals
        baseline_metrics: Baseline aggregate_metrics to compare against
        regression_threshold: Minimum decline to flag as regression (default 5%)

    Returns:
        Dict mapping metric name to whether it has regressed
    """
    metrics_to_check = [
        "avg_judge_overall",
        "avg_clause_recall",
        "avg_clause_precision",
        "avg_clause_f1",
        "avg_risk_recall",
        "avg_guardrail_confidence",
        "pass_rate",
    ]

    regression_flags = {}
    for metric in metrics_to_check:
        current = current_metrics.get(metric, 0.0)
        baseline = baseline_metrics.get(metric, 0.0)

        if baseline > 0:
            decline = baseline - current
            regression_flags[metric] = decline > regression_threshold
        else:
            regression_flags[metric] = False

    overall_regression = any(regression_flags.values())

    return {
        "overall_regression": overall_regression,
        "metric_regressions": regression_flags,
    }
