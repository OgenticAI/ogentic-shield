"""Therapy domain recognizers for HIPAA PHI, psychotherapy notes, and clinical risk."""

from presidio_analyzer import Pattern, PatternRecognizer


class PatientNameRecognizer(PatternRecognizer):
    """Detects patient name references in clinical context."""

    PATTERNS = [
        Pattern(
            name="patient_label",
            regex=r"\b[Pp]atient:?\s+(?-i:[A-Z][a-z]+(\s+[A-Z]\.?)(\s+[A-Z][a-z]+)?)\b",
            score=0.93,
        ),
        Pattern(
            name="patient_name_ref",
            regex=r"\b[Pp]atient\s+(name:?\s+)?(?-i:[A-Z][a-z]+\s+[A-Z][a-z]+)\b",
            score=0.90,
        ),
        Pattern(
            name="client_label",
            regex=r"\b[Cc]lient:?\s+(?-i:[A-Z][a-z]+(\s+[A-Z]\.?)(\s+[A-Z][a-z]+)?)\b",
            score=0.88,
        ),
    ]

    CONTEXT_WORDS = ["patient", "therapy", "session", "treatment", "clinical"]

    def __init__(self):
        super().__init__(
            supported_entity="PATIENT_NAME",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class DateOfBirthRecognizer(PatternRecognizer):
    """Detects date of birth references in clinical context."""

    PATTERNS = [
        Pattern(
            name="dob_slash",
            regex=r"\bDOB:?\s*\d{1,2}/\d{1,2}/\d{2,4}\b",
            score=0.95,
        ),
        Pattern(
            name="dob_dash",
            regex=r"\bDOB:?\s*\d{4}-\d{2}-\d{2}\b",
            score=0.95,
        ),
        Pattern(
            name="date_of_birth_label",
            regex=r"\b[Dd]ate\s+of\s+[Bb]irth:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            score=0.95,
        ),
        Pattern(
            name="born_date",
            regex=r"\bborn\s+(on\s+)?\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            score=0.90,
        ),
    ]

    CONTEXT_WORDS = ["patient", "age", "birth", "DOB", "demographics"]

    def __init__(self):
        super().__init__(
            supported_entity="DATE_OF_BIRTH",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class DiagnosisCodeRecognizer(PatternRecognizer):
    """Detects ICD-10 mental health diagnosis codes."""

    PATTERNS = [
        Pattern(
            name="icd10_f_code",
            regex=r"\bF\d{2}(\.\d{1,2})?\b",
            score=0.92,
        ),
        Pattern(
            name="dsm5_diagnosis",
            regex=r"\bDSM[\s-]?5?\s+(diagnosis|code|criteria)\b",
            score=0.88,
        ),
        Pattern(
            name="diagnosis_code_label",
            regex=r"\b[Dd]iagnosis\s+[Cc]ode:?\s*[A-Z]\d{2}(\.\d{1,2})?\b",
            score=0.95,
        ),
    ]

    CONTEXT_WORDS = ["diagnosis", "diagnostic", "ICD", "DSM", "code", "criteria"]

    def __init__(self):
        super().__init__(
            supported_entity="DIAGNOSIS_CODE",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class ClinicalRiskFlagRecognizer(PatternRecognizer):
    """Detects clinical risk indicators including suicidal ideation and self-harm."""

    PATTERNS = [
        Pattern(
            name="suicidal_ideation",
            regex=r"\bsuicidal\s+(ideation|thought|intent|plan)\b",
            score=0.97,
        ),
        Pattern(
            name="self_harm",
            regex=r"\bself[\s-]harm(ing)?\b",
            score=0.95,
        ),
        Pattern(
            name="homicidal",
            regex=r"\bhomicidal\s+(ideation|thought|intent)\b",
            score=0.97,
        ),
        Pattern(
            name="safety_plan",
            regex=r"\bsafety\s+(plan|contract|assessment)\b",
            score=0.85,
        ),
        Pattern(
            name="risk_assessment",
            regex=r"\b(suicide|violence)\s+risk\s+assessment\b",
            score=0.93,
        ),
    ]

    CONTEXT_WORDS = ["risk", "safety", "crisis", "emergency", "ideation", "plan"]

    def __init__(self):
        super().__init__(
            supported_entity="CLINICAL_RISK_FLAG",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class SessionMarkerRecognizer(PatternRecognizer):
    """Detects therapy session markers and clinical documentation references."""

    PATTERNS = [
        Pattern(
            name="session_number",
            regex=r"\b[Ss]ession\s+\d{1,3}\b",
            score=0.88,
        ),
        Pattern(
            name="session_notes",
            regex=r"\bsession\s+notes?\b",
            score=0.88,
        ),
        Pattern(
            name="intake_assessment",
            regex=r"\b(intake|initial)\s+(assessment|evaluation|interview)\b",
            score=0.90,
        ),
        Pattern(
            name="treatment_plan",
            regex=r"\btreatment\s+plan\b",
            score=0.88,
        ),
        Pattern(
            name="progress_note",
            regex=r"\bprogress\s+note\b",
            score=0.88,
        ),
    ]

    CONTEXT_WORDS = ["therapy", "clinical", "patient", "therapist", "treatment"]

    def __init__(self):
        super().__init__(
            supported_entity="SESSION_MARKER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class InsuranceIdRecognizer(PatternRecognizer):
    """Detects insurance identifiers and member IDs."""

    PATTERNS = [
        Pattern(
            name="insurance_id_label",
            regex=r"\b[Ii]nsurance\s+(ID|Id):?\s*[A-Z]{2,5}[\s-]?\d{5,10}\b",
            score=0.95,
        ),
        Pattern(
            name="member_id",
            regex=r"\b[Mm]ember\s+(ID|Id|#):?\s*[A-Z0-9]{5,15}\b",
            score=0.90,
        ),
        Pattern(
            name="policy_number",
            regex=r"\b[Pp]olicy\s+(number|#|no\.?):?\s*[A-Z0-9]{5,15}\b",
            score=0.90,
        ),
        Pattern(
            name="group_number",
            regex=r"\b[Gg]roup\s+(number|#|no\.?):?\s*[A-Z0-9]{4,12}\b",
            score=0.88,
        ),
    ]

    CONTEXT_WORDS = ["insurance", "coverage", "plan", "subscriber", "copay"]

    def __init__(self):
        super().__init__(
            supported_entity="INSURANCE_ID",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class MedicationRecognizer(PatternRecognizer):
    """Detects psychiatric medications and dosages."""

    PATTERNS = [
        Pattern(
            name="psych_medications",
            regex=(
                r"\b("
                r"[Ss]ertraline|[Ff]luoxetine|[Ee]scitalopram|[Cc]italopram|[Pp]aroxetine|"
                r"[Vv]enlafaxine|[Dd]uloxetine|[Bb]upropion|[Mm]irtazapine|[Tt]razodone|"
                r"[Aa]mitriptyline|[Nn]ortriptyline|[Ll]ithium|[Ll]amotrigine|[Vv]alproate|"
                r"[Cc]arbamazepine|[Qq]uetiapine|[Oo]lanzapine|[Rr]isperidone|[Aa]ripiprazole|"
                r"[Cc]lozapine|[Zz]iprasidone|[Ll]orazepam|[Cc]lonazepam|[Aa]lprazolam|"
                r"[Dd]iazepam|[Bb]uspirone|[Hh]ydroxyzine|[Mm]ethylphenidate|[Aa]mphetamine|"
                r"[Ll]isdexamfetamine|[Aa]tomoxetine|[Gg]uanfacine|[Nn]altrexone|"
                r"[Zz]olpidem|[Ee]szopiclone|[Gg]abapentin|[Pp]regabalin|[Pp]ropranolol|"
                r"[Pp]razosin|[Tt]opiramate|[Mm]odafinil|[Dd]extromethorphan|[Pp]imozide|"
                r"[Hh]aloperidol|[Cc]hlorpromazine|[Ff]luphenazine|[Pp]erphenazine|"
                r"[Ll]oxapine|[Mm]olidone|[Pp]aliperidone|[Ll]urasidone|[Bb]rexpiprazole|"
                r"[Cc]ariprazine|[Zz]oloft|[Pp]rozac|[Ll]exapro|[Cc]elexa|[Pp]axil|"
                r"[Ee]ffexor|[Cc]ymbalta|[Ww]ellbutrin|[Rr]emeron|[Ss]eroquel|"
                r"[Zz]yprexa|[Rr]isperdal|[Aa]bilify|[Xx]anax|[Kk]lonopin|[Aa]tivan|"
                r"[Vv]alium|[Aa]dderall|[Rr]italin|[Vv]yvanse|[Aa]mbien|[Dd]epakote|"
                r"[Tt]egretol|[Ll]amictal"
                r")\b"
            ),
            score=0.88,
        ),
        Pattern(
            name="dosage_pattern",
            regex=r"\b\d+\s*mg\s*(daily|bid|tid|qd|qhs|prn|q\.?d\.?|b\.?i\.?d\.?)\b",
            score=0.80,
        ),
    ]

    CONTEXT_WORDS = ["prescribed", "medication", "dose", "mg", "daily", "treatment"]

    def __init__(self):
        super().__init__(
            supported_entity="MEDICATION",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class ProviderNameRecognizer(PatternRecognizer):
    """Detects mental health provider name references."""

    PATTERNS = [
        Pattern(
            name="dr_prefix",
            regex=r"\bDr\.?\s+(?-i:[A-Z][a-z]+(\s+[A-Z][a-z]+)?)\b",
            score=0.75,
        ),
        Pattern(
            name="therapist_name",
            regex=r"\b[Tt]herapist\s+(?-i:[A-Z][a-z]+(\s+[A-Z][a-z]+)?)\b",
            score=0.90,
        ),
        Pattern(
            name="provider_label",
            regex=r"\b[Pp]rovider:?\s+(?-i:[A-Z][a-z]+(\s+[A-Z][a-z]+)?)\b",
            score=0.85,
        ),
        Pattern(
            name="clinician_name",
            regex=r"\b[Cc]linician:?\s+(?-i:[A-Z][a-z]+(\s+[A-Z][a-z]+)?)\b",
            score=0.88,
        ),
        Pattern(
            name="credentials",
            regex=r"\b(?-i:[A-Z][a-z]+(\s+[A-Z][a-z]+)?),?\s+(LCSW|LMFT|LPC|PsyD|PhD|LMHC|LCPC)\b",
            score=0.92,
        ),
    ]

    CONTEXT_WORDS = ["therapist", "provider", "clinician", "treating", "referred"]

    def __init__(self):
        super().__init__(
            supported_entity="PROVIDER_NAME",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class SsnRecognizer(PatternRecognizer):
    """Detects Social Security Numbers."""

    PATTERNS = [
        Pattern(
            name="ssn_dashed",
            regex=r"\b\d{3}-\d{2}-\d{4}\b",
            score=0.90,
        ),
        Pattern(
            name="ssn_label",
            regex=r"\bSSN:?\s*\d{3}[\s-]?\d{2}[\s-]?\d{4}\b",
            score=0.95,
        ),
        Pattern(
            name="social_security",
            regex=r"\b[Ss]ocial\s+[Ss]ecurity\s+(number|#|no\.?):?\s*\d{3}[\s-]?\d{2}[\s-]?\d{4}\b",
            score=0.97,
        ),
    ]

    CONTEXT_WORDS = ["social security", "SSN", "tax", "identification"]

    def __init__(self):
        super().__init__(
            supported_entity="SSN",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class PsychotherapyNoteMarkerRecognizer(PatternRecognizer):
    """Detects psychotherapy note indicators protected under HIPAA."""

    PATTERNS = [
        Pattern(
            name="process_notes",
            regex=r"\bprocess\s+notes?\b",
            score=0.93,
        ),
        Pattern(
            name="countertransference",
            regex=r"\bcountertransference\b",
            score=0.95,
        ),
        Pattern(
            name="therapeutic_alliance",
            regex=r"\btherapeutic\s+alliance\b",
            score=0.93,
        ),
        Pattern(
            name="psychotherapy_notes",
            regex=r"\bpsychotherapy\s+notes?\b",
            score=0.97,
        ),
        Pattern(
            name="clinical_impressions",
            regex=r"\bclinical\s+impression[s]?\b",
            score=0.88,
        ),
        Pattern(
            name="transference",
            regex=r"\btransference\b",
            score=0.80,
        ),
    ]

    CONTEXT_WORDS = ["therapy", "session", "clinical", "patient", "psychotherapy"]

    def __init__(self):
        super().__init__(
            supported_entity="PSYCHOTHERAPY_NOTE_MARKER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )
