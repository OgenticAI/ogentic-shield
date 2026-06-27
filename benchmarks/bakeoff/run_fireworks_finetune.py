"""Submit and monitor a LoRA fine-tuning job on Fireworks AI.

Mirrors ``run_together_finetune.py`` for the Fireworks platform so the two
runs use identical training data, model class, and hyperparameters — the only
variable is the platform. This is the bake-off design: same inputs, measure
platform differences.

Requirements:
  - FIREWORKS_API_KEY environment variable
  - FIREWORKS_ACCOUNT_ID environment variable (your Fireworks account slug)
  - Fine-tuning JSONL files in benchmarks/bakeoff/finetune_data/ (from prepare_finetune_data.py)
  - ``requests`` package

Budget guardrail: Phase 1 target is <=500 USD total across both platforms.

Fireworks fine-tuning docs:
  https://docs.fireworks.ai/fine-tuning/fine-tuning-models

Usage:
    export FIREWORKS_API_KEY=your_key
    export FIREWORKS_ACCOUNT_ID=your_account
    python benchmarks/bakeoff/run_fireworks_finetune.py --domain legal_privilege
    python benchmarks/bakeoff/run_fireworks_finetune.py --dry-run
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

FIREWORKS_BASE_URL = "https://api.fireworks.ai/v1"

DEFAULT_MODEL = "accounts/fireworks/models/qwen3-8b"
LORA_DEFAULT_RANK = 16
DEFAULT_EPOCHS = 3
DEFAULT_LEARNING_RATE = 2e-5
DEFAULT_BATCH_SIZE = 8
POLL_INTERVAL_SECONDS = 30


def _get_credentials() -> tuple[str, str]:
    api_key = os.environ.get("FIREWORKS_API_KEY")
    account_id = os.environ.get("FIREWORKS_ACCOUNT_ID")
    if not api_key:
        sys.exit("Error: FIREWORKS_API_KEY environment variable not set.")
    if not account_id:
        sys.exit("Error: FIREWORKS_ACCOUNT_ID environment variable not set.")
    return api_key, account_id


def _get_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _upload_dataset(path: Path, api_key: str, account_id: str) -> str:
    """Upload a JSONL dataset to Fireworks and return the dataset ID."""
    try:
        import requests
    except ImportError:
        sys.exit("Error: 'requests' package not available.")

    upload_url = f"{FIREWORKS_BASE_URL}/accounts/{account_id}/datasets"
    print(f"  Uploading {path.name} ({path.stat().st_size // 1024}KB)...", end=" ", flush=True)
    with open(path, "rb") as f:
        resp = requests.post(
            upload_url,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (path.name, f, "application/jsonl")},
            data={"datasetId": path.stem.replace("_", "-")},
            timeout=120,
        )
    resp.raise_for_status()
    dataset_id = resp.json().get("datasetId") or resp.json().get("id")
    print(f"OK -> {dataset_id}")
    return dataset_id


def _start_finetune(
    dataset_id: str,
    model: str,
    suffix: str,
    api_key: str,
    account_id: str,
    n_epochs: int,
    learning_rate: float,
    batch_size: int,
) -> str:
    """Start a LoRA fine-tuning job on Fireworks and return the job ID."""
    try:
        import requests
    except ImportError:
        sys.exit("Error: 'requests' package not available.")

    payload = {
        "settings": {
            "base_model": model,
            "epochs": n_epochs,
            "learning_rate": learning_rate,
            "batch_size": batch_size,
            "lora": {"rank": LORA_DEFAULT_RANK},
        },
        "dataset_id": dataset_id,
        "output_model_id": f"{account_id}/models/{suffix}",
    }
    url = f"{FIREWORKS_BASE_URL}/accounts/{account_id}/fineTuningJobs"
    print(f"  Starting fine-tune job: {json.dumps(payload, indent=2)}")
    resp = requests.post(
        url,
        headers=_get_headers(api_key),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    job_id = resp.json().get("jobId") or resp.json().get("id")
    print(f"  Job created: {job_id}")
    return job_id


def _poll_job(job_id: str, api_key: str, account_id: str) -> dict:
    """Poll a Fireworks fine-tuning job until it reaches a terminal state."""
    try:
        import requests
    except ImportError:
        sys.exit("Error: 'requests' package not available.")

    terminal_states = {"COMPLETED", "FAILED", "CANCELLED", "completed", "failed", "cancelled"}
    attempt = 0
    url = f"{FIREWORKS_BASE_URL}/accounts/{account_id}/fineTuningJobs/{job_id}"
    while True:
        resp = requests.get(url, headers=_get_headers(api_key), timeout=30)
        resp.raise_for_status()
        job = resp.json()
        status = job.get("status", "UNKNOWN")
        attempt += 1
        elapsed_min = attempt * POLL_INTERVAL_SECONDS // 60
        print(
            f"  [{elapsed_min:3d}m] status={status}  "
            f"progress={job.get('progress', '?')}",
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
        help="Domain to fine-tune on (default: all)",
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
        help=f"Directory containing fine-tuning JSONL files (default: {DEFAULT_FINETUNE_DIR})",
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
        help="Print configuration without making API calls",
    )
    args = parser.parse_args()

    if args.domain == "all":
        train_files = sorted(args.finetune_dir.glob("*_fireworks_train.jsonl"))
        val_files = sorted(args.finetune_dir.glob("*_fireworks_val.jsonl"))
        suffix = "shield-all-lora"
    else:
        train_files = [args.finetune_dir / f"{args.domain}_fireworks_train.jsonl"]
        val_files = [args.finetune_dir / f"{args.domain}_fireworks_val.jsonl"]
        suffix = f"shield-{args.domain.replace('_', '-')}-lora"

    missing = [p for p in train_files + val_files if not p.exists()]
    if missing:
        print("Error: Missing files (run prepare_finetune_data.py first):")
        for p in missing:
            print(f"  {p}")
        return 1

    train_count = sum(sum(1 for line in open(p) if line.strip()) for p in train_files)
    val_count = sum(sum(1 for line in open(p) if line.strip()) for p in val_files)

    print("Fireworks AI LoRA fine-tuning — OGE-794 bake-off")
    print(f"  Base model:    {args.model}")
    print(f"  Domain:        {args.domain}")
    print(f"  Suffix:        {suffix}")
    print(f"  Train samples: {train_count}")
    print(f"  Val samples:   {val_count}")
    print(f"  Epochs:        {args.epochs}")
    print(f"  Learning rate: {args.learning_rate}")
    print(f"  Batch size:    {args.batch_size}")
    print(f"  LoRA rank:     {LORA_DEFAULT_RANK}")
    print()

    if args.dry_run:
        print("DRY RUN — no API calls made.")
        return 0

    api_key, account_id = _get_credentials()

    # Upload combined dataset for "all" mode
    if args.domain == "all" and len(train_files) > 1:
        combined_train = args.finetune_dir / "_combined_fireworks_train.jsonl"
        combined_val = args.finetune_dir / "_combined_fireworks_val.jsonl"
        with open(combined_train, "w") as out:
            for p in train_files:
                out.write(p.read_text())
        with open(combined_val, "w") as out:
            for p in val_files:
                out.write(p.read_text())
        upload_train = combined_train
    else:
        upload_train = train_files[0]

    print("Uploading training data...")
    dataset_id = _upload_dataset(upload_train, api_key, account_id)

    print("\nStarting LoRA fine-tuning job...")
    job_id = _start_finetune(
        dataset_id, args.model, suffix, api_key, account_id,
        args.epochs, args.learning_rate, args.batch_size,
    )

    print(f"\nPolling job {job_id} (every {POLL_INTERVAL_SECONDS}s)...")
    job = _poll_job(job_id, api_key, account_id)

    status = job.get("status", "").upper()
    if status == "COMPLETED":
        model_id = job.get("outputModelId") or job.get("output_model_id", "")
        print("\nFine-tuning succeeded!")
        print(f"  Model ID: {model_id}")
        print(f"  Job ID:   {job_id}")
        print(model_id)  # stdout for piping to eval_finetuned.py
        return 0
    else:
        print(f"\nFine-tuning failed: status={status}")
        print(json.dumps(job, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
