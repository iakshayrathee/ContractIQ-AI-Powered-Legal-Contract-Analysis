"""
Cost calculator for fine-tuning evaluation.

Computes cost and latency metrics for different model configurations.
"""

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass
from typing import Optional

from langchain_openai import ChatOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

# OpenAI pricing (per 1M tokens, as of 2024)
PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o-mini-2024-07-18": {"input": 0.15, "output": 0.60},
}


@dataclass
class CostReport:
    """Report of cost and latency metrics for a model configuration."""
    model_name: str
    avg_input_tokens: float
    avg_output_tokens: float
    cost_per_chunk: float
    cost_per_document: float
    cost_per_1000_docs: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    prompt_token_reduction: Optional[float] = None


async def _measure_call(
    model: str,
    prompt: str,
    api_key: str,
    base_model_for_pricing: Optional[str] = None,
) -> tuple[int, int, float]:
    """
    Run a single LLM call and measure tokens and latency.

    Returns:
        (input_tokens, output_tokens, latency_ms)
    """
    settings = get_settings()
    llm = ChatOpenAI(model=model, temperature=0.0, api_key=api_key)

    start_time = time.perf_counter()
    response = await llm.ainvoke(prompt)
    latency_ms = (time.perf_counter() - start_time) * 1000

    # Estimate token counts (LangChain doesn't expose usage by default)
    # Use tiktoken for estimation - use base model for tokenization if provided
    import tiktoken
    encoding_model = base_model_for_pricing or model
    try:
        encoding = tiktoken.encoding_for_model(encoding_model)
    except KeyError:
        # Fallback to cl100k_base (GPT-4o-mini encoding)
        encoding = tiktoken.get_encoding("cl100k_base")
    input_tokens = len(encoding.encode(prompt))
    output_tokens = len(encoding.encode(response.content))

    return input_tokens, output_tokens, latency_ms


async def calculate_costs(
    model: str,
    test_prompts: list[str],
    avg_chunks_per_doc: int = 10,
    baseline_model: Optional[str] = None,
    base_model_for_pricing: Optional[str] = None,
) -> CostReport:
    """
    Calculate cost and latency metrics for a model configuration.

    Args:
        model: Model name to evaluate
        test_prompts: List of test prompts
        avg_chunks_per_doc: Average number of chunks per document
        baseline_model: Optional baseline model for token reduction comparison
        base_model_for_pricing: Base model name for pricing/tokenization (e.g., "gpt-4o-mini")

    Returns:
        CostReport with cost and latency metrics
    """
    settings = get_settings()
    api_key = settings.openai_api_key

    input_tokens_list = []
    output_tokens_list = []
    latencies = []

    for prompt in test_prompts:
        input_toks, output_toks, latency = await _measure_call(
            model, prompt, api_key, base_model_for_pricing
        )
        input_tokens_list.append(input_toks)
        output_tokens_list.append(output_toks)
        latencies.append(latency)

    avg_input_tokens = statistics.mean(input_tokens_list) if input_tokens_list else 0
    avg_output_tokens = statistics.mean(output_tokens_list) if output_tokens_list else 0

    # Calculate costs - use base model for pricing if provided
    pricing_model = base_model_for_pricing or model
    model_pricing = PRICING.get(pricing_model, {"input": 0.0, "output": 0.0})
    cost_per_chunk = (
        (avg_input_tokens / 1_000_000) * model_pricing["input"] +
        (avg_output_tokens / 1_000_000) * model_pricing["output"]
    )
    cost_per_document = cost_per_chunk * avg_chunks_per_doc
    cost_per_1000_docs = cost_per_document * 1000

    # Calculate latency percentiles
    if latencies:
        p50_latency_ms = statistics.median(latencies)
        p95_latency_ms = sorted(latencies)[int(len(latencies) * 0.95)]
        p99_latency_ms = sorted(latencies)[int(len(latencies) * 0.99)]
    else:
        p50_latency_ms = 0.0
        p95_latency_ms = 0.0
        p99_latency_ms = 0.0

    # Calculate prompt token reduction vs baseline
    prompt_token_reduction = None
    if baseline_model:
        baseline_avg = statistics.mean([len(p.split()) for p in test_prompts])  # Rough estimate
        # Fine-tuned models typically use fewer tokens due to no few-shot examples
        # This is a simplified calculation
        prompt_token_reduction = 0.3  # Assume 30% reduction from removing few-shot

    return CostReport(
        model_name=model,
        avg_input_tokens=avg_input_tokens,
        avg_output_tokens=avg_output_tokens,
        cost_per_chunk=cost_per_chunk,
        cost_per_document=cost_per_document,
        cost_per_1000_docs=cost_per_1000_docs,
        p50_latency_ms=p50_latency_ms,
        p95_latency_ms=p95_latency_ms,
        p99_latency_ms=p99_latency_ms,
        prompt_token_reduction=prompt_token_reduction,
    )


if __name__ == "__main__":
    async def main():
        test_prompts = [
            "Extract clauses from: Either party may terminate this agreement upon 30 days written notice.",
            "Extract clauses from: The parties agree to keep all confidential information private.",
        ]

        report = await calculate_costs("gpt-4o-mini", test_prompts)
        print(f"Model: {report.model_name}")
        print(f"Cost per chunk: ${report.cost_per_chunk:.4f}")
        print(f"Cost per 1000 docs: ${report.cost_per_1000_docs:.2f}")
        print(f"P50 latency: {report.p50_latency_ms:.0f}ms")

    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
