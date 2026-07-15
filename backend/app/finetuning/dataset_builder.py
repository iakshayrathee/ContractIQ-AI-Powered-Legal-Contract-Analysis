"""
Dataset builder for LoRA fine-tuning.

Builds CUAD-based training dataset for LoRA fine-tuning. Previously included
silver labels (OpenAI fine-tuning) and synthetic data — both removed.

For OpenAI chat-format JSONL (now only used internally as an intermediate
step before LoRA format conversion), use the module-level build_dataset().

For instruction-tuning format (### Instruction / ### Input / ### Response)
used by the open-weight LoRA pipeline, use DatasetBuilder.build_lora_format().
"""

import hashlib
import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import tiktoken
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.schemas.contract import Clause

logger = logging.getLogger(__name__)

# Constants
MAX_TOKENS_PER_EXAMPLE = 4096
MAX_CHARS_PER_EXAMPLE = 2500
NEAR_DUPLICATE_THRESHOLD = 0.85
TRAIN_SPLIT = 0.85
TEST_SIZE = 40  # Held-out test set (CUAD gold only)


def _hash_text(text: str) -> str:
    """Compute SHA-256 hash of text for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_at_sentence_boundary(text: str, max_chars: int) -> list[str]:
    """Split text at sentence boundaries, respecting max_chars per chunk."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current_chunk = ""
    sentences = re.split(r'(?<=[.!?])\s+', text)

    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= max_chars:
            current_chunk += (" " if current_chunk else "") + sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def _count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Count tokens using tiktoken."""
    encoding = tiktoken.get_encoding(encoding_name)
    return len(encoding.encode(text))


def _validate_format(example: dict) -> bool:
    """Validate that assistant message matches Clause Pydantic schema."""
    try:
        messages = example.get("messages", [])
        if not messages or len(messages) < 3:
            return False

        assistant_msg = messages[-1]
        if assistant_msg.get("role") != "assistant":
            return False

        content = assistant_msg.get("content")
        if not content:
            return False

        # Try to parse as Clause
        Clause(**json.loads(content))
        return True

    except Exception as e:
        logger.debug("Format validation failed: %s", e)
        return False


def _remove_near_duplicates(examples: list[dict], threshold: float = NEAR_DUPLICATE_THRESHOLD) -> list[dict]:
    """Remove near-duplicates using TF-IDF cosine similarity."""
    if len(examples) <= 1:
        return examples

    # Extract user messages (chunk text)
    texts = []
    for ex in examples:
        messages = ex.get("messages", [])
        if len(messages) >= 2:
            texts.append(messages[1].get("content", ""))
        else:
            texts.append("")

    # Compute TF-IDF vectors
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(texts)

    # Compute pairwise similarity
    similarity_matrix = cosine_similarity(tfidf_matrix)

    # Find near-duplicates
    to_remove = set()
    for i in range(len(examples)):
        for j in range(i + 1, len(examples)):
            if similarity_matrix[i][j] >= threshold:
                # Keep CUAD gold version if conflict exists
                source_i = examples[i].get("metadata", {}).get("source", "")
                source_j = examples[j].get("metadata", {}).get("source", "")
                if source_i == "cuad_gold" and source_j != "cuad_gold":
                    to_remove.add(j)
                elif source_j == "cuad_gold" and source_i != "cuad_gold":
                    to_remove.add(i)
                else:
                    # Remove the later one
                    to_remove.add(j)

    return [ex for i, ex in enumerate(examples) if i not in to_remove]


def build_dataset(
    cuad_path: Path,
    output_dir: Optional[Path] = None,
) -> dict:
    """
    Build train/val/test datasets from CUAD gold labels.

    Silver labels and synthetic data have been removed. CUAD gold is the
    sole training source. The output format is OpenAI chat-format JSONL,
    which can be converted to LoRA instruction format via
    DatasetBuilder.build_lora_format().

    Args:
        cuad_path: Path to CUAD processed JSONL
        output_dir: Directory to save final datasets

    Returns:
        Metadata dictionary with dataset statistics
    """
    if output_dir is None:
        output_dir = Path(__file__).parent.parent.parent.parent / "data" / "finetuning"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading CUAD data...")
    all_examples = []
    source_counts: Counter = Counter()

    # Load CUAD gold
    if cuad_path.exists():
        with open(cuad_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    ex = json.loads(line)
                    all_examples.append(ex)
                    source_counts["cuad_gold"] += 1
                except Exception as e:
                    logger.warning("Failed to parse CUAD line: %s", e)
    logger.info("Loaded %d CUAD gold examples", source_counts["cuad_gold"])

    logger.info("Total examples loaded: %d", len(all_examples))

    # Step 1: Exact deduplication by hash
    logger.info("Step 1: Exact deduplication...")
    seen_hashes: dict = {}
    deduped = []
    conflict_count = 0

    for ex in all_examples:
        messages = ex.get("messages", [])
        if len(messages) >= 2:
            text = messages[1].get("content", "")
            text_hash = _hash_text(text)

            if text_hash in seen_hashes:
                conflict_count += 1
                continue

            seen_hashes[text_hash] = ex
            deduped.append(ex)

    logger.info("Exact deduplication: %d -> %d examples, %d conflicts resolved",
                 len(all_examples), len(deduped), conflict_count)

    # Step 2: Near-duplicate removal
    logger.info("Step 2: Near-duplicate removal...")
    deduped = _remove_near_duplicates(deduped)
    logger.info("Near-duplicate removal: %d examples remain", len(deduped))

    # Step 3: Length check and truncation
    logger.info("Step 3: Length check and truncation...")
    length_checked = []
    for ex in deduped:
        messages = ex.get("messages", [])
        if len(messages) >= 2:
            user_text = messages[1].get("content", "")
            if len(user_text) > MAX_CHARS_PER_EXAMPLE:
                chunks = _split_at_sentence_boundary(user_text, MAX_CHARS_PER_EXAMPLE)
                for chunk in chunks:
                    new_ex = ex.copy()
                    new_ex["messages"] = [
                        messages[0],  # system
                        {"role": "user", "content": chunk},
                        messages[2],  # assistant
                    ]
                    length_checked.append(new_ex)
            else:
                length_checked.append(ex)
    logger.info("Length check: %d examples after truncation", len(length_checked))

    # Step 4: Format validation
    logger.info("Step 4: Format validation...")
    validated = []
    dropped = 0
    for ex in length_checked:
        if _validate_format(ex):
            validated.append(ex)
        else:
            dropped += 1
    logger.info("Format validation: %d valid, %d dropped", len(validated), dropped)

    # Extract test set (CUAD gold only, held out permanently)
    import random
    random.seed(42)  # Reproducible split
    all_cuad = list(validated)
    test_set = random.sample(all_cuad, min(TEST_SIZE, len(all_cuad)))
    remaining = [ex for ex in all_cuad if ex not in test_set]

    logger.info("Test set: %d CUAD gold examples (held out)", len(test_set))

    # 85% train, 15% val from remaining CUAD gold
    n_train = int(len(remaining) * TRAIN_SPLIT)
    train_set = remaining[:n_train]
    val_set = remaining[n_train:]

    logger.info("Split: Train=%d, Val=%d, Test=%d", len(train_set), len(val_set), len(test_set))

    # Token count validation
    logger.info("Validating token counts...")

    def _token_filter(examples: list) -> list:
        out = []
        for ex in examples:
            messages = ex.get("messages", [])
            full_text = " ".join(m.get("content", "") for m in messages)
            if _count_tokens(full_text) <= MAX_TOKENS_PER_EXAMPLE:
                out.append(ex)
        return out

    train_validated = _token_filter(train_set)
    val_validated = _token_filter(val_set)
    test_validated = _token_filter(test_set)

    logger.info("Token validation: Train=%d, Val=%d, Test=%d",
                 len(train_validated), len(val_validated), len(test_validated))

    # Save datasets
    train_path = output_dir / "train.jsonl"
    val_path = output_dir / "val.jsonl"
    test_path = output_dir / "test.jsonl"

    with open(train_path, "w", encoding="utf-8") as f:
        for ex in train_validated:
            f.write(json.dumps(ex) + "\n")

    with open(val_path, "w", encoding="utf-8") as f:
        for ex in val_validated:
            f.write(json.dumps(ex) + "\n")

    with open(test_path, "w", encoding="utf-8") as f:
        for ex in test_validated:
            f.write(json.dumps(ex) + "\n")

    # Compute dataset hash
    dataset_hash = hashlib.sha256(
        (train_path.read_text(encoding="utf-8") + val_path.read_text(encoding="utf-8")).encode("utf-8")
    ).hexdigest()

    # Compute clause type distribution
    clause_type_dist: Counter = Counter()
    for ex in train_validated:
        metadata = ex.get("metadata", {})
        clause_type = metadata.get("clause_type")
        if clause_type:
            clause_type_dist[clause_type] += 1

    # Save metadata
    metadata = {
        "dataset_hash": dataset_hash,
        "source_model": "cuad_gold_only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "clause_type_distribution": dict(clause_type_dist),
        "train_count": len(train_validated),
        "val_count": len(val_validated),
        "test_count": len(test_validated),
        "sources_breakdown": dict(source_counts),
    }

    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Dataset build complete:")
    logger.info("  Train: %s (%d examples)", train_path, len(train_validated))
    logger.info("  Val: %s (%d examples)", val_path, len(val_validated))
    logger.info("  Test: %s (%d examples)", test_path, len(test_validated))
    logger.info("  Metadata: %s", metadata_path)

    return metadata


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    base_path = Path(__file__).parent.parent.parent.parent / "data" / "finetuning" / "sources"
    cuad_path = base_path / "cuad_processed.jsonl"

    build_dataset(cuad_path)


# ---------------------------------------------------------------------------
# DatasetBuilder class — adds LoRA format support
# ---------------------------------------------------------------------------

class DatasetBuilder:
    """
    Class-based dataset builder with support for both output formats:

    - OpenAI chat format  : build_dataset() module-level function (unchanged)
    - Instruction format  : build_lora_format()  ← open-weight LoRA pipeline

    The instruction format uses the Alpaca-style template:
        ### Instruction:  (system prompt)
        ### Input:        (contract chunk text)
        ### Response:     (JSON clause array)

    This is the format consumed by the Colab notebook (Section 3) and
    LoRATrainer.build_dataset_from_cuad().
    """

    # Clause types accepted by ContractIQ
    _CLAUSE_TYPES_STR = (
        "confidentiality, termination, indemnification, liability, non_compete, "
        "non_solicitation, intellectual_property, payment, governing_law, "
        "dispute_resolution, force_majeure, data_privacy, warranty, insurance, "
        "assignment, amendment, entire_agreement, severability, auto_renewal, other"
    )

    _INSTRUCTION = (
        "You are a legal contract analysis AI. Extract contract clauses from "
        "the following text. Return a JSON array where each item has:\n"
        '- "clause_type": one of [{clause_types}]\n'
        '- "title": short descriptive title\n'
        '- "text": the exact clause text\n'
        '- "section_reference": section number if present (null if not)\n'
        '- "obligations": list of objects with "party", "description", '
        '"type" (must/must_not/may)'
    )

    def build_lora_format(
        self,
        output_path: Optional[str] = None,
        cuad_path: Optional[Path] = None,
        silver_path: Optional[Path] = None,
        max_examples: int = 2000,
    ) -> str:
        """
        Build an instruction-tuning JSONL from existing dataset sources.

        Reads the OpenAI-format train.jsonl (or raw source files) and
        converts each example to the Alpaca instruction format used by the
        LoRA training pipeline.

        Args:
            output_path:   Where to write the output JSONL.
                           Defaults to data/finetuning/lora_train.jsonl.
            cuad_path:     Override path to cuad_processed.jsonl.
            silver_path:   Override path to silver_labeled.jsonl.
            max_examples:  Maximum number of examples to include.

        Returns:
            Absolute path to the written JSONL file.
        """
        base_dir = Path(__file__).parent.parent.parent.parent / "data" / "finetuning"
        base_dir.mkdir(parents=True, exist_ok=True)

        if output_path is None:
            dest = base_dir / "lora_train.jsonl"
        else:
            dest = Path(output_path)

        # Resolve source paths
        cuad_src = cuad_path or (base_dir / "sources" / "cuad_processed.jsonl")
        silver_src = silver_path or (base_dir / "sources" / "silver_labeled.jsonl")

        # Fall back to the pre-built train.jsonl if sources don't exist yet
        sources = []
        if cuad_src.exists():
            sources.append(cuad_src)
        if silver_src.exists():
            sources.append(silver_src)
        if not sources:
            train_path = base_dir / "train.jsonl"
            if train_path.exists():
                sources.append(train_path)
            else:
                raise FileNotFoundError(
                    "No source files found. Run 'build-dataset' first, or provide "
                    "cuad_path / silver_path arguments."
                )

        instruction_text = self._INSTRUCTION.format(
            clause_types=self._CLAUSE_TYPES_STR
        )

        written = 0
        skipped = 0

        with open(dest, "w", encoding="utf-8") as out_f:
            for src_path in sources:
                if written >= max_examples:
                    break
                with open(src_path, "r", encoding="utf-8") as in_f:
                    for line in in_f:
                        if written >= max_examples:
                            break
                        try:
                            ex = json.loads(line)
                        except json.JSONDecodeError:
                            skipped += 1
                            continue

                        converted = self._convert_openai_to_lora(ex, instruction_text)
                        if converted is None:
                            skipped += 1
                            continue

                        out_f.write(json.dumps(converted) + "\n")
                        written += 1

        logger.info(
            "lora_format_build_complete",
            written=written,
            skipped=skipped,
            output_path=str(dest),
        )
        return str(dest)

    @staticmethod
    def _convert_openai_to_lora(example: dict, instruction_text: str) -> Optional[dict]:
        """
        Convert an OpenAI chat-format example to instruction-tuning format.

        OpenAI format:
            {"messages": [{"role": "system", ...}, {"role": "user", ...},
                          {"role": "assistant", ...}]}

        Instruction format:
            {"prompt": "### Instruction:\n...\n\n### Input:\n{text}\n\n### Response:\n",
             "response": "{json_clauses}",
             "metadata": {...}}
        """
        messages = example.get("messages", [])
        if len(messages) < 3:
            return None

        # user message = contract chunk text
        user_content = messages[1].get("content", "") if len(messages) > 1 else ""
        # assistant message = clause JSON
        assistant_content = messages[2].get("content", "") if len(messages) > 2 else ""

        if not user_content or not assistant_content:
            return None

        prompt = (
            f"### Instruction:\n{instruction_text}\n\n"
            f"### Input:\n{user_content[:1500]}\n\n"
            f"### Response:\n"
        )

        return {
            "prompt": prompt,
            "response": assistant_content,
            "metadata": example.get("metadata", {}),
        }
