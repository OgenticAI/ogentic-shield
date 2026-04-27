"""Core data models for ogentic-shield."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum


class SensitivityLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CategoryGroup(str, Enum):
    PRIVILEGE = "PRIVILEGE"
    PHI = "PHI"
    MNPI = "MNPI"
    PII = "PII"
    CONFIDENTIAL = "CONFIDENTIAL"
    SAFE = "SAFE"


class DetectionLayer(str, Enum):
    REGEX = "REGEX"
    NER = "NER"
    RULES = "RULES"
    LLM = "LLM"


@dataclass
class DetectedEntity:
    text: str
    category: str
    category_group: CategoryGroup
    confidence: float
    detection_layer: DetectionLayer
    start: int
    end: int
    metadata: dict = field(default_factory=dict)


@dataclass
class AnalysisResult:
    text_hash: str
    entities: list[DetectedEntity]
    score: int
    sensitivity_level: SensitivityLevel
    category_groups_found: set[CategoryGroup]
    top_category: str | None
    top_confidence: float
    entity_count: int
    processing_time_ms: float
    layers_invoked: list[DetectionLayer]
    profile_ids: list[str]
    routing_suggestion: str


@dataclass
class Rule:
    id: str
    name: str
    description: str
    pattern: str
    flags: int
    category: str
    category_group: CategoryGroup
    confidence: float
    context_patterns: list[str] = field(default_factory=list)
    context_window: int = 200
    context_confidence_boost: float = 0.05
    enabled: bool = True


@dataclass
class ShieldProfile:
    id: str
    name: str
    version: str
    description: str
    recognizers: list
    rules: list[Rule]
    # `Mapping` is covariant in the value type, so int literals like
    # {CategoryGroup.PRIVILEGE: 30} satisfy `Mapping[K, float]`. Using
    # invariant `dict` here would force every profile to spell out
    # `30.0` instead of `30`.
    scoring_weights: Mapping[CategoryGroup, float]
    supported_entities: list[str]


# Exceptions

class ShieldError(Exception):
    """Base exception for ogentic-shield."""


class ProfileNotFoundError(ShieldError):
    """Raised when a requested profile doesn't exist."""


class ProfileValidationError(ShieldError):
    """Raised when a profile YAML is malformed."""


class ConfigError(ShieldError):
    """Raised when config file is invalid."""


# Category group priority for overlap resolution
CATEGORY_GROUP_PRIORITY = {
    CategoryGroup.PRIVILEGE: 5,
    CategoryGroup.PHI: 4,
    CategoryGroup.MNPI: 3,
    CategoryGroup.PII: 2,
    CategoryGroup.CONFIDENTIAL: 1,
    CategoryGroup.SAFE: 0,
}

DEFAULT_MIN_CONFIDENCE = 0.5
