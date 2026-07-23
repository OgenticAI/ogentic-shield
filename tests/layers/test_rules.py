"""Tests for Layer 2: the context-aware rules engine (run_layer2)."""

import re
from types import SimpleNamespace

from ogentic_shield.layers.rules import run_layer2
from ogentic_shield.models import CategoryGroup, DetectedEntity, DetectionLayer, Rule


def _profile(*rules):
    """Minimal stand-in — run_layer2 only reads ``profile.rules``."""
    return SimpleNamespace(rules=list(rules))


def _rule(**kw):
    defaults = dict(
        id="r",
        name="r",
        description="",
        flags=re.IGNORECASE,
        category="PATIENT_NAME",
        category_group=CategoryGroup.PHI,
        confidence=0.9,
    )
    defaults.update(kw)
    return Rule(**defaults)


class TestRuleEmission:
    def test_normal_rule_creates_new_entity(self):
        """A regular rule whose pattern IS the signal still mints an entity."""
        rule = _rule(
            id="mnpi", pattern=r"\bMNPI\b", category="MNPI_MARKER",
            category_group=CategoryGroup.MNPI, confidence=0.97,
        )
        out = run_layer2("This memo contains MNPI.", [], [_profile(rule)])
        mnpi = [e for e in out if e.category == "MNPI_MARKER"]
        assert len(mnpi) == 1
        assert mnpi[0].detection_layer == DetectionLayer.RULES
        assert mnpi[0].text == "MNPI"


class TestBoostOnly:
    def test_boost_only_does_not_mint_entity_from_trigger_word(self):
        """A boost_only rule must NOT create an entity from its trigger word."""
        rule = _rule(id="patient-trigger", pattern=r"\bpatient\b", boost_only=True)
        out = run_layer2("she is a patient", [], [_profile(rule)])
        assert [e for e in out if e.category == "PATIENT_NAME"] == []

    def test_boost_only_still_boosts_existing_entity(self):
        """It should still raise the confidence of a real entity in its span."""
        rule = _rule(id="patient-trigger", pattern=r"\bpatient\b", confidence=0.99, boost_only=True)
        existing = DetectedEntity(
            text="patient",
            category="PATIENT_NAME",
            category_group=CategoryGroup.PHI,
            confidence=0.5,
            detection_layer=DetectionLayer.REGEX,
            start=9,
            end=16,
        )
        out = run_layer2("she is a patient", [existing], [_profile(rule)])
        pat = [e for e in out if e.category == "PATIENT_NAME"]
        assert len(pat) == 1
        assert pat[0].confidence == 0.99
        assert pat[0].metadata.get("boosted_by_rule") == "patient-trigger"
