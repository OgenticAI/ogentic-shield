"""Evaluate a fine-tuned model endpoint against the expanded eval corpus.

Runs inference against a Together AI or Fireworks model endpoint using the
same precision/recall/F1 scoring logic as ``run_benchmarks.py``. Results are
comparable to the L1+L2 and zero-shot L3 baselines in MOE_COMPARISON.md.

This is the Phase 1 decision gate: whichever platform's fine-tuned model
hits the best precision/recall/F1 combination at acceptable p95 latency
and within the $500 budget becomes the Phase 2 platform.

Requirements:
  - TOGETHER_API_KEY or FIREWORKS_API_KEY (matching --provider)
  - Expanded eval corpus in benchmarks/eval_corpus/ (from generate_eval_corpus.py)
  - ``requests`` package

Usage:
    # Evaluate a Together AI fine-tuned model:
    python benchmarks/bakeoff/eval_finetuned.py \
        --model-id your-fine-tuned-model-id \
        --provider together \
        --domain legal_privilege

    # Evaluate a Fireworks fine-tuned model:
    python benchmarks/bakeoff/eval_finetuned.py \
        --model-id accounts/your-account/models/shield-legal-lora \
        --provider fireworks \
        --domain all

    # Pipe from fine-tune script:
    python run_together_finetune.py | \
        xargs -I{} python eval_finetuned.py --model-id {} --provider together
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BAKEOFF_DIR = Path(__file__).parent
DEFAULT_CORPUS_DIR = BAKEOFF_DIR.parent / "eval_corpus"

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"

PERFORMANCE_TARGET_MS = 500.0  # remote endpoint; more lenient than 100ms local target

DOMAIN_FILES = {
    "legal_privilege": DEFAULT_CORPUS_DIR / "legal_privilege_expanded.jsonl",
    "therapy_phi": DEFAULT_CORPUS_DIR / "therapy_phi_expanded.jsonl",
    "finance_mnpi": DEFAULT_CORPUS_DIR / "finance_mnpi_expanded.jsonl",
}

SYSTEM_PROMPTS: dict[str, str] = {
    "legal_privilege": (
        "You are a legal privilege detector. Identify attorney-client privileged, "
        "work product, or litigation-sensitive text. Output ONLY valid JSON: "
        '{"detections": [{"category": "<CATEGORY>", "span_text": "<exact text>", '
        '"confidence": <0-1>, "reasoning": "<one sentence>"}]}. '
        "Output {\"detections\": []} for non-sensitive text. "
        "Allowed categories: COUNSEL_COMMUNICATION, PRIVILEGE_MARKER, WORK_PRODUCT, "
        "LITIGATION_MARKER, SETTLEMENT_TERMS, CASE_NUMBER, LAW_FIRM_NAME, COURT_FILING, "
        "BATES_NUMBER, EXECUTIVE_NAME."
    ),
    "therapy_phi": (
        "You are a clinical PHI detector. Identify protected health information under HIPAA. "
        "Output ONLY valid JSON: "
        '{"detections": [{"category": "<CATEGORY>", "span_text": "<exact text>", '
        '"confidence": <0-1>, "reasoning": "<one sentence>"}]}. '
        "Output {\"detections\": []} for non-sensitive text. "
        "Allowed categories: PATIENT_NAME, DATE_OF_BIRTH, DIAGNOSIS_CODE, CLINICAL_RISK_FLAG, "
        "SESSION_MARKER, INSURANCE_ID, MEDICATION, PROVIDER_NAME, PSYCHOTHERAPY_NOTE_MARKER, SSN."
    ),
    "finance_mnpi": (
        "You are a financial MNPI detector. Identify material non-public information. "
        "Output ONLY valid JSON: "
        '{"detections": [{"category": "<CATEGORY>", "span_text": "<exact text>", '
        '"confidence": <0-1>, "reasoning": "<one sentence>"}]}. '
        "Output {\"detections\": []} for non-sensitive text. "
        "Allowed categories: MNPI_MARKER, MA_ACTIVITY, DEAL_VALUE, INSIDER_MARKER, "
        "FUND_INFORMATION, LEVERAGE_RATIO, CARRY_TERMS, INSTITUTION_NAME, "
        "FINANCIAL_TERMS, DISTRIBUTION_RESTRICTION."
    ),
}


@dataclass
class EvalResult:
    domain: str
    model_id: str
    provider: str
    examples: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    durations_ms: list[float] = field(default_factory=list)

    @property
    def precision(self) -> float:
        d = self.true_positives + self.false_positives
        return self.true_positives / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.true_positives + self.false_negatives
        return self.true_positives / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def median_ms(self) -> float:
        return statistics.median(self.durations_ms) if self.durations_ms else 0.0

    @property
    def p95_ms(self) -> float:
        if not self.durations_ms:
            return 0.0
        if len(self.durations_ms) < 20:
            return max(self.durations_ms)
        return statistics.quantiles(self.durations_ms, n=20)[18]


def _get_api_key(provider: str) -> str:
    env_var = "TOGETHER_API_KEY" if provider == "together" else "FIREWORKS_API_KEY"
    key = os.environ.get(env_var)
    if not key:
        sys.exit(f"Error: {env_var} environment variable not set.")
    return key


def _call_model(
    text: str,
    system_prompt: str,
    model_id: str,
    provider: str,
    api_key: str,
    timeout_s: float,
) -> tuple[dict[str, Any] | None, float]:
    """Call the model endpoint and return (parsed_response, duration_ms)."""
    try:
        import requests
    except ImportError:
        sys.exit("Error: 'requests' package not available.")

    base_url = TOGETHER_BASE_URL if provider == "together" else FIREWORKS_BASE_URL
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0.0,
        "max_tokens": 512,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    start = time.perf_counter()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
        resp.raise_for_status()
        elapsed_ms = (time.perf_counter() - start) * 1000
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return parsed, elapsed_ms
    except (requests.RequestException, KeyError, json.JSONDecodeError):
        elapsed_ms = (time.perf_counter() - start) * 1000
        return None, elapsed_ms


def evaluate_domain(
    domain: str,
    corpus_path: Path,
    model_id: str,
    provider: str,
    api_key: str,
    timeout_s: float,
    max_examples: int | None,
) -> EvalResult:
    examples: list[dict] = []
    with open(corpus_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                examples.append(json.loads(line))

    if max_examples:
        examples = examples[:max_examples]

    system_prompt = SYSTEM_PROMPTS[domain]
    result = EvalResult(
        domain=domain, model_id=model_id, provider=provider,
        examples=len(examples), true_positives=0, false_positives=0,
        false_negatives=0, true_negatives=0,
    )

    for i, ex in enumerate(examples, 1):
        if i % 10 == 0:
            print(f"    [{i}/{len(examples)}]", end="\r", flush=True)

        response, duration_ms = _call_model(
            ex["text"], system_prompt, model_id, provider, api_key, timeout_s
        )
        result.durations_ms.append(duration_ms)

        detected_categories: set[str] = set()
        if response and "detections" in response:
            for det in response["detections"]:
                if isinstance(det, dict) and "category" in det:
                    detected_categories.add(det["category"])

        expected_categories = {e["type"] for e in ex.get("expected_entities", [])}
        is_positive = ex.get("category") == "true_positive"

        if is_positive:
            if detected_categories & expected_categories:
                result.true_positives += 1
            else:
                result.false_negatives += 1
        else:
            if detected_categories:
                result.false_positives += 1
            else:
                result.true_negatives += 1

    print()  # clear progress line
    return result


def print_report(results: list[EvalResult]) -> None:
    bar = "=" * 70
    print(f"\n{bar}")
    print(" Fine-tuned model eval — OGE-794 bake-off")
    print(f"{bar}\n")

    for r in results:
        meets_perf = r.p95_ms < PERFORMANCE_TARGET_MS
        print(f"Domain:    {r.domain}")
        print(f"Provider:  {r.provider}   Model: {r.model_id}")
        print(f"Examples:  {r.examples}")
        print(f"TP/FP/FN/TN: {r.true_positives}/{r.false_positives}/{r.false_negatives}/{r.true_negatives}")
        print(f"Precision: {r.precision * 100:.1f}%")
        print(f"Recall:    {r.recall * 100:.1f}%")
        print(f"F1:        {r.f1 * 100:.1f}%")
        print(
            f"Latency:   median={r.median_ms:.0f}ms  "
            f"p95={r.p95_ms:.0f}ms  "
            f"(target p95<{PERFORMANCE_TARGET_MS:.0f}ms) "
            f"{'OK' if meets_perf else 'SLOW'}"
        )
        print()

    print(bar)
    print()


def write_json_report(results: list[EvalResult], out_path: Path) -> None:
    payload = [
        {
            "domain": r.domain,
            "model_id": r.model_id,
            "provider": r.provider,
            "examples": r.examples,
            "true_positives": r.true_positives,
            "false_positives": r.false_positives,
            "false_negatives": r.false_negatives,
            "true_negatives": r.true_negatives,
            "precision": r.precision,
            "recall": r.recall,
            "f1": r.f1,
            "median_ms": r.median_ms,
            "p95_ms": r.p95_ms,
        }
        for r in results
    ]
    out_path.write_text(json.dumps(payload, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--model-id",
        required=True,
        help="Fine-tuned model ID from the platform (Together model name or Fireworks model path)",
    )
    parser.add_argument(
        "--provider",
        choices=["together", "fireworks"],
        required=True,
        help="API provider to call for inference",
    )
    parser.add_argument(
        "--domain",
        choices=["legal_privilege", "therapy_phi", "finance_mnpi", "all"],
        default="all",
        help="Domain(s) to evaluate (default: all)",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=DEFAULT_CORPUS_DIR,
        help=f"Directory containing expanded eval corpus JSONL files (default: {DEFAULT_CORPUS_DIR})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=None,
        help="Cap examples per domain for faster smoke-testing (default: all)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Write machine-readable JSON report to this path",
    )
    args = parser.parse_args()

    domains = list(DOMAIN_FILES.keys()) if args.domain == "all" else [args.domain]
    api_key = _get_api_key(args.provider)

    results: list[EvalResult] = []
    for domain in domains:
        corpus_path = args.corpus_dir / f"{domain}_expanded.jsonl"
        if not corpus_path.exists():
            print(f"  [SKIP] {corpus_path} not found — run generate_eval_corpus.py first")
            continue
        print(f"Evaluating {domain} ({args.provider})...")
        r = evaluate_domain(
            domain, corpus_path, args.model_id, args.provider,
            api_key, args.timeout, args.max_examples,
        )
        results.append(r)

    if not results:
        print("No domains evaluated.")
        return 1

    print_report(results)

    if args.json:
        write_json_report(results, args.json)
        print(f"JSON report written to {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
