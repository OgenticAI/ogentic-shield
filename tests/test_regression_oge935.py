"""Regression tests for OGE-935: NER overreach on capitalized labels."""

import pytest
from pathlib import Path

from ogentic_shield import Shield


@pytest.fixture
def clinical_sample():
    """Load the clinical sample that reproduces the bug."""
    fixture_path = Path(__file__).parent / "fixtures/regression/oge-935/clinical-sample.txt"
    return fixture_path.read_text()


@pytest.fixture
def legal_sample():
    """Load the legal sample that reproduces the bug."""
    fixture_path = Path(__file__).parent / "fixtures/regression/oge-935/legal-sample.txt"
    return fixture_path.read_text()


@pytest.fixture
def therapy_shield():
    """Shield configured with therapy profile."""
    return Shield(profiles=["shield-therapy"])


@pytest.fixture
def legal_shield():
    """Shield configured with legal profile."""
    return Shield(profiles=["shield-legal"])


class TestNerBlocklist:
    """Tests for NER PERSON blocklist functionality (AC2)."""

    def test_therapy_patient_label_not_redacted(self, therapy_shield):
        """'Patient:' label should not be treated as a PERSON entity."""
        text = "Patient: John Doe"
        result = therapy_shield.analyze(text)

        # Find all PERSON entities
        person_entities = [e for e in result.entities if e.category == "PERSON"]

        # The word "Patient" should NOT be in any PERSON entity
        for entity in person_entities:
            assert "Patient" not in entity.text

    def test_therapy_provider_label_not_redacted(self, therapy_shield):
        """'Provider:' label should not be treated as a PERSON entity."""
        text = "Provider: Dr. Smith"
        result = therapy_shield.analyze(text)

        person_entities = [e for e in result.entities if e.category == "PERSON"]
        for entity in person_entities:
            assert "Provider" not in entity.text

    def test_legal_attorney_label_not_redacted(self, legal_shield):
        """'Attorney:' label should not be treated as a PERSON entity."""
        text = "Attorney: Jane Smith, Esq."
        result = legal_shield.analyze(text)

        person_entities = [e for e in result.entities if e.category == "PERSON"]
        for entity in person_entities:
            assert "Attorney" not in entity.text

    def test_legal_client_label_not_redacted(self, legal_shield):
        """'Client:' label should not be treated as a PERSON entity."""
        text = "Client: Acme Corporation"
        result = legal_shield.analyze(text)

        person_entities = [e for e in result.entities if e.category == "PERSON"]
        for entity in person_entities:
            assert "Client" not in entity.text

    def test_legal_plaintiff_defendant_not_redacted(self, legal_shield):
        """'Plaintiff' and 'Defendant' labels should not be PERSON entities."""
        text = "Plaintiff: Acme Corp\nDefendant: Beta Corp"
        result = legal_shield.analyze(text)

        person_entities = [e for e in result.entities if e.category == "PERSON"]
        for entity in person_entities:
            assert "Plaintiff" not in entity.text
            assert "Defendant" not in entity.text


class TestProperNounDetection:
    """Tests for proper noun detection after labels (AC3)."""

    def test_patient_name_detected_after_label(self, therapy_shield):
        """'Robin Example' should be detected as PATIENT_NAME."""
        text = "Patient: Robin Example"
        result = therapy_shield.analyze(text)

        # Should detect Robin Example as a patient name
        patient_names = [e for e in result.entities if e.category == "PATIENT_NAME"]
        assert len(patient_names) >= 1
        assert any("Robin" in e.text and "Example" in e.text for e in patient_names)

    def test_multiple_patient_name_occurrences(self, therapy_shield, clinical_sample):
        """All occurrences of 'Robin Example' should be detected."""
        result = therapy_shield.analyze(clinical_sample)

        # Should detect multiple occurrences of Robin Example
        patient_entities = [e for e in result.entities
                          if e.category == "PATIENT_NAME" or
                          (e.category == "PERSON" and "Robin" in e.text)]
        assert len(patient_entities) >= 1

    def test_attorney_name_detected_after_label(self, legal_shield):
        """'Sarah Johnson' should be detected after 'Attorney:' label."""
        text = "Attorney: Sarah Johnson, Esq."
        result = legal_shield.analyze(text)

        # Should detect Sarah Johnson (but not "Attorney")
        all_entities = [e for e in result.entities]
        # At least one entity should contain Sarah Johnson
        assert any("Sarah" in e.text or "Johnson" in e.text for e in all_entities)
        # But "Attorney" alone should not be an entity
        assert not any(e.text == "Attorney" for e in all_entities)


class TestProviderCredentialHandling:
    """Tests for provider name + credential detection (AC4)."""

    def test_provider_with_credential_single_entity(self, therapy_shield):
        """'Dr. Casey Imaginary, LCSW' should be one PROVIDER_NAME entity."""
        text = "Dr. Casey Imaginary, LCSW"
        result = therapy_shield.analyze(text)

        provider_entities = [e for e in result.entities if e.category == "PROVIDER_NAME"]
        assert len(provider_entities) >= 1

        # The full span should be captured as one entity
        full_span_found = any(
            "Casey" in e.text and "Imaginary" in e.text and "LCSW" in e.text
            for e in provider_entities
        )
        assert full_span_found, "Full provider name with credential not captured as single entity"

    def test_provider_with_md_credential(self, therapy_shield):
        """'Dr. John Smith, MD' should be detected as single entity."""
        text = "Dr. John Smith, MD"
        result = therapy_shield.analyze(text)

        provider_entities = [e for e in result.entities if e.category == "PROVIDER_NAME"]
        assert len(provider_entities) >= 1
        full_span_found = any(
            "John" in e.text and "Smith" in e.text and "MD" in e.text
            for e in provider_entities
        )
        assert full_span_found


class TestRegressionFixtures:
    """Integration tests using the actual regression fixtures (AC1, AC5)."""

    def test_clinical_sample_key_entities(self, therapy_shield, clinical_sample):
        """Clinical sample should detect key PHI entities correctly."""
        result = therapy_shield.analyze(clinical_sample)

        # Check that real patient name is detected
        patient_entities = [e for e in result.entities
                          if "Robin" in e.text or "Example" in e.text]
        assert len(patient_entities) > 0, "Patient name 'Robin Example' not detected"

        # Check that "Patient:" label is NOT a separate entity
        assert not any(e.text == "Patient" or e.text == "Patient:"
                      for e in result.entities)

        # Check that provider name with credential is detected
        provider_entities = [e for e in result.entities
                           if "Casey" in e.text or "Imaginary" in e.text]
        assert len(provider_entities) > 0, "Provider 'Dr. Casey Imaginary, LCSW' not detected"

        # Check diagnosis code is detected
        diagnosis_entities = [e for e in result.entities
                            if e.category == "DIAGNOSIS_CODE"]
        assert len(diagnosis_entities) > 0, "Diagnosis code F41.1 not detected"

    def test_legal_sample_key_entities(self, legal_shield, legal_sample):
        """Legal sample should detect privilege markers without false positives."""
        result = legal_shield.analyze(legal_sample)

        # Check that privilege markers are detected
        privilege_entities = [e for e in result.entities
                            if e.category_group.value == "PRIVILEGE"]
        assert len(privilege_entities) > 0, "No privilege markers detected"

        # Check that label words are NOT separate entities
        label_words = ["Attorney", "Client", "Plaintiff", "Defendant", "Counsel"]
        for word in label_words:
            # The word alone (not part of a larger span) should not be an entity
            assert not any(e.text == word or e.text == f"{word}:"
                         for e in result.entities), f"Label '{word}' incorrectly detected as entity"

        # Check that real names are detected
        name_entities = [e for e in result.entities
                       if "Sarah" in e.text or "Johnson" in e.text or "Michael" in e.text or "Brown" in e.text]
        assert len(name_entities) > 0, "Real names not detected in legal sample"

    def test_clinical_sample_no_hanging_credentials(self, therapy_shield, clinical_sample):
        """No credentials should be left hanging without the associated name."""
        result = therapy_shield.analyze(clinical_sample)

        # Check that standalone credentials are not entities
        standalone_credentials = ["LCSW", "MD", "PhD", "LMFT", "LPC"]
        for cred in standalone_credentials:
            # Credential alone should not be an entity (should be part of provider name)
            standalone = [e for e in result.entities if e.text == cred]
            assert len(standalone) == 0, f"Credential '{cred}' found as standalone entity"