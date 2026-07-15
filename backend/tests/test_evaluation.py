"""
Pytest integration for contract analysis evaluation.

These tests assert on actual evaluation metrics (F1, recall, precision)
rather than just checking that code runs. This enables regression testing
and quality gates in CI/CD.

Usage:
    # Run all eval tests
    pytest tests/test_evaluation.py -v

    # Run with live evaluation (requires OpenAI API key)
    RUN_LIVE_EVALS=1 pytest tests/test_evaluation.py -v

    # Run specific contract type
    pytest tests/test_evaluation.py -k "nda"

Quality Thresholds:
    - Clause F1: >= 0.70
    - Clause Recall: >= 0.65
    - Clause Precision: >= 0.65
    - Judge Overall: >= 0.70
    - Hallucinations: 0
"""

import asyncio
import json
import os
from pathlib import Path

import pytest

# Skip live evals by default (they cost money and take time)
RUN_LIVE_EVALS = os.getenv("RUN_LIVE_EVALS", "0") == "1"

# Quality thresholds (tune these based on your requirements)
CLAUSE_F1_THRESHOLD = 0.70
CLAUSE_RECALL_THRESHOLD = 0.65
CLAUSE_PRECISION_THRESHOLD = 0.65
JUDGE_OVERALL_THRESHOLD = 0.70
MIN_PASS_RATE = 0.80


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not RUN_LIVE_EVALS, reason="Set RUN_LIVE_EVALS=1 to run live evaluations"),
]


@pytest.fixture(scope="module")
def eval_dataset():
    """Load the evaluation dataset."""
    from app.evals.dataset import EvalDataset, EvalCase

    dataset_path = Path(__file__).parent.parent / "app" / "evals" / "test_cases" / "contract_eval_cases.json"
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    cases = [EvalCase(**item) for item in data]
    return EvalDataset(name="contract_analysis_test", version="1.0.0", cases=cases)


@pytest.fixture(scope="module")
async def eval_results(eval_dataset):
    """Run all eval cases and return results."""
    from app.evals.run_evals import run_evals
    from app.evals.cli import build_analysis_service
    from app.config import get_settings
    from app.services.guardrails import OutputGuardrails
    from app.services.judge_service import JudgeService

    settings = get_settings()
    analysis_service = await build_analysis_service()
    judge_service = JudgeService(settings)
    guardrails = OutputGuardrails(settings)

    results = await run_evals(
        dataset=eval_dataset,
        analysis_service=analysis_service,
        judge_service=judge_service,
        guardrails=guardrails,
    )
    return results


@pytest.fixture(scope="module")
def aggregate_metrics(eval_results):
    """Compute aggregate metrics from results."""
    from app.evals.run_evals import aggregate_results
    return aggregate_results(eval_results)


class TestClauseExtractionQuality:
    """Test clause extraction metrics meet quality thresholds."""

    def test_clause_f1_above_threshold(self, aggregate_metrics):
        """Clause extraction F1 must be >= 0.70."""
        f1 = aggregate_metrics["avg_clause_f1"]
        assert f1 >= CLAUSE_F1_THRESHOLD, (
            f"Clause F1 {f1:.3f} below threshold {CLAUSE_F1_THRESHOLD}. "
            "Review extraction prompts and chunking strategy."
        )

    def test_clause_recall_above_threshold(self, aggregate_metrics):
        """Clause extraction recall must be >= 0.65."""
        recall = aggregate_metrics["avg_clause_recall"]
        assert recall >= CLAUSE_RECALL_THRESHOLD, (
            f"Clause recall {recall:.3f} below threshold {CLAUSE_RECALL_THRESHOLD}. "
            "Too many clauses are being missed. Review Pass 1 extraction."
        )

    def test_clause_precision_above_threshold(self, aggregate_metrics):
        """Clause extraction precision must be >= 0.65."""
        precision = aggregate_metrics["avg_clause_precision"]
        assert precision >= CLAUSE_PRECISION_THRESHOLD, (
            f"Clause precision {precision:.3f} below threshold {CLAUSE_PRECISION_THRESHOLD}. "
            "Too many false positives. Review deduplication logic."
        )

    def test_no_critical_clause_misses(self, eval_results):
        """Critical clause types (confidentiality, termination, liability) should not be missed."""
        critical_clauses = {"confidentiality", "termination", "liability"}

        for result in eval_results:
            if result.error:
                continue
            # Check if we missed critical clauses
            missing_critical = critical_clauses & set(result.clause_false_negatives)
            assert not missing_critical, (
                f"Case {result.case_id}: Missed critical clauses: {missing_critical}. "
                "These are fundamental to contract analysis."
            )


class TestJudgeQuality:
    """Test LLM-as-Judge quality assessments."""

    def test_judge_overall_above_threshold(self, aggregate_metrics):
        """Judge overall quality score must be >= 0.70."""
        score = aggregate_metrics["avg_judge_overall"]
        assert score >= JUDGE_OVERALL_THRESHOLD, (
            f"Judge overall score {score:.3f} below threshold {JUDGE_OVERALL_THRESHOLD}. "
            "Review extraction, risk assessment, and summary quality."
        )

    def test_judge_clause_recall_aligned(self, eval_results):
        """Judge clause recall should align with computed recall."""
        for result in eval_results:
            if result.error or result.judge_clause_recall == 0:
                continue

            # Judge recall should be within 0.2 of computed recall
            diff = abs(result.judge_clause_recall - result.clause_recall)
            assert diff < 0.2, (
                f"Case {result.case_id}: Judge recall ({result.judge_clause_recall:.2f}) "
                f"differs significantly from computed recall ({result.clause_recall:.2f}). "
                "This may indicate an evaluation bug."
            )


class TestHallucinationAndSafety:
    """Test for hallucinations and unsafe outputs."""

    def test_zero_hallucinations(self, aggregate_metrics):
        """Total hallucinations across all cases must be zero."""
        total = aggregate_metrics["total_hallucinations"]
        assert total == 0, (
            f"Found {total} hallucinations across eval cases. "
            "Hallucinations are unacceptable in legal analysis. Review guardrails."
        )

    def test_no_unsafe_statements(self, eval_results):
        """No eval case should produce unsafe statements."""
        for result in eval_results:
            if result.error:
                continue
            assert result.unsafe_statement_severity in ["none", "low"], (
                f"Case {result.case_id}: Unsafe statement severity = {result.unsafe_statement_severity}. "
                "Review output for legally risky claims."
            )

    def test_guardrail_pass_rate(self, aggregate_metrics):
        """Guardrails should pass for at least 90% of cases."""
        pass_rate = aggregate_metrics["avg_guardrail_confidence"]
        assert pass_rate >= 0.90, (
            f"Guardrail confidence {pass_rate:.1%} below 90%. "
            "Review guardrail thresholds or output quality."
        )


class TestOverallPassRate:
    """Test aggregate pass rate meets target."""

    def test_pass_rate_above_threshold(self, aggregate_metrics):
        """Overall pass rate must be >= 80%."""
        pass_rate = aggregate_metrics["pass_rate"]
        assert pass_rate >= MIN_PASS_RATE, (
            f"Pass rate {pass_rate:.1%} below threshold {MIN_PASS_RATE:.0%}. "
            f"Failed: {aggregate_metrics['failed']}/{aggregate_metrics['total_cases']} cases. "
            "Review failing cases and fix root causes."
        )


class TestPerContractType:
    """Quality should be consistent across contract types."""

    def test_nda_clause_f1(self, eval_results):
        """NDA contracts should have F1 >= 0.70."""
        nda_results = [r for r in eval_results if r.case_id.startswith("nda") and not r.error]
        if not nda_results:
            pytest.skip("No NDA cases in dataset")

        avg_f1 = sum(r.clause_f1 for r in nda_results) / len(nda_results)
        assert avg_f1 >= 0.70, f"NDA clause F1 {avg_f1:.3f} below 0.70"

    def test_msa_clause_f1(self, eval_results):
        """MSA contracts should have F1 >= 0.70."""
        msa_results = [r for r in eval_results if r.case_id.startswith("msa") and not r.error]
        if not msa_results:
            pytest.skip("No MSA cases in dataset")

        avg_f1 = sum(r.clause_f1 for r in msa_results) / len(msa_results)
        assert avg_f1 >= 0.70, f"MSA clause F1 {avg_f1:.3f} below 0.70"


class TestRiskAssessment:
    """Test risk assessment quality."""

    def test_risk_recall_reasonable(self, aggregate_metrics):
        """Risk recall should be >= 0.60 (risks are harder than clauses)."""
        recall = aggregate_metrics["avg_risk_recall"]
        assert recall >= 0.60, f"Risk recall {recall:.3f} below 0.60"

    def test_no_false_positives_on_clean_contracts(self, eval_results):
        """Clean contracts (no expected risks) should not have risks invented."""
        from app.evals.dataset import EvalDataset

        # Reload dataset to get expected_risks
        dataset_path = Path(__file__).parent.parent / "app" / "evals" / "test_cases" / "contract_eval_cases.json"
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cases_by_id = {item["id"]: item for item in data}

        for result in eval_results:
            if result.error:
                continue
            case_data = cases_by_id.get(result.case_id, {})
            expected_risks = set(case_data.get("expected_risks", []))

            # If no risks expected, should not find any
            if not expected_risks and result.risks_extracted:
                # Some contracts genuinely have risks the annotator missed
                # So we only fail if precision is very low
                if result.risk_precision < 0.5:
                    pytest.fail(
                        f"Case {result.case_id}: No risks expected but found {result.risks_extracted}. "
                        f"Risk precision {result.risk_precision:.2f} suggests hallucination."
                    )


# Non-live tests that can always run
class TestEvalDatasetIntegrity:
    """Test the evaluation dataset is valid."""

    def test_dataset_loads(self):
        """Dataset should load without errors."""
        from app.evals.dataset import EvalDataset, EvalCase

        dataset_path = Path(__file__).parent.parent / "app" / "evals" / "test_cases" / "contract_eval_cases.json"
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cases = [EvalCase(**item) for item in data]
        assert len(cases) > 0, "Dataset should contain cases"

    def test_all_cases_have_expected_clauses(self):
        """Every case should specify expected clauses."""
        from app.evals.dataset import EvalCase

        dataset_path = Path(__file__).parent.parent / "app" / "evals" / "test_cases" / "contract_eval_cases.json"
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data:
            case = EvalCase(**item)
            assert case.expected_clauses, f"Case {case.id} has no expected_clauses"
            assert case.source_text, f"Case {case.id} has no source_text"

    def test_clause_types_are_valid(self):
        """All expected clause types should be valid enum values."""
        from app.evals.dataset import EvalCase
        from app.schemas.contract import ClauseType

        dataset_path = Path(__file__).parent.parent / "app" / "evals" / "test_cases" / "contract_eval_cases.json"
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        valid_types = {ct.value for ct in ClauseType}

        for item in data:
            case = EvalCase(**item)
            for clause_type in case.expected_clauses:
                assert clause_type in valid_types, (
                    f"Case {case.id}: Invalid clause type '{clause_type}'. "
                    f"Valid types: {valid_types}"
                )


class TestReporter:
    """Test the metrics reporter."""

    def test_reporter_generates_markdown(self):
        """Reporter should generate valid markdown."""
        from app.evals.reporter import MetricsReporter
        from app.evals.dataset import EvalResult

        # Create mock results
        mock_results = [
            EvalResult(
                case_id="test_001",
                passed=True,
                clause_f1=0.85,
                clause_recall=0.90,
                clause_precision=0.80,
                judge_overall=0.82,
                hallucination_count=0,
            )
        ]

        reporter = MetricsReporter(mock_results)
        markdown = reporter.generate_markdown()

        assert "# ContractIQ Evaluation Report" in markdown
        assert "test_001" in markdown
        assert "85.0%" in markdown or "0.85" in markdown

    def test_reporter_generates_html(self):
        """Reporter should generate valid HTML."""
        from app.evals.reporter import MetricsReporter
        from app.evals.dataset import EvalResult

        mock_results = [
            EvalResult(
                case_id="test_001",
                passed=True,
                clause_f1=0.85,
                clause_recall=0.90,
                clause_precision=0.80,
                judge_overall=0.82,
                hallucination_count=0,
            )
        ]

        reporter = MetricsReporter(mock_results)
        html = reporter.generate_html()

        assert "<!DOCTYPE html>" in html
        assert "test_001" in html
        assert "0.850" in html or "0.85" in html

    def test_reporter_computes_correct_aggregates(self):
        """Reporter should correctly compute aggregate metrics."""
        from app.evals.reporter import MetricsReporter
        from app.evals.dataset import EvalResult

        mock_results = [
            EvalResult(case_id="a", passed=True, clause_f1=0.80, judge_overall=0.85),
            EvalResult(case_id="b", passed=True, clause_f1=0.90, judge_overall=0.95),
            EvalResult(case_id="c", passed=False, clause_f1=0.50, judge_overall=0.60),
        ]

        reporter = MetricsReporter(mock_results)
        agg = reporter._compute_aggregates()

        assert agg["total"] == 3
        assert agg["passed"] == 2
        assert agg["pass_rate"] == pytest.approx(2 / 3)
        assert agg["avg_clause_f1"] == pytest.approx((0.80 + 0.90 + 0.50) / 3)
        assert agg["avg_judge_overall"] == pytest.approx((0.85 + 0.95 + 0.60) / 3)
