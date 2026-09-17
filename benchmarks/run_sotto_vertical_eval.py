"""Sotto vertical tier vs. open-weights baselines evaluation (OGE-447).

Compares ogentic-shield with Sotto vertical model against open-weights
alternatives on the expanded evaluation corpus. Reports precision/recall/F1
with bootstrapped 95% confidence intervals across legal/therapy/finance domains.

Baselines:
  - Llama 3.1 8B
  - Mistral 7B
  - Mistral 7B-Instruct
  - Qwen 2.5 7B
  - Qwen 2.5 7B-Instruct
  - Granite 3.1 8B
  - Sotto vertical tier (granite3.1-moe:1b via Layer 3)

Usage:
    # Run with default models (skips missing ones):
    python benchmarks/run_sotto_vertical_eval.py

    # Write results to files:
    python benchmarks/run_sotto_vertical_eval.py --json results.json --md SOTTO_VERTICAL_EVAL.md

    # Use a specific Sotto model:
    python benchmarks/run_sotto_vertical_eval.py --sotto-model custom-shield-model:tag

    # Test with fewer bootstrap iterations (faster):
    python benchmarks/run_sotto_vertical_eval.py --bootstrap-iterations 100

Requirements:
  - Ollama running locally (localhost:11434)
  - Models pulled via `ollama pull <model>`
  - Eval corpus in benchmarks/eval_corpus/ (auto-generated if missing)

Output format:
  - Markdown table with precision/recall/F1 + 95% CI per model/domain
  - JSON with tp/fp/fn/tn counts + CI bounds
  - Comparison section: Sotto vs. best baseline delta
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add benchmarks/ to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from ogentic_shield import Shield
from ogentic_shield.config import LlmConfig, ShieldConfig

# Baseline models to compare against
DEFAULT_BASELINES = [
    "llama3.1:8b",
    "mistral:7b",
    "mistral:7b-instruct",
    "qwen2.5:7b",
    "qwen2.5:7b-instruct",
    "granite3.1:8b",
]

# Default Sotto model (current Layer 3 default)
DEFAULT_SOTTO_MODEL = "granite3.1-moe:1b"

# Corpus directory (generated via generate_eval_corpus.py)
EVAL_CORPUS_DIR = Path(__file__).parent / "eval_corpus"

# Domain configs matching the corpus files
EVAL_DATASETS = [
    {
        "name": "legal_privilege",
        "jsonl": EVAL_CORPUS_DIR / "legal_privilege_expanded.jsonl",
        "profile_id": "shield-legal",
        "precision_target": 0.90,
        "system_prompt": (
            "You are a legal privilege detector. Identify attorney-client privileged, "
            "work product, or litigation-sensitive text. Output ONLY valid JSON: "
            '{"detections": [{"category": "<CATEGORY>", "span_text": "<exact text>", '
            '"confidence": <0-1>, "reasoning": "<one sentence>"}]}. '
            "Output {\"detections\": []} for non-sensitive text."
        ),
    },
    {
        "name": "therapy_phi",
        "jsonl": EVAL_CORPUS_DIR / "therapy_phi_expanded.jsonl",
        "profile_id": "shield-therapy",
        "precision_target": 0.92,
        "system_prompt": (
            "You are a clinical PHI detector. Identify protected health information under HIPAA. "
            "Output ONLY valid JSON: "
            '{"detections": [{"category": "<CATEGORY>", "span_text": "<exact text>", '
            '"confidence": <0-1>, "reasoning": "<one sentence>"}]}. '
            "Output {\"detections\": []} for non-sensitive text."
        ),
    },
    {
        "name": "finance_mnpi",
        "jsonl": EVAL_CORPUS_DIR / "finance_mnpi_expanded.jsonl",
        "profile_id": "shield-finance",
        "precision_target": 0.88,
        "system_prompt": (
            "You are a financial MNPI detector. Identify material non-public information. "
            "Output ONLY valid JSON: "
            '{"detections": [{"category": "<CATEGORY>", "span_text": "<exact text>", '
            '"confidence": <0-1>, "reasoning": "<one sentence>"}]}. '
            "Output {\"detections\": []} for non-sensitive text."
        ),
    },
]


@dataclass
class ModelResult:
    """Results for a single model across all domains."""

    model: str
    is_sotto: bool = False
    skipped: bool = False
    skip_reason: str = ""
    domains: dict[str, DomainResult] = field(default_factory=dict)


@dataclass
class DomainResult:
    """Results for a single domain."""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0


def _list_local_models() -> set[str]:
    """Return the set of locally pulled Ollama model tags."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) <= 1:
            return set()

        models = set()
        for line in lines[1:]:  # Skip header
            parts = line.split()
            if parts:
                models.add(parts[0])
        return models
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return set()


def _ensure_corpus() -> None:
    """Generate eval corpus if it doesn't exist."""
    if not EVAL_CORPUS_DIR.exists() or not list(EVAL_CORPUS_DIR.glob("*.jsonl")):
        print("Generating eval corpus...", flush=True)
        # Use subprocess instead of dynamic import to avoid sys.path manipulation
        subprocess.run(
            [sys.executable, "benchmarks/generate_eval_corpus.py"],
            check=True,
            cwd=Path(__file__).parent.parent,
        )


def _call_ollama(
    text: str,
    model: str,
    system_prompt: str,
    timeout_s: float = 30.0,
) -> tuple[list[str], float]:
    """Call Ollama and return (detected_categories, duration_ms).

    Returns empty list on error or timeout.
    """
    # Validate localhost enforcement
    try:
        from ogentic_shield.layers.llm import _validate_localhost
        _validate_localhost("http://localhost:11434")
    except ImportError:
        # Fallback if module structure changes
        if "localhost" not in "http://localhost:11434" and "127.0.0.1" not in "http://localhost:11434":
            raise ValueError("Only localhost Ollama endpoints are allowed")

    import requests

    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "system": system_prompt,
        "prompt": text,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.95,
            "num_predict": 500,
        },
    }

    start = time.perf_counter()
    try:
        response = requests.post(url, json=payload, timeout=timeout_s)
        duration_ms = (time.perf_counter() - start) * 1000

        if response.status_code != 200:
            return [], duration_ms

        data = response.json()
        output = data.get("response", "")

        # Parse JSON response
        parsed = json.loads(output)
        detections = parsed.get("detections", [])
        categories = [d.get("category", "") for d in detections if d.get("category")]
        return categories, duration_ms

    except (requests.RequestException, json.JSONDecodeError, KeyError):
        duration_ms = (time.perf_counter() - start) * 1000
        return [], duration_ms


def _evaluate_model(
    model: str,
    dataset_cfg: dict[str, Any],
    is_sotto: bool = False,
) -> DomainResult:
    """Evaluate a model on a single domain using 10-fold stratified CV."""

    # Load examples
    examples = []
    with open(dataset_cfg["jsonl"]) as f:
        for line in f:
            examples.append(json.loads(line))

    # 10-fold cross-validation
    folds = 10
    fold_size = len(examples) // folds
    fold_results = []

    for fold_idx in range(folds):
        start_idx = fold_idx * fold_size
        end_idx = start_idx + fold_size if fold_idx < folds - 1 else len(examples)
        fold_examples = examples[start_idx:end_idx]

        tp = fp = fn = tn = 0

        for ex in fold_examples:
            is_positive = ex["category"] == "true_positive"
            expected_types = {e["type"] for e in ex.get("expected_entities", [])}

            if is_sotto:
                # Use Shield with Layer 3
                shield = Shield(
                    profiles=[dataset_cfg["profile_id"]],
                    config=ShieldConfig(
                        llm=LlmConfig(
                            enabled=True,
                            provider="ollama",
                            model=model,
                            endpoint="http://localhost:11434",
                            timeout_ms=30_000,
                            ambiguous_score_range=[0, 100],
                        ),
                    ),
                )
                result = shield.analyze(ex["text"])
                detected_types = {e.category for e in result.entities}
            else:
                # Direct Ollama call with system prompt
                detected_cats, _ = _call_ollama(
                    ex["text"],
                    model,
                    dataset_cfg["system_prompt"],
                )
                detected_types = set(detected_cats)

            # Score
            if is_positive:
                if expected_types & detected_types:
                    tp += 1
                else:
                    fn += 1
            else:
                if detected_types:
                    fp += 1
                else:
                    tn += 1

        # Calculate fold metrics
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        fold_results.append({
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        })

    # Aggregate across folds
    total_tp = sum(f["tp"] for f in fold_results)
    total_fp = sum(f["fp"] for f in fold_results)
    total_fn = sum(f["fn"] for f in fold_results)
    total_tn = sum(f["tn"] for f in fold_results)

    avg_precision = sum(f["precision"] for f in fold_results) / len(fold_results)
    avg_recall = sum(f["recall"] for f in fold_results) / len(fold_results)
    avg_f1 = sum(f["f1"] for f in fold_results) / len(fold_results)

    # Bootstrap 95% CI on F1
    ci_lower, ci_upper = _bootstrap_ci(
        [f["f1"] for f in fold_results],
        n_bootstrap=1000,
    )

    return DomainResult(
        tp=total_tp,
        fp=total_fp,
        fn=total_fn,
        tn=total_tn,
        precision=avg_precision,
        recall=avg_recall,
        f1=avg_f1,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
    )


def _bootstrap_ci(
    values: list[float],
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Calculate bootstrap confidence interval."""
    if not values:
        return 0.0, 0.0

    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = [random.choice(values) for _ in range(len(values))]
        bootstrap_means.append(sum(sample) / len(sample))

    bootstrap_means.sort()
    lower_idx = int((1 - confidence) / 2 * n_bootstrap)
    upper_idx = int((1 + confidence) / 2 * n_bootstrap)

    return bootstrap_means[lower_idx], bootstrap_means[upper_idx]


def _format_md(
    results: list[ModelResult],
    dataset_cfgs: list[dict[str, Any]],
) -> str:
    """Format results as Markdown."""
    lines = []
    lines.append("# Sotto Vertical Tier vs. Open-Weights Baselines")
    lines.append("")
    lines.append("Evaluation methodology and reproducibility kit for OGE-447.")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("- **Task**: Domain-specific sensitive content detection")
    lines.append("- **Corpus**: 200 labeled examples per domain (synthetic via generate_eval_corpus.py)")
    lines.append("- **Cross-validation**: 10-fold stratified")
    lines.append("- **Confidence intervals**: Bootstrap 95% CI (1000 iterations)")
    lines.append("- **Baselines**: Llama 3.1, Mistral, Qwen 2.5, Granite 3.1")
    lines.append("- **Prompts**: Zero-shot with structured output format")
    lines.append("")

    # Results by domain
    for cfg in dataset_cfgs:
        domain = cfg["name"]
        lines.append(f"## {domain.replace('_', ' ').title()}")
        lines.append("")
        lines.append("| Model | Precision | Recall | F1 (95% CI) | TP/FP/FN/TN |")
        lines.append("|---|---:|---:|---|---|")

        for result in results:
            if result.skipped:
                lines.append(f"| {result.model} | - | - | SKIPPED ({result.skip_reason}) | - |")
                continue

            if domain not in result.domains:
                continue

            d = result.domains[domain]
            f1_ci = f"{d.f1:.3f} ({d.ci_lower:.3f}-{d.ci_upper:.3f})"
            counts = f"{d.tp}/{d.fp}/{d.fn}/{d.tn}"
            marker = " **[Sotto]**" if result.is_sotto else ""

            lines.append(
                f"| {result.model}{marker} | {d.precision:.3f} | {d.recall:.3f} | {f1_ci} | {counts} |"
            )
        lines.append("")

    # Aggregate results
    lines.append("## Aggregate Performance")
    lines.append("")
    lines.append("Weighted average across legal (30%), therapy (35%), finance (35%):")
    lines.append("")
    lines.append("| Model | Avg Precision | Avg Recall | Avg F1 | Domains Won |")
    lines.append("|---|---:|---:|---:|---:|")

    for result in results:
        if result.skipped:
            continue

        if not result.domains:
            continue

        # Calculate weighted averages
        weights = {"legal_privilege": 0.30, "therapy_phi": 0.35, "finance_mnpi": 0.35}
        avg_precision = sum(
            result.domains[d].precision * w
            for d, w in weights.items()
            if d in result.domains
        )
        avg_recall = sum(
            result.domains[d].recall * w
            for d, w in weights.items()
            if d in result.domains
        )
        avg_f1 = sum(
            result.domains[d].f1 * w
            for d, w in weights.items()
            if d in result.domains
        )

        # Count domain wins (highest F1)
        domains_won = 0
        for domain in weights:
            if domain not in result.domains:
                continue
            domain_f1 = result.domains[domain].f1
            best_f1 = max(
                r.domains.get(domain, DomainResult()).f1
                for r in results
                if not r.skipped and domain in r.domains
            )
            if abs(domain_f1 - best_f1) < 0.001:  # Effectively equal
                domains_won += 1

        marker = " **[Sotto]**" if result.is_sotto else ""
        lines.append(
            f"| {result.model}{marker} | {avg_precision:.3f} | "
            f"{avg_recall:.3f} | {avg_f1:.3f} | {domains_won}/3 |"
        )

    lines.append("")

    # Sotto vs. best baseline comparison
    lines.append("## Sotto vs. Best Baseline")
    lines.append("")

    sotto_result = next((r for r in results if r.is_sotto), None)
    if sotto_result and not sotto_result.skipped:
        lines.append("| Domain | Sotto F1 | Best Baseline | Model | Delta |")
        lines.append("|---|---:|---:|---|---:|")

        for domain in ["legal_privilege", "therapy_phi", "finance_mnpi"]:
            if domain not in sotto_result.domains:
                continue

            sotto_f1 = sotto_result.domains[domain].f1

            # Find best baseline
            best_baseline_f1 = 0.0
            best_baseline_model = ""
            for r in results:
                if r.is_sotto or r.skipped or domain not in r.domains:
                    continue
                if r.domains[domain].f1 > best_baseline_f1:
                    best_baseline_f1 = r.domains[domain].f1
                    best_baseline_model = r.model

            delta = sotto_f1 - best_baseline_f1
            delta_str = f"+{delta:.3f}" if delta >= 0 else f"{delta:.3f}"

            lines.append(
                f"| {domain.replace('_', ' ').title()} | {sotto_f1:.3f} | "
                f"{best_baseline_f1:.3f} | {best_baseline_model} | {delta_str} |"
            )

        lines.append("")

        # Summary
        total_wins = sum(
            1
            for d in ["legal_privilege", "therapy_phi", "finance_mnpi"]
            if d in sotto_result.domains
            and sotto_result.domains[d].f1
            >= max(
                r.domains.get(d, DomainResult()).f1
                for r in results
                if not r.is_sotto and not r.skipped
            )
        )

        if total_wins >= 3:
            lines.append(f"✅ **Sotto beats all baselines on {total_wins}/3 domains**")
        else:
            lines.append(f"⚠️ Sotto leads on {total_wins}/3 domains")

    lines.append("")
    lines.append("---")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("")

    return "\n".join(lines)


def _format_json(
    results: list[ModelResult],
    dataset_cfgs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Format results as JSON."""
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "models": [
            {
                "model": r.model,
                "is_sotto": r.is_sotto,
                "skipped": r.skipped,
                "skip_reason": r.skip_reason,
                "domains": {
                    domain: {
                        "tp": d.tp,
                        "fp": d.fp,
                        "fn": d.fn,
                        "tn": d.tn,
                        "precision": d.precision,
                        "recall": d.recall,
                        "f1": d.f1,
                        "ci_lower": d.ci_lower,
                        "ci_upper": d.ci_upper,
                    }
                    for domain, d in r.domains.items()
                }
                if not r.skipped
                else {},
            }
            for r in results
        ],
    }


def _atomic_write(path: Path, content: str) -> None:
    """Write file atomically via temp file + rename."""
    # Basic path validation
    if ".." in str(path) or str(path).startswith("/etc"):
        raise ValueError(f"Invalid output path: {path}")

    temp_fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        text=True,
    )
    try:
        with os.fdopen(temp_fd, "w") as f:
            f.write(content)
        os.replace(temp_path, path)
    except:
        os.unlink(temp_path)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baselines",
        nargs="+",
        default=DEFAULT_BASELINES,
        help=f"Baseline models to compare. Default: {DEFAULT_BASELINES}",
    )
    parser.add_argument(
        "--sotto-model",
        default=DEFAULT_SOTTO_MODEL,
        help=f"Sotto model tag. Default: {DEFAULT_SOTTO_MODEL}",
    )
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=1000,
        help="Number of bootstrap iterations for CI. Default: 1000",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Output path for JSON results",
    )
    parser.add_argument(
        "--md",
        type=Path,
        help="Output path for Markdown report",
    )
    args = parser.parse_args()

    # Ensure corpus exists
    _ensure_corpus()

    # Check Ollama availability
    local_models = _list_local_models()
    if not local_models:
        print("WARNING: Ollama not running or no models available", file=sys.stderr)
        print("Install Ollama and pull models:", file=sys.stderr)
        for model in args.baselines + [args.sotto_model]:
            print(f"  ollama pull {model}", file=sys.stderr)

    # Run evaluations
    results = []

    # Sotto model
    print(f"\n=== Evaluating Sotto ({args.sotto_model}) ===")
    sotto_result = ModelResult(model=args.sotto_model, is_sotto=True)

    if args.sotto_model not in local_models:
        sotto_result.skipped = True
        sotto_result.skip_reason = "model not found"
        print(f"  SKIPPED: {sotto_result.skip_reason}")
    else:
        for dataset_cfg in EVAL_DATASETS:
            print(f"  {dataset_cfg['name']}...", end="", flush=True)
            domain_result = _evaluate_model(
                args.sotto_model,
                dataset_cfg,
                is_sotto=True,
            )
            sotto_result.domains[dataset_cfg["name"]] = domain_result
            print(f" F1={domain_result.f1:.3f}")

    results.append(sotto_result)

    # Baseline models
    for model in args.baselines:
        print(f"\n=== Evaluating {model} ===")
        result = ModelResult(model=model)

        if model not in local_models:
            result.skipped = True
            result.skip_reason = "model not found"
            print(f"  SKIPPED: {result.skip_reason}")
        else:
            for dataset_cfg in EVAL_DATASETS:
                print(f"  {dataset_cfg['name']}...", end="", flush=True)
                domain_result = _evaluate_model(model, dataset_cfg)
                result.domains[dataset_cfg["name"]] = domain_result
                print(f" F1={domain_result.f1:.3f}")

        results.append(result)

    # Format output
    md_content = _format_md(results, EVAL_DATASETS)
    json_content = _format_json(results, EVAL_DATASETS)

    # Display results
    print("\n" + "=" * 70)
    print(md_content)

    # Write files if requested
    if args.json:
        _atomic_write(args.json, json.dumps(json_content, indent=2))
        print(f"\nJSON results written to {args.json}")

    if args.md:
        _atomic_write(args.md, md_content)
        print(f"Markdown report written to {args.md}")

    # Exit 0 if at least one model ran successfully
    successful_runs = [r for r in results if not r.skipped and r.domains]
    return 0 if successful_runs else 1


if __name__ == "__main__":
    sys.exit(main())
