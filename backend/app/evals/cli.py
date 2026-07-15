"""
CLI for running contract analysis evals.

Usage:
    # Run all eval cases
    python -m app.evals.cli run

    # Run a specific eval case
    python -m app.evals.cli run --case nda_easy_001

    # Run with custom dataset
    python -m app.evals.cli run --dataset my_custom_cases

    # Check regression vs baseline
    python -m app.evals.cli regression

    # Show trends from Langfuse
    python -m app.evals.cli trends
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add the backend directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.evals.dataset import EvalDataset, EvalCase
from app.evals.run_evals import run_evals, aggregate_results, save_results, load_results
from app.evals.langfuse_tracking import log_eval_run, check_regression, get_eval_trends
from app.services.guardrails import OutputGuardrails
from app.services.judge_service import JudgeService
from app.config import get_settings
from app.db.database import engine, async_sessionmaker
from app.services.vector_store_service import VectorStoreService
from app.services.contract_analysis_service import ContractAnalysisService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_default_dataset() -> EvalDataset:
    """Load the default eval dataset from test_cases directory."""
    dataset_path = Path(__file__).parent / "test_cases" / "contract_eval_cases.json"
    if not dataset_path.exists():
        raise FileNotFoundError(f"Eval dataset not found: {dataset_path}")

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = [EvalCase(**item) for item in data]
    return EvalDataset(name="contract_analysis_v1", version="1.0.0", cases=cases)


async def build_analysis_service() -> ContractAnalysisService:
    """Build a ContractAnalysisService with real dependencies."""
    settings = get_settings()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    vs_service = VectorStoreService(settings)
    return ContractAnalysisService(settings, vs_service, session_factory)


async def cmd_run(args: argparse.Namespace) -> None:
    """Run eval cases."""
    dataset = load_default_dataset()

    # Filter by case ID if specified
    if args.case:
        dataset.cases = [c for c in dataset.cases if c.id == args.case]
        if not dataset.cases:
            logger.error("Case '%s' not found in dataset", args.case)
            return

    if args.contract_type:
        dataset.cases = [c for c in dataset.cases if c.contract_type.value == args.contract_type]
        logger.info("Filtered to %d cases of type '%s'", len(dataset.cases), args.contract_type)

    if args.difficulty:
        dataset.cases = [c for c in dataset.cases if c.difficulty.value == args.difficulty]
        logger.info("Filtered to %d cases of difficulty '%s'", len(dataset.cases), args.difficulty)

    if not dataset.cases:
        logger.error("No cases to run after filtering")
        return

    logger.info("=" * 60)
    logger.info("Starting evals: dataset=%s, cases=%d", dataset.name, len(dataset.cases))
    logger.info("=" * 60)

    settings = get_settings()
    analysis_service = await build_analysis_service()
    judge_service = JudgeService(settings) if settings.judge_enabled else None
    guardrails = OutputGuardrails(settings) if settings.guardrails_enabled else None

    results = await run_evals(
        dataset=dataset,
        analysis_service=analysis_service,
        judge_service=judge_service,
        guardrails=guardrails,
    )

    # Aggregate
    summary = aggregate_results(results)

    # Print summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("EVAL SUMMARY")
    logger.info("=" * 60)
    logger.info(
        "  Pass rate: %d/%d (%.1f%%)",
        summary["passed"],
        summary["total_cases"],
        summary["pass_rate"] * 100,
    )
    logger.info(
        "  Avg judge score: %.3f  (threshold: %.2f)",
        summary["avg_judge_overall"],
        settings.judge_quality_threshold,
    )
    logger.info(
        "  Avg clause F1:   %.3f  (recall: %.3f, precision: %.3f)",
        summary["avg_clause_f1"],
        summary["avg_clause_recall"],
        summary["avg_clause_precision"],
    )
    logger.info(
        "  Avg guardrail confidence: %.3f",
        summary["avg_guardrail_confidence"],
    )
    logger.info(
        "  Total hallucinations: %d",
        summary["total_hallucinations"],
    )
    logger.info(
        "  Total missing clauses: %d",
        summary["total_missing_clauses"],
    )

    # Per-contract-type breakdown
    if summary.get("by_contract_type"):
        logger.info("")
        logger.info("By contract type:")
        for ct, data in summary["by_contract_type"].items():
            logger.info(
                "  %-12s  pass=%d/%d (%5.1f%%)  avg_judge=%.3f",
                ct,
                data["passed"],
                data["total"],
                data.get("pass_rate", 0) * 100,
                data["avg_judge"],
            )

    # Per-difficulty breakdown
    if summary.get("by_difficulty"):
        logger.info("")
        logger.info("By difficulty:")
        for diff, data in summary["by_difficulty"].items():
            logger.info(
                "  %-12s  pass=%d/%d (%5.1f%%)  avg_judge=%.3f",
                diff,
                data["passed"],
                data["total"],
                data.get("pass_rate", 0) * 100,
                data["avg_judge"],
            )

    # Quality flags
    logger.info("")
    logger.info("Quality flags:")
    flags = []
    if summary.get("has_low_judge_scores"):
        flags.append("LOW_JUDGE_SCORES")
    if summary.get("has_poor_clause_recall"):
        flags.append("POOR_CLAUSE_RECALL")
    if summary.get("has_poor_clause_precision"):
        flags.append("POOR_CLAUSE_PRECISION")
    if flags:
        for flag in flags:
            logger.warning("  ! %s", flag)
    else:
        logger.info("  No quality issues detected")

    # Save results
    output_path = Path(__file__).parent / "results" / f"eval_run_{dataset.name}.json"
    save_results(results, output_path)
    logger.info("Results saved to: %s", output_path)

    # Log to Langfuse
    if settings.langfuse_enabled:
        log_eval_run(
            dataset_name=dataset.name,
            total_cases=summary["total_cases"],
            passed=summary["passed"],
            failed=summary["failed"],
            aggregate_metrics=summary,
            model_version=os.getenv("MODEL_VERSION", "unknown"),
        )

    # Exit code based on pass rate
    if summary["pass_rate"] < 0.8:
        sys.exit(1)


async def cmd_regression(args: argparse.Namespace) -> None:
    """Check for regressions vs a baseline."""
    baseline_path = Path(__file__).parent / "results" / f"eval_run_{args.baseline}.json"
    if not baseline_path.exists():
        logger.error("Baseline results not found: %s", baseline_path)
        logger.info("Run 'python -m app.evals.cli run' first to generate baseline results")
        return

    # Load current results (latest)
    current_path = Path(__file__).parent / "results"
    current_files = sorted(current_path.glob("eval_run_*.json"), key=lambda p: p.stat().st_mtime)
    if not current_files:
        logger.error("No current results found. Run 'python -m app.evals.cli run' first.")
        return

    current_results = load_results(current_files[-1])
    current_summary = aggregate_results(current_results)

    baseline_results = load_results(baseline_path)
    baseline_summary = aggregate_results(baseline_results)

    regression = check_regression(current_summary, baseline_summary)

    logger.info("=" * 60)
    logger.info("REGRESSION CHECK")
    logger.info("=" * 60)
    logger.info("Current: %s", current_files[-1].name)
    logger.info("Baseline: %s", baseline_path.name)
    logger.info("")
    logger.info("Overall regression: %s", "YES" if regression["overall_regression"] else "NO")
    if regression["overall_regression"]:
        logger.warning("")
        logger.warning("Regressed metrics:")
        for metric, is_reg in regression["metric_regressions"].items():
            if is_reg:
                logger.warning("  ! %s", metric)
    else:
        logger.info("No regressions detected")


async def cmd_trends(args: argparse.Namespace) -> None:
    """Show eval trends from Langfuse."""
    settings = get_settings()
    if not settings.langfuse_enabled:
        logger.error("Langfuse is not enabled. Set LANGFUSE_ENABLED=true in your .env")
        return

    trends = get_eval_trends(dataset_name=args.dataset, days=args.days)

    if "error" in trends:
        logger.error("Failed to fetch trends: %s", trends["error"])
        return

    logger.info("=" * 60)
    logger.info("EVAL TRENDS (last %d days)", args.days)
    logger.info("=" * 60)

    for metric_name, data_points in trends.items():
        if not data_points:
            continue
        logger.info("")
        logger.info("%s:", metric_name)
        for point in data_points[-10:]:  # Show last 10
            ts = point.get("timestamp", "unknown")
            value = point.get("value", 0)
            dataset = point.get("dataset", "unknown")
            logger.info("  %s  |  %s  |  %.3f", ts[:10], dataset, value)


def main() -> None:
    parser = argparse.ArgumentParser(description="ContractIQ Eval CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Run eval cases")
    run_parser.add_argument("--case", help="Run a specific case ID only")
    run_parser.add_argument(
        "--contract-type",
        help="Filter by contract type (NDA, MSA, SaaS, Employment, etc.)",
    )
    run_parser.add_argument(
        "--difficulty",
        help="Filter by difficulty (easy, medium, hard)",
    )

    # regression command
    subparsers.add_parser("regression", help="Check for regressions vs baseline")
    subparsers.add_parser("trends", help="Show eval trends from Langfuse")

    # Shared args
    for p in [run_parser]:
        p.add_argument(
            "--dataset",
            default="contract_analysis_v1",
            help="Dataset name to load (default: contract_analysis_v1)",
        )

    trends_parser = subparsers.add_parser("trends", help="Show eval trends")
    trends_parser.add_argument("--dataset", help="Filter by dataset name")
    trends_parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to look back (default: 30)",
    )

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "regression":
        asyncio.run(cmd_regression(args))
    elif args.command == "trends":
        asyncio.run(cmd_trends(args))


if __name__ == "__main__":
    main()
