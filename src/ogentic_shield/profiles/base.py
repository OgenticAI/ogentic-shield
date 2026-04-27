"""ShieldProfile loader for YAML-based custom profiles."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]  # PyYAML stubs not pinned.

from ogentic_shield.models import CategoryGroup, Rule, ShieldProfile

logger = logging.getLogger("ogentic_shield.profiles.base")


def load_profile_from_yaml(path: str | Path) -> ShieldProfile:
    """Load a custom shield profile from a YAML file."""
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)

    rules = []
    for rule_data in data.get("rules", []):
        rules.append(
            Rule(
                id=rule_data["id"],
                name=rule_data.get("name", rule_data["id"]),
                description=rule_data.get("description", ""),
                pattern=rule_data["pattern"],
                flags=re.IGNORECASE,
                category=rule_data["category"],
                category_group=CategoryGroup(rule_data["category_group"]),
                confidence=rule_data.get("confidence", 0.85),
                context_patterns=rule_data.get("context_patterns", []),
                context_window=rule_data.get("context_window", 200),
                context_confidence_boost=rule_data.get("context_confidence_boost", 0.05),
            )
        )

    scoring_weights = {}
    for group_name, weight in data.get("scoring_weights", {}).items():
        scoring_weights[CategoryGroup(group_name)] = weight

    return ShieldProfile(
        id=data["id"],
        name=data.get("name", data["id"]),
        version=data.get("version", "0.1.0"),
        description=data.get("description", ""),
        recognizers=[],
        rules=rules,
        scoring_weights=scoring_weights,
        supported_entities=[r.category for r in rules],
    )
