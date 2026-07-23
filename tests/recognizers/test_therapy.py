"""Tests for therapy domain recognizers."""

import pytest

from ogentic_shield import Shield


@pytest.fixture
def therapy_shield():
    return Shield(profiles=["shield-therapy"])


class TestPatientNameRecognizer:
    """Tests for PATIENT_NAME detection."""

    def test_detects_patient_label(self, therapy_shield):
        result = therapy_shield.analyze("Patient: Jane D. presented for session.")
        entities = [e for e in result.entities if e.category == "PATIENT_NAME"]
        assert len(entities) >= 1

    def test_detects_patient_full_name(self, therapy_shield):
        result = therapy_shield.analyze("Patient name: John Smith is being treated.")
        entities = [e for e in result.entities if e.category == "PATIENT_NAME"]
        assert len(entities) >= 1

    def test_detects_client_label(self, therapy_shield):
        result = therapy_shield.analyze("Client: Mary J. arrived for intake.")
        entities = [e for e in result.entities if e.category == "PATIENT_NAME"]
        assert len(entities) >= 1

    def test_ignores_general_patient(self, therapy_shield):
        result = therapy_shield.analyze("Hospital satisfaction scores are improving across all departments.")
        entities = [e for e in result.entities if e.category == "PATIENT_NAME"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, therapy_shield):
        result = therapy_shield.analyze("The weather forecast says rain tomorrow.")
        entities = [e for e in result.entities if e.category == "PATIENT_NAME"]
        assert len(entities) == 0

    def test_ignores_bare_patient_word(self, therapy_shield):
        """The common word 'patient' is not a name — must never be flagged PATIENT_NAME
        (regression: the 'therapy-phi-patient-context' rule used to mint it)."""
        result = therapy_shield.analyze("She is a patient.")
        entities = [e for e in result.entities if e.category == "PATIENT_NAME"]
        assert entities == []


class TestDateOfBirthRecognizer:
    """Tests for DATE_OF_BIRTH detection."""

    def test_detects_dob_slash(self, therapy_shield):
        result = therapy_shield.analyze("DOB: 03/15/1988")
        entities = [e for e in result.entities if e.category == "DATE_OF_BIRTH"]
        assert len(entities) >= 1

    def test_detects_dob_dash(self, therapy_shield):
        result = therapy_shield.analyze("DOB: 1988-03-15")
        entities = [e for e in result.entities if e.category == "DATE_OF_BIRTH"]
        assert len(entities) >= 1

    def test_detects_full_label(self, therapy_shield):
        result = therapy_shield.analyze("Date of Birth: 03/15/1988")
        entities = [e for e in result.entities if e.category == "DATE_OF_BIRTH"]
        assert len(entities) >= 1

    def test_ignores_random_date(self, therapy_shield):
        result = therapy_shield.analyze("The meeting is on 03/15/2026.")
        entities = [e for e in result.entities if e.category == "DATE_OF_BIRTH"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, therapy_shield):
        result = therapy_shield.analyze("The book was published in 2020.")
        entities = [e for e in result.entities if e.category == "DATE_OF_BIRTH"]
        assert len(entities) == 0


class TestDiagnosisCodeRecognizer:
    """Tests for DIAGNOSIS_CODE detection."""

    def test_detects_icd10_f33(self, therapy_shield):
        result = therapy_shield.analyze("Diagnosis: F33.1 Major Depressive Disorder.")
        entities = [e for e in result.entities if e.category == "DIAGNOSIS_CODE"]
        assert len(entities) >= 1

    def test_detects_icd10_f41(self, therapy_shield):
        result = therapy_shield.analyze("Code F41.0 panic disorder without agoraphobia.")
        entities = [e for e in result.entities if e.category == "DIAGNOSIS_CODE"]
        assert len(entities) >= 1

    def test_detects_dsm5_reference(self, therapy_shield):
        result = therapy_shield.analyze("Meets DSM-5 criteria for PTSD.")
        entities = [e for e in result.entities if e.category == "DIAGNOSIS_CODE"]
        assert len(entities) >= 1

    def test_ignores_random_codes(self, therapy_shield):
        result = therapy_shield.analyze("Error code A404 not found.")
        entities = [e for e in result.entities if e.category == "DIAGNOSIS_CODE"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, therapy_shield):
        result = therapy_shield.analyze("My favorite color is blue.")
        entities = [e for e in result.entities if e.category == "DIAGNOSIS_CODE"]
        assert len(entities) == 0


class TestClinicalRiskFlagRecognizer:
    """Tests for CLINICAL_RISK_FLAG detection."""

    def test_detects_suicidal_ideation(self, therapy_shield):
        result = therapy_shield.analyze("Patient reports suicidal ideation.")
        entities = [e for e in result.entities if e.category == "CLINICAL_RISK_FLAG"]
        assert len(entities) >= 1
        assert entities[0].confidence >= 0.90

    def test_detects_self_harm(self, therapy_shield):
        result = therapy_shield.analyze("History of self-harm behaviors noted.")
        entities = [e for e in result.entities if e.category == "CLINICAL_RISK_FLAG"]
        assert len(entities) >= 1

    def test_detects_homicidal_ideation(self, therapy_shield):
        result = therapy_shield.analyze("Denies homicidal ideation.")
        entities = [e for e in result.entities if e.category == "CLINICAL_RISK_FLAG"]
        assert len(entities) >= 1

    def test_detects_safety_plan(self, therapy_shield):
        result = therapy_shield.analyze("Safety plan reviewed and updated.")
        entities = [e for e in result.entities if e.category == "CLINICAL_RISK_FLAG"]
        assert len(entities) >= 1

    def test_ignores_general_safety(self, therapy_shield):
        result = therapy_shield.analyze("The building has good safety features like fire exits.")
        entities = [e for e in result.entities if e.category == "CLINICAL_RISK_FLAG"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, therapy_shield):
        result = therapy_shield.analyze("I enjoy playing guitar on weekends.")
        entities = [e for e in result.entities if e.category == "CLINICAL_RISK_FLAG"]
        assert len(entities) == 0


class TestSessionMarkerRecognizer:
    """Tests for SESSION_MARKER detection."""

    def test_detects_session_number(self, therapy_shield):
        result = therapy_shield.analyze("Session 12 progress note.")
        entities = [e for e in result.entities if e.category == "SESSION_MARKER"]
        assert len(entities) >= 1

    def test_detects_session_notes(self, therapy_shield):
        result = therapy_shield.analyze("Completed session notes for today.")
        entities = [e for e in result.entities if e.category == "SESSION_MARKER"]
        assert len(entities) >= 1

    def test_detects_intake_assessment(self, therapy_shield):
        result = therapy_shield.analyze("Initial assessment completed on intake.")
        entities = [e for e in result.entities if e.category == "SESSION_MARKER"]
        assert len(entities) >= 1

    def test_ignores_music_session(self, therapy_shield):
        result = therapy_shield.analyze("The recording session went well at the studio.")
        entities = [e for e in result.entities if e.category == "SESSION_MARKER"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, therapy_shield):
        result = therapy_shield.analyze("The pizza was delicious.")
        entities = [e for e in result.entities if e.category == "SESSION_MARKER"]
        assert len(entities) == 0


class TestInsuranceIdRecognizer:
    """Tests for INSURANCE_ID detection."""

    def test_detects_insurance_id(self, therapy_shield):
        result = therapy_shield.analyze("Insurance ID: UHC-8847291")
        entities = [e for e in result.entities if e.category == "INSURANCE_ID"]
        assert len(entities) >= 1

    def test_detects_member_id(self, therapy_shield):
        result = therapy_shield.analyze("Member ID: ABC12345678")
        entities = [e for e in result.entities if e.category == "INSURANCE_ID"]
        assert len(entities) >= 1

    def test_detects_policy_number(self, therapy_shield):
        result = therapy_shield.analyze("Policy number: POL987654")
        entities = [e for e in result.entities if e.category == "INSURANCE_ID"]
        assert len(entities) >= 1

    def test_ignores_general_id(self, therapy_shield):
        result = therapy_shield.analyze("My employee badge number is 42.")
        entities = [e for e in result.entities if e.category == "INSURANCE_ID"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, therapy_shield):
        result = therapy_shield.analyze("The library closes at 8pm.")
        entities = [e for e in result.entities if e.category == "INSURANCE_ID"]
        assert len(entities) == 0


class TestMedicationRecognizer:
    """Tests for MEDICATION detection."""

    def test_detects_sertraline(self, therapy_shield):
        result = therapy_shield.analyze("Prescribed Sertraline 100mg daily.")
        entities = [e for e in result.entities if e.category == "MEDICATION"]
        assert len(entities) >= 1

    def test_detects_brand_name(self, therapy_shield):
        result = therapy_shield.analyze("Patient started on Zoloft last week.")
        entities = [e for e in result.entities if e.category == "MEDICATION"]
        assert len(entities) >= 1

    def test_detects_lexapro(self, therapy_shield):
        result = therapy_shield.analyze("Switched from Lexapro to Wellbutrin.")
        entities = [e for e in result.entities if e.category == "MEDICATION"]
        assert len(entities) >= 1

    def test_ignores_general_medicine(self, therapy_shield):
        result = therapy_shield.analyze("I took some aspirin for my headache.")
        entities = [e for e in result.entities if e.category == "MEDICATION"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, therapy_shield):
        result = therapy_shield.analyze("The garden needs watering today.")
        entities = [e for e in result.entities if e.category == "MEDICATION"]
        assert len(entities) == 0

    def test_ignores_bare_medication_word(self, therapy_shield):
        """'medication'/'prescribed' are context triggers, not drug names — must never be
        flagged MEDICATION (regression: 'therapy-medication-diagnosis-boost' minted it)."""
        result = therapy_shield.analyze("The medication list was reviewed at the appointment.")
        entities = [e for e in result.entities if e.category == "MEDICATION"]
        assert entities == []


class TestProviderNameRecognizer:
    """Tests for PROVIDER_NAME detection."""

    def test_detects_therapist_name(self, therapy_shield):
        result = therapy_shield.analyze("Therapist Sarah conducted the session.")
        entities = [e for e in result.entities if e.category == "PROVIDER_NAME"]
        assert len(entities) >= 1

    def test_detects_credentials(self, therapy_shield):
        result = therapy_shield.analyze("Treated by Johnson, LCSW.")
        entities = [e for e in result.entities if e.category == "PROVIDER_NAME"]
        assert len(entities) >= 1

    def test_detects_clinician_label(self, therapy_shield):
        result = therapy_shield.analyze("Clinician: Roberts reviewed the plan.")
        entities = [e for e in result.entities if e.category == "PROVIDER_NAME"]
        assert len(entities) >= 1

    def test_ignores_general_names(self, therapy_shield):
        result = therapy_shield.analyze("Alice went shopping downtown.")
        entities = [e for e in result.entities if e.category == "PROVIDER_NAME"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, therapy_shield):
        result = therapy_shield.analyze("The sunset was beautiful yesterday.")
        entities = [e for e in result.entities if e.category == "PROVIDER_NAME"]
        assert len(entities) == 0


class TestSsnRecognizer:
    """Tests for SSN detection."""

    def test_detects_dashed_ssn(self, therapy_shield):
        result = therapy_shield.analyze("SSN: 123-45-6789")
        entities = [e for e in result.entities if e.category == "SSN"]
        assert len(entities) >= 1

    def test_detects_labeled_ssn(self, therapy_shield):
        result = therapy_shield.analyze("Social Security number: 123-45-6789")
        entities = [e for e in result.entities if e.category == "SSN"]
        assert len(entities) >= 1

    def test_detects_ssn_prefix(self, therapy_shield):
        result = therapy_shield.analyze("SSN 987-65-4321 on file.")
        entities = [e for e in result.entities if e.category == "SSN"]
        assert len(entities) >= 1

    def test_ignores_phone_number(self, therapy_shield):
        result = therapy_shield.analyze("Call 555-123-4567 for info.")
        entities = [e for e in result.entities if e.category == "SSN"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, therapy_shield):
        result = therapy_shield.analyze("The movie starts at seven thirty.")
        entities = [e for e in result.entities if e.category == "SSN"]
        assert len(entities) == 0


class TestPsychotherapyNoteMarkerRecognizer:
    """Tests for PSYCHOTHERAPY_NOTE_MARKER detection."""

    def test_detects_process_notes(self, therapy_shield):
        result = therapy_shield.analyze("Process notes from today's session.")
        entities = [e for e in result.entities if e.category == "PSYCHOTHERAPY_NOTE_MARKER"]
        assert len(entities) >= 1

    def test_detects_countertransference(self, therapy_shield):
        result = therapy_shield.analyze("Countertransference noted in response to patient anger.")
        entities = [e for e in result.entities if e.category == "PSYCHOTHERAPY_NOTE_MARKER"]
        assert len(entities) >= 1

    def test_detects_therapeutic_alliance(self, therapy_shield):
        result = therapy_shield.analyze("Therapeutic alliance remains strong.")
        entities = [e for e in result.entities if e.category == "PSYCHOTHERAPY_NOTE_MARKER"]
        assert len(entities) >= 1

    def test_detects_psychotherapy_notes(self, therapy_shield):
        result = therapy_shield.analyze("These are psychotherapy notes protected under HIPAA.")
        entities = [e for e in result.entities if e.category == "PSYCHOTHERAPY_NOTE_MARKER"]
        assert len(entities) >= 1

    def test_ignores_general_notes(self, therapy_shield):
        result = therapy_shield.analyze("I took notes during the meeting about the project timeline.")
        entities = [e for e in result.entities if e.category == "PSYCHOTHERAPY_NOTE_MARKER"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, therapy_shield):
        result = therapy_shield.analyze("The concert was amazing last night.")
        entities = [e for e in result.entities if e.category == "PSYCHOTHERAPY_NOTE_MARKER"]
        assert len(entities) == 0
