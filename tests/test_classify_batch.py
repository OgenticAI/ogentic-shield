"""Tests for Shield.classify_batch() — OGE-1057."""

from __future__ import annotations

import pytest

from ogentic_shield import AnalysisResult, BatchItemError, SensitivityLevel, Shield


@pytest.fixture
def default_shield() -> Shield:
    """Shield with the default profile set (shield-legal as a known-good profile)."""
    return Shield(profiles=["shield-legal"])


class TestClassifyBatchOrderPreservation:
    """Results align positionally with inputs."""

    def test_returns_one_result_per_input(self, default_shield: Shield) -> None:
        results = default_shield.classify_batch(["a", "b"])
        assert len(results) == 2
        assert all(isinstance(r, AnalysisResult) for r in results)


class TestClassifyBatchEmptyList:
    """Empty input must return an empty list without touching the pipeline."""

    def test_empty_list_returns_empty_list(self, default_shield: Shield) -> None:
        results = default_shield.classify_batch([])
        assert results == []


class TestClassifyBatchPerItemIsolation:
    """An exception on one item must not abort the batch."""

    def test_second_item_failure_captured_as_batch_item_error(
        self, default_shield: Shield, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        call_count = 0

        def _analyze_side_effect(text: str, **kwargs: object) -> AnalysisResult:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("simulated analysis failure")
            # Delegate to the real analyze for the first call.
            return Shield(profiles=["shield-legal"]).analyze(text)

        monkeypatch.setattr(default_shield, "analyze", _analyze_side_effect)

        results = default_shield.classify_batch(["first text", "second text"])

        assert len(results) == 2
        assert isinstance(results[0], AnalysisResult)
        assert isinstance(results[1], BatchItemError)
        assert results[1].index == 1
        assert results[1].error_type == "RuntimeError"
        assert "simulated analysis failure" in results[1].error


class TestClassifyBatchEmptyString:
    """An empty string is valid input and should return a NONE-sensitivity result."""

    def test_empty_string_returns_analysis_result_with_no_entities(
        self, default_shield: Shield
    ) -> None:
        results = default_shield.classify_batch([""])
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, AnalysisResult)
        assert result.sensitivity_level == SensitivityLevel.NONE
        assert result.entities == []


class TestClassifyBatchProfileOverride:
    """profile= kwarg must be applied to every item in the batch."""

    def test_profile_override_reflected_in_profile_ids(
        self, default_shield: Shield
    ) -> None:
        results = default_shield.classify_batch(
            ["some text to analyze"], profile="shield-legal"
        )
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, AnalysisResult)
        assert "shield-legal" in result.profile_ids


class TestClassifyBatchProfileNoneUsesInstanceProfiles:
    """When profile=None, the Shield's configured profiles are used."""

    def test_instance_profiles_used_when_profile_is_none(self) -> None:
        finance_shield = Shield(profiles=["shield-finance"])
        results = finance_shield.classify_batch(["some text to analyze"])
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, AnalysisResult)
        assert result.profile_ids == ["shield-finance"]


class TestClassifyBatchAllFail:
    """When every item raises, the method must return a list of BatchItemError, not propagate."""

    def test_all_fail_returns_all_batch_item_errors(
        self, default_shield: Shield, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _always_raise(text: str, **kwargs: object) -> AnalysisResult:
            raise RuntimeError("always fails")

        monkeypatch.setattr(default_shield, "analyze", _always_raise)

        results = default_shield.classify_batch(["alpha", "beta", "gamma"])

        assert len(results) == 3
        assert all(isinstance(r, BatchItemError) for r in results)
        assert [r.index for r in results] == [0, 1, 2]  # type: ignore[union-attr]


class TestClassifyBatchFailureAtIndexZero:
    """A failure at index 0 must not prevent index 1 from being analyzed."""

    def test_first_item_fails_second_item_succeeds(
        self, default_shield: Shield, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        call_count = 0

        def _raise_on_first(text: str, **kwargs: object) -> AnalysisResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first item fails")
            return Shield(profiles=["shield-legal"]).analyze(text)

        monkeypatch.setattr(default_shield, "analyze", _raise_on_first)

        results = default_shield.classify_batch(["first text", "second text"])

        assert len(results) == 2
        assert isinstance(results[0], BatchItemError)
        assert results[0].index == 0
        assert isinstance(results[1], AnalysisResult)


class TestClassifyBatchProfileNotFoundIsolation:
    """An invalid profile must produce a BatchItemError, not a raised exception."""

    def test_invalid_profile_returns_batch_item_error(
        self, default_shield: Shield
    ) -> None:
        results = default_shield.classify_batch(["text"], profile="shield-nonexistent")

        assert len(results) == 1
        assert isinstance(results[0], BatchItemError)
        assert results[0].error_type == "ProfileNotFoundError"
