"""Layer 3: Local LLM classification (stub in v0.1)."""

from __future__ import annotations

import logging

from ogentic_shield.models import DetectedEntity, ShieldProfile

logger = logging.getLogger("ogentic_shield.layers.llm")


def run_layer3(
    text: str,
    existing_entities: list[DetectedEntity],
    profiles: list[ShieldProfile],
    score: int,
    config: dict | None = None,
) -> list[DetectedEntity]:
    """Run Layer 3: Local LLM classification.

    Raises NotImplementedError in v0.1 — LLM layer requires Ollama integration
    which is out of scope for the initial release.
    """
    try:
        import ollama  # noqa: F401
    except ImportError:
        raise NotImplementedError(
            "LLM layer requires the 'ollama' package. "
            "Install with: pip install ogentic-shield[llm]"
        )

    raise NotImplementedError(
        "LLM classification layer is not implemented in v0.1. "
        "This will be available in v0.2 with Ollama integration."
    )
