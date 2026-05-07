"""MoE vs dense Layer 3 model comparison (OGE-320).

Loops the Layer 3 benchmark over a list of candidate models, captures
precision / recall / F1 / latency per (model, profile), and emits both a
JSON results file and a markdown table suitable for committing to the repo.

Why a separate runner: ``run_layer3_benchmark.py`` runs **one** model at a
time (it's the precision oracle for OGE-313/314). This script wraps it,
substituting ``OGENTIC_SHIELD_OLLAMA_MODEL`` per model, and produces the
side-by-side table OGE-320 needs.

Usage (from repo root, with Ollama running):

    .venv/bin/python benchmarks/run_moe_comparison.py
    .venv/bin/python benchmarks/run_moe_comparison.py --json /tmp/moe.json --md benchmarks/MOE_COMPARISON.md
    .venv/bin/python benchmarks/run_moe_comparison.py --models granite3.1-moe:1b llama3.2:3b

Default model list mirrors the OGE-320 ticket. Models that aren't pulled
are skipped with a clear note in the report; we don't fail the run because
benchmark hardware varies.

The "no LLM" row is always included as the L1+L2-only baseline so readers
can see whether enabling Layer 3 helps each profile.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Reuse the runner module — sits next to this file.
sys.path.insert(0, str(Path(__file__).parent))

from run_benchmarks import (  # noqa: E402  (sys.path tweak above)
    DATASETS,
    report_for_dataset,
)

from ogentic_shield import Shield
from ogentic_shield.config import LlmConfig, ShieldConfig

DEFAULT_MODELS = [
    "granite3.1-moe:1b",
    "granite3-moe:3b",
    "llama3.2:3b",
    "qwen3:4b",
]


@dataclass
class RunResult:
    model: str  # "" for L1+L2-only baseline
    enabled: bool
    skipped: bool = False
    skip_reason: str = ""
    per_dataset: dict[str, dict[str, float]] = field(default_factory=dict)


def _list_local_models() -> set[str]:
    """Return the set of locally pulled Ollama model tags. Empty on failure."""
    try:
        out = subprocess.run(
            ["ollama", "list"], check=True, capture_output=True, text=True, timeout=10
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return set()
    names: set[str] = set()
    for line in out.splitlines()[1:]:  # skip header
        parts = line.split()
        if parts:
            names.add(parts[0])
    return names


def _build_shield(profile_id: str, model: str | None) -> Shield:
    """Construct a Shield for a given profile + model.

    ``model=None`` builds an L1+L2-only Shield (LLM disabled — the v0.1 baseline).
    Otherwise enables Layer 3 with the requested model and a wide score gate
    so every benchmark example exercises the LLM.
    """
    if model is None:
        return Shield(profiles=[profile_id])

    config = ShieldConfig(
        profiles=[profile_id],
        llm=LlmConfig(
            enabled=True,
            provider="ollama",
            model=model,
            endpoint="http://localhost:11434",
            timeout_ms=60_000,
            max_retries=1,
            ambiguous_score_range=[0, 100],
        ),
    )
    return Shield(profiles=[profile_id], config=config)


def _run_one(model: str | None, local_models: set[str]) -> RunResult:
    label = model or "(L1+L2 only)"
    result = RunResult(model=model or "", enabled=model is not None)
    if model and model not in local_models:
        result.skipped = True
        result.skip_reason = f"model '{model}' not found via `ollama list`"
        return result

    print(f"\n=== Running benchmarks for {label} ===", flush=True)
    started = time.perf_counter()
    for cfg in DATASETS:
        shield = _build_shield(cfg["profile_id"], model)
        report, _ = report_for_dataset(cfg, shield)
        result.per_dataset[cfg["name"]] = {
            "precision": report.precision,
            "recall": report.recall,
            "f1": report.f1,
            "median_ms": report.median_duration_ms,
            "p95_ms": report.p95_duration_ms,
            "examples": float(report.examples),
            "tp": float(report.true_positives),
            "fp": float(report.false_positives),
            "fn": float(report.false_negatives),
            "tn": float(report.true_negatives),
            "precision_target": cfg["precision_target"],
            "meets_target": float(report.meets_precision_target()),
        }
    elapsed = time.perf_counter() - started
    print(f"  total wall time: {elapsed:.1f}s", flush=True)
    return result


def _format_md(results: list[RunResult]) -> str:
    """Render a Markdown comparison report.

    One precision table per profile (rows = models, cols = precision /
    recall / F1 / median latency). Followed by a summary section that
    flags which models meet the per-profile PRD §8 precision target.
    """
    out: list[str] = []
    out.append("# Layer 3 model comparison — OGE-320")
    out.append("")
    out.append("Generated by `benchmarks/run_moe_comparison.py`. Each row is one")
    out.append("model running the Layer 3 stack against the OGE-51 labelled JSONL")
    out.append("datasets, with ``ambiguous_score_range=[0,100]`` so every example")
    out.append("exercises the LLM. The first row is the L1+L2-only v0.1 baseline.")
    out.append("")

    # Per-profile tables
    for cfg in DATASETS:
        name = cfg["name"]
        target = cfg["precision_target"]
        out.append(f"## `{name}` (profile: `{cfg['profile_id']}`, target precision ≥{target * 100:.0f}%)")
        out.append("")
        out.append("| Model | Precision | Recall | F1 | TP / FP / FN / TN | Median latency | Meets target |")
        out.append("|---|---:|---:|---:|---|---:|:---:|")
        for r in results:
            label = r.model if r.enabled else "_(L1+L2 only — v0.1 baseline)_"
            if r.skipped:
                out.append(f"| `{label}` | — | — | — | _skipped: {r.skip_reason}_ | — | — |")
                continue
            d = r.per_dataset.get(name)
            if d is None:
                out.append(f"| `{label}` | — | — | — | _no data_ | — | — |")
                continue
            tick = "✅" if d["meets_target"] >= 1.0 else "❌"
            counts = f"{int(d['tp'])} / {int(d['fp'])} / {int(d['fn'])} / {int(d['tn'])}"
            out.append(
                f"| `{label}` | {d['precision'] * 100:.1f}% | {d['recall'] * 100:.1f}% | "
                f"{d['f1'] * 100:.1f}% | {counts} | {d['median_ms']:.0f}ms | {tick} |"
            )
        out.append("")

    # Summary
    out.append("## Summary")
    out.append("")
    summary_rows: list[tuple[str, int, list[str]]] = []
    for r in results:
        if r.skipped:
            continue
        passed_for: list[str] = []
        for name, d in r.per_dataset.items():
            if d["meets_target"] >= 1.0:
                passed_for.append(name)
        label = r.model if r.enabled else "(L1+L2 only)"
        summary_rows.append((label, len(passed_for), passed_for))
    summary_rows.sort(key=lambda row: row[1], reverse=True)
    out.append("| Model | Profiles meeting target | Notes |")
    out.append("|---|:---:|---|")
    for label, count, profiles in summary_rows:
        notes = ", ".join(profiles) if profiles else "_no profiles met target_"
        out.append(f"| `{label}` | {count}/{len(DATASETS)} | {notes} |")
    out.append("")

    # Latency caveats
    out.append("### Latency caveat")
    out.append("")
    out.append("The ``run_benchmarks`` runner's median-latency target (<100ms) was")
    out.append("designed for the L1+L2-only path. With Layer 3 ON the median naturally")
    out.append("includes a model round-trip and is not directly comparable to the v0.1")
    out.append("target. Compare medians _across models_ here, not against 100ms.")
    out.append("")

    return "\n".join(out)


def _format_json(results: list[RunResult]) -> dict:
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "datasets": [
            {"name": d["name"], "profile_id": d["profile_id"], "precision_target": d["precision_target"]}
            for d in DATASETS
        ],
        "runs": [
            {
                "model": r.model,
                "enabled": r.enabled,
                "skipped": r.skipped,
                "skip_reason": r.skip_reason,
                "per_dataset": r.per_dataset,
            }
            for r in results
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        nargs="*",
        default=DEFAULT_MODELS,
        help=f"Ollama model tags to compare. Default: {' '.join(DEFAULT_MODELS)}",
    )
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="Skip the L1+L2-only baseline row.",
    )
    parser.add_argument("--json", type=Path, help="Path for machine-readable JSON output.")
    parser.add_argument("--md", type=Path, help="Path for the Markdown report.")
    args = parser.parse_args()

    local = _list_local_models()
    if not local:
        print(
            "WARNING: no local models reported by `ollama list` — every model run will be skipped.",
            file=sys.stderr,
        )

    runs: list[RunResult] = []
    if not args.no_baseline:
        runs.append(_run_one(None, local))
    for model in args.models:
        runs.append(_run_one(model, local))

    payload = _format_json(runs)
    md = _format_md(runs)

    print("\n" + md)

    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
        print(f"\nJSON written to {args.json}")
    if args.md:
        args.md.write_text(md)
        print(f"Markdown written to {args.md}")

    # Exit 0 if at least the L1+L2 baseline plus one model produced data.
    succeeded = [r for r in runs if not r.skipped and r.per_dataset]
    return 0 if succeeded else 1


if __name__ == "__main__":
    sys.exit(main())


# Keep statistics import alive for type-checkers; it's used transitively by
# DatasetReport's median/quantile helpers via the runner module.
_ = statistics

__all__ = ["main", "DEFAULT_MODELS", "RunResult"]
