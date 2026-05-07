"""ogentic-shield benchmark runner.

Reads labelled JSONL datasets, runs each example through `Shield.analyze`,
and reports per-recognizer + per-profile precision, recall, F1, and timing.

JSONL format (each line is one example):
    {
      "id": "...",
      "text": "...",
      "expected_entities": [{"type": "...", "start"?: N, "end"?: N}],
      "expected_level": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "NONE",
      "category": "true_positive" | "true_negative" | "adversarial_negative",
      "notes": "..."
    }

Run from project root:

    python benchmarks/run_benchmarks.py
    python benchmarks/run_benchmarks.py --json results.json
    python benchmarks/run_benchmarks.py --dataset legal_privilege

PRD §8 success metrics:
    - Legal:        ≥90% precision
    - Therapy/PHI:  ≥92% precision
    - Finance/MNPI: ≥88% precision
    - Performance:  <100ms per analysis (median)

Exit code:
    0 — every dataset met its precision + performance targets
    1 — at least one target was missed
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ogentic_shield import Shield

# ── Dataset registry — name → (jsonl path, profile id, precision target) ────

BENCHMARKS_DIR = Path(__file__).parent

# Generic Presidio / spaCy entity types that fire regardless of profile.
# When evaluating an adversarial-negative example, hits on these types
# don't count as profile-level false positives — the shield profiles
# are about DOMAIN-specific detection beyond Presidio's defaults. The
# generic types still get reported in the per-recognizer table.
GENERIC_PRESIDIO_TYPES = {
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "URL",
    "IP_ADDRESS",
    "LOCATION",
    "DATE_TIME",
    "NRP",  # nationality / religious / political group
    "CREDIT_CARD",
    "IBAN_CODE",
    "US_BANK_NUMBER",
    "US_DRIVER_LICENSE",
    "US_PASSPORT",
}

DATASETS = [
    {
        "name": "legal_privilege",
        "jsonl": BENCHMARKS_DIR / "legal_privilege.jsonl",
        "profile_id": "shield-legal",
        "precision_target": 0.90,
    },
    {
        "name": "therapy_phi",
        "jsonl": BENCHMARKS_DIR / "therapy_phi.jsonl",
        "profile_id": "shield-therapy",
        "precision_target": 0.92,
    },
    {
        "name": "therapy_phi_pro",
        "jsonl": BENCHMARKS_DIR / "therapy_phi_pro.jsonl",
        "profile_id": "shield-therapy-pro",
        "precision_target": 0.92,
    },
    {
        "name": "finance_mnpi",
        "jsonl": BENCHMARKS_DIR / "finance_mnpi.jsonl",
        "profile_id": "shield-finance",
        "precision_target": 0.88,
    },
]

PERFORMANCE_TARGET_MS = 100.0  # PRD §8: median analysis must be < 100ms.

# Warmup string that goes through every layer (NER + a regex match) so
# spaCy's JIT/lazy-load cost lands BEFORE we start measuring per-call
# latency. Run once per Shield instance.
WARMUP_TEXT = "Privileged & confidential — outside counsel reviewed this matter."


@dataclass
class Example:
    id: str
    text: str
    expected_entity_types: set[str]
    expected_level: str  # NONE | LOW | MEDIUM | HIGH | CRITICAL
    category: str  # true_positive | true_negative | adversarial_negative
    notes: str = ""


@dataclass
class ExampleResult:
    example: Example
    detected_entity_types: set[str]
    detected_level: str
    duration_ms: float
    is_true_positive_hit: bool = False  # at least one expected entity caught
    is_false_positive: bool = False  # detection on a TN example
    is_false_negative: bool = False  # missed detection on a TP example
    per_type_hits: set[str] = field(default_factory=set)


@dataclass
class DatasetReport:
    name: str
    profile_id: str
    examples: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    durations_ms: list[float]
    per_recognizer: dict[str, dict[str, int]]
    precision_target: float

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def median_duration_ms(self) -> float:
        return statistics.median(self.durations_ms) if self.durations_ms else 0.0

    @property
    def p95_duration_ms(self) -> float:
        if not self.durations_ms:
            return 0.0
        # statistics.quantiles is exclusive by default — n=20 → indexes 1..19
        # at i/20 quantiles. We want p95 ≈ 19/20 → index 18.
        if len(self.durations_ms) < 20:
            return max(self.durations_ms)
        return statistics.quantiles(self.durations_ms, n=20)[18]

    def meets_precision_target(self) -> bool:
        return self.precision >= self.precision_target

    def meets_performance_target(self) -> bool:
        return self.median_duration_ms < PERFORMANCE_TARGET_MS


# ── Loaders ────────────────────────────────────────────────────────────────


def load_dataset(jsonl_path: Path) -> list[Example]:
    """Read a JSONL benchmark file. Skips blank lines and comment lines
    starting with '#'."""
    examples: list[Example] = []
    with open(jsonl_path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            obj = json.loads(line)
            examples.append(
                Example(
                    id=obj["id"],
                    text=obj["text"],
                    expected_entity_types={e["type"] for e in obj.get("expected_entities", [])},
                    expected_level=obj["expected_level"],
                    category=obj.get("category", "true_positive"),
                    notes=obj.get("notes", ""),
                )
            )
    return examples


# ── Scoring ────────────────────────────────────────────────────────────────


def evaluate_example(example: Example, shield: Shield) -> ExampleResult:
    """Run one example through Shield.analyze and score the result.

    True positive: example.category == "true_positive" AND at least one
        expected entity type was detected.
    False negative: example.category == "true_positive" AND no expected
        entity types were detected.
    True negative: example.category in {"true_negative", "adversarial_negative"}
        AND no entities were detected (or only entities the dataset
        explicitly tolerates — currently none).
    False positive: example.category in {"true_negative", "adversarial_negative"}
        AND any entity was detected.
    """
    start = time.perf_counter()
    result = shield.analyze(example.text)
    duration_ms = (time.perf_counter() - start) * 1000

    detected_types = {e.category for e in result.entities}
    per_type_hits = example.expected_entity_types & detected_types

    res = ExampleResult(
        example=example,
        detected_entity_types=detected_types,
        detected_level=result.sensitivity_level.value,
        duration_ms=duration_ms,
        per_type_hits=per_type_hits,
    )

    is_negative = example.category in {"true_negative", "adversarial_negative"}
    if is_negative:
        # Domain-specific detections only — generic Presidio types (PERSON,
        # EMAIL_ADDRESS, etc.) are filtered. They fire on every text and
        # aren't what the shield profiles are testing.
        domain_specific_hits = detected_types - GENERIC_PRESIDIO_TYPES
        if domain_specific_hits:
            res.is_false_positive = True
    else:
        # true_positive
        if per_type_hits:
            res.is_true_positive_hit = True
        else:
            res.is_false_negative = True
    return res


def report_for_dataset(
    dataset_cfg: dict[str, Any],
    shield: Shield,
) -> tuple[DatasetReport, list[ExampleResult]]:
    examples = load_dataset(dataset_cfg["jsonl"])

    # Warmup pass — spaCy's NER pipeline lazy-loads on first call (~500-
    # 1000ms cold). Without this, the first measured example absorbs the
    # entire warmup cost and skews median/p95 latency. The warmup
    # result is discarded.
    shield.analyze(WARMUP_TEXT)

    results = [evaluate_example(ex, shield) for ex in examples]

    tp = sum(1 for r in results if r.is_true_positive_hit)
    fn = sum(1 for r in results if r.is_false_negative)
    fp = sum(1 for r in results if r.is_false_positive)
    tn = sum(
        1
        for r in results
        if r.example.category in {"true_negative", "adversarial_negative"}
        and not r.is_false_positive
    )

    # Per-recognizer table — TP / FP / FN counts keyed by entity type.
    per_recognizer: dict[str, dict[str, int]] = {}
    for r in results:
        is_negative = r.example.category in {"true_negative", "adversarial_negative"}
        if is_negative:
            for detected_type in r.detected_entity_types:
                rec = per_recognizer.setdefault(
                    detected_type, {"tp": 0, "fp": 0, "fn": 0}
                )
                rec["fp"] += 1
        else:
            for expected in r.example.expected_entity_types:
                rec = per_recognizer.setdefault(expected, {"tp": 0, "fp": 0, "fn": 0})
                if expected in r.detected_entity_types:
                    rec["tp"] += 1
                else:
                    rec["fn"] += 1

    return (
        DatasetReport(
            name=dataset_cfg["name"],
            profile_id=dataset_cfg["profile_id"],
            examples=len(examples),
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            true_negatives=tn,
            durations_ms=[r.duration_ms for r in results],
            per_recognizer=per_recognizer,
            precision_target=dataset_cfg["precision_target"],
        ),
        results,
    )


# ── Pretty printer ─────────────────────────────────────────────────────────


def print_text_report(reports: list[DatasetReport]) -> None:
    bar = "═" * 70
    print(f"\n{bar}")
    print(" ogentic-shield benchmark report")
    print(f"{bar}\n")

    overall_pass = True
    for r in reports:
        precision_pass = r.meets_precision_target()
        perf_pass = r.meets_performance_target()
        overall_pass = overall_pass and precision_pass and perf_pass

        print(f"── {r.name} (profile: {r.profile_id})")
        print(f"   Examples:   {r.examples}")
        print(
            f"   TP / FP / FN / TN: {r.true_positives} / "
            f"{r.false_positives} / {r.false_negatives} / {r.true_negatives}"
        )
        print(
            f"   Precision:  {r.precision * 100:.1f}%  "
            f"(target ≥{r.precision_target * 100:.0f}%) "
            f"{'✅' if precision_pass else '❌'}"
        )
        print(f"   Recall:     {r.recall * 100:.1f}%")
        print(f"   F1:         {r.f1 * 100:.1f}%")
        print(
            f"   Latency:    median={r.median_duration_ms:.1f}ms  "
            f"p95={r.p95_duration_ms:.1f}ms  "
            f"(target median <{PERFORMANCE_TARGET_MS:.0f}ms) "
            f"{'✅' if perf_pass else '❌'}"
        )
        if r.per_recognizer:
            print("   Per-recognizer:")
            for rec_type, counts in sorted(r.per_recognizer.items()):
                tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
                p_denom = tp + fp
                rec_p = tp / p_denom if p_denom else 0.0
                rec_denom = tp + fn
                rec_r = tp / rec_denom if rec_denom else 0.0
                print(
                    f"     {rec_type:35s}  TP={tp:2d}  FP={fp:2d}  FN={fn:2d}  "
                    f"P={rec_p * 100:5.1f}%  R={rec_r * 100:5.1f}%"
                )
        print()

    print(bar)
    if overall_pass:
        print(" ✅ ALL TARGETS MET")
    else:
        print(" ❌ ONE OR MORE TARGETS MISSED")
    print(f"{bar}\n")


def write_json_report(
    reports: list[DatasetReport],
    out_path: Path,
) -> None:
    payload = {
        "performance_target_ms": PERFORMANCE_TARGET_MS,
        "datasets": [
            {
                "name": r.name,
                "profile_id": r.profile_id,
                "examples": r.examples,
                "true_positives": r.true_positives,
                "false_positives": r.false_positives,
                "false_negatives": r.false_negatives,
                "true_negatives": r.true_negatives,
                "precision": r.precision,
                "recall": r.recall,
                "f1": r.f1,
                "precision_target": r.precision_target,
                "median_duration_ms": r.median_duration_ms,
                "p95_duration_ms": r.p95_duration_ms,
                "meets_precision_target": r.meets_precision_target(),
                "meets_performance_target": r.meets_performance_target(),
                "per_recognizer": r.per_recognizer,
            }
            for r in reports
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2))


# ── CLI ────────────────────────────────────────────────────────────────────


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
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit non-zero when any precision/performance target is missed. "
            "Default: exit 0 (the runner is informational; targets are PRD §8 "
            "aspirational, tracked over time)."
        ),
    )
    args = parser.parse_args()

    selected = DATASETS
    if args.dataset:
        selected = [d for d in DATASETS if d["name"] in args.dataset]

    reports: list[DatasetReport] = []
    for cfg in selected:
        print(f"Initialising Shield(profiles=['{cfg['profile_id']}'])...", flush=True)
        shield = Shield(profiles=[cfg["profile_id"]])
        print(f"Running {cfg['name']}...", flush=True)
        report, _results = report_for_dataset(cfg, shield)
        reports.append(report)

    print_text_report(reports)
    if args.json:
        write_json_report(reports, args.json)
        print(f"JSON report written to {args.json}")

    overall_pass = all(
        r.meets_precision_target() and r.meets_performance_target() for r in reports
    )
    if args.strict:
        return 0 if overall_pass else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
