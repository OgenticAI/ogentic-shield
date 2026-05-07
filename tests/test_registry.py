"""Tests for ogentic_shield.registry — ModelRegistry / ModelTier (OGE-315)."""

from __future__ import annotations

import pytest

from ogentic_shield import ModelRegistry, ModelTier, Shield
from ogentic_shield.registry import ROLE_CLASSIFICATION, ROLE_NER_AUGMENT


class TestRequiredModels:
    def test_fast_returns_granite_moe(self):
        assert ModelRegistry().required_models("fast") == ["granite3.1-moe:1b"]

    def test_quality_returns_mixtral(self):
        assert ModelRegistry().required_models("quality") == ["mixtral:8x7b"]

    def test_comprehensive_returns_classifier_and_ner_model(self):
        models = ModelRegistry().required_models("comprehensive")
        assert "mixtral:8x7b" in models
        assert "qwen3:4b" in models
        assert len(models) == 2  # no dupes

    def test_default_is_fast(self):
        assert ModelRegistry().required_models() == ["granite3.1-moe:1b"]

    def test_accepts_enum(self):
        assert ModelRegistry().required_models(ModelTier.QUALITY) == ["mixtral:8x7b"]

    def test_unknown_tier_raises(self):
        with pytest.raises(ValueError, match="Unknown quality tier"):
            ModelRegistry().required_models("ridiculous")


class TestOverrides:
    def test_override_substitutes_in_required_models(self):
        registry = ModelRegistry({ROLE_CLASSIFICATION: "phi4:14b"})
        assert registry.required_models("fast") == ["phi4:14b"]

    def test_override_wins_over_default(self):
        registry = ModelRegistry({ROLE_CLASSIFICATION: "custom-model:latest"})
        assert registry.get(ROLE_CLASSIFICATION, "quality") == "custom-model:latest"

    def test_unknown_role_at_tier_raises(self):
        # NER augment isn't part of "fast" — and there's no override either.
        with pytest.raises(KeyError, match="ner_augment"):
            ModelRegistry().get(ROLE_NER_AUGMENT, "fast")

    def test_override_can_satisfy_otherwise_unknown_role(self):
        registry = ModelRegistry({ROLE_NER_AUGMENT: "qwen3:1.7b"})
        assert registry.get(ROLE_NER_AUGMENT, "fast") == "qwen3:1.7b"

    def test_dedup_when_override_collides(self):
        registry = ModelRegistry({ROLE_NER_AUGMENT: "mixtral:8x7b"})
        models = registry.required_models("comprehensive")
        assert models == ["mixtral:8x7b"]


class TestShieldIntegration:
    def test_required_models_via_shield_default(self, legal_shield: Shield):
        # Shield's default quality is "fast" (from LlmConfig default).
        assert legal_shield.required_models() == ["granite3.1-moe:1b"]

    def test_required_models_via_shield_explicit_tier(self, legal_shield: Shield):
        assert legal_shield.required_models("quality") == ["mixtral:8x7b"]

    def test_shield_quality_kwarg_changes_default(self):
        shield = Shield(profiles=["shield-finance"], quality="quality")
        assert shield.required_models() == ["mixtral:8x7b"]

    def test_shield_model_override_kwarg_substitutes(self):
        shield = Shield(
            profiles=["shield-legal"],
            model_override={ROLE_CLASSIFICATION: "llama3.1:8b"},
        )
        assert shield.required_models("fast") == ["llama3.1:8b"]
