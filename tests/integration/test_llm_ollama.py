"""Live Layer 3 integration test against a real Ollama daemon.

Skipped by default. Enable on a machine that has Ollama running and the model
pulled:

    ollama serve &
    ollama pull granite3.1-moe:1b
    OGENTIC_SHIELD_OLLAMA_INTEGRATION=1 .venv/bin/pytest tests/integration/

CI runners don't have Ollama, so this is a local-only verification gate.
The benchmark runner (``benchmarks/run_layer3_benchmark.py``) is the
authoritative precision check for OGE-314 — this test just proves the wire
works end-to-end against a real daemon.
"""

from __future__ import annotations

import os

import pytest

from ogentic_shield import Shield
from ogentic_shield.config import LlmConfig, ShieldConfig

INTEGRATION_ENABLED = os.environ.get("OGENTIC_SHIELD_OLLAMA_INTEGRATION") == "1"
INTEGRATION_MODEL = os.environ.get("OGENTIC_SHIELD_OLLAMA_MODEL", "granite3.1-moe:1b")
INTEGRATION_ENDPOINT = os.environ.get(
    "OGENTIC_SHIELD_OLLAMA_ENDPOINT", "http://localhost:11434"
)

pytestmark = pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="Set OGENTIC_SHIELD_OLLAMA_INTEGRATION=1 to run live Ollama tests.",
)


def _live_shield(profile_id: str) -> Shield:
    config = ShieldConfig(
        profiles=[profile_id],
        llm=LlmConfig(
            enabled=True,
            provider="ollama",
            model=INTEGRATION_MODEL,
            endpoint=INTEGRATION_ENDPOINT,
            timeout_ms=30000,
            max_retries=1,
            ambiguous_score_range=[0, 100],  # force Layer 3 regardless of score
        ),
    )
    return Shield(profiles=[profile_id], config=config)


def test_legal_ambiguous_text_round_trips_through_layer3():
    shield = _live_shield("shield-legal")
    text = (
        "Brief note from outside counsel discussing the proposed settlement. "
        "Please treat as work product prepared for the matter."
    )
    result = shield.analyze(text)
    # We only assert the wire works: layer was invoked and returned a result
    # without raising. Per-profile precision lives in the benchmark runner.
    from ogentic_shield.models import DetectionLayer

    assert DetectionLayer.LLM in result.layers_invoked


def test_therapy_ambiguous_text_round_trips_through_layer3():
    shield = _live_shield("shield-therapy")
    text = (
        "Patient mentioned mild trouble sleeping. Discussed sleep hygiene "
        "and follow-up scheduled."
    )
    result = shield.analyze(text)
    from ogentic_shield.models import DetectionLayer

    assert DetectionLayer.LLM in result.layers_invoked


def test_finance_ambiguous_text_round_trips_through_layer3():
    shield = _live_shield("shield-finance")
    text = (
        "Internal note: pricing committee meeting Wednesday to review terms "
        "for the upcoming engagement."
    )
    result = shield.analyze(text)
    from ogentic_shield.models import DetectionLayer

    assert DetectionLayer.LLM in result.layers_invoked
