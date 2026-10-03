"""Government domain recognizers for FOIA, Privacy Act, and federal records review.

These detect the things a records officer withholds on, or must notice before
processing: classification and CUI markings, confidential sources, investigative
techniques, deliberative material, and the citations that justify a withholding.

Personal identifiers — names, addresses, SSNs, phone numbers — are already
covered by the base recognizers and by `SsnRecognizer`, so nothing here repeats
them.
"""

from presidio_analyzer import Pattern, PatternRecognizer


class ClassificationMarkingRecognizer(PatternRecognizer):
    """Detects national-security classification banners and portion markings.

    This is a stop sign, not a redaction: a workstation that is not accredited
    for classified material should notice the marking and refuse the document.
    """

    # Every pattern here is wrapped in `(?-i: )`. Presidio compiles recognizer
    # patterns case-insensitively, and without this the word "secret" in ordinary
    # prose, and an outline item "(c)", are both read as classification markings —
    # a benign paragraph scored 69/HIGH before this was pinned down.
    PATTERNS = [
        Pattern(
            name="banner_top_secret",
            regex=r"(?-i:\bTOP\s+SECRET\b(\s*//\s*[A-Z/\-]+)?)",
            score=0.97,
        ),
        # Bare SECRET only counts as a banner when it carries a compartment.
        # "SECRET" alone, even upper case, is a word people write.
        Pattern(
            name="banner_secret_compartment",
            regex=r"(?-i:(?<![A-Za-z])SECRET\s*//\s*[A-Z/\-]+)",
            score=0.95,
        ),
        Pattern(
            name="banner_confidential_classified",
            regex=r"(?-i:\bCONFIDENTIAL\s*//\s*[A-Z/\-]+)",
            score=0.93,
        ),
        # Portion markings, but only the unambiguous ones: (TS), or a marking
        # that carries a compartment. Bare "(S)", "(C)" and "(U)" are dropped —
        # they are indistinguishable from outline lettering, and a genuinely
        # classified document will carry a banner or a "Classified By" line too.
        Pattern(
            name="portion_marking",
            regex=r"(?-i:\((TS|S|C|U)//[A-Z/\-]+\)|\(TS\))",
            score=0.90,
        ),
        Pattern(
            name="classified_by_line",
            regex=r"\b(Classified\s+By|Declassify\s+On|Derived\s+From)\s*:",
            score=0.95,
        ),
    ]

    CONTEXT_WORDS = ["classified", "classification", "declassify", "noforn", "sci"]

    def __init__(self):
        super().__init__(
            supported_entity="CLASSIFICATION_MARKING",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class CuiMarkingRecognizer(PatternRecognizer):
    """Detects Controlled Unclassified Information markings (32 CFR Part 2002).

    A CUI banner has to survive onto every export derived from the document, so
    it is worth detecting even though it is never itself withheld.
    """

    PATTERNS = [
        Pattern(
            name="cui_banner",
            regex=r"(?-i:\bCUI\b(\s*//\s*[A-Z/\-]+)?)",
            score=0.90,
        ),
        Pattern(
            name="cui_spelled",
            regex=r"\bCONTROLLED\s+UNCLASSIFIED\s+INFORMATION\b",
            score=0.95,
        ),
        Pattern(
            name="legacy_fouo",
            regex=r"(?-i:\b(FOUO|FOR\s+OFFICIAL\s+USE\s+ONLY)\b)",
            score=0.90,
        ),
        Pattern(
            name="law_enforcement_sensitive",
            regex=r"\bLAW\s+ENFORCEMENT\s+SENSITIVE\b",
            score=0.92,
        ),
    ]

    CONTEXT_WORDS = ["controlled", "dissemination", "handling", "safeguard"]

    def __init__(self):
        super().__init__(
            supported_entity="CUI_MARKING",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class ConfidentialSourceRecognizer(PatternRecognizer):
    """Detects references to a confidential source or informant — FOIA (b)(7)(D)."""

    PATTERNS = [
        Pattern(
            name="confidential_source",
            regex=r"\bconfidential\s+(source|informant|witness)\b",
            score=0.95,
        ),
        Pattern(
            name="informant_abbrev",
            regex=r"\b(CI|CHS)\s*#?\s*\d{2,6}\b",
            score=0.93,
        ),
        Pattern(
            name="source_identity",
            regex=r"\bsource(?:'s|s')?\s+identity\b",
            score=0.92,
        ),
        Pattern(
            name="cooperating_witness",
            regex=r"\bcooperating\s+(witness|defendant|individual)\b",
            score=0.92,
        ),
        Pattern(
            name="under_express_assurance",
            regex=r"\bexpress(ed)?\s+assurance\s+of\s+confidentiality\b",
            score=0.96,
        ),
    ]

    CONTEXT_WORDS = ["identity", "disclose", "protect", "anonymity", "informant"]

    def __init__(self):
        super().__init__(
            supported_entity="CONFIDENTIAL_SOURCE",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class InvestigativeTechniqueRecognizer(PatternRecognizer):
    """Detects law-enforcement techniques and procedures — FOIA (b)(7)(E)."""

    PATTERNS = [
        Pattern(
            name="investigative_technique",
            regex=r"\binvestigative\s+(technique|procedure|method)s?\b",
            score=0.95,
        ),
        Pattern(
            name="surveillance_method",
            regex=r"\bsurveillance\s+(technique|method|plan|operation)s?\b",
            score=0.93,
        ),
        Pattern(
            name="undercover",
            regex=r"\bundercover\s+(operation|agent|capacity)\b",
            score=0.93,
        ),
        Pattern(
            name="pen_register",
            regex=r"\b(pen\s+register|trap\s+and\s+trace|title\s+III\s+intercept)\b",
            score=0.94,
        ),
        Pattern(
            name="confidential_methods",
            regex=r"\b(tradecraft|source\s+handling\s+procedures)\b",
            score=0.90,
        ),
    ]

    CONTEXT_WORDS = ["investigation", "circumvent", "law enforcement", "operation"]

    def __init__(self):
        super().__init__(
            supported_entity="INVESTIGATIVE_TECHNIQUE",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class DeliberativeMarkerRecognizer(PatternRecognizer):
    """Detects pre-decisional, deliberative material — FOIA (b)(5)."""

    PATTERNS = [
        Pattern(
            name="pre_decisional",
            regex=r"\bpre[\s-]?decisional\b",
            score=0.95,
        ),
        Pattern(
            name="deliberative",
            regex=r"\bdeliberative(\s+process)?\b",
            score=0.93,
        ),
        Pattern(
            name="draft_not_for_release",
            regex=r"\bdraft\s*[—\-–:]\s*(not\s+for\s+(release|distribution)|internal\s+use)\b",
            score=0.94,
        ),
        Pattern(
            name="recommendation_to",
            regex=r"\brecommendation\s+to\s+the\s+(Secretary|Administrator|Director|Attorney\s+General)\b",
            score=0.90,
        ),
    ]

    CONTEXT_WORDS = ["decision", "internal", "draft", "policy", "recommend"]

    def __init__(self):
        super().__init__(
            supported_entity="DELIBERATIVE_MARKER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class LawEnforcementRecordRecognizer(PatternRecognizer):
    """Detects that a record was compiled for law enforcement purposes.

    FOIA (b)(7) only applies to such records, so this marker is what makes a
    (b)(7)(C) or (b)(7)(D) proposal defensible rather than a guess.
    """

    PATTERNS = [
        Pattern(
            name="compiled_for_law_enforcement",
            regex=r"\bcompiled\s+for\s+law\s+enforcement\s+purposes\b",
            score=0.97,
        ),
        Pattern(
            name="special_agent",
            regex=r"\b(Special\s+Agent|Case\s+Agent|Task\s+Force\s+Officer)\b",
            score=0.90,
        ),
        Pattern(
            name="investigation_number",
            regex=r"\b(case|investigation)\s+(file\s+)?(no\.?|number|#)\s*[\w\-/]+\b",
            score=0.88,
        ),
        Pattern(
            name="grand_jury",
            regex=r"\bgrand\s+jury\b",
            score=0.92,
        ),
    ]

    CONTEXT_WORDS = ["investigation", "enforcement", "criminal", "subject"]

    def __init__(self):
        super().__init__(
            supported_entity="LAW_ENFORCEMENT_MARKER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class FoiaRequestNumberRecognizer(PatternRecognizer):
    """Detects an agency FOIA tracking number.

    Not sensitive — it is the request's own identifier — but recognising it lets
    a reviewer tie a document to its request, and lets a tool avoid proposing it
    as a withholding.
    """

    PATTERNS = [
        Pattern(
            name="foia_tracking",
            regex=r"\b(19|20)\d{2}[\s\-]?FOIA[\s\-]?\d{3,6}\b",
            score=0.95,
        ),
        Pattern(
            name="foia_request_no",
            regex=r"\bFOIA\s+(request\s+)?(no\.?|number|#)\s*[\w\-/]+\b",
            score=0.93,
        ),
        Pattern(
            name="privacy_act_request",
            regex=r"\bPrivacy\s+Act\s+request\s+(no\.?|number|#)\s*[\w\-/]+\b",
            score=0.92,
        ),
    ]

    CONTEXT_WORDS = ["request", "requester", "tracking", "appeal"]

    def __init__(self):
        super().__init__(
            supported_entity="FOIA_REQUEST_NUMBER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class StatutoryExemptionRecognizer(PatternRecognizer):
    """Detects an exemption citation already asserted in the document — (b)(3) and friends."""

    PATTERNS = [
        Pattern(
            name="foia_exemption_citation",
            regex=r"\b5\s*U\.?S\.?C\.?\s*§?\s*552\s*\(b\)\s*\(\d\)(\s*\([A-F]\))?",
            score=0.97,
        ),
        Pattern(
            name="exempt_from_disclosure",
            regex=r"\bexempt\s+from\s+(mandatory\s+)?disclosure\b",
            score=0.92,
        ),
    ]

    CONTEXT_WORDS = ["exemption", "withhold", "release", "foia", "statute"]

    def __init__(self):
        super().__init__(
            supported_entity="STATUTORY_EXEMPTION",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class UsStreetAddressRecognizer(PatternRecognizer):
    """Detects a US street address: a house number, the street name and its suffix.

    Without it the NER layer tags a street name such as "Larkmead Terrace" as a
    PERSON and leaves the house number out, so a redaction box covers half an
    address. The span here includes the number, so it is longer than the NER
    span and wins the overlap.

    Street-name words must be capitalised; Presidio matches case-insensitively,
    so that is pinned with ``(?-i:...)``. That keeps "88 pages per Court order"
    and similar prose from matching.
    """

    _SUFFIX = (
        r"(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd|Court|Ct|"
        r"Terrace|Ter|Place|Pl|Way|Circle|Cir|Parkway|Pkwy|Highway|Hwy|Square|Sq|"
        r"Trail|Trl|Pike|Row|Alley|Loop|Crescent)\.?"
    )

    PATTERNS = [
        Pattern(
            name="us_street_address",
            regex=(
                r"\b\d{1,6}[A-Z]?\s+"
                r"(?:(?:N|S|E|W|NE|NW|SE|SW|North|South|East|West)\.?\s+)?"
                r"(?-i:(?:[A-Z][A-Za-z'\-]+\s+){1,3}" + _SUFFIX + r")"
                r"(?-i:\s+(?:N|S|E|W|NE|NW|SE|SW)\b\.?)?"
                r"(?:,?\s+(?:Apt|Apartment|Suite|Ste|Unit|#)\.?\s*[\w\-]+)?\b"
            ),
            score=0.90,
        ),
    ]

    CONTEXT_WORDS = ["address", "home", "residence", "lives", "resides", "mailing"]

    def __init__(self):
        super().__init__(
            supported_entity="ADDRESS",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )
