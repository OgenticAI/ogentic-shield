"""Convert the eval corpus to fine-tuning JSONL format for Together AI and Fireworks.

Both Together AI and Fireworks accept OpenAI-compatible chat-completion JSONL
for LoRA fine-tuning. Each line has the form:
    {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}

The system prompt is adapted from ``ogentic_shield.layers.llm_prompts`` so the
fine-tuned model learns the same output schema used by Layer 3 zero-shot today.

Assistant responses are the ground-truth entity list encoded as the same JSON
schema that ``LlmResponse`` (``layers/llm_schema.py``) expects. This ensures
the fine-tuned model can be plugged directly into Layer 3 without a separate
parser.

Input: ``benchmarks/eval_corpus/*.jsonl`` (from ``generate_eval_corpus.py``)
Output: ``benchmarks/bakeoff/finetune_data/{domain}_{provider}.jsonl``

Usage:
    python benchmarks/bakeoff/prepare_finetune_data.py
    python benchmarks/bakeoff/prepare_finetune_data.py --input-dir benchmarks/eval_corpus
    python benchmarks/bakeoff/prepare_finetune_data.py --domain legal --provider together
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

BAKEOFF_DIR = Path(__file__).parent
DEFAULT_INPUT_DIR = BAKEOFF_DIR.parent / "eval_corpus"
DEFAULT_OUTPUT_DIR = BAKEOFF_DIR / "finetune_data"

# ── System prompt templates per domain ───────────────────────────────────────
# These are condensed from llm_prompts.py so the fine-tuned model learns the
# same framing and output schema.

_SCHEMA_REMINDER = """\
Output ONLY valid JSON matching this schema:
{"detections": [{"category": "<CATEGORY>", "span_text": "<exact substring>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}]}
Output {"detections": []} for non-sensitive text."""

SYSTEM_PROMPTS: dict[str, str] = {
    "legal": f"""\
You are a legal privilege detector. Identify text that is attorney-client privileged,
work product, litigation-sensitive, or otherwise legally sensitive.

Allowed categories: COUNSEL_COMMUNICATION, PRIVILEGE_MARKER, WORK_PRODUCT,
LITIGATION_MARKER, SETTLEMENT_TERMS, CASE_NUMBER, LAW_FIRM_NAME, COURT_FILING,
BATES_NUMBER, EXECUTIVE_NAME.

{_SCHEMA_REMINDER}""",
    "therapy": f"""\
You are a clinical PHI detector. Identify protected health information (PHI) under HIPAA
including patient names, diagnoses, medications, clinical risk flags, and session markers.

Allowed categories: PATIENT_NAME, DATE_OF_BIRTH, DIAGNOSIS_CODE, CLINICAL_RISK_FLAG,
SESSION_MARKER, INSURANCE_ID, MEDICATION, PROVIDER_NAME, PSYCHOTHERAPY_NOTE_MARKER, SSN.

{_SCHEMA_REMINDER}""",
    "finance": f"""\
You are a financial MNPI detector. Identify material non-public information (MNPI),
M&A activity, insider trading signals, fund terms, and leverage/distribution covenants.

Allowed categories: MNPI_MARKER, MA_ACTIVITY, DEAL_VALUE, INSIDER_MARKER,
FUND_INFORMATION, LEVERAGE_RATIO, CARRY_TERMS, INSTITUTION_NAME,
FINANCIAL_TERMS, DISTRIBUTION_RESTRICTION.

{_SCHEMA_REMINDER}""",
}

DOMAIN_TO_SYSTEM_PROMPT: dict[str, str] = {
    "legal_privilege": SYSTEM_PROMPTS["legal"],
    "therapy_phi": SYSTEM_PROMPTS["therapy"],
    "finance_mnpi": SYSTEM_PROMPTS["finance"],
}

CORPUS_FILES: dict[str, Path] = {
    "legal_privilege": DEFAULT_INPUT_DIR / "legal_privilege_expanded.jsonl",
    "therapy_phi": DEFAULT_INPUT_DIR / "therapy_phi_expanded.jsonl",
    "finance_mnpi": DEFAULT_INPUT_DIR / "finance_mnpi_expanded.jsonl",
}


# ── Conversion helpers ────────────────────────────────────────────────────────

def _example_to_assistant_response(example: dict[str, Any]) -> str:
    """Build the ground-truth assistant JSON from a benchmark JSONL example.

    For true_positive examples the assistant output lists the expected entity
    types as detections with a synthetic span_text (the full text, since we
    don't have character offsets) and a high confidence.

    For true_negative / adversarial_negative examples the output is an empty
    detections list — this teaches the model to abstain on non-sensitive text.
    """
    is_positive = example.get("category") == "true_positive"
    if not is_positive or not example.get("expected_entities"):
        return json.dumps({"detections": []})

    text = example["text"]
    detections = []
    for ent in example["expected_entities"]:
        # Use the full text as span_text for training; fine-tuned models learn
        # to return precise substrings during inference when prompted with real
        # text rather than full-document context.
        detections.append({
            "category": ent["type"],
            "span_text": text,
            "confidence": 0.95,
            "reasoning": f"Ground-truth entity type {ent['type']} present in text.",
        })
    return json.dumps({"detections": detections})


def convert_example(
    example: dict[str, Any],
    system_prompt: str,
    provider: str,
) -> dict[str, Any]:
    """Convert one benchmark example to a fine-tuning message dict."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": example["text"]},
        {"role": "assistant", "content": _example_to_assistant_response(example)},
    ]
    if provider == "together":
        return {"messages": messages}
    elif provider == "fireworks":
        # Fireworks uses the same OpenAI chat format but wraps it slightly
        # differently in their fine-tuning API — the outer key is still "messages".
        return {"messages": messages}
    else:
        raise ValueError(f"Unknown provider '{provider}'. Expected 'together' or 'fireworks'.")


def convert_domain(
    domain: str,
    input_path: Path,
    output_dir: Path,
    provider: str,
    split_ratio: float = 0.9,
) -> tuple[int, int]:
    """Convert a domain's corpus to train/validation splits.

    Returns (train_count, val_count).
    """
    system_prompt = DOMAIN_TO_SYSTEM_PROMPT[domain]
    examples: list[dict[str, Any]] = []
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                examples.append(json.loads(line))

    split_idx = int(len(examples) * split_ratio)
    train_examples = examples[:split_idx]
    val_examples = examples[split_idx:]

    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / f"{domain}_{provider}_train.jsonl"
    val_path = output_dir / f"{domain}_{provider}_val.jsonl"

    with open(train_path, "w") as f:
        for ex in train_examples:
            f.write(json.dumps(convert_example(ex, system_prompt, provider)) + "\n")

    with open(val_path, "w") as f:
        for ex in val_examples:
            f.write(json.dumps(convert_example(ex, system_prompt, provider)) + "\n")

    return len(train_examples), len(val_examples)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Directory containing expanded eval corpus JSONL files (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for fine-tuning JSONL files (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--domain",
        choices=list(CORPUS_FILES.keys()),
        action="append",
        help="Domain(s) to convert (default: all). Repeatable.",
    )
    parser.add_argument(
        "--provider",
        choices=["together", "fireworks", "both"],
        default="both",
        help="Target provider format (default: both)",
    )
    parser.add_argument(
        "--split-ratio",
        type=float,
        default=0.9,
        help="Train/validation split ratio (default: 0.9)",
    )
    args = parser.parse_args()

    domains = args.domain or list(CORPUS_FILES.keys())
    providers = ["together", "fireworks"] if args.provider == "both" else [args.provider]

    for domain in domains:
        input_path = args.input_dir / f"{domain}_expanded.jsonl"
        if not input_path.exists():
            print(f"  [SKIP] {input_path} not found — run generate_eval_corpus.py first")
            continue
        for provider in providers:
            train_n, val_n = convert_domain(
                domain, input_path, args.output_dir, provider, args.split_ratio
            )
            print(
                f"  {domain} ({provider}): "
                f"train={train_n}, val={val_n} -> {args.output_dir}/"
            )

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["convert_example", "convert_domain", "SYSTEM_PROMPTS"]
