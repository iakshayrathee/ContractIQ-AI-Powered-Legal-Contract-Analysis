"""
Click CLI for fine-tuning and evaluation operations.

Commands:
  build-dataset       Process CUAD and build LoRA training dataset
  evaluate            Run two-model comparison evaluation (GPT-4o, GPT-4o-mini)
  lora-build-dataset  Download CUAD from HuggingFace Hub, build instruction-tuning JSONL
  lora-evaluate       Evaluate a LoRA adapter against held-out test set
  lora-serve          Start local REST inference server for a LoRA adapter
"""

import asyncio
import logging
from pathlib import Path

import click

from app.finetuning.dataset_builder import DatasetBuilder
from app.finetuning.evaluator import run_evaluation

logger = logging.getLogger(__name__)


@click.group()
def cli():
    """ContractIQ Fine-Tuning CLI"""
    logging.basicConfig(level=logging.INFO)


@cli.command("build-dataset")
@click.option("--max-cuad", type=int, default=None, help="Max CUAD examples to process (for testing)")
@click.option("--output-dir", type=click.Path(), default=None, help="Output directory for JSONL files")
def build_dataset_cmd(max_cuad, output_dir):
    """
    Build CUAD-based training dataset for LoRA fine-tuning.

    Downloads and processes the CUAD dataset, converts to instruction-tuning
    format (### Instruction / ### Input / ### Response), and saves to
    data/finetuning/lora_train.jsonl.

    Note: Silver labels and synthetic data generation have been removed.
    The LoRA pipeline trains on CUAD gold labels only.
    """
    click.echo("Building dataset from CUAD...")

    from app.finetuning.data.cuad_processor import process_cuad_dataset

    async def _build():
        base_path = Path(__file__).parent.parent.parent.parent / "data" / "finetuning" / "sources"

        # Step 1: CUAD processing
        click.echo("Processing CUAD dataset...")
        cuad_path = await process_cuad_dataset(
            output_path=base_path / "cuad_processed.jsonl",
            max_examples=max_cuad,
        )
        click.echo(f"CUAD processed: {cuad_path}")

        # Step 2: Build LoRA instruction-tuning format
        click.echo("Converting to LoRA instruction format...")
        out_dir = Path(output_dir) if output_dir else None
        db = DatasetBuilder()
        lora_path = db.build_lora_format(
            output_path=str(out_dir / "lora_train.jsonl") if out_dir else None,
            cuad_path=cuad_path,
        )

        click.echo(f"\nDataset build complete!")
        click.echo(f"  LoRA training data: {lora_path}")
        click.echo("\nNext step:")
        click.echo("  Open notebooks/contractiq_lora_finetune.ipynb in Google Colab")

    asyncio.run(_build())


@cli.command("evaluate")
@click.option("--test-data", type=click.Path(exists=False), default=None,
              help="Path to test JSONL. Defaults to data/finetuning/lora_train.jsonl.")
def evaluate_cmd(test_data):
    """
    Run two-model comparison evaluation (GPT-4o, GPT-4o-mini).

    Evaluates extraction quality (F1), hallucination rate, consistency,
    and cost/latency. Results saved to data/finetuning/eval_comparison.json
    and eval_comparison.md.

    Note: The fine-tuned GPT-4o-mini column has been removed.
    Use 'lora-evaluate' to add a Llama-3.2-3B LoRA column.
    """
    click.echo("Running evaluation...")

    async def _eval():
        output_dir = Path(__file__).parent.parent.parent.parent / "data" / "finetuning"
        output_dir.mkdir(parents=True, exist_ok=True)

        test_path = Path(test_data) if test_data else output_dir / "lora_train.jsonl"
        if not test_path.exists():
            # Fall back to any available test data
            test_path = output_dir / "test.jsonl"

        if not test_path.exists():
            click.echo(
                "Error: No test data found. Run 'build-dataset' or 'lora-build-dataset' first.",
                err=True,
            )
            raise SystemExit(1)

        results = await run_evaluation(test_path, None, output_dir)

        click.echo("Evaluation complete!")
        click.echo(f"Results: {output_dir / 'eval_comparison.json'}")
        click.echo(f"Report:  {output_dir / 'eval_comparison.md'}")

        for model_name, data in results.items():
            click.echo(f"\n{model_name}:")
            click.echo(f"  F1: {data['f1']['f1']:.3f}")
            click.echo(f"  Cost/1000 docs: ${data['cost']['cost_per_1000_docs']:.2f}")

    asyncio.run(_eval())


# ---------------------------------------------------------------------------
# LoRA commands (open-weight fine-tuning pipeline)
# ---------------------------------------------------------------------------

@cli.command("lora-build-dataset")
@click.option(
    "--max-examples",
    type=int,
    default=500,
    show_default=True,
    help="Maximum number of CUAD examples to convert.",
)
def lora_build_dataset(max_examples):
    """
    Download CUAD and build instruction-tuning dataset for LoRA training.

    Downloads theatticusproject/cuad from HuggingFace Hub, converts each
    example to ContractIQ's instruction format (### Instruction / ### Input /
    ### Response), and saves to data/finetuning/lora_train.jsonl.

    Requires: pip install -r requirements-lora.txt  (datasets library)
    """
    click.echo(f"Building LoRA dataset from CUAD (max {max_examples} examples)...")

    try:
        from app.finetuning.lora_trainer import LoRATrainer
    except ImportError:
        click.echo(
            "Error: datasets library not installed.\n"
            "Run: pip install -r requirements-lora.txt",
            err=True,
        )
        raise SystemExit(1)

    trainer = LoRATrainer()
    output_path = trainer.build_dataset_from_cuad(max_examples=max_examples)

    click.echo(f"Dataset saved to: {output_path}")
    click.echo("\nNext step:")
    click.echo("  Open notebooks/contractiq_lora_finetune.ipynb in Google Colab")


@cli.command("lora-evaluate")
@click.option(
    "--adapter-path",
    type=str,
    required=True,
    help="Path to local LoRA adapter directory or HuggingFace Hub model ID.",
)
@click.option(
    "--test-data",
    type=click.Path(exists=False),
    default=None,
    help="Path to test JSONL. Defaults to data/finetuning/lora_train.jsonl.",
)
def lora_evaluate(adapter_path, test_data):
    """
    Evaluate a LoRA adapter and append results to eval_comparison.json.

    Loads the adapter, runs inference on the held-out test set, computes
    F1 / precision / recall, and appends a 'lora_llama3' column to the
    existing eval_comparison.json report.

    Requires: pip install -r requirements-lora.txt
    """
    click.echo(f"Evaluating LoRA adapter: {adapter_path}")

    async def _eval():
        from app.finetuning.evaluator import compare_with_lora
        output_dir = Path(__file__).parent.parent.parent.parent / "data" / "finetuning"
        test_path = Path(test_data) if test_data else None

        results = await compare_with_lora(
            lora_adapter_path=adapter_path,
            test_path=test_path,
            output_dir=output_dir,
        )

        click.echo("\nLoRA Evaluation Results:")
        click.echo(f"  F1:        {results['f1']['f1']:.3f}")
        click.echo(f"  Precision: {results['f1']['precision']:.3f}")
        click.echo(f"  Recall:    {results['f1']['recall']:.3f}")
        click.echo(f"  Avg Latency: {results['avg_latency_ms']:.0f}ms")
        meets = results['meets_f1_threshold']
        click.echo(f"  Meets F1 threshold (>=0.70): {meets}")
        click.echo(f"\nResults appended to {output_dir / 'eval_comparison.json'}")

    asyncio.run(_eval())


@cli.command("lora-serve")
@click.option(
    "--adapter-path",
    type=str,
    required=True,
    help="Path to local LoRA adapter directory or HuggingFace Hub model ID.",
)
@click.option(
    "--port",
    type=int,
    default=8001,
    show_default=True,
    help="Port to run the inference micro-server on.",
)
@click.option(
    "--host",
    type=str,
    default="127.0.0.1",
    show_default=True,
    help="Host address to bind to.",
)
def lora_serve(adapter_path, port, host):
    """
    Serve a LoRA adapter as a local REST inference endpoint.

    Starts a lightweight FastAPI micro-server on the specified port
    with a POST /extract endpoint that accepts contract text and returns
    extracted clause JSON.

    Endpoint:
        POST http://localhost:{port}/extract
        Body: {"text": "<contract text>"}
        Response: {"clauses": [...]}

    Requires: pip install -r requirements-lora.txt
    """
    click.echo(f"Loading LoRA adapter: {adapter_path}")
    click.echo(f"Starting inference server on {host}:{port} ...")

    try:
        from app.finetuning.lora_trainer import LoRATrainer
        import uvicorn  # type: ignore[import-untyped]
        from fastapi import FastAPI
        from pydantic import BaseModel as _BaseModel
    except ImportError as e:
        click.echo(
            f"Error: Missing dependency - {e}\n"
            "Run: pip install -r requirements-lora.txt",
            err=True,
        )
        raise SystemExit(1)

    trainer = LoRATrainer()
    trainer.load_adapter(adapter_path)
    click.echo(f"Adapter loaded. Server ready at http://{host}:{port}/extract")

    app = FastAPI(
        title="ContractIQ LoRA Inference Server",
        description="Local LoRA adapter inference endpoint for ContractIQ.",
        version="1.0.0",
    )

    class ExtractRequest(_BaseModel):
        text: str

    class ExtractResponse(_BaseModel):
        clauses: list
        model: str
        adapter_path: str

    @app.post("/extract", response_model=ExtractResponse)
    async def extract(request: ExtractRequest):
        clauses = await trainer.run_inference(request.text)
        return ExtractResponse(
            clauses=clauses,
            model="llama-3.2-3b-lora",
            adapter_path=adapter_path,
        )

    @app.get("/health")
    async def health():
        return {"status": "ok", "adapter": adapter_path}

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    cli()
