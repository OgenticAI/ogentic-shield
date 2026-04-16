"""shield-therapy profile: recognizers, rules, and scoring weights for HIPAA PHI detection."""

import re

from ogentic_shield.models import CategoryGroup, Rule, ShieldProfile
from ogentic_shield.recognizers.therapy import (
    ClinicalRiskFlagRecognizer,
    DateOfBirthRecognizer,
    DiagnosisCodeRecognizer,
    InsuranceIdRecognizer,
    MedicationRecognizer,
    PatientNameRecognizer,
    ProviderNameRecognizer,
    PsychotherapyNoteMarkerRecognizer,
    SessionMarkerRecognizer,
    SsnRecognizer,
)

PROFILE_ID = "shield-therapy"
PROFILE_VERSION = "0.1.0"

RECOGNIZERS = [
    PatientNameRecognizer(),
    DateOfBirthRecognizer(),
    DiagnosisCodeRecognizer(),
    ClinicalRiskFlagRecognizer(),
    SessionMarkerRecognizer(),
    InsuranceIdRecognizer(),
    MedicationRecognizer(),
    ProviderNameRecognizer(),
    SsnRecognizer(),
    PsychotherapyNoteMarkerRecognizer(),
]

RULES = [
    Rule(
        id="therapy-phi-patient-context",
        name="PHI Patient Context",
        description="Boost confidence when patient name appears with clinical markers",
        pattern=r"\b[Pp]atient\b",
        flags=re.IGNORECASE,
        category="PATIENT_NAME",
        category_group=CategoryGroup.PHI,
        confidence=0.93,
        context_patterns=["diagnosis", "treatment", "session", "medication"],
        context_window=300,
        context_confidence_boost=0.07,
    ),
    Rule(
        id="therapy-clinical-risk-boost",
        name="Clinical Risk Boost",
        description="Boost confidence for clinical risk terms in therapy session context",
        pattern=r"\b(suicidal|self[\s-]harm|homicidal)\b",
        flags=re.IGNORECASE,
        category="CLINICAL_RISK_FLAG",
        category_group=CategoryGroup.PHI,
        confidence=0.97,
        context_patterns=["patient", "session", "assessment", "risk"],
        context_window=200,
        context_confidence_boost=0.03,
    ),
    Rule(
        id="therapy-psychotherapy-note-boost",
        name="Psychotherapy Note Boost",
        description="Boost confidence when psychotherapy note markers appear with session context",
        pattern=r"\b(process\s+notes?|countertransference|therapeutic\s+alliance)\b",
        flags=re.IGNORECASE,
        category="PSYCHOTHERAPY_NOTE_MARKER",
        category_group=CategoryGroup.PHI,
        confidence=0.95,
        context_patterns=["therapy", "session", "patient", "clinical"],
        context_window=300,
        context_confidence_boost=0.05,
    ),
    Rule(
        id="therapy-medication-diagnosis-boost",
        name="Medication Diagnosis Context",
        description="Boost medication confidence when diagnosis codes appear nearby",
        pattern=r"\b(prescribed|medication|started\s+on)\b",
        flags=re.IGNORECASE,
        category="MEDICATION",
        category_group=CategoryGroup.PHI,
        confidence=0.90,
        context_patterns=["diagnosis", "F\\d{2}", "mg", "dosage"],
        context_window=200,
        context_confidence_boost=0.05,
    ),
]

SCORING_WEIGHTS = {
    CategoryGroup.PHI: 28,
    CategoryGroup.PII: 15,
    CategoryGroup.CONFIDENTIAL: 10,
}


def create_profile() -> ShieldProfile:
    return ShieldProfile(
        id=PROFILE_ID,
        name="Therapy PHI Protection",
        version=PROFILE_VERSION,
        description="Detects HIPAA PHI, psychotherapy note content, and clinical risk indicators.",
        recognizers=RECOGNIZERS,
        rules=RULES,
        scoring_weights=SCORING_WEIGHTS,
        supported_entities=[r.supported_entities[0] for r in RECOGNIZERS],
    )
