"""Score calculation, sensitivity level assignment, and routing suggestion."""

from __future__ import annotations

import logging

from ogentic_shield.models import (
    CategoryGroup,
    DetectedEntity,
    SensitivityLevel,
    ShieldProfile,
)

logger = logging.getLogger("ogentic_shield.scoring")


def calculate_score(entities: list[DetectedEntity], profiles: list[ShieldProfile]) -> int:
    """Calculate weighted sensitivity score from detected entities.

    Merges scoring weights from all active profiles (max wins on conflict).
    Returns 0-100 integer score.
    """
    if not entities:
        return 0

    weights: dict[CategoryGroup, float] = {}
    for profile in profiles:
        for group, weight in profile.scoring_weights.items():
            weights[group] = max(weights.get(group, 0), weight)

    raw_score = sum(
        weights.get(entity.category_group, 10) * entity.confidence
        for entity in entities
    )

    return min(100, round(raw_score))


def determine_sensitivity_level(score: int) -> SensitivityLevel:
    """Map a 0-100 score to a sensitivity level."""
    if score == 0:
        return SensitivityLevel.NONE
    if score <= 20:
        return SensitivityLevel.LOW
    if score <= 50:
        return SensitivityLevel.MEDIUM
    if score <= 80:
        return SensitivityLevel.HIGH
    return SensitivityLevel.CRITICAL


def suggest_routing(entities: list[DetectedEntity], score: int) -> str:
    """Suggest a routing decision based on entities and score.

    Returns one of: LOCAL_ONLY, REDACT_CLOUD, CLOUD_OK
    """
    has_privilege = any(e.category_group == CategoryGroup.PRIVILEGE for e in entities)
    has_mnpi = any(e.category_group == CategoryGroup.MNPI for e in entities)

    if has_privilege or has_mnpi:
        return "LOCAL_ONLY"

    has_phi = any(e.category_group == CategoryGroup.PHI for e in entities)
    if has_phi or score > 30:
        return "REDACT_CLOUD"

    return "CLOUD_OK"
