"""Pipeline orchestration: runs detection layers in strict order."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import replace

from ogentic_shield.calibration import Calibrator, get_calibrator
from ogentic_shield.layers.regex_ner import run_layer1
from ogentic_shield.layers.rules import run_layer2
from ogentic_shield.models import (
    AnalysisResult,
    CategoryGroup,
    DetectedEntity,
    DetectionLayer,
    ShieldProfile,
)
from ogentic_shield.scoring import calculate_score, determine_sensitivity_level, suggest_routing

logger = logging.getLogger("ogentic_shield.pipeline")


def text_hash_for(text: str) -> str:
    """Stable hash prefix used in AnalysisResult.text_hash. Public so the
    streaming API can reuse it without depending on hashlib directly."""
    return f"sha256:{hashlib.sha256(text.encode()).hexdigest()[:16]}"


def _should_run_llm(
    entities: list[DetectedEntity],
    profiles: list[ShieldProfile],
    llm_config: dict | None,
) -> tuple[bool, int]:
    """Layer 3 gating decision. Returns ``(should_run, current_score)``.

    Reused by both the sync pipeline and the AsyncShield streaming variant
    so they stay in lockstep. Same rules: enabled flag + score in ambiguous
    range + no PRIVILEGE/MNPI already detected.
    """
    score = calculate_score(entities, profiles)
    if not llm_config or not llm_config.get("enabled"):
        return False, score
    ambiguous_range = tuple(llm_config.get("ambiguous_score_range", [20, 60]))
    has_privilege = any(e.category_group == CategoryGroup.PRIVILEGE for e in entities)
    has_mnpi = any(e.category_group == CategoryGroup.MNPI for e in entities)
    if has_privilege or has_mnpi:
        return False, score
    return ambiguous_range[0] <= score <= ambiguous_range[1], score


def _calibrate_entities(
    entities: list[DetectedEntity],
    calibrator: Calibrator,
) -> list[DetectedEntity]:
    """Rewrite each entity's ``confidence`` to the calibrated value.

    Identity-fallback layers (no calibration registered) pass through
    unchanged so this is safe to call even when the user has installed
    a partial calibrator. The original raw confidence is preserved at
    ``entity.metadata['raw_confidence']`` for debugging — Layer 3 already
    does this; Layers 1 and 2 only stash it when calibration moves the
    value.
    """
    out: list[DetectedEntity] = []
    for entity in entities:
        if not calibrator.has(entity.detection_layer):
            out.append(entity)
            continue
        calibrated = calibrator.apply(entity.confidence, entity.detection_layer)
        if calibrated == entity.confidence:
            out.append(entity)
            continue
        meta = dict(entity.metadata)
        # Don't clobber a raw_confidence already set by Layer 3.
        meta.setdefault("raw_confidence", entity.confidence)
        out.append(replace(entity, confidence=calibrated, metadata=meta))
    return out


def build_analysis_result(
    text: str,
    entities: list[DetectedEntity],
    profiles: list[ShieldProfile],
    layers_invoked: list[DetectionLayer],
    min_confidence: float,
    started_at: float,
    calibrator: Calibrator | None = None,
) -> AnalysisResult:
    """Final score + level + routing assembly.

    Extracted from :func:`run_pipeline` so the streaming path
    (:meth:`ogentic_shield.async_shield.AsyncShield.analyze_stream`) gets the
    same authoritative result without re-running the layers. ``started_at``
    is a ``time.perf_counter()`` value taken at the start of the analysis.

    Calibration (OGE-321) is applied here, before the ``min_confidence``
    filter, so that ``min_confidence`` always compares against calibrated
    values — the same scale the caller's threshold was tuned against.
    """
    cal = calibrator if calibrator is not None else get_calibrator()
    calibrated_entities = _calibrate_entities(entities, cal)

    final = [e for e in calibrated_entities if e.confidence >= min_confidence]
    final.sort(key=lambda e: e.start)

    score = calculate_score(final, profiles)
    top = max(final, key=lambda e: e.confidence) if final else None
    processing_time_ms = (time.perf_counter() - started_at) * 1000

    return AnalysisResult(
        text_hash=text_hash_for(text),
        entities=final,
        score=score,
        sensitivity_level=determine_sensitivity_level(score),
        category_groups_found={e.category_group for e in final},
        top_category=top.category if top else None,
        top_confidence=top.confidence if top else 0.0,
        entity_count=len(final),
        processing_time_ms=round(processing_time_ms, 1),
        layers_invoked=layers_invoked,
        profile_ids=[p.id for p in profiles],
        routing_suggestion=suggest_routing(final, score),
    )


def run_pipeline(
    text: str,
    profiles: list[ShieldProfile],
    layers: list[DetectionLayer] | None = None,
    min_confidence: float = 0.5,
    llm_config: dict | None = None,
) -> AnalysisResult:
    """Run the full detection pipeline.

    Layers execute in strict order: REGEX/NER → RULES → LLM (if enabled).
    """
    started_at = time.perf_counter()

    if layers is None:
        layers = [DetectionLayer.REGEX, DetectionLayer.NER, DetectionLayer.RULES]

    layers_invoked: list[DetectionLayer] = []
    entities: list[DetectedEntity] = []

    # Layer 1: Regex + NER
    if DetectionLayer.REGEX in layers or DetectionLayer.NER in layers:
        entities = run_layer1(text, profiles, min_confidence)
        if DetectionLayer.REGEX in layers:
            layers_invoked.append(DetectionLayer.REGEX)
        if DetectionLayer.NER in layers:
            layers_invoked.append(DetectionLayer.NER)

    # Layer 2: Rules
    if DetectionLayer.RULES in layers:
        entities = run_layer2(text, entities, profiles)
        layers_invoked.append(DetectionLayer.RULES)

    # Layer 3: LLM (only if explicitly enabled and score is ambiguous)
    if DetectionLayer.LLM in layers:
        should_run, score = _should_run_llm(entities, profiles, llm_config)
        if should_run:
            from ogentic_shield.layers.llm import run_layer3

            entities = run_layer3(text, entities, profiles, score, llm_config)
            layers_invoked.append(DetectionLayer.LLM)

    return build_analysis_result(
        text=text,
        entities=entities,
        profiles=profiles,
        layers_invoked=layers_invoked,
        min_confidence=min_confidence,
        started_at=started_at,
    )
