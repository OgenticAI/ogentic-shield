"""ogentic-shield: Regulatory sensitivity detection for AI applications."""

from ogentic_shield.async_shield import AsyncShield, StreamEvent
from ogentic_shield.calibration import (
    CalibrationMethod,
    Calibrator,
    LayerCalibration,
    get_calibrator,
    set_calibrator,
)
from ogentic_shield.documents import (
    ChunkResult,
    DocumentAnalysisResult,
    DocumentRedactionResult,
    UnsupportedDocumentFormatError,
)
from ogentic_shield.models import (
    AnalysisResult,
    BatchItemError,
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
from ogentic_shield.registry import ModelRegistry, ModelTier
from ogentic_shield.shield import Shield

__version__ = "0.4.0"

__all__ = [
    "Shield",
    "AsyncShield",
    "StreamEvent",
    "AnalysisResult",
    "BatchItemError",
    "CalibrationMethod",
    "Calibrator",
    "CategoryGroup",
    "ChunkResult",
    "DetectedEntity",
    "DetectionLayer",
    "DocumentAnalysisResult",
    "DocumentRedactionResult",
    "UnsupportedDocumentFormatError",
    "LayerCalibration",
    "ModelRegistry",
    "ModelTier",
    "RedactionMapping",
    "SensitivityLevel",
    "ShieldProfile",
    "get_calibrator",
    "list_profiles",
    "load_profile_from_yaml",
    "register_profile",
    "redact_text",
    "set_calibrator",
    "unredact_text",
    "CATEGORY_LABEL_TO_ENTITY_TYPES",
    "DEFAULT_REDACT_CATEGORIES",
    "PROFILE_REDACT_CATEGORIES",
    "__version__",
]
