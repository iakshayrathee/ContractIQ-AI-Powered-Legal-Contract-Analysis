#!/usr/bin/env python3
"""
CI/CD evaluation script for ContractIQ.

Can be integrated into any CI system (GitHub Actions, GitLab CI, Jenkins, etc.)
Runs evaluations, generates reports, and exits with appropriate status codes.

Exit codes:
    0 - All quality checks passed
    1 - Quality threshold violations detected
    2 - Runtime error during evaluation

Usage:
    # Basic evaluation
    python scripts/ci_eval.py

    # With regression check
    python scripts/ci_eval.py --baseline path/to/baseline.json

    # Generate reports to specific directory
    python scripts/ci_eval.py --output-dir ./reports

    # Fail thresholds
    python scripts/ci_eval.py --min-f1 0.75 --min-pass-rate 0.85

Environment variables:
    OPENAI_API_KEY - Required for live evaluations
    DATABASE_URL - PostgreSQL connection (default: postgresql+asyncpg://localhost/contractiq)
    QDRANT_URL - Vector DB connection (default: http://localhost:6333)
    RUN_LIVE_EVALS - Set to "1" to enable (default: "1" in CI)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.evals.cli import build_analysis_service, load_default_dataset
from app.evals.dataset import EvalResult
from app.evals.reporter import MetricsReporter, compare_runs
from app.evals.run_evals import aggregate_results, run_evals, load_results
from app.config import get_settings
from app.services.guardrails import OutputGuardrails
from app.services.judge_service import JudgeService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# Default quality thresholds
DEFAULT_MIN_F1 = 0.70
DEFAULT_MIN_RECALL = 0.65
DEFAULT_MIN_PRECISION = 0.65
DEFAULT_MIN_JUDGE = 0.70
DEFAULT_MIN_PASS_RATE = 0.80


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="CI/CD Evaluation for ContractIQ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/ci_eval.py
    python scripts/ci_eval.py --baseline ./baseline.json --output-dir ./reports
    python scripts/ci_eval.py --min-f1 0.75 --min-pass-rate 0.90
        """,
    )

    parser.add_argument(
        "--baseline",
        type=Path,
        help="Path to baseline results for regression comparison",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./eval-reports"),
        help="Directory to save reports (default: ./eval-reports)",
    )
    parser.add_argument(
        "--min-f1",
        type=float,
        default=DEFAULT_MIN_F1,
        help=f"Minimum clause F1 score (default: {DEFAULT_MIN_F1})",
    )
    parser.add_argument(
        "--min-recall",
        type=float,
        default=DEFAULT_MIN_RECALL,
        help=f"Minimum clause recall (default: {DEFAULT_MIN_RECALL})",
    )
    parser.add_argument(
        "--min-precision",
        type=float,
        default=DEFAULT_MIN_PRECISION,
        help=f"Minimum clause precision (default: {DEFAULT_MIN_PRECISION})",
    )
    parser.add_argument(
        "--min-judge",
        type=float,
        default=DEFAULT_MIN_JUDGE,
        help=f"Minimum judge overall score (default: {DEFAULT_MIN_JUDGE})",
    )
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=DEFAULT_MIN_PASS_RATE,
        help=f"Minimum pass rate (default: {DEFAULT_MIN_PASS_RATE})",
    )
    parser.add_argument(
        "--max-hallucinations",
        type=int,
        default=0,
        help="Maximum allowed hallucinations (default: 0)",
    )
    parser.add_argument(
        "--no-reports",
        action="store_true",
        help="Skip generating reports, only run checks",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Fail if regressions detected vs baseline",
    )

    return parser.parse_args()


async def run_evaluation() -> list[EvalResult]:
    """Run the full evaluation suite."""
    logger.info("=" * 60)
    logger.info("Starting ContractIQ Evaluation")
    logger.info("=" * 60)

    settings = get_settings()
    dataset = load_default_dataset()

    logger.info("Dataset: %s (%d cases)", dataset.name, len(dataset.cases))

    analysis_service = await build_analysis_service()
    judge_service = JudgeService(settings) if settings.judge_enabled else None
    guardrails = OutputGuardrails(settings) if settings.guardrails_enabled else None

    results = await run_evals(
        dataset=dataset,
        analysis_service=analysis_service,
        judge_service=judge_service,
        guardrails=guardrails,
    )

    return results


def check_quality(agg: dict, thresholds: dict) -> tuple[bool, list[str]]:
    """Check aggregate metrics against thresholds.

    Returns:
        (passed, list of failure messages)
    """
    failures = []

    if agg["avg_clause_f1"] < thresholds["min_f1"]:
        failures.append(
            f"Clause F1 {agg['avg_clause_f1']:.3f} < {thresholds['min_f1']}"
        )

    if agg["avg_clause_recall"] < thresholds["min_recall"]:
        failures.append(
            f"Clause recall {agg['avg_clause_recall']:.3f} < {thresholds['min_recall']}"
        )

    if agg["avg_clause_precision"] < thresholds["min_precision"]:
        failures.append(
            f"Clause precision {agg['avg_clause_precision']:.3f} < {thresholds['min_precision']}"
        )

    if agg["avg_judge_overall"] < thresholds["min_judge"]:
        failures.append(
            f"Judge score {agg['avg_judge_overall']:.3f} < {thresholds['min_judge']}"
        )

    if agg["pass_rate"] < thresholds["min_pass_rate"]:
        failures.append(
            f"Pass rate {agg['pass_rate']:.1%} < {thresholds['min_pass_rate']:.0%}"
        )

    if agg["total_hallucinations"] > thresholds["max_hallucinations"]:
        failures.append(
            f"Hallucinations {agg['total_hallucinations']} > {thresholds['max_hallucinations']}"
        )

    return len(failures) == 0, failures


def print_summary(agg: dict, thresholds: dict, prefix: str = ""):
    """Print a formatted summary of results."""
    print(f"\n{prefix}╔" + "═" * 58 + "╗")
    print(f"{prefix}║" + " ContractIQ Evaluation Results ".center(58) + "║")
    print(f"{prefix}╠" + "═" * 58 + "╣")

    metrics = [
        ("Pass Rate", f"{agg['pass_rate']:.1%}", agg["pass_rate"] >= thresholds["min_pass_rate"]),
        ("Clause F1", f"{agg['avg_clause_f1']:.3f}", agg["avg_clause_f1"] >= thresholds["min_f1"]),
        ("Clause Recall", f"{agg['avg_clause_recall']:.3f}", agg["avg_clause_recall"] >= thresholds["min_recall"]),
        ("Clause Precision", f"{agg['avg_clause_precision']:.3f}", agg["avg_clause_precision"] >= thresholds["min_precision"]),
        ("Judge Score", f"{agg['avg_judge_overall']:.3f}", agg["avg_judge_overall"] >= thresholds["min_judge"]),
        ("Hallucinations", str(agg["total_hallucinations"]), agg["total_hallucinations"] <= thresholds["max_hallucinations"]),
    ]

    for name, value, passed in metrics:
        status = "✅" if passed else "❌"
        line = f"{status} {name}: {value}"
        print(f"{prefix}║ {line:<56} ║")

    print(f"{prefix}╚" + "═" * 58 + "╝")


def main() -> int:
    """Main entry point."""
    args = parse_args()

    thresholds = {
        "min_f1": args.min_f1,
        "min_recall": args.min_recall,
        "min_precision": args.min_precision,
        "min_judge": args.min_judge,
        "min_pass_rate": args.min_pass_rate,
        "max_hallucinations": args.max_hallucinations,
    }

    try:
        # Run evaluation
        results = asyncio.run(run_evaluation())
        agg = aggregate_results(results)

        # Generate reports
        if not args.no_reports:
            reporter = MetricsReporter(results)
            paths = reporter.save_reports(args.output_dir, prefix=f"eval_{agg['timestamp'][:10]}")
            print(f"\n📊 Reports saved:")
            for fmt, path in paths.items():
                print(f"   {fmt}: {path}")

        # Print summary
        print_summary(agg, thresholds)

        # Check quality
        passed, failures = check_quality(agg, thresholds)

        if not passed:
            print("\n❌ Quality checks FAILED:")
            for failure in failures:
                print(f"   - {failure}")

        # Check regression if baseline provided
        if args.baseline:
            if not args.baseline.exists():
                print(f"\n⚠️ Baseline not found: {args.baseline}")
            else:
                baseline_results = load_results(args.baseline)
                comparison = compare_runs(baseline_results, results)

                print(f"\n📊 Regression Check:")
                print(f"   Baseline: {args.baseline}")

                if comparison["has_regression"]:
                    print(f"\n❌ REGRESSIONS DETECTED ({comparison['regression_count']}):")
                    for reg in comparison["regressions"]:
                        print(f"   - {reg['case_id']}: {reg['change']}")

                    if args.fail_on_regression:
                        return 1
                else:
                    print("   ✅ No regressions")

                if comparison["improvements"]:
                    print(f"\n✨ Improvements ({len(comparison['improvements'])}):")
                    for imp in comparison["improvements"]:
                        print(f"   - {imp['case_id']}: {imp['change']}")

        # Final status
        if passed:
            print("\n✅ All quality checks PASSED")
            return 0
        else:
            return 1

    except Exception as e:
        logger.error("Evaluation failed: %s", e, exc_info=True)
        print(f"\n💥 Evaluation runtime error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
