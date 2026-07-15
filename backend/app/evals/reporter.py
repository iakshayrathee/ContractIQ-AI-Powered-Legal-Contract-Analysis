"""
Evaluation metrics reporter for generating human-readable reports.

Produces:
- Markdown summary reports
- HTML dashboard reports
- JSON metrics for CI/CD integration
- Regression comparison reports
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.evals.dataset import EvalResult

logger = logging.getLogger(__name__)


class MetricsReporter:
    """Generate evaluation reports from EvalResult data."""

    def __init__(self, results: list[EvalResult]):
        self.results = results
        self.timestamp = datetime.utcnow().isoformat()

    def _compute_aggregates(self) -> dict:
        """Compute aggregate metrics across all results."""
        total = len(self.results)
        if total == 0:
            return {"total": 0}

        passed = sum(1 for r in self.results if r.passed)
        valid = [r for r in self.results if r.error is None]
        failed_runs = [r for r in self.results if r.error is not None]

        if not valid:
            return {
                "total": total,
                "passed": passed,
                "failed_count": len(failed_runs),
                "pass_rate": 0.0,
            }

        return {
            "total": total,
            "passed": passed,
            "failed_count": len(failed_runs),
            "pass_rate": passed / total if total > 0 else 0.0,
            "avg_judge_overall": sum(r.judge_overall for r in valid) / len(valid),
            "avg_clause_recall": sum(r.clause_recall for r in valid) / len(valid),
            "avg_clause_precision": sum(r.clause_precision for r in valid) / len(valid),
            "avg_clause_f1": sum(r.clause_f1 for r in valid) / len(valid),
            "avg_risk_recall": sum(r.risk_recall for r in valid) / len(valid),
            "avg_risk_precision": sum(r.risk_precision for r in valid) / len(valid),
            "total_hallucinations": sum(r.hallucination_count for r in valid),
            "total_missing_clauses": sum(r.missing_clause_count for r in valid),
            "guardrail_pass_rate": sum(1 for r in valid if r.guardrail_passed) / len(valid),
        }

    def _get_grade(self, score: float) -> str:
        """Convert numeric score to letter grade."""
        if score >= 0.9:
            return "A"
        elif score >= 0.8:
            return "B"
        elif score >= 0.7:
            return "C"
        elif score >= 0.6:
            return "D"
        else:
            return "F"

    def _get_grade_emoji(self, grade: str) -> str:
        """Get emoji for grade."""
        return {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "❌"}.get(grade, "⚪")

    def generate_markdown(self) -> str:
        """Generate a Markdown summary report."""
        agg = self._compute_aggregates()

        if agg["total"] == 0:
            return "# Evaluation Report\n\nNo results to report.\n"

        lines = [
            "# ContractIQ Evaluation Report",
            f"\n**Generated:** {self.timestamp[:19]} UTC",
            f"**Total Cases:** {agg['total']}",
            "",
            "## Summary",
            "",
            f"| Metric | Value | Grade |",
            f"|--------|-------|-------|",
            f"| Pass Rate | {agg['pass_rate']:.1%} | {self._get_grade_emoji(self._get_grade(agg['pass_rate']))} {self._get_grade(agg['pass_rate'])} |",
            f"| Avg Judge Score | {agg['avg_judge_overall']:.3f} | {self._get_grade_emoji(self._get_grade(agg['avg_judge_overall']))} {self._get_grade(agg['avg_judge_overall'])} |",
            f"| Clause F1 | {agg['avg_clause_f1']:.3f} | {self._get_grade_emoji(self._get_grade(agg['avg_clause_f1']))} {self._get_grade(agg['avg_clause_f1'])} |",
            f"| Clause Recall | {agg['avg_clause_recall']:.3f} | {self._get_grade_emoji(self._get_grade(agg['avg_clause_recall']))} {self._get_grade(agg['avg_clause_recall'])} |",
            f"| Clause Precision | {agg['avg_clause_precision']:.3f} | {self._get_grade_emoji(self._get_grade(agg['avg_clause_precision']))} {self._get_grade(agg['avg_clause_precision'])} |",
            "",
            "## Detailed Metrics",
            "",
            f"- **Risk Recall:** {agg['avg_risk_recall']:.3f}",
            f"- **Risk Precision:** {agg['avg_risk_precision']:.3f}",
            f"- **Guardrail Pass Rate:** {agg['guardrail_pass_rate']:.1%}",
            f"- **Total Hallucinations:** {agg['total_hallucinations']}",
            f"- **Total Missing Clauses:** {agg['total_missing_clauses']}",
            f"- **Failed Runs:** {agg['failed_count']}",
            "",
            "## Per-Case Breakdown",
            "",
            "| Case | Passed | Judge | F1 | Hallucinations |",
            "|------|--------|-------|-----|----------------|",
        ]

        for r in self.results:
            status = "✅" if r.passed else "❌"
            judge = f"{r.judge_overall:.2f}" if r.judge_overall > 0 else "N/A"
            f1 = f"{r.clause_f1:.2f}"
            hall = str(r.hallucination_count) if r.hallucination_count > 0 else "-"
            lines.append(f"| {r.case_id} | {status} | {judge} | {f1} | {hall} |")

        lines.extend([
            "",
            "## Quality Thresholds",
            "",
            "- Judge Score ≥ 0.70",
            "- Clause Recall ≥ 0.60",
            "- Clause Precision ≥ 0.60",
            "- Zero hallucinations",
            "",
            "---",
            "*Report generated by ContractIQ Eval Framework*",
        ])

        return "\n".join(lines)

    def generate_html(self) -> str:
        """Generate an HTML dashboard report."""
        agg = self._compute_aggregates()

        css = """
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
            h1 { color: #1a1a2e; border-bottom: 3px solid #16213e; padding-bottom: 10px; }
            h2 { color: #16213e; margin-top: 30px; }
            .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
            .metric-card { background: #f8f9fa; border-radius: 8px; padding: 15px; border-left: 4px solid #16213e; }
            .metric-value { font-size: 28px; font-weight: bold; color: #16213e; }
            .metric-label { font-size: 12px; color: #666; text-transform: uppercase; }
            .grade-a { border-left-color: #28a745; }
            .grade-b { border-left-color: #6c757d; }
            .grade-c { border-left-color: #ffc107; }
            .grade-d { border-left-color: #fd7e14; }
            .grade-f { border-left-color: #dc3545; }
            table { width: 100%; border-collapse: collapse; margin: 20px 0; }
            th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background: #16213e; color: white; }
            tr:hover { background: #f5f5f5; }
            .pass { color: #28a745; }
            .fail { color: #dc3545; }
            .thresholds { background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; }
        </style>
        """

        def grade_class(score: float) -> str:
            if score >= 0.9:
                return "grade-a"
            elif score >= 0.8:
                return "grade-b"
            elif score >= 0.7:
                return "grade-c"
            elif score >= 0.6:
                return "grade-d"
            else:
                return "grade-f"

        rows = []
        for r in self.results:
            status_class = "pass" if r.passed else "fail"
            status_text = "✅ PASS" if r.passed else "❌ FAIL"
            judge = f"{r.judge_overall:.2f}" if r.judge_overall > 0 else "N/A"
            rows.append(f"""
                <tr>
                    <td>{r.case_id}</td>
                    <td class="{status_class}">{status_text}</td>
                    <td>{judge}</td>
                    <td>{r.clause_f1:.2f}</td>
                    <td>{r.clause_recall:.2f}</td>
                    <td>{r.clause_precision:.2f}</td>
                    <td>{r.hallucination_count}</td>
                </tr>
            """)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>ContractIQ Eval Report</title>
    {css}
</head>
<body>
    <h1>ContractIQ Evaluation Report</h1>
    <p><strong>Generated:</strong> {self.timestamp[:19]} UTC | <strong>Cases:</strong> {agg['total']}</p>

    <h2>Summary Metrics</h2>
    <div class="summary-grid">
        <div class="metric-card {grade_class(agg['pass_rate'])}">
            <div class="metric-value">{agg['pass_rate']:.1%}</div>
            <div class="metric-label">Pass Rate</div>
        </div>
        <div class="metric-card {grade_class(agg['avg_judge_overall'])}">
            <div class="metric-value">{agg['avg_judge_overall']:.3f}</div>
            <div class="metric-label">Avg Judge Score</div>
        </div>
        <div class="metric-card {grade_class(agg['avg_clause_f1'])}">
            <div class="metric-value">{agg['avg_clause_f1']:.3f}</div>
            <div class="metric-label">Clause F1</div>
        </div>
        <div class="metric-card {grade_class(agg['avg_clause_recall'])}">
            <div class="metric-value">{agg['avg_clause_recall']:.3f}</div>
            <div class="metric-label">Clause Recall</div>
        </div>
        <div class="metric-card {grade_class(agg['avg_clause_precision'])}">
            <div class="metric-value">{agg['avg_clause_precision']:.3f}</div>
            <div class="metric-label">Clause Precision</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{agg['total_hallucinations']}</div>
            <div class="metric-label">Hallucinations</div>
        </div>
    </div>

    <div class="thresholds">
        <strong>Quality Thresholds:</strong> Judge ≥ 0.70 | Recall ≥ 0.60 | Precision ≥ 0.60 | Hallucinations = 0
    </div>

    <h2>Per-Case Results</h2>
    <table>
        <thead>
            <tr>
                <th>Case ID</th>
                <th>Status</th>
                <th>Judge Score</th>
                <th>F1</th>
                <th>Recall</th>
                <th>Precision</th>
                <th>Hallucinations</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>

    <p><em>Generated by ContractIQ Eval Framework</em></p>
</body>
</html>"""
        return html

    def generate_json(self) -> dict:
        """Generate JSON metrics for CI/CD integration."""
        agg = self._compute_aggregates()
        return {
            "timestamp": self.timestamp,
            "aggregates": agg,
            "cases": [r.model_dump() for r in self.results],
            "summary": {
                "grade": self._get_grade(agg["avg_clause_f1"]),
                "recommendation": self._generate_recommendation(agg),
            },
        }

    def _generate_recommendation(self, agg: dict) -> str:
        """Generate a recommendation based on metrics."""
        issues = []
        if agg["avg_clause_recall"] < 0.6:
            issues.append("Low clause recall - extraction prompt needs tuning")
        if agg["avg_clause_precision"] < 0.6:
            issues.append("Low clause precision - review false positives")
        if agg["avg_judge_overall"] < 0.7:
            issues.append("Judge scores below threshold - review overall quality")
        if agg["total_hallucinations"] > 0:
            issues.append(f"{agg['total_hallucinations']} hallucinations detected - strengthen guardrails")
        if agg["pass_rate"] < 0.8:
            issues.append("Pass rate below 80% - review failing cases")

        if not issues:
            return "All quality metrics within acceptable thresholds."
        return "; ".join(issues)

    def save_reports(self, output_dir: Path, prefix: str = "eval_report") -> dict:
        """Save all report formats to output directory."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = {}

        # Markdown
        md_path = output_dir / f"{prefix}.md"
        md_path.write_text(self.generate_markdown(), encoding="utf-8")
        paths["markdown"] = str(md_path)
        logger.info("Saved Markdown report: %s", md_path)

        # HTML
        html_path = output_dir / f"{prefix}.html"
        html_path.write_text(self.generate_html(), encoding="utf-8")
        paths["html"] = str(html_path)
        logger.info("Saved HTML report: %s", html_path)

        # JSON
        json_path = output_dir / f"{prefix}.json"
        json_path.write_text(
            json.dumps(self.generate_json(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        paths["json"] = str(json_path)
        logger.info("Saved JSON metrics: %s", json_path)

        return paths


def compare_runs(baseline: list[EvalResult], current: list[EvalResult]) -> dict:
    """Compare two evaluation runs and identify regressions."""
    baseline_by_id = {r.case_id: r for r in baseline}
    current_by_id = {r.case_id: r for r in current}

    regressions = []
    improvements = []
    new_cases = []
    removed_cases = []

    for case_id, current_result in current_by_id.items():
        if case_id not in baseline_by_id:
            new_cases.append(case_id)
            continue

        baseline_result = baseline_by_id[case_id]

        # Check for regressions
        if baseline_result.passed and not current_result.passed:
            regressions.append({
                "case_id": case_id,
                "change": "PASS → FAIL",
                "baseline_judge": baseline_result.judge_overall,
                "current_judge": current_result.judge_overall,
            })
        elif current_result.judge_overall < baseline_result.judge_overall - 0.1:
            regressions.append({
                "case_id": case_id,
                "change": f"Judge score dropped by {baseline_result.judge_overall - current_result.judge_overall:.2f}",
                "baseline_judge": baseline_result.judge_overall,
                "current_judge": current_result.judge_overall,
            })
        elif not baseline_result.passed and current_result.passed:
            improvements.append({
                "case_id": case_id,
                "change": "FAIL → PASS",
            })

    for case_id in baseline_by_id:
        if case_id not in current_by_id:
            removed_cases.append(case_id)

    return {
        "regressions": regressions,
        "improvements": improvements,
        "new_cases": new_cases,
        "removed_cases": removed_cases,
        "has_regression": len(regressions) > 0,
        "regression_count": len(regressions),
    }
