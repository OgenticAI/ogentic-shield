"""Configurable NER spaCy model + analyzer caching (lean-memory deployment).

The NER layer's spaCy model is now selectable: ``en_core_web_lg`` (default,
accuracy) or a smaller model like ``en_core_web_sm`` (~5x less memory) for
constrained deployments. The analyzer is cached per (model, profiles) so the
model loads once instead of on every request.

These tests avoid loading Presidio where possible by patching ``run_pipeline`` /
``run_layer1`` — a real model load per test would be slow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ogentic_shield.config import DEFAULT_NER_MODEL, ShieldConfig, load_config


def test_default_ner_model_is_lg() -> None:
    assert ShieldConfig().ner_model == "en_core_web_lg"
    assert DEFAULT_NER_MODEL == "en_core_web_lg"


def test_load_config_reads_ner_model(tmp_path: Path) -> None:
    cfg_file = tmp_path / "shield.yaml"
    cfg_file.write_text("layers:\n  ner_model: en_core_web_sm\n", encoding="utf-8")
    cfg = load_config(cfg_file)
    assert cfg.ner_model == "en_core_web_sm"


def test_load_config_defaults_ner_model_when_absent(tmp_path: Path) -> None:
    cfg_file = tmp_path / "shield.yaml"
    cfg_file.write_text("version: '0.1'\n", encoding="utf-8")
    assert load_config(cfg_file).ner_model == "en_core_web_lg"


def test_shield_threads_ner_model_to_pipeline(monkeypatch: Any) -> None:
    """Shield.analyze must pass its configured ner_model down to run_pipeline —
    verified without loading Presidio by capturing the call."""
    captured: dict[str, Any] = {}

    def _fake_run_pipeline(**kwargs: Any) -> Any:
        captured.update(kwargs)
        from ogentic_shield.models import AnalysisResult, SensitivityLevel

        return AnalysisResult(
            text_hash="sha256:x",
            entities=[],
            score=0,
            sensitivity_level=SensitivityLevel.NONE,
            category_groups_found=set(),
            top_category=None,
            top_confidence=0.0,
            entity_count=0,
            processing_time_ms=0.0,
            layers_invoked=[],
            profile_ids=["shield-legal"],
            routing_suggestion="cloud_ok",
        )

    monkeypatch.setattr("ogentic_shield.shield.run_pipeline", _fake_run_pipeline)

    from ogentic_shield import Shield

    shield = Shield(profiles=["shield-legal"], config=ShieldConfig(
        profiles=["shield-legal"], ner_model="en_core_web_sm"
    ))
    shield.analyze("hello")
    assert captured["ner_model"] == "en_core_web_sm"


def test_run_layer1_default_model_arg() -> None:
    """run_layer1's ner_model default stays lg (backward compatible signature)."""
    import inspect

    from ogentic_shield.layers.regex_ner import run_layer1

    assert inspect.signature(run_layer1).parameters["ner_model"].default == "en_core_web_lg"


def test_analyzer_is_cached_per_model_and_profiles() -> None:
    """The same (model, profiles) returns the same cached analyzer instance —
    proving the model isn't rebuilt per call. Uses the small model for speed."""
    from ogentic_shield.layers.regex_ner import _get_analyzer

    a = _get_analyzer("en_core_web_sm", ("shield-legal",))
    b = _get_analyzer("en_core_web_sm", ("shield-legal",))
    assert a is b  # cache hit — model loaded once
    c = _get_analyzer("en_core_web_sm", ("shield-finance",))
    assert c is not a  # different profile set → different analyzer
