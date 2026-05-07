"""Layer 3 precision benchmark — verifies OGE-314's PRD §8 targets.

Reuses the labelled JSONL datasets and per-recognizer scorer from
``run_benchmarks.py`` but enables Layer 3 (with the ambiguous-score gate
widened to ``[0, 100]`` so every example gets the LLM treatment) so the
reported precision reflects the full L1+L2+L3 stack.

Run locally with Ollama serving the configured model:

    ollama serve &
    ollama pull granite3.1-moe:1b
    .venv/bin/python benchmarks/run_layer3_benchmark.py

Exit code: 0 if every dataset meets its precision and performance target;
1 otherwise. Use the JSON output to track precision over time:

    .venv/bin/python benchmarks/run_layer3_benchmark.py --json layer3.json

The same precision targets apply (legal ≥90%, PHI ≥92%, MNPI ≥88%) — Layer 3
is expected to *improve* recall on adversarial-negative examples without
degrading precision on the canonical positives.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Local import — the runner module sits next to this file.
sys.path.insert(0, str(Path(__file__).parent))

from run_benchmarks import (  # noqa: E402  (sys.path tweak above)
    DATASETS,
    DatasetReport,
    print_text_report,
    report_for_dataset,
    write_json_report,
)

from ogentic_shield import Shield
from ogentic_shield.config import LlmConfig, ShieldConfig


def _build_layer3_shield(profile_id: str) -> Shield:
    """Construct a Shield wired for Layer 3 against localhost Ollama.

    Score gate widened to [0, 100] so the LLM always runs on benchmark text
    (the canonical positives sit above the default 60 ceiling).
    """
    model = os.environ.get("OGENTIC_SHIELD_OLLAMA_MODEL", "granite3.1-moe:1b")
    endpoint = os.environ.get("OGENTIC_SHIELD_OLLAMA_ENDPOINT", "http://localhost:11434")
    timeout_ms = int(os.environ.get("OGENTIC_SHIELD_OLLAMA_TIMEOUT_MS", "30000"))

    config = ShieldConfig(
        profiles=[profile_id],
        llm=LlmConfig(
            enabled=True,
            provider="ollama",
            model=model,
            endpoint=endpoint,
            timeout_ms=timeout_ms,
            max_retries=1,
            ambiguous_score_range=[0, 100],
        ),
    )
    return Shield(profiles=[profile_id], config=config)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        choices=[d["name"] for d in DATASETS],
        action="append",
        help="Run only the specified dataset(s). Repeatable. Default: all.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Write a machine-readable JSON report to this path.",
    )
    args = parser.parse_args()

    selected = DATASETS if not args.dataset else [d for d in DATASETS if d["name"] in args.dataset]

    reports: list[DatasetReport] = []
    for cfg in selected:
        print(
            f"Initialising Shield(profiles=['{cfg['profile_id']}'], llm.enabled=True)...",
            flush=True,
        )
        shield = _build_layer3_shield(cfg["profile_id"])
        print(f"Running {cfg['name']} with Layer 3 ON...", flush=True)
        report, _results = report_for_dataset(cfg, shield)
        reports.append(report)

    print_text_report(reports)
    if args.json:
        write_json_report(reports, args.json)
        print(f"JSON report written to {args.json}")

    overall_pass = all(
        r.meets_precision_target() and r.meets_performance_target() for r in reports
    )
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["main", "_build_layer3_shield"]
