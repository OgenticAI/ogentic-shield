"""ogentic-shield: Regulatory sensitivity detection for AI applications."""

from ogentic_shield.models import (
    AnalysisResult,
    CategoryGroup,
    DetectedEntity,
    DetectionLayer,
    RedactionMapping,
    SensitivityLevel,
    ShieldProfile,
)
from ogentic_shield.profiles import (
    list_profiles,
    load_profile_from_yaml,
    register_profile,
)
from ogentic_shield.redaction import (
    CATEGORY_LABEL_TO_ENTITY_TYPES,
    DEFAULT_REDACT_CATEGORIES,
    PROFILE_REDACT_CATEGORIES,
    redact_text,
    unredact_text,
)
from ogentic_shield.shield import Shield

__version__ = "0.2.0.dev0"

__all__ = [
    "Shield",
    "AnalysisResult",
    "CategoryGroup",
    "DetectedEntity",
    "DetectionLayer",
    "RedactionMapping",
    "SensitivityLevel",
    "ShieldProfile",
    "list_profiles",
    "load_profile_from_yaml",
    "register_profile",
    "redact_text",
    "unredact_text",
    "CATEGORY_LABEL_TO_ENTITY_TYPES",
    "DEFAULT_REDACT_CATEGORIES",
    "PROFILE_REDACT_CATEGORIES",
    "__version__",
]
