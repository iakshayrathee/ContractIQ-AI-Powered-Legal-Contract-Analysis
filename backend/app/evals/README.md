# ContractIQ Evaluation Framework

A production-grade evaluation system for measuring contract analysis quality with **precision**, **recall**, **F1 scores**, and **LLM-as-Judge** assessments.

## 🎯 Why This Matters

Most "AI-powered" projects can't prove they work. This evaluation framework provides:

- **Quantified quality**: F1, precision, recall for clause extraction
- **Regression detection**: Know when changes hurt performance
- **Safety checks**: Hallucination detection and unsafe statement flags
- **CI/CD integration**: Quality gates that block bad deployments

## 📊 Quality Metrics

| Metric | Target | Description |
|--------|--------|-------------|
| **Clause F1** | ≥ 0.70 | Harmonic mean of precision and recall |
| **Clause Recall** | ≥ 0.65 | % of expected clauses found |
| **Clause Precision** | ≥ 0.65 | % of found clauses that are correct |
| **Judge Overall** | ≥ 0.70 | LLM-as-Judge quality assessment |
| **Pass Rate** | ≥ 80% | % of eval cases passing all thresholds |
| **Hallucinations** | 0 | Fabricated content (unacceptable in legal) |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Eval Dataset                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   NDA Easy  │  │  MSA Medium │  │ Employment  │  ...        │
│  │   (6 cases) │  │   (4 cases) │  │   (5 cases) │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
└─────────┼────────────────┼────────────────┼─────────────────────┘
          │                │                │
          └────────────────┴────────────────┘
                           │
          ┌────────────────┴────────────────┐
          │         Run Evals               │
          │  ┌─────────────────────────────┐  │
          │  │  Two-Pass Analysis Pipeline │  │
          │  │  (Pass 1: Chunk Extraction)  │  │
          │  │  (Pass 2: Merge & Dedupe)    │  │
          │  └─────────────┬───────────────┘  │
          │                │                  │
          │  ┌─────────────┴───────────────┐  │
          │  │  Risk Analysis (40/60)     │  │
          │  │  Summary Generation          │  │
          │  └─────────────┬───────────────┘  │
          └───────────────┼──────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
┌─────────▼─────┐  ┌──────▼──────┐  ┌────▼───────┐
│   Ground Truth │  │  LLM Judge  │  │ Guardrails │
│   Metrics     │  │ (Quality)   │  │ (Safety)   │
└───────────────┘  └─────────────┘  └────────────┘
         │                │               │
         └────────────────┴───────────────┘
                          │
          ┌───────────────┴───────────────┐
          │         Eval Results            │
          │   - TP/FP/FN per case          │
          │   - Recall/Precision/F1        │
          │   - Judge scores               │
          │   - Hallucination flags        │
          └───────────────┬───────────────┘
                          │
          ┌───────────────┴───────────────┐
          │          Reporter              │
          │   ┌───────┐ ┌───────┐ ┌─────┐ │
          │   │ .md   │ │ .html │ │.json│ │
          │   └───────┘ └───────┘ └─────┘ │
          └─────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Run Evaluation (CLI)

```bash
cd backend

# Run all eval cases
python -m app.evals.cli run

# Run specific case
python -m app.evals.cli run --case nda_easy_001

# Run by contract type
python -m app.evals.cli run --contract-type NDA

# Check regression vs baseline
python -m app.evals.cli regression
```

### 2. Run Evaluation (CI Script)

```bash
# Basic evaluation with quality gates
python scripts/ci_eval.py

# With custom thresholds
python scripts/ci_eval.py \
  --min-f1 0.75 \
  --min-pass-rate 0.90 \
  --output-dir ./reports

# Check for regressions
python scripts/ci_eval.py \
  --baseline ./baselines/v1.0.json \
  --fail-on-regression
```

### 3. Run Evaluation (Pytest)

```bash
# Fast validation (no OpenAI calls)
pytest tests/test_evaluation.py::TestEvalDatasetIntegrity -v

# Full evaluation with live LLM calls ($)
RUN_LIVE_EVALS=1 pytest tests/test_evaluation.py -v

# Specific tests only
RUN_LIVE_EVALS=1 pytest tests/test_evaluation.py::TestClauseExtractionQuality -v
```

## 📁 Dataset Format

Eval cases are defined in `test_cases/contract_eval_cases.json`:

```json
{
  "id": "nda_easy_001",
  "contract_type": "NDA",
  "difficulty": "easy",
  "source_text": "MUTUAL NON-DISCLOSURE AGREEMENT...",
  "expected_clauses": ["confidentiality", "termination", "governing_law"],
  "unexpected_clauses": ["indemnification", "payment"],
  "expected_risks": [],
  "expected_parties": ["Acme Corporation", "Beta Industries LLC"],
  "expected_summary_keywords": ["non-disclosure", "confidential"],
  "excluded_summary_keywords": ["indemnification"],
  "notes": "Straightforward mutual NDA"
}
```

### Evaluation Dimensions

| Field | Purpose |
|-------|---------|
| `expected_clauses` | Clause types that MUST be found (recall test) |
| `unexpected_clauses` | Clause types that should NOT be found (precision test) |
| `expected_risks` | Risk items that should be detected |
| `expected_summary_keywords` | Content that must appear in plain-English summary |
| `excluded_summary_keywords` | Content that must NOT appear (hallucination test) |

## 📈 Metrics Computation

### Clause Extraction Metrics

```python
# True Positives: Expected clauses that were found
tp = len(expected_clauses ∩ extracted_clauses)

# False Positives: Extracted clauses not in expected
fp = len(extracted_clauses - expected_clauses - unexpected_clauses)

# False Negatives: Expected clauses not found
fn = len(expected_clauses - extracted_clauses)

recall = tp / (tp + fn)
precision = tp / (tp + fp)
f1 = 2 * precision * recall / (precision + recall)
```

### LLM-as-Judge

A separate GPT-4o instance evaluates:

1. **Clause Extraction Recall** (0.0-1.0): Did we find all significant clauses?
2. **Clause Extraction Precision** (0.0-1.0): Are extracted texts accurate?
3. **Risk Assessment Accuracy** (0.0-1.0): Are risks genuine and well-calibrated?
4. **Summary Faithfulness** (0.0-1.0): Does summary match the contract?

```python
judge_output = await judge_service.judge_analysis(
    source_chunks=chunks,
    analysis=contract_analysis,
    risk_report=risk_report,
    plain_summary=summary,
)
# Returns: overall_score, hallucinations, missing_content, unsafe_statements
```

## 🔍 Understanding Results

### Sample Eval Result

```json
{
  "case_id": "nda_easy_001",
  "passed": true,
  "clause_recall": 0.85,
  "clause_precision": 0.90,
  "clause_f1": 0.87,
  "clause_true_positives": ["confidentiality", "termination"],
  "clause_false_negatives": ["governing_law"],
  "judge_overall": 0.82,
  "judge_clause_recall": 0.80,
  "hallucination_count": 0,
  "guardrail_passed": true
}
```

### What to Do When Evals Fail

| Failure Pattern | Likely Cause | Fix Strategy |
|-----------------|--------------|--------------|
| Low recall | Missing clauses in extraction | Tune `CHUNK_EXTRACTION_PROMPT`, increase chunk overlap |
| Low precision | False positive clauses | Improve deduplication logic, tune type classification |
| Low judge score | Overall quality issues | Review all pipeline stages, check for prompt drift |
| Hallucinations | LLM fabricating content | Strengthen guardrails, add citation requirements |
| Missing risks | Risk detection too conservative | Tune risk prompt, review severity thresholds |

## 🔧 CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/eval.yml
- name: Run evaluation
  env:
    RUN_LIVE_EVALS: 1
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: python scripts/ci_eval.py --min-f1 0.70

- name: Upload results
  uses: actions/upload-artifact@v4
  with:
    name: eval-results
    path: eval-reports/
```

### Quality Gates

The CI script exits with:
- `0`: All quality checks passed ✅
- `1`: Quality threshold violations ❌
- `2`: Runtime error 💥

### Regression Detection

```bash
# Save baseline
python scripts/ci_eval.py --output-dir ./baselines
mv ./baselines/eval_*.json ./baselines/baseline_main.json

# In CI: compare against baseline
python scripts/ci_eval.py \
  --baseline ./baselines/baseline_main.json \
  --fail-on-regression
```

## 📊 Reports

The reporter generates three formats:

### Markdown (`eval_report.md`)
- Human-readable summary
- Per-case breakdown table
- Quality grades (A/B/C/D/F)

### HTML (`eval_report.html`)
- Interactive dashboard
- Color-coded metric cards
- Sortable results table

### JSON (`eval_report.json`)
- Machine-readable metrics
- CI/CD integration
- Trend analysis data

## 🧪 Adding New Eval Cases

1. **Create test contract text**:
   ```python
   case = EvalCase(
       id="mycontract_hard_001",
       contract_type=ContractType.NDA,
       difficulty=Difficulty.HARD,
       source_text="...",  # Full contract text
       expected_clauses=["confidentiality", "non_compete"],
       unexpected_clauses=["payment"],
       expected_risks=["non_compete_too_broad"],
   )
   ```

2. **Add to dataset**:
   ```bash
   # Edit test_cases/contract_eval_cases.json
   # Add your case to the JSON array
   ```

3. **Run and verify**:
   ```bash
   python -m app.evals.cli run --case mycontract_hard_001
   ```

## 🔐 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | For analysis + judge |
| `DATABASE_URL` | Yes | PostgreSQL for results |
| `QDRANT_URL` | Yes | Vector store |
| `RUN_LIVE_EVALS` | No | Set to `1` for live tests |
| `MODEL_VERSION` | No | Tag for result tracking |
| `PIPELINE_VERSION` | No | Tag for result tracking |

## 📚 Key Files

| File | Purpose |
|------|---------|
| `dataset.py` | `EvalCase`, `EvalResult`, `EvalDataset` schemas |
| `run_evals.py` | Core evaluation logic, metric computation |
| `reporter.py` | Report generation (MD/HTML/JSON) |
| `cli.py` | Command-line interface |
| `test_cases/*.json` | Ground truth dataset |
| `../../tests/test_evaluation.py` | Pytest integration |
| `../../scripts/ci_eval.py` | CI/CD script |

## 🎓 Interview Talking Points

This evaluation framework demonstrates:

1. **Metrics-driven development**: F1 scores, not gut feel
2. **Production safety**: Hallucination detection, unsafe statement flags
3. **Regression testing**: Baseline comparison in CI/CD
4. **Multi-dimensional quality**: Ground truth + LLM judge + guardrails
5. **Domain expertise**: Legal-specific clause types and risk categories

When asked "how do you know your AI works?", point to:
- F1 scores computed against 20+ hand-annotated contracts
- LLM-as-Judge providing independent quality assessment
- Zero hallucination tolerance in CI gates
- Regression detection on every PR

---

**Status**: Production-ready | **Last Updated**: 2025-05-11
