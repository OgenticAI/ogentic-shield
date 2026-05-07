"""shield-therapy-pro profile (OGE-355).

Extends `shield-therapy` v0.1 with the billing-and-diagnosis layer that
distinguishes "session-note assist" from "insurance documentation":
DSM-5-TR named diagnoses, CPT mental-health billing codes, expanded DOB
patterns, minor-client markers, and trauma indicators.

Per architecture decision AD-02 (CLAUDE.md §3): built-in profiles are
Python modules, not YAML — the v0.1 + pro recognizer set needs
class-level patterns, context words, and (future) NER post-processing
that YAML can't express.

The pro profile loads BOTH the v0.1 recognizers and the new pro
recognizers. Layer-1 deduplication (longest span wins, then highest
confidence) handles overlapping detections cleanly.

Scoring weight rationale (vs. v0.1 shield-therapy):

- ``PHI``: 32 (vs. 28). Billing+diagnosis text is uniformly PHI-dense
  under HIPAA; bumping the weight pushes more results into HIGH/CRITICAL
  routing buckets, which is what insurance-documentation flows want.
- ``PII``: 15 (unchanged).
- ``CONFIDENTIAL``: 10 (unchanged).

Open question for clinician sign-off (UAT criterion): are these the
right relative weights for billing-letter workflows? Default values
ship; clinician review on the linked ticket either confirms or tunes.
"""

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
from ogentic_shield.recognizers.therapy_pro import (
    CptMentalHealthCodeRecognizer,
    Dsm5DiagnosisRecognizer,
    ExpandedDateOfBirthRecognizer,
    MinorClientMarkerRecognizer,
    TraumaIndicatorRecognizer,
)

PROFILE_ID = "shield-therapy-pro"
PROFILE_VERSION = "0.3.0"

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
    Dsm5DiagnosisRecognizer(),
    CptMentalHealthCodeRecognizer(),
    ExpandedDateOfBirthRecognizer(),
    MinorClientMarkerRecognizer(),
    TraumaIndicatorRecognizer(),
]

RULES = [
    Rule(
        id="therapy-pro-cpt-billing-context",
        name="CPT Billing Context Boost",
        description="Boost CPT code confidence when invoice/billing context is nearby",
        pattern=r"\b(90791|90792|90832|90834|90837|90847|90853)\b",
        flags=re.IGNORECASE,
        category="CPT_CODE",
        category_group=CategoryGroup.PHI,
        confidence=0.92,
        context_patterns=["billing", "claim", "insurance", "session", "CPT"],
        context_window=200,
        context_confidence_boost=0.06,
    ),
    Rule(
        # Layer-2 rules emit a new entity whenever the pattern matches (context
        # only boosts confidence). Keep patterns strict to multi-word phrasings
        # that match the corresponding recognizer's high-confidence patterns —
        # otherwise bare words like "Bipolar" trigger false positives outside
        # clinical context.
        id="therapy-pro-dsm5-diagnosis-context",
        name="DSM-5 Diagnosis Context Boost",
        description="Boost confidence on DSM-5 disorder names when paired with diagnostic context",
        pattern=r"\b(Major\s+Depressive\s+Disorder|Generalized\s+Anxiety\s+Disorder|Bipolar\s+(I|II|Disorder)|Borderline\s+Personality\s+Disorder)\b",
        flags=re.IGNORECASE,
        category="DSM5_DIAGNOSIS",
        category_group=CategoryGroup.PHI,
        confidence=0.95,
        context_patterns=["diagnosis", "criteria", "DSM", "disorder", "F\\d{2}"],
        context_window=300,
        context_confidence_boost=0.04,
    ),
    Rule(
        id="therapy-pro-minor-client-boost",
        name="Minor Client Marker Boost",
        description="Boost minor-client markers when paired with patient/clinical context",
        pattern=r"\b(minor\s+(client|patient|child)|legal\s+guardian|guardian\s+(present|attended|consented|on\s+file)|parental\s+consent\s+(on\s+file|provided|obtained))\b",
        flags=re.IGNORECASE,
        category="MINOR_CLIENT_MARKER",
        category_group=CategoryGroup.PHI,
        confidence=0.93,
        context_patterns=["patient", "client", "session", "consent", "intake"],
        context_window=300,
        context_confidence_boost=0.05,
    ),
    Rule(
        id="therapy-pro-trauma-context",
        name="Trauma Indicator Context",
        description="Surface trauma context with high confidence (advisory; do NOT redact)",
        pattern=r"\b(PTSD|C[\s-]PTSD|trauma\s+history|history\s+of\s+abuse|sexual\s+abuse|physical\s+abuse|domestic\s+violence|adverse\s+childhood\s+experiences?)\b",
        flags=re.IGNORECASE,
        category="TRAUMA_INDICATOR",
        category_group=CategoryGroup.PHI,
        confidence=0.92,
        context_patterns=["history", "patient", "session", "exposure", "survivor"],
        context_window=300,
        context_confidence_boost=0.05,
    ),
    Rule(
        id="therapy-pro-patient-context",
        name="PHI Patient Context (inherited)",
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
        id="therapy-pro-clinical-risk-boost",
        name="Clinical Risk Boost (inherited)",
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
        id="therapy-pro-psychotherapy-note-boost",
        name="Psychotherapy Note Boost (inherited)",
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
        id="therapy-pro-medication-diagnosis-boost",
        name="Medication Diagnosis Context (inherited)",
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
    CategoryGroup.PHI: 32,
    CategoryGroup.PII: 15,
    CategoryGroup.CONFIDENTIAL: 10,
}


def create_profile() -> ShieldProfile:
    return ShieldProfile(
        id=PROFILE_ID,
        name="Therapy PHI Protection (Pro — billing + diagnosis)",
        version=PROFILE_VERSION,
        description=(
            "Extends shield-therapy with DSM-5-TR named diagnoses, CPT mental-health "
            "billing codes, expanded DOB patterns, minor-client markers, and trauma "
            "indicators. For insurance-documentation and treatment-summary workflows."
        ),
        recognizers=RECOGNIZERS,
        rules=RULES,
        scoring_weights=SCORING_WEIGHTS,
        supported_entities=[r.supported_entities[0] for r in RECOGNIZERS],
    )
