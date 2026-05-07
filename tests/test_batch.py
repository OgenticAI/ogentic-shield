"""Tests for Shield.analyze_batch (OGE-319)."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from ogentic_shield import AnalysisResult, BatchItemError, Shield


@pytest.fixture(scope="module")
def finance_shield_module() -> Shield:
    # Module-scoped to amortize the Presidio cold-start cost across the suite.
    return Shield(profiles=["shield-finance"])


SAMPLE_TEXTS = [
    "Goldman Sachs is advising the buyer at $47/share. Insider info.",
    "The weather is nice today.",
    "Confidential: pending acquisition of TargetCo for $4.2B.",
    "Just a normal status update from the team.",
]


# ── Happy path ─────────────────────────────────────────────────────────────


class TestAnalyzeBatchSuccess:
    def test_returns_one_result_per_input(self, finance_shield_module: Shield):
        results = finance_shield_module.analyze_batch(SAMPLE_TEXTS, max_workers=2)
        assert len(results) == len(SAMPLE_TEXTS)
        assert all(isinstance(r, AnalysisResult) for r in results)

    def test_preserves_input_order(self, finance_shield_module: Shield):
        results = finance_shield_module.analyze_batch(SAMPLE_TEXTS, max_workers=4)
        # Sensitive items 0 and 2 should outscore boring items 1 and 3.
        scores = [r.score for r in results if isinstance(r, AnalysisResult)]
        assert scores[0] > scores[1]
        assert scores[2] > scores[3]

    def test_empty_input_returns_empty(self, finance_shield_module: Shield):
        assert finance_shield_module.analyze_batch([]) == []

    def test_single_item_batch(self, finance_shield_module: Shield):
        results = finance_shield_module.analyze_batch(["A safe sentence."])
        assert len(results) == 1
        assert isinstance(results[0], AnalysisResult)

    def test_invalid_max_workers_raises(self, finance_shield_module: Shield):
        with pytest.raises(ValueError, match="max_workers"):
            finance_shield_module.analyze_batch(["x"], max_workers=0)


# ── Per-item error containment (the headline AC) ──────────────────────────


class TestPerItemErrorContainment:
    def test_one_failure_does_not_abort_batch(self, finance_shield_module: Shield):
        # Patch Shield.analyze to raise on a specific input; everything else
        # should still flow through cleanly.
        original = Shield.analyze
        sentinel = "POISON-PILL"

        def stubbed(self, text, *args, **kwargs):
            if text == sentinel:
                raise RuntimeError("simulated detector failure")
            return original(self, text, *args, **kwargs)

        with patch.object(Shield, "analyze", stubbed):
            results = finance_shield_module.analyze_batch(
                [SAMPLE_TEXTS[0], sentinel, SAMPLE_TEXTS[2]],
                max_workers=2,
            )

        assert len(results) == 3
        assert isinstance(results[0], AnalysisResult)
        assert isinstance(results[1], BatchItemError)
        assert isinstance(results[2], AnalysisResult)

        err = results[1]
        assert isinstance(err, BatchItemError)
        assert err.index == 1
        assert err.error_type == "RuntimeError"
        assert "simulated detector failure" in err.error

    def test_all_items_fail_returns_all_errors(self, finance_shield_module: Shield):
        def always_fail(self, text, *args, **kwargs):  # noqa: ARG001
            raise ValueError(f"nope: {text[:10]}")

        with patch.object(Shield, "analyze", always_fail):
            results = finance_shield_module.analyze_batch(
                ["a", "b", "c"], max_workers=2
            )

        assert len(results) == 3
        assert all(isinstance(r, BatchItemError) for r in results)
        assert [r.index for r in results] == [0, 1, 2]  # type: ignore[union-attr]


# ── Throughput vs sequential (informational) ──────────────────────────────


class TestThroughput:
    def test_batch_no_slower_than_sequential_for_small_inputs(
        self, finance_shield_module: Shield
    ):
        """A weak guarantee — Layers 1+2 are mostly C-extension code which
        releases the GIL during regex / spaCy hot paths, so we don't promise
        a strict speedup. We DO promise that the threading overhead doesn't
        make small batches catastrophically slower."""
        texts = SAMPLE_TEXTS * 2  # 8 inputs

        # Warm up Presidio once so the first sequential analyze isn't
        # paying the cold-start cost.
        finance_shield_module.analyze(texts[0])

        seq_start = time.perf_counter()
        for t in texts:
            finance_shield_module.analyze(t)
        seq_elapsed = time.perf_counter() - seq_start

        batch_start = time.perf_counter()
        finance_shield_module.analyze_batch(texts, max_workers=4)
        batch_elapsed = time.perf_counter() - batch_start

        # Allow the batch to be up to 3x slower (defensive for weak hardware
        # or cold caches in CI). The point is to catch a regression where
        # batching adds *catastrophic* overhead, not to micro-benchmark.
        assert batch_elapsed < seq_elapsed * 3, (
            f"batch took {batch_elapsed:.3f}s vs sequential {seq_elapsed:.3f}s "
            "— threading overhead may have regressed"
        )
