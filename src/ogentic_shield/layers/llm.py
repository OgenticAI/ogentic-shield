"""Layer 3: Local LLM classification.

Invoked by :func:`ogentic_shield.pipeline.run_pipeline` only when:

- ``layers`` includes :py:attr:`DetectionLayer.LLM`,
- ``llm_config["enabled"]`` is true,
- the L1+L2 score falls inside ``ambiguous_score_range`` (default ``[20, 60]``),
- no PRIVILEGE/MNPI category has already fired (those are decisive on their own).

For each profile, builds a tuned prompt (see :mod:`.llm_prompts`), calls
localhost Ollama via :class:`.llm_client.OllamaClient`, and merges valid
detections into the entity list. The orchestrator never raises into the
pipeline — every failure path returns the existing entities unchanged so
the L1+L2 score stands.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ogentic_shield.layers.llm_client import (
    LocalhostOnlyError,
    OllamaClient,
)
from ogentic_shield.layers.llm_prompts import CATEGORY_TO_GROUP, build_prompt
from ogentic_shield.layers.llm_schema import LlmDetection, LlmResponse
from ogentic_shield.models import DetectedEntity, DetectionLayer, ShieldProfile
from ogentic_shield.registry import ROLE_CLASSIFICATION, ModelRegistry, ModelTier

logger = logging.getLogger("ogentic_shield.layers.llm")


def run_layer3(
    text: str,
    existing_entities: list[DetectedEntity],
    profiles: list[ShieldProfile],
    score: int,
    config: dict[str, Any] | None = None,
) -> list[DetectedEntity]:
    """Run Layer 3: localhost LLM classification.

    Returns the merged entity list. Never raises — on any failure (no Ollama
    extra, service down, malformed output) returns ``existing_entities``
    unchanged so the L1+L2 score stands.
    """
    if not config or not config.get("enabled"):
        return existing_entities

    model = _resolve_model(config)
    try:
        client = OllamaClient(
            endpoint=config.get("endpoint", "http://localhost:11434"),
            model=model,
            timeout_ms=int(config.get("timeout_ms", 5000)),
            max_retries=int(config.get("max_retries", 2)),
        )
    except LocalhostOnlyError as exc:
        logger.error("Refusing to run Layer 3: %s", exc)
        return existing_entities

    started = time.perf_counter()
    new_entities: list[DetectedEntity] = []
    seen_spans: set[tuple[int, int, str]] = {
        (e.start, e.end, e.category) for e in existing_entities
    }

    for profile in profiles:
        prompt = build_prompt(profile.id, text, existing_entities)
        if prompt is None:
            logger.debug("No Layer 3 prompt template for profile '%s'; skipping.", profile.id)
            continue

        response = client.classify(prompt, LlmResponse)
        if response is None:
            continue

        for detection in response.detections:
            entity = _to_entity(detection, text, model, profile.id)
            if entity is None:
                continue
            key = (entity.start, entity.end, entity.category)
            if key in seen_spans:
                continue
            new_entities.append(entity)
            seen_spans.add(key)

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "Layer 3 complete: %d new entities in %.1fms (model=%s, profiles=%s, gating_score=%d)",
        len(new_entities),
        elapsed_ms,
        model,
        ",".join(p.id for p in profiles),
        score,
    )
    return existing_entities + new_entities


def _resolve_model(config: dict[str, Any]) -> str:
    """Pick the model name. Explicit ``config['model']`` wins; otherwise registry."""
    explicit = config.get("model")
    if explicit:
        return str(explicit)
    quality = config.get("quality", ModelTier.FAST.value)
    return ModelRegistry().get(ROLE_CLASSIFICATION, quality)


def _to_entity(
    detection: LlmDetection,
    text: str,
    model: str,
    profile_id: str,
) -> DetectedEntity | None:
    """Convert one ``LlmDetection`` into a ``DetectedEntity``, or drop it.

    Drops the detection when:
    - ``category`` isn't in :data:`CATEGORY_TO_GROUP` (LLM hallucinated a label), or
    - ``span_text`` isn't an exact substring of ``text`` (LLM hallucinated a span).

    Both checks are defensive against models that ignore the structured-output
    constraint. Without them a hallucinated category would slip into the
    scoring engine and a hallucinated span would leak fabricated text into
    audit events.
    """
    group = CATEGORY_TO_GROUP.get(detection.category)
    if group is None:
        logger.debug(
            "Dropping LLM detection with unknown category '%s' (profile=%s).",
            detection.category,
            profile_id,
        )
        return None

    span_start = text.find(detection.span_text)
    if span_start < 0:
        logger.debug(
            "Dropping hallucinated span '%s…' (profile=%s, category=%s).",
            detection.span_text[:40],
            profile_id,
            detection.category,
        )
        return None

    span_end = span_start + len(detection.span_text)
    # Layer 3 emits raw model confidence; pipeline.build_analysis_result
    # applies the per-layer calibration centrally (OGE-321).
    raw_confidence = max(0.0, min(1.0, detection.confidence))

    return DetectedEntity(
        text=detection.span_text,
        category=detection.category,
        category_group=group,
        confidence=raw_confidence,
        detection_layer=DetectionLayer.LLM,
        start=span_start,
        end=span_end,
        metadata={
            "model": model,
            "profile": profile_id,
            "reasoning": detection.reasoning,
        },
    )


__all__ = ["run_layer3"]
