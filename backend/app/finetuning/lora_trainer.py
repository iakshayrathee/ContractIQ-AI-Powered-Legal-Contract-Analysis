"""
Fine-tuning trainer for open-weight models (Llama-3.2-3B-Instruct + QLoRA).

Provides the LoRATrainer class which mirrors the interface of the existing
OpenAITrainer but targets local open-weight training via Google Colab + Unsloth.

For production GPU training see the TODO in submit_training_job().

Requires:  pip install -r requirements-lora.txt  (for load_adapter / run_inference)
           peft>=0.13.0, bitsandbytes>=0.43.0, transformers>=4.45.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import structlog

# Heavy ML imports are guarded so the module can be imported at startup
# without paying the torch/transformers/peft load cost when
# LLM_PROVIDER != local_lora.
if TYPE_CHECKING:
    from peft import PeftModel  # noqa: F401
    from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: F401

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_MODEL_ID = "unsloth/Llama-3.2-3B-Instruct"
# Deployed HuggingFace LoRA adapter (trained via notebooks/contractiq_lora_finetune.ipynb)
HF_ADAPTER_ID = "iakshayrathee/contractiq-lora-llama3"
MAX_SEQ_LENGTH = 2048
LORA_CONFIG = {
    "r": 16,
    "lora_alpha": 16,
    "lora_dropout": 0,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj",
                       "gate_proj", "up_proj", "down_proj"],
}

# Mapping from CUAD question text fragments → ContractIQ ClauseType values.
# CUAD has 41 question categories; we map them to ContractIQ's 20 types.
_CUAD_QUESTION_MAP: list[tuple[str, str]] = [
    ("termination", "termination"),
    ("convenience", "termination"),
    ("breach", "termination"),
    ("non-compete", "non_compete"),
    ("non compete", "non_compete"),
    ("non-solicit", "non_solicitation"),
    ("solicit", "non_solicitation"),
    ("confiden", "confidentiality"),
    ("non-disclosure", "confidentiality"),
    ("indemnif", "indemnification"),
    ("liability", "liability"),
    ("limitation of liability", "liability"),
    ("intellectual property", "intellectual_property"),
    ("ip ", "intellectual_property"),
    ("patent", "intellectual_property"),
    ("copyright", "intellectual_property"),
    ("source code", "intellectual_property"),
    ("payment", "payment"),
    ("price", "payment"),
    ("fee", "payment"),
    ("govern", "governing_law"),
    ("jurisdiction", "governing_law"),
    ("dispute", "dispute_resolution"),
    ("arbitrat", "dispute_resolution"),
    ("warranty", "warranty"),
    ("warrant", "warranty"),
    ("insurance", "insurance"),
    ("assign", "assignment"),
    ("renewal", "auto_renewal"),
    ("auto-renew", "auto_renewal"),
    ("force majeure", "force_majeure"),
    ("data", "data_privacy"),
    ("privacy", "data_privacy"),
    ("amendment", "amendment"),
    ("entire agreement", "entire_agreement"),
    ("severab", "severability"),
]

# Instruction-tuning prompt template (matches Colab notebook Section 3)
_INSTRUCTION_TEMPLATE = """\
### Instruction:
You are a legal contract analysis AI. Extract contract clauses from the following text. \
Return a JSON array where each item has:
- "clause_type": one of [{clause_types}]
- "title": short descriptive title
- "text": the exact clause text
- "section_reference": section number if present (null if not)
- "obligations": list of objects with "party", "description", "type" (must/must_not/may)

### Input:
{contract_text}

### Response:
"""

_CLAUSE_TYPES_STR = (
    "confidentiality, termination, indemnification, liability, non_compete, "
    "non_solicitation, intellectual_property, payment, governing_law, "
    "dispute_resolution, force_majeure, data_privacy, warranty, insurance, "
    "assignment, amendment, entire_agreement, severability, auto_renewal, other"
)


# ---------------------------------------------------------------------------
# LoRATrainer
# ---------------------------------------------------------------------------

class LoRATrainer:
    """
    Open-weight LoRA fine-tuning pipeline for ContractIQ.

    Handles dataset preparation, Colab notebook generation, adapter loading,
    inference, and evaluation.  Training itself runs in Google Colab
    (see submit_training_job for details).

    For open-weight LoRA training, see this class.
    For OpenAI Fine-Tuning API training, see OpenAITrainer in trainer.py.
    """

    def __init__(self) -> None:
        self._model: Optional[Any] = None
        self._tokenizer: Optional[Any] = None
        self._adapter_path: Optional[str] = None
        self._executor = None  # ThreadPoolExecutor, created lazily

    # ------------------------------------------------------------------
    # Dataset building
    # ------------------------------------------------------------------

    def build_dataset_from_cuad(self, max_examples: int = 500) -> str:
        """
        Download CUAD from HuggingFace Hub and convert to instruction-tuning format.

        Args:
            max_examples: Maximum number of CUAD examples to include.

        Returns:
            Absolute path to the output JSONL file.
        """
        try:
            from datasets import load_dataset  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "datasets library is required. Run: pip install -r requirements-lora.txt"
            ) from exc

        output_dir = Path(__file__).parent.parent.parent.parent / "data" / "finetuning"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "lora_train.jsonl"

        logger.info("lora_dataset_build_start", max_examples=max_examples)

        dataset = load_dataset("theatticusproject/cuad", split="train", trust_remote_code=True)

        written = 0
        skipped = 0

        with open(output_path, "w", encoding="utf-8") as f:
            for example in dataset:
                if written >= max_examples:
                    break

                formatted = cuad_to_contractiq(example)
                if formatted is None:
                    skipped += 1
                    continue

                f.write(json.dumps(formatted) + "\n")
                written += 1

        logger.info(
            "lora_dataset_build_complete",
            written=written,
            skipped=skipped,
            output_path=str(output_path),
        )
        return str(output_path)

    # ------------------------------------------------------------------
    # Training job (Colab-delegated)
    # ------------------------------------------------------------------

    def submit_training_job(self, dataset_path: str) -> dict:
        """
        Validate dataset, optionally upload to HuggingFace Hub, and return
        instructions for running training in Google Colab.

        Since local GPU training is not available in production, this method:
          1. Validates the dataset file exists and has the correct format.
          2. Optionally uploads the dataset to HuggingFace Hub as a private dataset.
          3. Returns a structured response with Colab instructions.

        # TODO: Replace with Modal / RunPod API call for automated training
        # in production.  The dataset upload + notebook generation logic here
        # is the correct entry point — just swap the return value for an
        # async GPU job submission.

        Args:
            dataset_path: Path to the instruction-tuning JSONL file.

        Returns:
            dict with status, dataset_url, notebook_path, and instructions.
        """
        path = Path(dataset_path)
        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {dataset_path}")

        # Validate format
        valid_count = 0
        invalid_count = 0
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 50:  # Sample first 50
                    break
                try:
                    obj = json.loads(line)
                    required = {"prompt", "response"}
                    if not required.issubset(obj.keys()):
                        invalid_count += 1
                    else:
                        valid_count += 1
                except json.JSONDecodeError:
                    invalid_count += 1

        if invalid_count > valid_count:
            raise ValueError(
                f"Dataset format validation failed: {invalid_count} invalid lines "
                f"vs {valid_count} valid (expected {{prompt, response}} keys)"
            )

        notebook_path = (
            Path(__file__).parent.parent.parent.parent.parent
            / "notebooks"
            / "contractiq_lora_finetune.ipynb"
        )

        instructions = (
            "The LoRA adapter is already deployed at:\n"
            f"  https://huggingface.co/{HF_ADAPTER_ID}\n\n"
            "To re-train with new data:\n"
            "1. Open notebooks/contractiq_lora_finetune.ipynb in Google Colab\n"
            "2. Upload the dataset file to Colab (or mount Google Drive)\n"
            "3. Set your HuggingFace token in the Setup cell\n"
            "4. Run all cells — training takes ~45-90 min on a free T4 GPU\n"
            "5. The new LoRA adapter will be pushed to HuggingFace Hub automatically\n"
            "6. Update LOCAL_LORA_ADAPTER_PATH in .env if using a different adapter path\n"
            "7. Set LLM_PROVIDER=local_lora and restart the backend\n\n"
            "Current adapter: LOCAL_LORA_ADAPTER_PATH=iakshayrathee/contractiq-lora-llama3"
        )


        logger.info(
            "lora_training_job_deferred",
            dataset_path=str(path),
            valid_examples=valid_count,
            status="colab_required",
        )

        return {
            "status": "colab_required",
            "dataset_path": str(path),
            "dataset_examples": valid_count,
            "notebook_path": str(notebook_path) if notebook_path.exists() else None,
            "instructions": instructions,
            "message": (
                "Local GPU training is not available. Open the Colab notebook "
                "and follow the instructions to train on a free T4 GPU."
            ),
        }

    # ------------------------------------------------------------------
    # Adapter loading
    # ------------------------------------------------------------------

    def load_adapter(self, adapter_path: str) -> None:
        """
        Load a LoRA adapter from a local directory or HuggingFace Hub ID.

        Uses 4-bit quantization (BitsAndBytesConfig) if a CUDA GPU is
        available, otherwise falls back to CPU with float32.

        Requires: pip install -r requirements-lora.txt

        Args:
            adapter_path: Local path to adapter dir, or HF Hub model ID
                          (e.g. "username/contractiq-lora-llama3").
        """
        try:
            import torch  # type: ignore[import-untyped]
            from peft import PeftModel  # type: ignore[import-untyped]
            from transformers import (  # type: ignore[import-untyped]
                AutoModelForCausalLM,
                AutoTokenizer,
                BitsAndBytesConfig,
            )
        except ImportError as exc:
            raise ImportError(
                "peft, transformers, and bitsandbytes are required to load a LoRA adapter. "
                "Run: pip install -r requirements-lora.txt"
            ) from exc

        logger.info("lora_adapter_loading", adapter_path=adapter_path)

        use_gpu = torch.cuda.is_available()
        device_map = "auto" if use_gpu else "cpu"

        if use_gpu:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
            model_kwargs: dict = {
                "quantization_config": quantization_config,
                "device_map": device_map,
            }
        else:
            model_kwargs = {
                "torch_dtype": torch.float32,
                "device_map": device_map,
            }

        base_model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL_ID,
            **model_kwargs,
        )
        self._tokenizer = AutoTokenizer.from_pretrained(
            adapter_path,
            trust_remote_code=True,
        )
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        self._model = PeftModel.from_pretrained(base_model, adapter_path)
        self._model.eval()
        self._adapter_path = adapter_path

        logger.info(
            "lora_adapter_loaded",
            adapter_path=adapter_path,
            device="cuda" if use_gpu else "cpu",
        )

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def _sync_run_inference(self, text: str) -> list[dict]:
        """Synchronous inference — called via run_in_executor."""
        if self._model is None or self._tokenizer is None:
            raise RuntimeError("Adapter not loaded. Call load_adapter() first.")

        try:
            import torch  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError("torch is required for inference.") from exc

        from app.config import get_settings
        settings = get_settings()

        prompt = _INSTRUCTION_TEMPLATE.format(
            clause_types=_CLAUSE_TYPES_STR,
            contract_text=text[:1500],
        )

        inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_SEQ_LENGTH,
        )
        device = next(self._model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=settings.local_lora_max_new_tokens,
                temperature=max(settings.local_lora_temperature, 1e-6),
                do_sample=settings.local_lora_temperature > 0.0,
                pad_token_id=self._tokenizer.pad_token_id,
            )

        # Decode only the newly generated tokens (not the prompt)
        input_len = inputs["input_ids"].shape[1]
        generated = outputs[0][input_len:]
        raw_text = self._tokenizer.decode(generated, skip_special_tokens=True)

        return _parse_clause_json(raw_text)

    async def run_inference(self, text: str) -> list[dict]:
        """
        Run clause extraction inference using the loaded LoRA adapter.

        Wraps synchronous transformers inference in asyncio.run_in_executor
        so it does not block the FastAPI event loop.

        Returns:
            List of clause dicts matching ContractIQ's Clause schema
            (clause_type, title, text, section_reference, obligations).
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_run_inference, text)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    async def evaluate_adapter(
        self,
        adapter_path: str,
        test_data_path: str,
    ) -> dict:
        """
        Evaluate a LoRA adapter against the held-out test set.

        Reuses the same F1 logic as backend/app/finetuning/evaluator.py
        (_compute_f1_score) and returns metrics in the same format as the
        existing eval reporter.

        Args:
            adapter_path: Local path or HF Hub ID of the LoRA adapter.
            test_data_path: Path to test.jsonl (instruction-tuning format).

        Returns:
            Metrics dict: {f1, precision, recall, per_type_f1, avg_latency_ms}
        """
        if self._model is None:
            self.load_adapter(adapter_path)

        test_path = Path(test_data_path)
        if not test_path.exists():
            raise FileNotFoundError(f"Test data not found: {test_data_path}")

        test_examples: list[dict] = []
        with open(test_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    test_examples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        test_examples = test_examples[:50]  # Match Colab notebook Section 5
        logger.info("lora_eval_start", n_examples=len(test_examples))

        all_predicted: list[dict] = []
        all_ground_truth: list[dict] = []
        latencies: list[float] = []

        for ex in test_examples:
            prompt = ex.get("prompt", "")
            # Extract the contract text from the prompt (between ### Input: and ### Response:)
            contract_text = _extract_input_from_prompt(prompt)
            ground_truth_raw = ex.get("response", "[]")

            t0 = time.perf_counter()
            predicted = await self.run_inference(contract_text)
            latencies.append((time.perf_counter() - t0) * 1000)

            try:
                if isinstance(ground_truth_raw, str):
                    gt_data = json.loads(ground_truth_raw)
                else:
                    gt_data = ground_truth_raw
                if isinstance(gt_data, dict):
                    gt_data = [gt_data]
                all_ground_truth.extend(gt_data)
            except (json.JSONDecodeError, TypeError):
                pass

            all_predicted.extend(predicted)

        f1_results = _compute_f1_score(all_predicted, all_ground_truth)
        per_type_f1 = _compute_per_type_f1(all_predicted, all_ground_truth)

        avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0

        metrics = {
            "model": "llama-3.2-3b-lora",
            "adapter_path": adapter_path,
            "f1": f1_results["f1"],
            "precision": f1_results["precision"],
            "recall": f1_results["recall"],
            "per_type_f1": per_type_f1,
            "avg_latency_ms": avg_latency_ms,
            "n_examples": len(test_examples),
            "meets_threshold": f1_results["f1"] >= 0.70,
        }

        logger.info(
            "lora_eval_complete",
            f1=round(f1_results["f1"], 3),
            precision=round(f1_results["precision"], 3),
            recall=round(f1_results["recall"], 3),
            avg_latency_ms=round(avg_latency_ms, 1),
        )

        return metrics


# ---------------------------------------------------------------------------
# Helpers (module-level, reused by Colab notebook logic)
# ---------------------------------------------------------------------------

def cuad_to_contractiq(example: dict) -> Optional[dict]:
    """
    Convert a single CUAD QA example to ContractIQ instruction-tuning format.

    CUAD schema:
        context:  contract text passage
        question: clause-type question (e.g. "Termination for Convenience")
        answers:  {text: [...], answer_start: [...]}

    Returns None if the example has no extracted answer text (clause absent).
    """
    question: str = example.get("question", "").lower()
    answers: dict = example.get("answers", {})
    answer_texts: list[str] = answers.get("text", [])

    # Skip examples where no clause is present
    if not answer_texts or not any(t.strip() for t in answer_texts):
        return None

    # Map CUAD question to ContractIQ clause type
    clause_type = "other"
    for fragment, ct in _CUAD_QUESTION_MAP:
        if fragment in question:
            clause_type = ct
            break

    context: str = example.get("context", "")[:1500]
    clause_text = answer_texts[0].strip()

    # Build a minimal ground-truth response JSON
    response_json = json.dumps([
        {
            "clause_type": clause_type,
            "title": clause_type.replace("_", " ").title(),
            "text": clause_text[:500],
            "section_reference": None,
            "obligations": [],
        }
    ])

    prompt = _INSTRUCTION_TEMPLATE.format(
        clause_types=_CLAUSE_TYPES_STR,
        contract_text=context,
    )

    return {
        "prompt": prompt,
        "response": response_json,
        "metadata": {
            "source": "cuad",
            "clause_type": clause_type,
            "original_question": example.get("question", ""),
        },
    }


def _parse_clause_json(raw_text: str) -> list[dict]:
    """
    Parse JSON clause array from model output.

    Handles common model output quirks: markdown fences, single-object
    responses, trailing text after the JSON block.

    Returns an empty list if parsing fails — never raises.
    """
    text = raw_text.strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Try to extract the first JSON array/object from the text
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        if start == -1:
            continue
        # Walk to find balanced closing bracket
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        snippet = text[start : i + 1]
                        data = json.loads(snippet)
                        if isinstance(data, dict):
                            return [data]
                        if isinstance(data, list):
                            return data
                    except json.JSONDecodeError:
                        pass
                    break

    logger.warning("lora_json_parse_failed", raw_text_preview=raw_text[:200])
    return []


def _extract_input_from_prompt(prompt: str) -> str:
    """Extract the contract text from between ### Input: and ### Response:."""
    try:
        start = prompt.index("### Input:\n") + len("### Input:\n")
        end = prompt.index("\n### Response:")
        return prompt[start:end].strip()
    except ValueError:
        return prompt


def _compute_f1_score(predicted: list[dict], ground_truth: list[dict]) -> dict:
    """
    Compute F1, precision, and recall for clause extraction.

    Matches by clause_type field. Mirrors the logic in evaluator.py
    _compute_f1_score() so results are directly comparable.
    """
    from collections import Counter

    pred_types = Counter(
        c.get("clause_type", "other") for c in predicted
    )
    true_types = Counter(
        c.get("clause_type", "other") for c in ground_truth
    )

    all_types = set(pred_types.keys()) | set(true_types.keys())
    tp = sum(min(pred_types[t], true_types[t]) for t in all_types)
    fp = sum(max(0, pred_types[t] - true_types[t]) for t in all_types)
    fn = sum(max(0, true_types[t] - pred_types[t]) for t in all_types)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {"f1": f1, "precision": precision, "recall": recall,
            "tp": tp, "fp": fp, "fn": fn}


def _compute_per_type_f1(
    predicted: list[dict], ground_truth: list[dict]
) -> dict[str, dict]:
    """Compute F1 breakdown per clause type."""
    from app.schemas.contract import ClauseType

    per_type: dict[str, dict] = {}
    for clause_type in ClauseType:
        ct_val = clause_type.value
        pred_for_type = [c for c in predicted if c.get("clause_type") == ct_val]
        true_for_type = [c for c in ground_truth if c.get("clause_type") == ct_val]
        if true_for_type:
            per_type[ct_val] = _compute_f1_score(pred_for_type, true_for_type)
    return per_type
