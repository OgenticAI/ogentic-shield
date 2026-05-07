"""GDPR custom recognizer example (OGE-322).

A worked example showing how to build EU-specific PII recognizers that
``ogentic-shield`` doesn't ship by default. Three recognizers covering:

- :class:`UkNinoRecognizer` — UK National Insurance Number (HMRC format).
- :class:`DeSteuerIdRecognizer` — German Steuer-Identifikationsnummer
  (11-digit personal Tax ID).
- :class:`EuVatNumberRecognizer` — EU VAT registration numbers across the
  most common member-state formats.

Run with the test harness:

    ogentic-shield test-recognizer examples/gdpr_recognizer.py

To plug these into a Shield instance for real analysis, build a profile
that registers them and pass that profile to ``Shield``. See
``src/ogentic_shield/profiles/legal.py`` for the canonical pattern.
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class UkNinoRecognizer(PatternRecognizer):
    """Detects UK National Insurance Numbers.

    Format: two prefix letters, six digits, one suffix letter. Certain
    prefix combinations are reserved by HMRC and never issued — we don't
    encode that here because the prefix-validity table changes over time
    and a downstream Layer-2 rule is a better place for it.
    """

    PATTERNS = [
        Pattern(
            name="nino_labelled",
            regex=r"\b(NI(?:NO)?|National\s+Insurance(\s+(No|Number))?)\s*:?\s*[A-CEGHJ-PR-TW-Z]{2}\s?\d{6}\s?[A-D]\b",
            score=0.95,
        ),
        Pattern(
            name="nino_bare",
            regex=r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{6}\s?[A-D]\b",
            score=0.78,
        ),
    ]

    CONTEXT_WORDS = ["NI", "NINO", "national insurance", "HMRC", "tax"]

    def __init__(self) -> None:
        super().__init__(
            supported_entity="UK_NINO",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class DeSteuerIdRecognizer(PatternRecognizer):
    """Detects German Steuer-Identifikationsnummer (Tax ID).

    Eleven digits, conventionally formatted in 2-3-3-3 groups separated
    by spaces but also issued as a single block. The 11th digit is a
    checksum we don't validate here — pattern alone gives ~0.85 with
    context boosts handling the rest.
    """

    PATTERNS = [
        Pattern(
            name="steuer_id_labelled",
            regex=r"\b(Steuer[\s-]?ID|Steueridentifikationsnummer|Tax\s+ID)\s*:?\s*\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b",
            score=0.95,
        ),
        Pattern(
            name="steuer_id_grouped",
            regex=r"\b\d{2}\s\d{3}\s\d{3}\s\d{3}\b",
            score=0.80,
        ),
    ]

    CONTEXT_WORDS = ["Steuer", "Finanzamt", "Tax", "Bundeszentralamt"]

    def __init__(self) -> None:
        super().__init__(
            supported_entity="DE_STEUER_ID",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class EuVatNumberRecognizer(PatternRecognizer):
    """Detects EU VAT registration numbers across the major member states.

    EU VAT numbers are a country-prefix (2 letters) followed by 8-12
    alphanumeric chars; the per-country format varies. We cover the
    largest registries (DE, FR, IT, ES, NL, PL, IE) plus the generic
    "EU + 9 digits" fallback for non-resident registrations.
    """

    PATTERNS = [
        Pattern(
            name="vat_labelled",
            regex=r"\b(VAT(\s+(No|Number|ID|Reg))?|USt[\s-]?ID|TVA|BTW)\s*:?\s*(DE\d{9}|FR[A-HJ-NP-Z0-9]{2}\d{9}|IT\d{11}|ES[A-Z0-9]\d{7}[A-Z0-9]|NL\d{9}B\d{2}|PL\d{10}|IE\d[A-Z0-9]\d{5}[A-Z]|EU\d{9})\b",
            score=0.97,
        ),
        Pattern(
            name="vat_bare_de",
            regex=r"\bDE\d{9}\b",
            score=0.85,
        ),
        Pattern(
            name="vat_bare_fr",
            regex=r"\bFR[A-HJ-NP-Z0-9]{2}\d{9}\b",
            score=0.85,
        ),
        Pattern(
            name="vat_bare_it",
            regex=r"\bIT\d{11}\b",
            score=0.85,
        ),
        Pattern(
            name="vat_bare_nl",
            regex=r"\bNL\d{9}B\d{2}\b",
            score=0.90,
        ),
    ]

    CONTEXT_WORDS = ["VAT", "USt", "TVA", "BTW", "invoice", "registration", "EU"]

    def __init__(self) -> None:
        super().__init__(
            supported_entity="EU_VAT_NUMBER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


SAMPLE_TEXTS: list[str] = [
    # UK NINO — labelled and bare forms.
    "Employee NINO: AB123456C on file with HMRC.",
    "Customer ref AB 123456 C verified.",
    # German Steuer-ID.
    "Steuer-ID: 12 345 678 901 confirmed by Finanzamt.",
    # EU VAT — multiple formats.
    "Invoice issued to VAT DE123456789 dated 2026-04-01.",
    "Vendor's VAT registration: NL123456789B01 — please retain for filing.",
    # Negative cases — should NOT match.
    "Schedule call with finance Tuesday at 10am.",
    "Conference badge ID 47291 — please print before lunch.",
]
