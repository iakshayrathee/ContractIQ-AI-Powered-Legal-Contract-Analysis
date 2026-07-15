"""
CUAD dataset processor for fine-tuning data.

Downloads CUAD dataset from HuggingFace, converts span-based labels to clause JSON schema,
and uses GPT-4o to fill missing parties/obligations fields only.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from datasets import load_dataset
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.schemas.contract import Clause, ClauseType, Obligation, ObligationType

logger = logging.getLogger(__name__)

# CUAD category to ClauseType mapping
CUAD_TO_CLAUSE_TYPE = {
    "Affiliate License": ClauseType.OTHER,
    "Anti-Assignment": ClauseType.ASSIGNMENT,
    "Audit Rights": ClauseType.OTHER,
    "Cap on Liability": ClauseType.LIABILITY,
    "Change of Control": ClauseType.OTHER,
    "Competitive Restriction": ClauseType.NON_COMPETE,
    "Covenant Not to Sue": ClauseType.OTHER,
    "Customer Data - Confidentiality": ClauseType.CONFIDENTIALITY,
    "Data Protection": ClauseType.DATA_PRIVACY,
    "Dispute Resolution": ClauseType.DISPUTE_RESOLUTION,
    "Effective Date": ClauseType.OTHER,
    "End Date": ClauseType.OTHER,
    "Exclusivity": ClauseType.OTHER,
    "Expiration Date": ClauseType.OTHER,
    "Force Majeure": ClauseType.FORCE_MAJEURE,
    "Governing Law": ClauseType.GOVERNING_LAW,
    "Indemnification": ClauseType.INDEMNIFICATION,
    "Insurance": ClauseType.INSURANCE,
    "Intellectual Property Assignment": ClauseType.INTELLECTUAL_PROPERTY,
    "Irrevocable Permits": ClauseType.OTHER,
    "License Grant": ClauseType.INTELLECTUAL_PROPERTY,
    "License Restriction": ClauseType.INTELLECTUAL_PROPERTY,
    "Liquidated Damages": ClauseType.LIABILITY,
    "Most Favored Nation": ClauseType.OTHER,
    "No Modification": ClauseType.AMENDMENT,
    "Non-Compete": ClauseType.NON_COMPETE,
    "Non-Disparagement": ClauseType.OTHER,
    "Non-Exclusivity": ClauseType.OTHER,
    "Non-Solicitation": ClauseType.NON_SOLICITATION,
    "Non-Transferable License": ClauseType.ASSIGNMENT,
    "Notice Period to Terminate Renewal": ClauseType.TERMINATION,
    "Notice Period to Terminate": ClauseType.TERMINATION,
    "Price Restrictions": ClauseType.PAYMENT,
    "Renewal Term": ClauseType.AUTO_RENEWAL,
    "Renewal Term (Auto)": ClauseType.AUTO_RENEWAL,
    "Revenue Sharing": ClauseType.PAYMENT,
    "Royalty Payment Terms": ClauseType.PAYMENT,
    "Source Code Escrow": ClauseType.OTHER,
    "Termination for Convenience": ClauseType.TERMINATION,
    "Termination for Cause": ClauseType.TERMINATION,
    "Third Party Beneficiary": ClauseType.OTHER,
    "Uncapped Liability": ClauseType.LIABILITY,
    "Unlimited Liability": ClauseType.LIABILITY,
    "Warranty Duration": ClauseType.WARRANTY,
    "Warranty Scope": ClauseType.WARRANTY,
}


def _map_cuad_category(cuad_category: str) -> ClauseType:
    """Map CUAD category to ClauseType enum."""
    mapped = CUAD_TO_CLAUSE_TYPE.get(cuad_category)
    if mapped is None:
        logger.warning("CUAD category '%s' not mapped to ClauseType, using OTHER", cuad_category)
        return ClauseType.OTHER
    return mapped


def _extract_clause_text(contract_text: str, start: int, end: int) -> str:
    """Extract clause text from contract using span indices."""
    # CUAD provides character-level spans
    if start < 0 or end > len(contract_text) or start >= end:
        return ""
    return contract_text[start:end].strip()


async def _fill_missing_fields_with_gpt4o(
    clause_text: str,
    contract_text: str,
) -> dict:
    """
    Use GPT-4o to extract parties and obligations from clause text.
    Only called when these fields are missing from CUAD ground truth.
    """
    settings = get_settings()
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.0,
        api_key=settings.openai_api_key,
    )

    prompt = f"""Extract parties and obligations from this contract clause.

CLAUSE TEXT:
{clause_text}

CONTEXT (surrounding contract text):
{contract_text[:2000]}

Return JSON:
{{
  "parties": ["<party names mentioned>"],
  "obligations": [
    {{
      "party": "<party name>",
      "description": "<what they must/may/must not do>",
      "deadline": "<deadline if stated, else null>",
      "type": "<must|must_not|may>"
    }}
  ]
}}

Rules:
- Extract ONLY what is explicitly stated
- Use null for missing fields
- Return ONLY valid JSON, no markdown"""

    try:
        response = await llm.ainvoke(prompt)
        cleaned = response.content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)
        return json.loads(cleaned)
    except Exception as e:
        logger.warning("GPT-4o extraction failed for parties/obligations: %s", e)
        return {"parties": [], "obligations": []}


async def process_cuad_dataset(
    output_path: Optional[Path] = None,
    max_examples: Optional[int] = None,
) -> Path:
    """
    Download and process CUAD dataset for fine-tuning.

    Args:
        output_path: Path to save processed JSONL file
        max_examples: Maximum number of examples to process (for testing)

    Returns:
        Path to the processed JSONL file
    """
    if output_path is None:
        output_path = Path(__file__).parent.parent.parent.parent / "data" / "finetuning" / "sources" / "cuad_processed.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Loading CUAD dataset from HuggingFace...")
    dataset = load_dataset("theatticusproject/cuad", split="train")

    if max_examples:
        dataset = dataset.select(range(min(max_examples, len(dataset))))
        logger.info("Processing %d examples (limited by max_examples)", len(dataset))
    else:
        logger.info("Processing %d examples from CUAD", len(dataset))

    processed_count = 0
    unmapped_categories = set()

    with open(output_path, "w", encoding="utf-8") as f:
        for idx, example in enumerate(dataset):
            try:
                contract_text = example["contract_text"]
                annotations = example["annotations"]  # List of {label, span_start, span_end}

                for annotation in annotations:
                    cuad_category = annotation["label"]
                    span_start = annotation["span_start"]
                    span_end = annotation["span_end"]

                    # Map CUAD category to ClauseType
                    clause_type = _map_cuad_category(cuad_category)
                    if cuad_category not in CUAD_TO_CLAUSE_TYPE:
                        unmapped_categories.add(cuad_category)

                    # Extract clause text
                    clause_text = _extract_clause_text(contract_text, span_start, span_end)
                    if not clause_text:
                        continue

                    # Use GPT-4o to fill parties and obligations
                    extracted = await _fill_missing_fields_with_gpt4o(clause_text, contract_text)

                    # Build obligations
                    obligations = []
                    for ob in extracted.get("obligations", []):
                        try:
                            ob_type = ObligationType(ob.get("type", "must"))
                        except ValueError:
                            ob_type = ObligationType.MUST
                        obligations.append(Obligation(
                            party=ob.get("party", "Unknown"),
                            description=ob.get("description", ""),
                            deadline=ob.get("deadline"),
                            type=ob_type,
                        ))

                    # Build clause
                    clause = Clause(
                        clause_type=clause_type,
                        title=cuad_category,  # Use CUAD category as title
                        text=clause_text,
                        section_reference=None,  # CUAD doesn't provide section refs
                        obligations=obligations,
                    )

                    # Format as OpenAI fine-tuning example
                    training_example = {
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a legal contract analyst. Extract structured clauses from contract text. Return JSON with clause_type, title, text, section_reference, and obligations array."
                            },
                            {
                                "role": "user",
                                "content": clause_text
                            },
                            {
                                "role": "assistant",
                                "content": json.dumps(clause.model_dump(), indent=None)
                            }
                        ],
                        "metadata": {
                            "source": "cuad_gold",
                            "cuad_category": cuad_category,
                            "clause_type": clause_type.value
                        }
                    }

                    f.write(json.dumps(training_example) + "\n")
                    processed_count += 1

                if idx % 10 == 0:
                    logger.info("Processed %d contracts, %d clauses extracted", idx + 1, processed_count)

            except Exception as e:
                logger.error("Failed to process example %d: %s", idx, e)
                continue

    logger.info("CUAD processing complete: %d clauses saved to %s", processed_count, output_path)
    if unmapped_categories:
        logger.warning("Unmapped CUAD categories: %s", unmapped_categories)

    return output_path


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(process_cuad_dataset())
