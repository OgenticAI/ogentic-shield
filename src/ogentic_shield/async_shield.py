"""Async variant of :class:`Shield` (OGE-318).

Wraps a sync :class:`Shield` and dispatches the CPU-bound pipeline through
``asyncio.to_thread`` so the calling coroutine stays responsive. Two extra
features beyond a thin coroutine wrapper:

- :meth:`AsyncShield.analyze_stream` — async generator that yields a
  :class:`StreamEvent` after every layer completes. Lets a UI surface
  partial results (e.g. real-time highlighting) without waiting for Layer 3
  to finish, while the final event still carries the authoritative
  :class:`AnalysisResult`.
- :meth:`AsyncShield.required_models` / :meth:`list_profiles` — sync
  passthrough to the underlying registry. They don't do I/O so awaiting
  them would just be ceremony.

The MCP server (``ogentic_shield.mcp.server``) uses :class:`AsyncShield`
natively so MCP tools don't need ``asyncio.to_thread`` wrappers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from ogentic_shield.config import ShieldConfig
from ogentic_shield.layers.regex_ner import run_layer1
from ogentic_shield.layers.rules import run_layer2
from ogentic_shield.models import (
    AnalysisResult,
    DetectedEntity,
    DetectionLayer,
    RedactionMapping,
    ShieldProfile,
)
from ogentic_shield.pipeline import (
    _should_run_llm,
    build_analysis_result,
)
from ogentic_shield.profiles import get_profile
from ogentic_shield.registry import ModelTier
from ogentic_shield.shield import Shield

logger = logging.getLogger("ogentic_shield.async_shield")


@dataclass(frozen=True)
class StreamEvent:
    """One snapshot emitted by :meth:`AsyncShield.analyze_stream`.

    Intermediate events (``is_final=False``) carry the layer that just
    completed and the running entity list — UIs can render this as
    "partial detections so far". The terminal event (``is_final=True``)
    carries the authoritative :class:`AnalysisResult` and is always the
    last value yielded.
    """

    layer: DetectionLayer | None
    entities: list[DetectedEntity] = field(default_factory=list)
    is_final: bool = False
    result: AnalysisResult | None = None


class AsyncShield:
    """Coroutine-friendly :class:`Shield`.

    >>> import asyncio
    >>> shield = AsyncShield(profiles=["shield-legal"])
    >>> async def run():
    ...     return await shield.analyze("some legal text")  # doctest: +SKIP
    """

    def __init__(
        self,
        profiles: list[str] | None = None,
        config: ShieldConfig | None = None,
        quality: str | ModelTier | None = None,
        model_override: dict[str, str] | None = None,
    ):
        self._shield = Shield(
            profiles=profiles,
            config=config,
            quality=quality,
            model_override=model_override,
        )

    @property
    def shield(self) -> Shield:
        """The wrapped sync Shield. Useful for tests / inspection."""
        return self._shield

    async def analyze(
        self,
        text: str,
        profiles: list[str] | None = None,
        layers: list[DetectionLayer] | None = None,
        min_confidence: float | None = None,
        include_context: bool = False,
    ) -> AnalysisResult:
        """Async passthrough to :meth:`Shield.analyze`."""
        return await asyncio.to_thread(
            self._shield.analyze,
            text,
            profiles,
            layers,
            min_confidence,
            include_context,
        )

    async def redact(
        self,
        text: str,
        profile: str | None = None,
        redact_categories: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> tuple[str, RedactionMapping]:
        """Async passthrough to :meth:`Shield.redact`."""
        return await asyncio.to_thread(
            self._shield.redact,
            text,
            profile,
            redact_categories,
            min_confidence,
        )

    @staticmethod
    async def unredact(text: str, mapping: RedactionMapping) -> str:
        """Async passthrough to :meth:`Shield.unredact`."""
        return await asyncio.to_thread(Shield.unredact, text, mapping)

    async def analyze_stream(
        self,
        text: str,
        profiles: list[str] | None = None,
        layers: list[DetectionLayer] | None = None,
        min_confidence: float | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield a :class:`StreamEvent` after each layer completes.

        Order: ``REGEX/NER`` → ``RULES`` → ``LLM`` (if gated on) → terminal.
        Each layer runs in a thread (``asyncio.to_thread``) so the calling
        coroutine can interleave other work between events. The terminal
        event is always last and always populates ``result``.
        """
        active_profiles = self._resolve_profiles(profiles)
        effective_min_confidence = (
            min_confidence
            if min_confidence is not None
            else self._shield._config.scoring.min_confidence
        )
        active_layers = (
            layers
            if layers is not None
            else self._default_layers()
        )
        llm_config = self._build_llm_config()

        started = time.perf_counter()
        layers_invoked: list[DetectionLayer] = []
        entities: list[DetectedEntity] = []

        # Layer 1: Regex + NER (treated as one "stage" — same thread call,
        # yields once with both layers stamped invoked).
        if DetectionLayer.REGEX in active_layers or DetectionLayer.NER in active_layers:
            entities = await asyncio.to_thread(
                run_layer1, text, active_profiles, effective_min_confidence
            )
            if DetectionLayer.REGEX in active_layers:
                layers_invoked.append(DetectionLayer.REGEX)
            if DetectionLayer.NER in active_layers:
                layers_invoked.append(DetectionLayer.NER)
            yield StreamEvent(layer=DetectionLayer.REGEX, entities=list(entities))

        # Layer 2: Rules.
        if DetectionLayer.RULES in active_layers:
            entities = await asyncio.to_thread(
                run_layer2, text, entities, active_profiles
            )
            layers_invoked.append(DetectionLayer.RULES)
            yield StreamEvent(layer=DetectionLayer.RULES, entities=list(entities))

        # Layer 3: LLM (gated, identical rules to run_pipeline).
        if DetectionLayer.LLM in active_layers:
            should_run, gating_score = _should_run_llm(entities, active_profiles, llm_config)
            if should_run:
                # Imported lazily — same pattern as pipeline.run_pipeline so
                # consumers without the [llm] extra don't pay an import cost.
                from ogentic_shield.layers.llm import run_layer3

                entities = await asyncio.to_thread(
                    run_layer3, text, entities, active_profiles, gating_score, llm_config
                )
                layers_invoked.append(DetectionLayer.LLM)
                yield StreamEvent(layer=DetectionLayer.LLM, entities=list(entities))

        # Terminal event — authoritative AnalysisResult.
        result = build_analysis_result(
            text=text,
            entities=entities,
            profiles=active_profiles,
            layers_invoked=layers_invoked,
            min_confidence=effective_min_confidence,
            started_at=started,
        )
        yield StreamEvent(layer=None, entities=result.entities, is_final=True, result=result)

    def required_models(self, tier: str | ModelTier | None = None) -> list[str]:
        """Sync passthrough — see :meth:`Shield.required_models`."""
        return self._shield.required_models(tier)

    @staticmethod
    def list_profiles() -> list[ShieldProfile]:
        """Sync passthrough — see :meth:`Shield.list_profiles`."""
        return Shield.list_profiles()

    @staticmethod
    def get_profile(profile_id: str) -> ShieldProfile:
        """Sync passthrough — see :meth:`Shield.get_profile`."""
        return Shield.get_profile(profile_id)

    # ── Internals ───────────────────────────────────────────────────────

    def _resolve_profiles(self, override: list[str] | None) -> list[ShieldProfile]:
        """Mirror :meth:`Shield.analyze`'s profile-resolution logic."""
        if override:
            return [get_profile(pid) for pid in override]
        return self._shield._profiles

    def _default_layers(self) -> list[DetectionLayer]:
        config = self._shield._config
        layers: list[DetectionLayer] = []
        if config.layers_regex:
            layers.append(DetectionLayer.REGEX)
        if config.layers_ner:
            layers.append(DetectionLayer.NER)
        if config.layers_rules:
            layers.append(DetectionLayer.RULES)
        if config.llm.enabled:
            layers.append(DetectionLayer.LLM)
        return layers

    def _build_llm_config(self) -> dict:
        """Same dict shape :meth:`Shield.analyze` builds — kept here so
        analyze_stream stays standalone without re-running run_pipeline."""
        from ogentic_shield.registry import ROLE_CLASSIFICATION

        cfg = self._shield._config.llm
        resolved_model = cfg.model or self._shield._registry.get(
            ROLE_CLASSIFICATION, self._shield._quality
        )
        return {
            "enabled": cfg.enabled,
            "provider": cfg.provider,
            "model": resolved_model,
            "endpoint": cfg.endpoint,
            "timeout_ms": cfg.timeout_ms,
            "max_retries": cfg.max_retries,
            "quality": self._shield._quality,
            "ambiguous_score_range": cfg.ambiguous_score_range,
        }


__all__ = ["AsyncShield", "StreamEvent"]
