"""Integration tests for Shield.analyze()."""

import pytest

from ogentic_shield import SensitivityLevel, Shield
from ogentic_shield.models import CategoryGroup


class TestShieldAnalyze:
    """Integration tests for the main Shield.analyze() entry point."""

    def test_legal_privileged_text(self, legal_shield):
        result = legal_shield.analyze(
            "Per our conversation with outside counsel at Davis Polk regarding "
            "the SEC investigation, this communication is privileged and confidential."
        )
        assert result.score > 30
        assert result.entity_count >= 2
        assert CategoryGroup.PRIVILEGE in result.category_groups_found
        assert result.routing_suggestion == "LOCAL_ONLY"

    def test_therapy_phi_text(self, therapy_shield):
        result = therapy_shield.analyze(
            "Patient: Jane D. DOB: 03/15/1988. Session 12 progress note. "
            "Diagnosis Code: F33.1. Patient reports suicidal ideation."
        )
        assert result.score > 30
        assert result.entity_count >= 3
        assert CategoryGroup.PHI in result.category_groups_found
        assert result.routing_suggestion in ("REDACT_CLOUD", "LOCAL_ONLY")

    def test_finance_mnpi_text(self, finance_shield):
        result = finance_shield.analyze(
            "CONFIDENTIAL — MATERIAL NON-PUBLIC INFORMATION. "
            "Goldman Sachs is advising on the acquisition of TargetCo at $47/share."
        )
        assert result.score > 30
        assert result.entity_count >= 2
        assert CategoryGroup.MNPI in result.category_groups_found
        assert result.routing_suggestion == "LOCAL_ONLY"

    def test_safe_text(self, legal_shield):
        result = legal_shield.analyze("The weather is nice today. I went for a walk.")
        assert result.score < 15
        assert result.routing_suggestion == "CLOUD_OK"
        assert result.sensitivity_level in (SensitivityLevel.NONE, SensitivityLevel.LOW)

    def test_multi_profile(self, all_profiles_shield):
        result = all_profiles_shield.analyze(
            "Outside counsel from Davis Polk advised on the acquisition at $47/share. "
            "Patient: Jane D. DOB: 03/15/1988."
        )
        assert result.entity_count >= 3
        assert len(result.profile_ids) == 3

    def test_empty_text(self, legal_shield):
        result = legal_shield.analyze("")
        assert result.score == 0
        assert result.entity_count == 0
        assert result.sensitivity_level == SensitivityLevel.NONE
        assert result.routing_suggestion == "CLOUD_OK"

    def test_result_has_text_hash(self, legal_shield):
        result = legal_shield.analyze("Test text for hashing.")
        assert result.text_hash.startswith("sha256:")

    def test_result_has_processing_time(self, legal_shield):
        result = legal_shield.analyze("Outside counsel reviewed the document.")
        assert result.processing_time_ms > 0

    def test_result_has_layers_invoked(self, legal_shield):
        result = legal_shield.analyze("Test text.")
        assert len(result.layers_invoked) >= 1

    def test_min_confidence_filter(self, legal_shield):
        result = legal_shield.analyze(
            "Outside counsel at Davis Polk reviewed the case.",
            min_confidence=0.99,
        )
        for entity in result.entities:
            assert entity.confidence >= 0.99

    def test_profile_override(self):
        shield = Shield(profiles=["shield-legal"])
        result = shield.analyze(
            "Patient: Jane D. DOB: 03/15/1988.",
            profiles=["shield-therapy"],
        )
        assert any(e.category == "PATIENT_NAME" for e in result.entities) or \
            any(e.category == "DATE_OF_BIRTH" for e in result.entities)


class TestShieldStaticMethods:
    """Tests for Shield static methods."""

    def test_list_profiles(self):
        profiles = Shield.list_profiles()
        assert len(profiles) >= 3
        ids = {p.id for p in profiles}
        assert "shield-legal" in ids
        assert "shield-therapy" in ids
        assert "shield-finance" in ids

    def test_get_profile(self):
        profile = Shield.get_profile("shield-legal")
        assert profile.id == "shield-legal"
        assert len(profile.recognizers) == 10
        assert len(profile.supported_entities) == 10

    def test_get_unknown_profile(self):
        from ogentic_shield.models import ProfileNotFoundError

        with pytest.raises(ProfileNotFoundError):
            Shield.get_profile("shield-nonexistent")
