"""Cross-layer confidence calibration (OGE-321).

Layer 1 (regex) returns binary match/no-match scores. Layer 2 (NER via
Presidio) returns Presidio's own confidences. Layer 2.5 (rules) hand-tunes
confidence per rule. Layer 3 (LLM) emits self-reported confidence which is
systematically over-optimistic relative to the corpus-tuned thresholds the
rest of the pipeline lives by.

Calibration normalizes these so a 0.9 from any layer means the same thing
in the final score. The framework supports three methods:

- ``linear`` — multiply raw confidence by a per-layer factor. Cheap and
  predictable; the v0.2.1 default uses linear scaling everywhere because
  the corpus is too small to fit a more elaborate curve reliably.
- ``platt`` — sigmoid fit ``1 / (1 + exp(a * raw + b))``. For when you
  have enough labelled data to fit a real probability calibration.
- ``isotonic`` — piecewise-linear monotonic fit defined by breakpoints
  ``[(raw, calibrated), ...]``. For non-parametric calibration when a
  sigmoid would over-smooth.

Default factors ship as :data:`PACKAGED_CALIBRATION_PATH` (``data/calibration.json``
inside the installed package). :func:`get_calibrator` lazy-loads it on first
call. Tests / consumers override via :func:`set_calibrator`.

The pipeline applies calibration centrally in
:func:`ogentic_shield.pipeline.build_analysis_result` — each detected
entity's ``confidence`` is rewritten to its calibrated value before the
``min_confidence`` filter and the final score are computed. The original
raw confidence is preserved at ``entity.metadata["raw_confidence"]``.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from importlib import resources
from pathlib import Path
from typing import Any

from ogentic_shield.models import DetectionLayer

logger = logging.getLogger("ogentic_shield.calibration")

# ── Method registry ─────────────────────────────────────────────────────────


class CalibrationMethod(str, Enum):
    """How a raw confidence is mapped to a calibrated confidence."""

    LINEAR = "linear"      # calibrated = clamp(raw * factor)
    PLATT = "platt"        # calibrated = 1 / (1 + exp(a * raw + b))
    ISOTONIC = "isotonic"  # piecewise-linear from breakpoints


def _clamp01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


@dataclass(frozen=True)
class LayerCalibration:
    """Calibration parameters for a single detection layer.

    Frozen so a Calibrator's contents can't drift after it's been read by
    multiple analyze calls running concurrently in AsyncShield's thread pool.
    """

    layer: DetectionLayer
    method: CalibrationMethod
    params: dict[str, Any] = field(default_factory=dict)
    fitted_at: str = ""
    notes: str = ""

    def apply(self, raw: float) -> float:
        if self.method is CalibrationMethod.LINEAR:
            factor = float(self.params.get("factor", 1.0))
            return _clamp01(raw * factor)
        if self.method is CalibrationMethod.PLATT:
            a = float(self.params["a"])
            b = float(self.params["b"])
            try:
                return _clamp01(1.0 / (1.0 + math.exp(a * raw + b)))
            except OverflowError:
                # exp overflow happens at extreme params; saturate cleanly.
                return 0.0 if (a * raw + b) > 0 else 1.0
        if self.method is CalibrationMethod.ISOTONIC:
            return _isotonic_apply(raw, self.params.get("breakpoints", []))
        raise ValueError(f"Unknown calibration method: {self.method!r}")


def _isotonic_apply(raw: float, breakpoints: list) -> float:
    """Piecewise-linear interpolation across (raw, calibrated) pairs.

    ``breakpoints`` is expected to be sorted ascending by raw input, with at
    least two points. Inputs below the first / above the last point clamp to
    the corresponding calibrated values (no extrapolation).
    """
    if not breakpoints or len(breakpoints) < 2:
        return _clamp01(raw)
    pts = [(float(p[0]), float(p[1])) for p in breakpoints]
    pts.sort(key=lambda t: t[0])
    if raw <= pts[0][0]:
        return _clamp01(pts[0][1])
    if raw >= pts[-1][0]:
        return _clamp01(pts[-1][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= raw <= x1:
            if x1 == x0:
                return _clamp01(y0)
            t = (raw - x0) / (x1 - x0)
            return _clamp01(y0 + t * (y1 - y0))
    return _clamp01(raw)


# ── Calibrator ──────────────────────────────────────────────────────────────


@dataclass
class CalibratorMetadata:
    """Provenance for a Calibrator — version, when fit, what data was used."""

    version: str = "v0.2.1"
    fitted_at: str = ""
    datasets: list[str] = field(default_factory=list)
    notes: str = ""


class Calibrator:
    """Per-layer confidence calibration.

    >>> from ogentic_shield.models import DetectionLayer
    >>> c = Calibrator.identity()
    >>> c.apply(0.5, DetectionLayer.LLM)
    0.5
    """

    def __init__(
        self,
        calibrations: dict[DetectionLayer, LayerCalibration] | None = None,
        metadata: CalibratorMetadata | None = None,
    ):
        self._cals: dict[DetectionLayer, LayerCalibration] = dict(calibrations or {})
        self.metadata = metadata or CalibratorMetadata()

    def apply(self, raw: float, layer: DetectionLayer) -> float:
        """Calibrate ``raw`` confidence according to ``layer``'s rule.

        Layers without a registered calibration pass through unchanged
        (identity fallback). Out-of-range inputs are clamped to ``[0, 1]``.
        """
        cal = self._cals.get(layer)
        if cal is None:
            return _clamp01(raw)
        return cal.apply(_clamp01(raw))

    def has(self, layer: DetectionLayer) -> bool:
        return layer in self._cals

    def calibrations(self) -> dict[DetectionLayer, LayerCalibration]:
        """Read-only snapshot of the per-layer calibrations."""
        return dict(self._cals)

    # ── Persistence ─────────────────────────────────────────────────────

    @classmethod
    def identity(cls) -> "Calibrator":
        """A passthrough calibrator. Useful in tests."""
        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Calibrator":
        layers: dict[DetectionLayer, LayerCalibration] = {}
        for layer_name, payload in (data.get("layers") or {}).items():
            try:
                layer = DetectionLayer(layer_name)
            except ValueError:
                logger.warning("Skipping calibration entry for unknown layer %r", layer_name)
                continue
            try:
                method = CalibrationMethod(payload.get("method", "linear"))
            except ValueError:
                logger.warning(
                    "Skipping calibration for %s: unknown method %r",
                    layer_name,
                    payload.get("method"),
                )
                continue
            layers[layer] = LayerCalibration(
                layer=layer,
                method=method,
                params=dict(payload.get("params") or {}),
                fitted_at=str(payload.get("fitted_at") or ""),
                notes=str(payload.get("notes") or ""),
            )
        meta = CalibratorMetadata(
            version=str(data.get("version", "v0.2.1")),
            fitted_at=str(data.get("fitted_at") or ""),
            datasets=list(data.get("datasets") or []),
            notes=str(data.get("notes") or ""),
        )
        return cls(calibrations=layers, metadata=meta)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.metadata.version,
            "fitted_at": self.metadata.fitted_at,
            "datasets": list(self.metadata.datasets),
            "notes": self.metadata.notes,
            "layers": {
                cal.layer.value: {
                    "method": cal.method.value,
                    "params": dict(cal.params),
                    "fitted_at": cal.fitted_at,
                    "notes": cal.notes,
                }
                for cal in self._cals.values()
            },
        }

    @classmethod
    def from_file(cls, path: Path | str) -> "Calibrator":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def save(self, path: Path | str) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n")


# ── Packaged default + module-level singleton ───────────────────────────────

PACKAGED_CALIBRATION_FILE = "calibration.json"

_default_calibrator: Calibrator | None = None


def _load_packaged() -> Calibrator:
    """Load the calibration JSON shipped inside the installed package.

    Returns an identity calibrator if the JSON is missing or malformed —
    Layer 3 will then run uncalibrated, matching pre-OGE-321 behavior.
    """
    try:
        with resources.files("ogentic_shield.data").joinpath(
            PACKAGED_CALIBRATION_FILE
        ).open("r") as fp:
            data = json.load(fp)
    except (FileNotFoundError, ModuleNotFoundError, json.JSONDecodeError) as exc:
        logger.warning(
            "Packaged calibration data missing or malformed (%s); using identity calibration.",
            exc,
        )
        return Calibrator.identity()
    return Calibrator.from_dict(data)


def get_calibrator() -> Calibrator:
    """Return the active calibrator. Lazy-loads the packaged default on first call."""
    global _default_calibrator
    if _default_calibrator is None:
        _default_calibrator = _load_packaged()
    return _default_calibrator


def set_calibrator(calibrator: Calibrator | None) -> None:
    """Override (or reset to default by passing ``None``) the active calibrator.

    Tests use this to install identity calibration so they can assert against
    raw layer confidences. Consumers pinning a specific corpus-fit calibration
    can call this once at startup.
    """
    global _default_calibrator
    _default_calibrator = calibrator


__all__ = [
    "Calibrator",
    "CalibrationMethod",
    "CalibratorMetadata",
    "LayerCalibration",
    "PACKAGED_CALIBRATION_FILE",
    "get_calibrator",
    "set_calibrator",
]
