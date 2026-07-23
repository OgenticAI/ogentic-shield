"""Layer 2: Context-aware rules engine."""

from __future__ import annotations

import logging
import re
import time

from ogentic_shield.models import DetectedEntity, DetectionLayer, Rule, ShieldProfile

logger = logging.getLogger("ogentic_shield.layers.rules")


def _check_context(text: str, match_start: int, match_end: int, rule: Rule) -> bool:
    """Check if any context patterns appear within the context window."""
    window_start = max(0, match_start - rule.context_window)
    window_end = min(len(text), match_end + rule.context_window)
    context_text = text[window_start:window_end].lower()

    for pattern in rule.context_patterns:
        if pattern.lower() in context_text:
            return True
    return False


def run_layer2(
    text: str,
    existing_entities: list[DetectedEntity],
    profiles: list[ShieldProfile],
) -> list[DetectedEntity]:
    """Run Layer 2: Apply domain rules to boost confidence and add new entities."""
    start_time = time.perf_counter()

    rules: list[Rule] = []
    for profile in profiles:
        rules.extend(r for r in profile.rules if r.enabled)

    logger.debug("Running %d rules against %d chars", len(rules), len(text))

    existing_spans = {(e.start, e.end, e.category) for e in existing_entities}
    boosted_entities: list[DetectedEntity] = list(existing_entities)
    new_entities: list[DetectedEntity] = []

    for rule in rules:
        compiled = re.compile(rule.pattern, rule.flags)
        for match in compiled.finditer(text):
            span_key = (match.start(), match.end(), rule.category)

            has_context = _check_context(text, match.start(), match.end(), rule)
            confidence = rule.confidence
            if has_context:
                confidence = min(1.0, confidence + rule.context_confidence_boost)

            found_existing = False
            updated_entities = []
            for entity in boosted_entities:
                if (
                    entity.category == rule.category
                    and entity.start >= match.start()
                    and entity.end <= match.end()
                    and confidence > entity.confidence
                ):
                    updated_entity = DetectedEntity(
                        text=entity.text,
                        category=entity.category,
                        category_group=entity.category_group,
                        confidence=confidence,
                        detection_layer=entity.detection_layer,
                        start=entity.start,
                        end=entity.end,
                        metadata={
                            **entity.metadata,
                            "boosted_by_rule": rule.id,
                            "context_matched": has_context,
                        },
                    )
                    updated_entities.append(updated_entity)
                    found_existing = True
                else:
                    updated_entities.append(entity)
            boosted_entities = updated_entities

            if not found_existing and span_key not in existing_spans and not rule.boost_only:
                new_entity = DetectedEntity(
                    text=text[match.start():match.end()],
                    category=rule.category,
                    category_group=rule.category_group,
                    confidence=confidence,
                    detection_layer=DetectionLayer.RULES,
                    start=match.start(),
                    end=match.end(),
                    metadata={
                        "rule_id": rule.id,
                        "context_matched": has_context,
                    },
                )
                new_entities.append(new_entity)
                existing_spans.add(span_key)

    result = boosted_entities + new_entities
    result.sort(key=lambda e: e.start)

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info("Layer 2 complete: %d entities (was %d) in %.1fms", len(result), len(existing_entities), elapsed_ms)

    return result
