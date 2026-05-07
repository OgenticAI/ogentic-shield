"""Tests for the cross-layer calibration framework (OGE-321)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ogentic_shield import (
    AnalysisResult,
    CategoryGroup,
    DetectedEntity,
    DetectionLayer,
    Shield,
)
from ogentic_shield.calibration import (
    CalibrationMethod,
    Calibrator,
    LayerCalibration,
    _isotonic_apply,
    get_calibrator,
    set_calibrator,
)
from ogentic_shield.pipeline import _calibrate_entities, build_analysis_result
from ogentic_shield.profiles import get_profile


@pytest.fixture(autouse=True)
def _restore_calibrator_singleton():
    """Each test starts with the packaged default; restore between tests."""
    set_calibrator(None)  # reset to lazy default
    yield
    set_calibrator(None)


# ── LayerCalibration methods ───────────────────────────────────────────────


class TestLinear:
    def test_factor_one_is_identity(self):
        cal = LayerCalibration(
            layer=DetectionLayer.LLM,
            method=CalibrationMethod.LINEAR,
            params={"factor": 1.0},
        )
        assert cal.apply(0.5) == 0.5

    def test_factor_half_halves(self):
        cal = LayerCalibration(
            layer=DetectionLayer.LLM,
            method=CalibrationMethod.LINEAR,
            params={"factor": 0.5},
        )
        assert cal.apply(0.6) == pytest.approx(0.3)

    def test_clamps_above_1(self):
        cal = LayerCalibration(
            layer=DetectionLayer.LLM,
            method=CalibrationMethod.LINEAR,
            params={"factor": 5.0},
        )
        assert cal.apply(0.5) == 1.0


class TestPlatt:
    def test_a_zero_b_zero_returns_half(self):
        cal = LayerCalibration(
            layer=DetectionLayer.LLM,
            method=CalibrationMethod.PLATT,
            params={"a": 0.0, "b": 0.0},
        )
        assert cal.apply(0.5) == pytest.approx(0.5)

    def test_strong_positive_a_pushes_toward_zero(self):
        # Sigmoid(a*raw + b) = 1/(1+exp(a*raw + b)); a=10, b=-5 → at raw=0.5, exp(0)=1 → 0.5
        cal = LayerCalibration(
            layer=DetectionLayer.LLM,
            method=CalibrationMethod.PLATT,
            params={"a": 10.0, "b": -5.0},
        )
        assert cal.apply(0.5) == pytest.approx(0.5, abs=0.01)
        assert cal.apply(0.9) < 0.1  # high raw → calibrated low (a positive saturates)

    def test_extreme_params_dont_overflow(self):
        cal = LayerCalibration(
            layer=DetectionLayer.LLM,
            method=CalibrationMethod.PLATT,
            params={"a": 1000.0, "b": 0.0},
        )
        # No exception; saturates cleanly.
        assert cal.apply(1.0) == 0.0
        assert cal.apply(-1.0) == 1.0


class TestIsotonic:
    def test_identity_breakpoints(self):
        cal = LayerCalibration(
            layer=DetectionLayer.LLM,
            method=CalibrationMethod.ISOTONIC,
            params={"breakpoints": [[0.0, 0.0], [1.0, 1.0]]},
        )
        assert cal.apply(0.5) == pytest.approx(0.5)

    def test_piecewise_linear_interpolation(self):
        # Down-weight high confidences: 0→0, 0.5→0.5, 1.0→0.7
        cal = LayerCalibration(
            layer=DetectionLayer.LLM,
            method=CalibrationMethod.ISOTONIC,
            params={"breakpoints": [[0.0, 0.0], [0.5, 0.5], [1.0, 0.7]]},
        )
        assert cal.apply(0.75) == pytest.approx(0.6)

    def test_clamps_outside_breakpoint_range(self):
        cal = LayerCalibration(
            layer=DetectionLayer.LLM,
            method=CalibrationMethod.ISOTONIC,
            params={"breakpoints": [[0.2, 0.1], [0.8, 0.6]]},
        )
        assert cal.apply(0.0) == pytest.approx(0.1)
        assert cal.apply(1.0) == pytest.approx(0.6)

    def test_isotonic_apply_handles_empty(self):
        # Defensive: identity if no breakpoints supplied.
        assert _isotonic_apply(0.42, []) == pytest.approx(0.42)


# ── Calibrator ──────────────────────────────────────────────────────────────


class TestCalibrator:
    def test_identity_passthrough(self):
        c = Calibrator.identity()
        assert c.apply(0.5, DetectionLayer.LLM) == 0.5
        assert not c.has(DetectionLayer.LLM)

    def test_unregistered_layer_passes_through(self):
        c = Calibrator(
            calibrations={
                DetectionLayer.LLM: LayerCalibration(
                    layer=DetectionLayer.LLM,
                    method=CalibrationMethod.LINEAR,
                    params={"factor": 0.5},
                )
            }
        )
        assert c.apply(0.5, DetectionLayer.REGEX) == 0.5  # no calibration registered
        assert c.apply(0.5, DetectionLayer.LLM) == 0.25

    def test_clamps_input(self):
        c = Calibrator.identity()
        assert c.apply(2.0, DetectionLayer.LLM) == 1.0
        assert c.apply(-0.5, DetectionLayer.LLM) == 0.0

    def test_round_trip_dict(self):
        c = Calibrator(
            calibrations={
                DetectionLayer.LLM: LayerCalibration(
                    layer=DetectionLayer.LLM,
                    method=CalibrationMethod.LINEAR,
                    params={"factor": 0.7},
                    notes="test",
                ),
            }
        )
        round_trip = Calibrator.from_dict(c.to_dict())
        assert round_trip.apply(0.9, DetectionLayer.LLM) == pytest.approx(0.63)

    def test_round_trip_file(self, tmp_path: Path):
        c = Calibrator(
            calibrations={
                DetectionLayer.LLM: LayerCalibration(
                    layer=DetectionLayer.LLM,
                    method=CalibrationMethod.PLATT,
                    params={"a": 1.0, "b": 0.0},
                ),
            }
        )
        path = tmp_path / "cal.json"
        c.save(path)
        loaded = Calibrator.from_file(path)
        assert loaded.apply(0.5, DetectionLayer.LLM) == pytest.approx(c.apply(0.5, DetectionLayer.LLM))

    def test_unknown_layer_in_json_skipped(self):
        c = Calibrator.from_dict(
            {
                "version": "test",
                "layers": {
                    "BOGUS": {"method": "linear", "params": {"factor": 0.5}},
                    "LLM": {"method": "linear", "params": {"factor": 0.7}},
                },
            }
        )
        assert c.apply(0.5, DetectionLayer.LLM) == pytest.approx(0.35)


# ── Packaged default loader ─────────────────────────────────────────────────


class TestPackagedDefault:
    def test_default_calibrator_loads_packaged_factors(self):
        c = get_calibrator()
        # The shipped JSON discounts LLM and passes through everything else.
        assert c.has(DetectionLayer.LLM)
        # Linear factor should be ≤ 1 — Layer 3 is being discounted.
        out = c.apply(1.0, DetectionLayer.LLM)
        assert out < 1.0

    def test_set_calibrator_overrides_singleton(self):
        custom = Calibrator(
            calibrations={
                DetectionLayer.LLM: LayerCalibration(
                    layer=DetectionLayer.LLM,
                    method=CalibrationMethod.LINEAR,
                    params={"factor": 0.1},
                ),
            }
        )
        set_calibrator(custom)
        assert get_calibrator().apply(1.0, DetectionLayer.LLM) == pytest.approx(0.1)

    def test_set_none_resets_to_packaged_default(self):
        # Install a marker calibrator, then reset.
        identity = Calibrator.identity()
        set_calibrator(identity)
        assert get_calibrator() is identity
        set_calibrator(None)
        # Next call rebuilds from packaged defaults.
        c = get_calibrator()
        assert c is not identity
        assert c.has(DetectionLayer.LLM)


# ── Pipeline integration ────────────────────────────────────────────────────


def _e(layer: DetectionLayer, conf: float) -> DetectedEntity:
    return DetectedEntity(
        text="x",
        category="MNPI_MARKER",
        category_group=CategoryGroup.MNPI,
        confidence=conf,
        detection_layer=layer,
        start=0,
        end=1,
    )


class TestCalibrateEntities:
    def test_pass_through_when_layer_uncalibrated(self):
        cal = Calibrator(
            calibrations={
                DetectionLayer.LLM: LayerCalibration(
                    layer=DetectionLayer.LLM,
                    method=CalibrationMethod.LINEAR,
                    params={"factor": 0.5},
                ),
            }
        )
        entity = _e(DetectionLayer.REGEX, 0.9)
        result = _calibrate_entities([entity], cal)
        assert result[0] is entity  # unchanged identity (no calibration registered)

    def test_calibrates_when_layer_registered(self):
        cal = Calibrator(
            calibrations={
                DetectionLayer.LLM: LayerCalibration(
                    layer=DetectionLayer.LLM,
                    method=CalibrationMethod.LINEAR,
                    params={"factor": 0.5},
                ),
            }
        )
        entity = _e(DetectionLayer.LLM, 0.8)
        result = _calibrate_entities([entity], cal)
        assert result[0].confidence == pytest.approx(0.4)
        assert result[0].metadata["raw_confidence"] == pytest.approx(0.8)

    def test_does_not_overwrite_existing_raw_confidence(self):
        cal = Calibrator(
            calibrations={
                DetectionLayer.LLM: LayerCalibration(
                    layer=DetectionLayer.LLM,
                    method=CalibrationMethod.LINEAR,
                    params={"factor": 0.5},
                ),
            }
        )
        # Pretend a future Layer 3 already pre-stamped raw_confidence.
        entity = DetectedEntity(
            text="x",
            category="MNPI_MARKER",
            category_group=CategoryGroup.MNPI,
            confidence=0.8,
            detection_layer=DetectionLayer.LLM,
            start=0,
            end=1,
            metadata={"raw_confidence": 0.95},
        )
        result = _calibrate_entities([entity], cal)
        assert result[0].metadata["raw_confidence"] == pytest.approx(0.95)


class TestBuildAnalysisResult:
    def test_min_confidence_compares_against_calibrated_value(self):
        # LLM calibration factor 0.5; raw 0.9 → calibrated 0.45.
        # min_confidence 0.5 should drop it.
        cal = Calibrator(
            calibrations={
                DetectionLayer.LLM: LayerCalibration(
                    layer=DetectionLayer.LLM,
                    method=CalibrationMethod.LINEAR,
                    params={"factor": 0.5},
                ),
            }
        )
        profile = get_profile("shield-finance")
        entities = [_e(DetectionLayer.LLM, 0.9)]
        result: AnalysisResult = build_analysis_result(
            text="abc",
            entities=entities,
            profiles=[profile],
            layers_invoked=[DetectionLayer.LLM],
            min_confidence=0.5,
            started_at=0.0,
            calibrator=cal,
        )
        assert result.entity_count == 0


# ── End-to-end via Shield ───────────────────────────────────────────────────


class TestShieldHonorsCalibratorOverride:
    def test_set_calibrator_zero_factor_drops_low_confidence_llm(self, finance_shield: Shield):
        # Force LLM confidences toward zero → no LLM entity should pass the
        # default min_confidence filter even if Layer 3 fires. (Layer 3 is
        # disabled by default so this is mostly a smoke test for the
        # set_calibrator hook reaching the pipeline.)
        zero = Calibrator(
            calibrations={
                DetectionLayer.LLM: LayerCalibration(
                    layer=DetectionLayer.LLM,
                    method=CalibrationMethod.LINEAR,
                    params={"factor": 0.0},
                ),
            }
        )
        set_calibrator(zero)
        result = finance_shield.analyze("Confidential MNPI: pending acquisition.")
        assert all(e.detection_layer != DetectionLayer.LLM for e in result.entities)
