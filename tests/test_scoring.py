"""Tests for scoring algorithm."""

from ogentic_shield.models import CategoryGroup, DetectedEntity, DetectionLayer, ShieldProfile
from ogentic_shield.scoring import calculate_score, determine_sensitivity_level, suggest_routing


def _make_entity(category_group: CategoryGroup, confidence: float = 0.9) -> DetectedEntity:
    return DetectedEntity(
        text="test",
        category="TEST",
        category_group=category_group,
        confidence=confidence,
        detection_layer=DetectionLayer.REGEX,
        start=0,
        end=4,
    )


def _make_profile(weights: dict[CategoryGroup, float]) -> ShieldProfile:
    return ShieldProfile(
        id="test-profile",
        name="Test",
        version="0.1.0",
        description="Test profile",
        recognizers=[],
        rules=[],
        scoring_weights=weights,
        supported_entities=[],
    )


class TestCalculateScore:
    """Tests for the scoring algorithm."""

    def test_empty_entities_returns_zero(self):
        profile = _make_profile({CategoryGroup.PRIVILEGE: 30})
        assert calculate_score([], [profile]) == 0

    def test_single_privilege_entity(self):
        entity = _make_entity(CategoryGroup.PRIVILEGE, 0.95)
        profile = _make_profile({CategoryGroup.PRIVILEGE: 30})
        score = calculate_score([entity], [profile])
        assert score == min(100, round(30 * 0.95))

    def test_multiple_entities(self):
        entities = [
            _make_entity(CategoryGroup.PRIVILEGE, 0.9),
            _make_entity(CategoryGroup.PII, 0.8),
        ]
        profile = _make_profile({CategoryGroup.PRIVILEGE: 30, CategoryGroup.PII: 15})
        score = calculate_score(entities, [profile])
        expected = min(100, round(30 * 0.9 + 15 * 0.8))
        assert score == expected

    def test_max_score_is_100(self):
        entities = [_make_entity(CategoryGroup.PRIVILEGE, 1.0) for _ in range(10)]
        profile = _make_profile({CategoryGroup.PRIVILEGE: 30})
        score = calculate_score(entities, [profile])
        assert score == 100

    def test_profile_weight_max_wins(self):
        entity = _make_entity(CategoryGroup.PRIVILEGE, 1.0)
        profile1 = _make_profile({CategoryGroup.PRIVILEGE: 20})
        profile2 = _make_profile({CategoryGroup.PRIVILEGE: 30})
        score = calculate_score([entity], [profile1, profile2])
        assert score == 30

    def test_default_weight_for_unknown_group(self):
        entity = _make_entity(CategoryGroup.SAFE, 0.5)
        profile = _make_profile({CategoryGroup.PRIVILEGE: 30})
        score = calculate_score([entity], [profile])
        assert score == round(10 * 0.5)


class TestDetermineSensitivityLevel:
    """Tests for sensitivity level mapping."""

    def test_none(self):
        from ogentic_shield.models import SensitivityLevel
        assert determine_sensitivity_level(0) == SensitivityLevel.NONE

    def test_low(self):
        from ogentic_shield.models import SensitivityLevel
        assert determine_sensitivity_level(15) == SensitivityLevel.LOW

    def test_medium(self):
        from ogentic_shield.models import SensitivityLevel
        assert determine_sensitivity_level(35) == SensitivityLevel.MEDIUM

    def test_high(self):
        from ogentic_shield.models import SensitivityLevel
        assert determine_sensitivity_level(65) == SensitivityLevel.HIGH

    def test_critical(self):
        from ogentic_shield.models import SensitivityLevel
        assert determine_sensitivity_level(85) == SensitivityLevel.CRITICAL

    def test_boundary_20(self):
        from ogentic_shield.models import SensitivityLevel
        assert determine_sensitivity_level(20) == SensitivityLevel.LOW

    def test_boundary_50(self):
        from ogentic_shield.models import SensitivityLevel
        assert determine_sensitivity_level(50) == SensitivityLevel.MEDIUM

    def test_boundary_80(self):
        from ogentic_shield.models import SensitivityLevel
        assert determine_sensitivity_level(80) == SensitivityLevel.HIGH


class TestSuggestRouting:
    """Tests for routing suggestion logic."""

    def test_privilege_returns_local_only(self):
        entities = [_make_entity(CategoryGroup.PRIVILEGE)]
        assert suggest_routing(entities, 50) == "LOCAL_ONLY"

    def test_mnpi_returns_local_only(self):
        entities = [_make_entity(CategoryGroup.MNPI)]
        assert suggest_routing(entities, 50) == "LOCAL_ONLY"

    def test_phi_returns_redact_cloud(self):
        entities = [_make_entity(CategoryGroup.PHI)]
        assert suggest_routing(entities, 25) == "REDACT_CLOUD"

    def test_high_score_returns_redact_cloud(self):
        entities = [_make_entity(CategoryGroup.PII)]
        assert suggest_routing(entities, 35) == "REDACT_CLOUD"

    def test_low_score_no_sensitive_returns_cloud_ok(self):
        entities = [_make_entity(CategoryGroup.PII)]
        assert suggest_routing(entities, 10) == "CLOUD_OK"

    def test_empty_entities_returns_cloud_ok(self):
        assert suggest_routing([], 0) == "CLOUD_OK"
