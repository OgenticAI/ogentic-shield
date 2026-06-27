"""Submit and monitor a LoRA fine-tuning job on Together AI.

Reads the fine-tuning JSONL files prepared by ``prepare_finetune_data.py``,
uploads them to Together AI, starts a LoRA fine-tuning job, and polls until
completion. Writes the resulting model ID to stdout so it can be piped to
``eval_finetuned.py``.

Requirements:
  - TOGETHER_API_KEY environment variable set to your Together AI API key
  - Fine-tuning JSONL files in benchmarks/bakeoff/finetune_data/ (from prepare_finetune_data.py)
  - ``requests`` package (available transitively via presidio)

Budget guardrail: Phase 1 target is <=500 USD total across both platforms.
Use Together AI's cost estimator before running:
  https://api.together.ai/v1/fine-tuning/estimate (or the web UI)

Usage:
    export TOGETHER_API_KEY=your_key
    python benchmarks/bakeoff/run_together_finetune.py --domain legal_privilege
    python benchmarks/bakeoff/run_together_finetune.py --domain therapy_phi --model Qwen/Qwen3-8B
    python benchmarks/bakeoff/run_together_finetune.py --dry-run  # print config only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

BAKEOFF_DIR = Path(__file__).parent
DEFAULT_FINETUNE_DIR = BAKEOFF_DIR / "finetune_data"

TOGETHER_BASE_URL = "https://api.together.xyz/v1"

# Default model for fine-tuning — Qwen3 8B class as specified in OGE-794.
# Override with --model if a different checkpoint is preferred.
DEFAULT_MODEL = "Qwen/Qwen3-8B"

# Together AI LoRA defaults for this bake-off.
LORA_DEFAULT_RANK = 16
LORA_DEFAULT_ALPHA = 32
DEFAULT_EPOCHS = 3
DEFAULT_LEARNING_RATE = 2e-5
DEFAULT_BATCH_SIZE = 8
POLL_INTERVAL_SECONDS = 30


def _get_headers() -> dict[str, str]:
    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        sys.exit("Error: TOGETHER_API_KEY environment variable not set.")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _upload_file(path: Path, headers: dict[str, str]) -> str:
    """Upload a JSONL file to Together AI and return the file ID."""
    try:
        import requests
    except ImportError:
        sys.exit("Error: 'requests' package not available. Install with: pip install requests")

    print(f"  Uploading {path.name} ({path.stat().st_size // 1024}KB)...", end=" ", flush=True)
    with open(path, "rb") as f:
        resp = requests.post(
            f"{TOGETHER_BASE_URL}/files",
            headers={"Authorization": headers["Authorization"]},
            files={"file": (path.name, f, "application/jsonl")},
            data={"purpose": "fine-tune"},
            timeout=120,
        )
    resp.raise_for_status()
    file_id = resp.json()["id"]
    print(f"OK -> {file_id}")
    return file_id


def _start_finetune(
    train_file_id: str,
    val_file_id: str,
    model: str,
    suffix: str,
    headers: dict[str, str],
    n_epochs: int,
    learning_rate: float,
    batch_size: int,
) -> str:
    """Start a LoRA fine-tuning job and return the job ID."""
    try:
        import requests
    except ImportError:
        sys.exit("Error: 'requests' package not available.")

    payload = {
        "model": model,
        "training_file": train_file_id,
        "validation_file": val_file_id,
        "n_epochs": n_epochs,
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "suffix": suffix,
        "lora": True,
        "lora_rank": LORA_DEFAULT_RANK,
        "lora_alpha": LORA_DEFAULT_ALPHA,
    }
    print(f"  Starting fine-tune job: {json.dumps(payload, indent=2)}")
    resp = requests.post(
        f"{TOGETHER_BASE_URL}/fine-tuning/jobs",
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    job_id = resp.json()["id"]
    print(f"  Job created: {job_id}")
    return job_id


def _poll_job(job_id: str, headers: dict[str, str]) -> dict:
    """Poll a fine-tuning job until it reaches a terminal state."""
    try:
        import requests
    except ImportError:
        sys.exit("Error: 'requests' package not available.")

    terminal_states = {"succeeded", "failed", "cancelled"}
    attempt = 0
    while True:
        resp = requests.get(
            f"{TOGETHER_BASE_URL}/fine-tuning/jobs/{job_id}",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        job = resp.json()
        status = job.get("status", "unknown")
        attempt += 1

        elapsed_min = attempt * POLL_INTERVAL_SECONDS // 60
        print(
            f"  [{elapsed_min:3d}m] status={status}  "
            f"trained_tokens={job.get('trained_tokens', '?')}",
            flush=True,
        )

        if status in terminal_states:
            return job

        time.sleep(POLL_INTERVAL_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--domain",
        choices=["legal_privilege", "therapy_phi", "finance_mnpi", "all"],
        default="all",
        help="Domain to fine-tune on (default: all — fine-tunes one combined job)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Base model to fine-tune (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--finetune-dir",
        type=Path,
        default=DEFAULT_FINETUNE_DIR,
        help=f"Directory containing prepared fine-tuning JSONL files (default: {DEFAULT_FINETUNE_DIR})",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=DEFAULT_EPOCHS,
        help=f"Number of training epochs (default: {DEFAULT_EPOCHS})",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=DEFAULT_LEARNING_RATE,
        help=f"Learning rate (default: {DEFAULT_LEARNING_RATE})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Batch size (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print configuration without uploading or starting a job",
    )
    args = parser.parse_args()

    # Determine which files to use
    if args.domain == "all":
        train_files = sorted(args.finetune_dir.glob("*_together_train.jsonl"))
        val_files = sorted(args.finetune_dir.glob("*_together_val.jsonl"))
        suffix = "shield-all"
    else:
        train_files = [args.finetune_dir / f"{args.domain}_together_train.jsonl"]
        val_files = [args.finetune_dir / f"{args.domain}_together_val.jsonl"]
        suffix = f"shield-{args.domain.replace('_', '-')}"

    missing = [p for p in train_files + val_files if not p.exists()]
    if missing:
        print("Error: Missing files (run prepare_finetune_data.py first):")
        for p in missing:
            print(f"  {p}")
        return 1

    train_count = sum(sum(1 for line in open(p) if line.strip()) for p in train_files)
    val_count = sum(sum(1 for line in open(p) if line.strip()) for p in val_files)

    print("Together AI LoRA fine-tuning — OGE-794 bake-off")
    print(f"  Base model:    {args.model}")
    print(f"  Domain:        {args.domain}")
    print(f"  Suffix:        {suffix}")
    print(f"  Train samples: {train_count}")
    print(f"  Val samples:   {val_count}")
    print(f"  Epochs:        {args.epochs}")
    print(f"  Learning rate: {args.learning_rate}")
    print(f"  Batch size:    {args.batch_size}")
    print(f"  LoRA rank:     {LORA_DEFAULT_RANK}, alpha: {LORA_DEFAULT_ALPHA}")
    print()

    if args.dry_run:
        print("DRY RUN — no API calls made. Set TOGETHER_API_KEY and remove --dry-run to proceed.")
        return 0

    headers = _get_headers()

    # For multi-domain "all" mode, concatenate all train/val files into temporary combined files
    if args.domain == "all" and len(train_files) > 1:
        combined_train = Path(args.finetune_dir / "_combined_together_train.jsonl")
        combined_val = Path(args.finetune_dir / "_combined_together_val.jsonl")
        with open(combined_train, "w") as out:
            for p in train_files:
                out.write(p.read_text())
        with open(combined_val, "w") as out:
            for p in val_files:
                out.write(p.read_text())
        upload_train = combined_train
        upload_val = combined_val
    else:
        upload_train = train_files[0]
        upload_val = val_files[0]

    print("Uploading training data...")
    train_file_id = _upload_file(upload_train, headers)
    val_file_id = _upload_file(upload_val, headers)

    print("\nStarting LoRA fine-tuning job...")
    job_id = _start_finetune(
        train_file_id, val_file_id, args.model, suffix, headers,
        args.epochs, args.learning_rate, args.batch_size,
    )

    print(f"\nPolling job {job_id} (every {POLL_INTERVAL_SECONDS}s)...")
    job = _poll_job(job_id, headers)

    if job.get("status") == "succeeded":
        model_id = job.get("fine_tuned_model", "")
        print("\nFine-tuning succeeded!")
        print(f"  Model ID: {model_id}")
        print(f"  Job ID:   {job_id}")
        print(model_id)  # stdout for piping to eval_finetuned.py
        return 0
    else:
        print(f"\nFine-tuning failed: status={job.get('status')}")
        print(json.dumps(job, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
