# Fine-Tuning Evaluation Report

Generated: 2026-06-04T23:26:22.495525+00:00

## 1. Extraction Quality

| Model | F1 | Precision | Recall |
|-------|-----|-----------|--------|
| gpt4o_mini_finetuned | 0.400 | 0.400 | 0.400 |
| gpt4o_baseline | 0.000 | 0.000 | 0.000 |
| gpt4o_mini_baseline | 0.000 | 0.000 | 0.000 |

### Per-Clause-Type F1 Breakdown

| Clause Type | GPT-4o | GPT-4o-mini | Fine-tuned |
|-------------|--------|-------------|------------|
| entire_agreement | 0.000 | 0.000 | 1.000 |
| insurance | 0.000 | 0.000 | 1.000 |
| intellectual_property | 0.000 | 0.000 | 0.000 |
| termination | 0.000 | 0.000 | 0.000 |
| warranty | 0.000 | 0.000 | 0.000 |

*Note: Rare clause types may underperform due to limited training data. v2 will address this via oversampling.*

## 2. Hallucination Analysis

| Model | Mean Overlap | P25 | P75 | P95 | Fabrication Rate |
|-------|--------------|-----|-----|-----|------------------|
| gpt4o_mini_finetuned | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| gpt4o_baseline | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| gpt4o_mini_baseline | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |

**Source overlap score** measures how much of the extracted clause text appears in the source chunk. **Fabrication rate** counts clauses with entities (party names, dates, dollar amounts) that don't exist in the source.

Fabrication rate matters more than F1 in legal contexts: a fabricated obligation or party name is a liability risk, not just a quality issue.

## 3. Consistency & Format Compliance

| Model | Consistency Score | Format Compliance |
|-------|-------------------|-------------------|
| gpt4o_mini_finetuned | 100.00% | 100.00% |
| gpt4o_baseline | 0.00% | 0.00% |
| gpt4o_mini_baseline | 0.00% | 0.00% |

**Production impact:** 99%+ format compliance means fallback parsing almost never fires, reducing latency variance and making the system predictable.

## 4. Cost & Latency Breakdown

| Model | Cost/Chunk | Cost/Doc | Cost/1000 Docs | P50 Latency | P95 Latency | P99 Latency |
|-------|------------|---------|---------------|-------------|-------------|-------------|
| gpt4o_mini_finetuned | $0.0000 | $0.00 | $0.00 | 0ms | 0ms | 0ms |
| gpt4o_baseline | $0.0000 | $0.00 | $0.00 | 0ms | 0ms | 0ms |
| gpt4o_mini_baseline | $0.0000 | $0.00 | $0.00 | 0ms | 0ms | 0ms |

**Token math:** input tokens × price + output tokens × price = cost per chunk → cost per doc → cost per 1000 docs
Fine-tuned models have no few-shot examples, reducing prompt tokens by ~30%.
**P99 latency argument:** Smaller model = more predictable response times = lower tail latency.

## 5. Summary Recommendation

Based on the evaluation results:

- **Best extraction quality:** gpt4o_mini_finetuned (F1=0.400)
- **Lowest cost:** gpt4o_mini_finetuned ($0.00/1000 docs)

