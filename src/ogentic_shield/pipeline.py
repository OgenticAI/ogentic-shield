"""Pipeline orchestration: runs detection layers in strict order."""

from __future__ import annotations

import hashlib
import logging
import time

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
    start_time = time.perf_counter()
    text_hash = f"sha256:{hashlib.sha256(text.encode()).hexdigest()[:16]}"

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
        score = calculate_score(entities, profiles)
        ambiguous_range = (20, 60)
        if llm_config and llm_config.get("enabled"):
            ambiguous_range = tuple(llm_config.get("ambiguous_score_range", [20, 60]))

        has_privilege = any(e.category_group == CategoryGroup.PRIVILEGE for e in entities)
        has_mnpi = any(e.category_group == CategoryGroup.MNPI for e in entities)

        if (
            llm_config
            and llm_config.get("enabled")
            and ambiguous_range[0] <= score <= ambiguous_range[1]
            and not has_privilege
            and not has_mnpi
        ):
            from ogentic_shield.layers.llm import run_layer3

            entities = run_layer3(text, entities, profiles, score, llm_config)
            layers_invoked.append(DetectionLayer.LLM)

    # Filter by min_confidence
    entities = [e for e in entities if e.confidence >= min_confidence]

    # Sort by start position
    entities.sort(key=lambda e: e.start)

    # Calculate results
    score = calculate_score(entities, profiles)
    sensitivity_level = determine_sensitivity_level(score)
    routing = suggest_routing(entities, score)

    category_groups_found = {e.category_group for e in entities}
    top_entity = max(entities, key=lambda e: e.confidence) if entities else None

    processing_time_ms = (time.perf_counter() - start_time) * 1000

    return AnalysisResult(
        text_hash=text_hash,
        entities=entities,
        score=score,
        sensitivity_level=sensitivity_level,
        category_groups_found=category_groups_found,
        top_category=top_entity.category if top_entity else None,
        top_confidence=top_entity.confidence if top_entity else 0.0,
        entity_count=len(entities),
        processing_time_ms=round(processing_time_ms, 1),
        layers_invoked=layers_invoked,
        profile_ids=[p.id for p in profiles],
        routing_suggestion=routing,
    )
