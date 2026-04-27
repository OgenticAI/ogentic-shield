"""ogentic-shield: Regulatory sensitivity detection for AI applications."""

from ogentic_shield.models import (
    AnalysisResult,
    CategoryGroup,
    DetectedEntity,
    DetectionLayer,
    SensitivityLevel,
    ShieldProfile,
)
from ogentic_shield.profiles import (
    list_profiles,
    load_profile_from_yaml,
    register_profile,
)
from ogentic_shield.shield import Shield

__version__ = "0.1.0"

__all__ = [
    "Shield",
    "AnalysisResult",
    "CategoryGroup",
    "DetectedEntity",
    "DetectionLayer",
    "SensitivityLevel",
    "ShieldProfile",
    "list_profiles",
    "load_profile_from_yaml",
    "register_profile",
    "__version__",
]
