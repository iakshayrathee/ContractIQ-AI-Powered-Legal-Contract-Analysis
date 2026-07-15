"""
Consistency tester for fine-tuning evaluation.

Tests model consistency by running the same input multiple times and measuring output stability.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.schemas.contract import Clause

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyReport:
    """Report of consistency metrics for a model configuration."""
    model_name: str
    consistency_score: float
    format_compliance: float
    total_runs: int
    identical_outputs: int
    format_errors: int


async def _run_extraction(
    model: str,
    chunk_text: str,
    api_key: str,
) -> Optional[dict]:
    """Run a single extraction with the given model."""
    settings = get_settings()
    llm = ChatOpenAI(model=model, temperature=0.0, api_key=api_key)

    prompt = f"""Extract structured clauses from this contract text.

CHUNK TEXT:
{chunk_text}

Return JSON with clause_type, title, text, section_reference, and obligations array.
Return ONLY valid JSON, no markdown fences."""

    try:
        response = await llm.ainvoke(prompt)
        cleaned = response.content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)
        return json.loads(cleaned)
    except Exception as e:
        logger.warning("Extraction failed: %s", e)
        return None


async def test_consistency(
    model: str,
    test_chunks: list[str],
    n_runs: int = 5,
) -> ConsistencyReport:
    """
    Test consistency of a model configuration.

    Args:
        model: Model name to test
        test_chunks: List of test chunk texts
        n_runs: Number of times to run each chunk

    Returns:
        ConsistencyReport with metrics
    """
    settings = get_settings()
    api_key = settings.openai_api_key

    total_runs = len(test_chunks) * n_runs
    identical_outputs = 0
    format_errors = 0

    for chunk in test_chunks:
        outputs = []
        for _ in range(n_runs):
            result = await _run_extraction(
                model, chunk, api_key
            )

            if result is None:
                format_errors += 1
                outputs.append(None)
            else:
                # Try to validate as Clause
                try:
                    Clause(**result)
                    outputs.append(json.dumps(result, sort_keys=True))
                except Exception:
                    format_errors += 1
                    outputs.append(None)

        # Count identical outputs
        valid_outputs = [o for o in outputs if o is not None]
        if valid_outputs:
            if len(set(valid_outputs)) == 1:
                identical_outputs += 1

    consistency_score = identical_outputs / len(test_chunks) if test_chunks else 0.0
    format_compliance = (total_runs - format_errors) / total_runs if total_runs else 0.0

    return ConsistencyReport(
        model_name=model,
        consistency_score=consistency_score,
        format_compliance=format_compliance,
        total_runs=total_runs,
        identical_outputs=identical_outputs,
        format_errors=format_errors,
    )


if __name__ == "__main__":
    async def main():
        test_chunks = [
            "Either party may terminate this agreement upon 30 days written notice.",
            "The parties agree to keep all confidential information private.",
        ]

        report = await test_consistency("gpt-4o-mini", test_chunks, n_runs=3)
        print(f"Model: {report.model_name}")
        print(f"Consistency: {report.consistency_score:.2%}")
        print(f"Format compliance: {report.format_compliance:.2%}")

    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
