"""Therapy-pro domain recognizers — billing-and-diagnosis layer (OGE-355).

Extends `shield-therapy` v0.1 with five recognizers that distinguish
"insurance documentation" workflows from generic session-note assist:

- :class:`Dsm5DiagnosisRecognizer` — DSM-5-TR named disorders + section labels
  (the v0.1 :class:`DiagnosisCodeRecognizer` already covers ICD-10 F-codes;
  this one covers the *name-form* diagnoses that appear in billing letters
  and treatment summaries).
- :class:`CptMentalHealthCodeRecognizer` — AMA CPT 2026 psychiatric +
  neuropsychological-testing codes used for insurance billing.
- :class:`ExpandedDateOfBirthRecognizer` — additional DOB patterns the v0.1
  recognizer doesn't cover ("Born:", "b. 04/12/", "Birthdate:", etc.).
- :class:`MinorClientMarkerRecognizer` — guardian / parental-consent
  markers indicating a minor patient (heightens HIPAA + state minor-consent
  obligations).
- :class:`TraumaIndicatorRecognizer` — PTSD / abuse-history terms. Flagged
  for *higher* protection but explicitly NOT for redaction (per ticket:
  trauma context is clinically essential — we surface it so the routing
  layer can keep it on-device, not strip it).
"""

from presidio_analyzer import Pattern, PatternRecognizer


class Dsm5DiagnosisRecognizer(PatternRecognizer):
    """Detects DSM-5-TR named disorders + section/criteria language.

    Complements :class:`ogentic_shield.recognizers.therapy.DiagnosisCodeRecognizer`
    (which handles ICD-10 F-code patterns). This recognizer focuses on the
    *named* form that appears in clinical letters, billing summaries, and
    treatment plans — where the F-code is paraphrased or omitted.
    """

    PATTERNS = [
        Pattern(
            name="dsm5_tr_marker",
            regex=r"\bDSM[\s-]?5(?:[\s-]?TR)?\b",
            score=0.90,
        ),
        Pattern(
            name="major_depressive_disorder",
            regex=r"\bMajor\s+Depressive\s+Disorder\b",
            score=0.93,
        ),
        Pattern(
            name="generalized_anxiety_disorder",
            regex=r"\bGeneralized\s+Anxiety\s+Disorder\b",
            score=0.93,
        ),
        Pattern(
            name="bipolar_disorder",
            regex=r"\bBipolar\s+(I|II|Disorder)\b",
            score=0.92,
        ),
        Pattern(
            # PTSD as an acronym + "trauma" variants are owned by
            # :class:`TraumaIndicatorRecognizer`. Here we keep only the
            # spelled-out clinical form so the two recognizers don't
            # collide on the same span (Layer-1 dedup is non-deterministic
            # when entities have the same length and confidence).
            name="ptsd_named",
            regex=r"\bPost[\s-]traumatic\s+Stress\s+Disorder\b",
            score=0.92,
        ),
        Pattern(
            name="adhd_named",
            regex=r"\b(Attention[\s-]Deficit/Hyperactivity\s+Disorder|ADHD)\b",
            score=0.90,
        ),
        Pattern(
            name="ocd_named",
            regex=r"\b(Obsessive[\s-]Compulsive\s+Disorder|OCD)\b",
            score=0.90,
        ),
        Pattern(
            name="borderline_personality_disorder",
            regex=r"\bBorderline\s+Personality\s+Disorder\b",
            score=0.93,
        ),
        Pattern(
            name="schizophrenia",
            regex=r"\bSchizophrenia\b",
            score=0.92,
        ),
        Pattern(
            name="autism_spectrum_disorder",
            regex=r"\b(Autism\s+Spectrum\s+Disorder|ASD)\b",
            score=0.90,
        ),
        Pattern(
            name="dsm5_specifier",
            regex=r"\b(provisional|in\s+partial\s+remission|in\s+full\s+remission|by\s+history|rule[\s-]out)\b",
            score=0.75,
        ),
    ]

    CONTEXT_WORDS = ["DSM", "diagnosis", "diagnostic", "criteria", "disorder", "condition"]

    def __init__(self):
        super().__init__(
            supported_entity="DSM5_DIAGNOSIS",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class CptMentalHealthCodeRecognizer(PatternRecognizer):
    """Detects CPT 2026 mental-health billing codes.

    Covers the psychiatric service range (90785–90899) and the
    psychological/neuropsychological testing range (96130–96139). Unlabeled
    bare codes are scored conservatively because 5-digit numerics are
    common in non-clinical text; labeled forms (``CPT 90834``,
    ``CPT code: 90834``) score high.
    """

    PATTERNS = [
        Pattern(
            name="cpt_label_psych",
            regex=r"\bCPT\s*(code\s*)?:?\s*(90791|90792|90832|90834|90837|90838|90839|90840|90846|90847|90849|90853|90875|90876|9078[5-9]|908[8-9]\d)\b",
            score=0.97,
        ),
        Pattern(
            name="cpt_label_testing",
            regex=r"\bCPT\s*(code\s*)?:?\s*(9613[0-9])\b",
            score=0.97,
        ),
        Pattern(
            name="bare_psych_code",
            regex=r"\b(90791|90792|90832|90834|90837|90838|90839|90840|90846|90847|90849|90853|90875|90876)\b",
            score=0.82,
        ),
        Pattern(
            name="bare_testing_code",
            regex=r"\b(9613[0-9])\b",
            score=0.78,
        ),
        Pattern(
            name="evaluation_management",
            regex=r"\b(99201|99202|99203|99204|99205|99211|99212|99213|99214|99215)\b",
            score=0.70,
        ),
    ]

    CONTEXT_WORDS = [
        "CPT",
        "billing",
        "code",
        "claim",
        "session",
        "psychotherapy",
        "evaluation",
        "insurance",
    ]

    def __init__(self):
        super().__init__(
            supported_entity="CPT_CODE",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class ExpandedDateOfBirthRecognizer(PatternRecognizer):
    """Additional DOB patterns beyond the v0.1 :class:`DateOfBirthRecognizer`.

    Emits the same ``DATE_OF_BIRTH`` entity type so downstream consumers see
    one consolidated category. Layer-1 deduplication (longest span wins)
    resolves overlap with the v0.1 recognizer for shared spans.
    """

    PATTERNS = [
        Pattern(
            name="born_label",
            regex=r"\bBorn:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            score=0.93,
        ),
        Pattern(
            name="b_abbrev_full",
            regex=r"\bb\.\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            score=0.90,
        ),
        Pattern(
            name="b_abbrev_year_paren",
            regex=r"\(b\.\s*\d{4}\)",
            score=0.85,
        ),
        Pattern(
            name="birthdate_label",
            regex=r"\b[Bb]irth\s*[Dd]ate:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            score=0.95,
        ),
        Pattern(
            name="dob_paren_year",
            regex=r"\bDOB:?\s*\d{4}\b",
            score=0.85,
        ),
    ]

    CONTEXT_WORDS = ["patient", "client", "minor", "demographics", "intake", "age"]

    def __init__(self):
        super().__init__(
            supported_entity="DATE_OF_BIRTH",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class MinorClientMarkerRecognizer(PatternRecognizer):
    """Detects markers indicating the patient is a minor.

    Minor status changes the HIPAA consent path (parent/guardian) and
    triggers state-specific minor-consent statutes (e.g. IL Mental Health
    and Developmental Disabilities Confidentiality Act § 4). Surface so
    the routing layer can apply the correct policy.
    """

    PATTERNS = [
        Pattern(
            name="guardian_present",
            regex=r"\b(legal\s+)?guardian\s+(present|attended|consented|on\s+file)\b",
            score=0.93,
        ),
        Pattern(
            name="parent_present",
            regex=r"\bparent\s+(present|attended|consented)\b",
            score=0.90,
        ),
        Pattern(
            name="parental_consent",
            regex=r"\bparental\s+consent\s+(on\s+file|provided|obtained)\b",
            score=0.95,
        ),
        Pattern(
            name="minor_client",
            regex=r"\bminor\s+(client|patient|child)\b",
            score=0.92,
        ),
        Pattern(
            name="court_appointed_guardian",
            regex=r"\bcourt[\s-]appointed\s+guardian\b",
            score=0.95,
        ),
        Pattern(
            name="age_under_18",
            regex=r"\b(age|aged?)\s+(\d|1[0-7])\s+(years?|y\.?o\.?)\b",
            score=0.85,
        ),
        Pattern(
            name="custodial_parent",
            regex=r"\bcustodial\s+parent\b",
            score=0.88,
        ),
    ]

    CONTEXT_WORDS = ["minor", "child", "guardian", "parent", "consent", "custody"]

    def __init__(self):
        super().__init__(
            supported_entity="MINOR_CLIENT_MARKER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class TraumaIndicatorRecognizer(PatternRecognizer):
    """Detects trauma-related clinical indicators (advisory, do-not-redact).

    Per OGE-355: "flagged for *higher* protection, not redaction". The
    routing layer should use the presence of trauma indicators to pin
    sessions on-device — but the redaction layer must NOT strip them,
    because trauma context is clinically essential and removing it
    misrepresents the patient's record.

    Profile authors should keep ``TRAUMA_INDICATOR`` *out* of the
    ``redact_categories`` list when calling :py:meth:`Shield.redact`.
    """

    PATTERNS = [
        Pattern(
            name="ptsd_indicator",
            regex=r"\b(PTSD|C[\s-]PTSD|complex\s+(PTSD|trauma))\b",
            score=0.93,
        ),
        Pattern(
            name="trauma_history",
            regex=r"\btrauma\s+(history|hx\.?)\b",
            score=0.92,
        ),
        Pattern(
            name="abuse_history",
            regex=r"\b(history\s+of\s+abuse|hx\.?\s+abuse)\b",
            score=0.95,
        ),
        Pattern(
            name="sexual_abuse",
            regex=r"\b(sexual|childhood\s+sexual)\s+abuse\b",
            score=0.95,
        ),
        Pattern(
            name="physical_abuse",
            regex=r"\bphysical\s+abuse\b",
            score=0.93,
        ),
        Pattern(
            name="emotional_abuse",
            regex=r"\bemotional\s+abuse\b",
            score=0.90,
        ),
        Pattern(
            name="aces",
            regex=r"\b(ACEs?|adverse\s+childhood\s+experiences?)\b",
            score=0.90,
        ),
        Pattern(
            name="domestic_violence",
            regex=r"\b(domestic\s+violence|intimate\s+partner\s+violence|IPV)\b",
            score=0.92,
        ),
        Pattern(
            name="trauma_exposure",
            regex=r"\btrauma\s+exposure\b",
            score=0.88,
        ),
    ]

    CONTEXT_WORDS = [
        "trauma",
        "abuse",
        "history",
        "violence",
        "PTSD",
        "exposure",
        "survivor",
    ]

    def __init__(self):
        super().__init__(
            supported_entity="TRAUMA_INDICATOR",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )
