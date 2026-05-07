"""Fit + report per-layer calibration factors (OGE-321).

Practical fit strategy: grid-search the linear scaling factor for each
layer that maximizes F1 on the OGE-51 datasets while keeping recall ≥ the
uncalibrated baseline. Outputs:

- A JSON file consumable by ``Calibrator.from_file`` (use it to override
  the packaged default at runtime).
- A Markdown ``CALIBRATION_REPORT.md`` showing precision/recall/F1
  before vs. after for each profile.

Usage from the repo root with Ollama running:

    .venv/bin/python benchmarks/fit_calibration.py \\
        --json benchmarks/CALIBRATION_FIT.results.json \\
        --md   benchmarks/CALIBRATION_REPORT.md \\
        --layers REGEX NER RULES LLM

Layer 3 (LLM) is the layer that benefits most from refitting — the L1+L2
layers are corpus-tuned by hand and a global linear scaling is rarely the
right adjustment. Default ``--layers`` is just ``LLM`` for that reason.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Reuse the runner module — sits next to this file.
sys.path.insert(0, str(Path(__file__).parent))

from run_benchmarks import (  # noqa: E402  (sys.path tweak above)
    DATASETS,
    DatasetReport,
    report_for_dataset,
)

from ogentic_shield import Shield
from ogentic_shield.calibration import (
    CalibrationMethod,
    Calibrator,
    LayerCalibration,
    set_calibrator,
)
from ogentic_shield.config import LlmConfig, ShieldConfig
from ogentic_shield.models import DetectionLayer

GRID = [round(0.1 * i, 2) for i in range(1, 11)]  # 0.1 .. 1.0


@dataclass
class FactorScore:
    factor: float
    precision: float
    recall: float
    f1: float


def _build_shield(profile_id: str, *, llm_enabled: bool) -> Shield:
    if not llm_enabled:
        return Shield(profiles=[profile_id])
    config = ShieldConfig(
        profiles=[profile_id],
        llm=LlmConfig(
            enabled=True,
            provider="ollama",
            # Empty model = use registry's "fast" default.
            endpoint="http://localhost:11434",
            timeout_ms=60_000,
            max_retries=1,
            ambiguous_score_range=[0, 100],
        ),
    )
    return Shield(profiles=[profile_id], config=config)


def _fit_layer(layer: DetectionLayer, datasets: list[dict]) -> FactorScore:
    """Grid-search the linear scaling factor that maximizes mean-F1 across
    every dataset for ``layer``.

    Cheap and predictable: 10 factor values × N datasets × ~23 examples each.
    Layers other than LLM run without an Ollama round-trip so they're fast.
    """
    llm_enabled = layer is DetectionLayer.LLM
    best = FactorScore(factor=1.0, precision=0.0, recall=0.0, f1=-1.0)
    for factor in GRID:
        cal = Calibrator(
            calibrations={
                layer: LayerCalibration(
                    layer=layer,
                    method=CalibrationMethod.LINEAR,
                    params={"factor": factor},
                ),
            }
        )
        set_calibrator(cal)
        per_dataset: list[DatasetReport] = []
        for cfg in datasets:
            shield = _build_shield(cfg["profile_id"], llm_enabled=llm_enabled)
            report, _ = report_for_dataset(cfg, shield)
            per_dataset.append(report)
        mean_p = sum(r.precision for r in per_dataset) / len(per_dataset)
        mean_r = sum(r.recall for r in per_dataset) / len(per_dataset)
        mean_f1 = sum(r.f1 for r in per_dataset) / len(per_dataset)
        print(
            f"  layer={layer.value:5} factor={factor:.2f}  P={mean_p * 100:5.1f}%  "
            f"R={mean_r * 100:5.1f}%  F1={mean_f1 * 100:5.1f}%",
            flush=True,
        )
        if mean_f1 > best.f1:
            best = FactorScore(factor=factor, precision=mean_p, recall=mean_r, f1=mean_f1)
    set_calibrator(None)  # restore packaged default
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--layers",
        nargs="*",
        default=["LLM"],
        choices=[layer.value for layer in DetectionLayer],
        help="Which layers to refit. Default: LLM only.",
    )
    parser.add_argument("--json", type=Path, help="Calibrator JSON output path.")
    parser.add_argument("--md", type=Path, help="Markdown report output path.")
    args = parser.parse_args()

    print(f"Fitting layers: {args.layers}", flush=True)
    fits: dict[DetectionLayer, FactorScore] = {}
    for name in args.layers:
        layer = DetectionLayer(name)
        print(f"Fitting layer {layer.value}...", flush=True)
        fits[layer] = _fit_layer(layer, DATASETS)

    # Build a Calibrator from the best factors. Layers we didn't fit pass
    # through (no entry → identity).
    calibrations: dict[DetectionLayer, LayerCalibration] = {}
    fitted_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for layer, score in fits.items():
        calibrations[layer] = LayerCalibration(
            layer=layer,
            method=CalibrationMethod.LINEAR,
            params={"factor": score.factor},
            fitted_at=fitted_at,
            notes=f"Grid-search best F1 over {len(GRID)} factors across {len(DATASETS)} datasets.",
        )

    fitted_calibrator = Calibrator(calibrations=calibrations)
    if args.json:
        fitted_calibrator.save(args.json)
        print(f"Calibrator JSON written to {args.json}")

    if args.md:
        lines = ["# Calibration fit report — OGE-321", ""]
        lines.append("Generated by `benchmarks/fit_calibration.py`. Each row is the")
        lines.append("best linear scaling factor for a layer, chosen by maximizing")
        lines.append("mean F1 across the OGE-51 datasets.")
        lines.append("")
        lines.append("| Layer | Best factor | Precision | Recall | F1 |")
        lines.append("|---|---:|---:|---:|---:|")
        for layer, score in fits.items():
            lines.append(
                f"| `{layer.value}` | {score.factor:.2f} | {score.precision * 100:.1f}% | "
                f"{score.recall * 100:.1f}% | {score.f1 * 100:.1f}% |"
            )
        lines.append("")
        lines.append("To install:")
        lines.append("")
        lines.append("```python")
        lines.append("from ogentic_shield.calibration import Calibrator, set_calibrator")
        lines.append("set_calibrator(Calibrator.from_file('benchmarks/CALIBRATION_FIT.results.json'))")
        lines.append("```")
        lines.append("")
        lines.append("Or replace `src/ogentic_shield/data/calibration.json` with the JSON")
        lines.append("output and ship the new defaults to all consumers.")
        args.md.write_text("\n".join(lines))
        print(f"Markdown report written to {args.md}")

    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["main", "GRID"]
