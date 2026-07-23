"""Legal domain recognizers for attorney-client privilege, work product, and litigation."""

from presidio_analyzer import Pattern, PatternRecognizer


class CounselCommunicationRecognizer(PatternRecognizer):
    """Detects references to communications with legal counsel."""

    PATTERNS = [
        Pattern(
            name="outside_counsel",
            regex=r"\b(outside|external)\s+counsel\b",
            score=0.93,
        ),
        Pattern(
            name="legal_counsel",
            regex=r"\blegal\s+counsel\b",
            score=0.93,
        ),
        Pattern(
            name="in_house_counsel",
            regex=r"\bin[\s-]house\s+counsel\b",
            score=0.93,
        ),
        Pattern(
            name="attorney_client",
            regex=r"\battorney[\s-]client\b",
            score=0.95,
        ),
    ]

    CONTEXT_WORDS = ["privileged", "confidential", "advice", "legal"]

    def __init__(self):
        super().__init__(
            supported_entity="COUNSEL_COMMUNICATION",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class PrivilegeMarkerRecognizer(PatternRecognizer):
    """Detects attorney-client privilege markers and confidentiality assertions."""

    PATTERNS = [
        Pattern(
            name="privileged_and_confidential",
            regex=r"\bprivileged\s+and\s+confidential\b",
            score=0.97,
        ),
        Pattern(
            name="attorney_client_privilege",
            regex=r"\battorney[\s-]client\s+privilege[d]?\b",
            score=0.97,
        ),
        Pattern(
            name="subject_to_privilege",
            regex=r"\bsubject\s+to\s+(attorney[\s-]client\s+)?privilege\b",
            score=0.95,
        ),
        Pattern(
            name="protected_by_privilege",
            regex=r"\bprotected\s+by\s+(the\s+)?(attorney[\s-]client\s+)?privilege\b",
            score=0.95,
        ),
        Pattern(
            name="privileged_communication",
            regex=r"\bprivileged\s+communication\b",
            score=0.95,
        ),
    ]

    CONTEXT_WORDS = ["counsel", "attorney", "confidential", "legal", "waive"]

    def __init__(self):
        super().__init__(
            supported_entity="PRIVILEGE_MARKER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class WorkProductRecognizer(PatternRecognizer):
    """Detects work product doctrine markers."""

    PATTERNS = [
        Pattern(
            name="attorney_work_product",
            regex=r"\battorney\s+work\s+product\b",
            score=0.95,
        ),
        Pattern(
            name="work_product_doctrine",
            regex=r"\bwork[\s-]product\s+doctrine\b",
            score=0.95,
        ),
        Pattern(
            name="direction_of_counsel",
            regex=r"\bat\s+the\s+direction\s+of\s+counsel\b",
            score=0.93,
        ),
        Pattern(
            name="anticipation_of_litigation",
            regex=r"\bprepared\s+in\s+anticipation\s+of\s+litigation\b",
            score=0.95,
        ),
        Pattern(
            name="litigation_preparation",
            regex=r"\b(prepared|drafted)\s+for\s+(purpose\s+of\s+)?litigation\b",
            score=0.90,
        ),
    ]

    CONTEXT_WORDS = ["privilege", "attorney", "counsel", "litigation", "trial"]

    def __init__(self):
        super().__init__(
            supported_entity="WORK_PRODUCT",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class SettlementTermsRecognizer(PatternRecognizer):
    """Detects settlement amounts and terms."""

    PATTERNS = [
        Pattern(
            name="settle_for_amount",
            regex=r"\bsettl(e|ed|ement)\s+(for\s+)?\$[\d,]+(\.\d+)?\s*(M|million|B|billion|K|thousand)?\b",
            score=0.92,
        ),
        Pattern(
            name="settlement_amount",
            regex=r"\bsettlement\s+(amount|sum|value|payment)\b",
            score=0.88,
        ),
        Pattern(
            name="settlement_agreement",
            regex=r"\bsettlement\s+agreement\b",
            score=0.85,
        ),
        Pattern(
            name="settlement_terms",
            regex=r"\bsettlement\s+terms?\b",
            score=0.85,
        ),
    ]

    CONTEXT_WORDS = ["confidential", "agreement", "parties", "damages", "liability"]

    def __init__(self):
        super().__init__(
            supported_entity="SETTLEMENT_TERMS",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class CaseNumberRecognizer(PatternRecognizer):
    """Detects court case numbers and docket references."""

    PATTERNS = [
        Pattern(
            name="federal_criminal",
            regex=r"\b\d{2}-cr-\d{3,6}\b",
            score=0.99,
        ),
        Pattern(
            name="federal_civil",
            regex=r"\b\d{2}-cv-\d{3,6}\b",
            score=0.99,
        ),
        Pattern(
            name="case_no_prefix",
            regex=r"\b[Cc]ase\s+[Nn]o\.?\s*\d{2,4}[\s-]\w+-\d{3,6}\b",
            score=0.95,
        ),
        Pattern(
            name="docket_number",
            regex=r"\b[Dd]ocket\s+[Nn]o\.?\s*\d[\w-]+\b",
            score=0.92,
        ),
    ]

    CONTEXT_WORDS = ["court", "filed", "case", "docket", "matter"]

    def __init__(self):
        super().__init__(
            supported_entity="CASE_NUMBER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class LawFirmNameRecognizer(PatternRecognizer):
    """Detects names of major law firms (AmLaw 200)."""

    PATTERNS = [
        Pattern(
            name="amlaw_firms",
            regex=(
                r"\b("
                r"Davis\s+Polk|Kirkland\s+&?\s*Ellis|Skadden|Wachtell|Sullivan\s+&?\s*Cromwell|"
                r"Cravath|Latham\s+&?\s*Watkins|Simpson\s+Thacher|Cleary\s+Gottlieb|"
                r"Paul[\s,]+Weiss|Gibson\s+Dunn|Debevoise|Milbank|White\s+&?\s*Case|"
                r"Sidley\s+Austin|Willkie\s+Farr|Morrison\s+&?\s*Foerster|Jones\s+Day|"
                r"Covington\s+&?\s*Burling|Quinn\s+Emanuel|Baker\s+McKenzie|"
                r"Hogan\s+Lovells|Freshfields|Allen\s+&?\s*Overy|Clifford\s+Chance|"
                r"Linklaters|DLA\s+Piper|Norton\s+Rose|King\s+&?\s*Spalding|"
                r"Goodwin\s+Procter|Ropes\s+&?\s*Gray|Akin\s+Gump|WilmerHale|"
                r"Mayer\s+Brown|O'Melveny|Proskauer|Weil\s+Gotshal|Dechert|"
                r"Shearman\s+&?\s*Sterling|Morgan\s+Lewis|Orrick|Pillsbury|"
                r"Arnold\s+&?\s*Porter|Cadwalader|Fried\s+Frank|Katten"
                r")\b"
            ),
            score=0.97,
        ),
    ]

    CONTEXT_WORDS = ["counsel", "attorney", "represent", "firm", "partner"]

    def __init__(self):
        super().__init__(
            supported_entity="LAW_FIRM_NAME",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class LitigationMarkerRecognizer(PatternRecognizer):
    """Detects litigation hold, legal hold, and preservation notices."""

    PATTERNS = [
        Pattern(
            name="litigation_hold",
            regex=r"\blitigation\s+hold\b",
            score=0.95,
        ),
        Pattern(
            name="legal_hold",
            regex=r"\blegal\s+hold\b",
            score=0.95,
        ),
        Pattern(
            name="preservation_notice",
            regex=r"\bpreservation\s+(notice|order|obligation)\b",
            score=0.93,
        ),
        Pattern(
            name="document_preservation",
            regex=r"\bdocument\s+preservation\b",
            score=0.90,
        ),
    ]

    CONTEXT_WORDS = ["litigation", "preserve", "retain", "destroy", "evidence"]

    def __init__(self):
        super().__init__(
            supported_entity="LITIGATION_MARKER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class CourtFilingRecognizer(PatternRecognizer):
    """Detects court filing references and legal pleadings."""

    PATTERNS = [
        Pattern(
            name="motion_to",
            regex=r"\bmotion\s+to\s+(dismiss|compel|suppress|strike|quash)\b",
            score=0.91,
        ),
        Pattern(
            name="summary_judgment",
            regex=r"\bsummary\s+judgment\b",
            score=0.91,
        ),
        Pattern(
            name="complaint",
            regex=r"\b(amended\s+)?complaint\b",
            score=0.70,
        ),
        Pattern(
            name="filing_terms",
            regex=r"\b(subpoena|deposition|interrogator(y|ies)|discovery\s+request)\b",
            score=0.88,
        ),
    ]

    CONTEXT_WORDS = ["court", "filed", "judge", "plaintiff", "defendant"]

    def __init__(self):
        super().__init__(
            supported_entity="COURT_FILING",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class BatesNumberRecognizer(PatternRecognizer):
    """Detects Bates numbers and document production stamps."""

    PATTERNS = [
        Pattern(
            name="bates_prefix",
            regex=r"\bBATES\s+\d{4,8}\b",
            score=0.99,
        ),
        Pattern(
            name="doc_stamp",
            regex=r"\bDOC-\d{4}-\d{3,6}\b",
            score=0.97,
        ),
        Pattern(
            name="bates_range",
            regex=r"\b[A-Z]{2,6}[-_]?\d{4,8}\s*(through|to|-)\s*[A-Z]{2,6}[-_]?\d{4,8}\b",
            score=0.95,
        ),
        Pattern(
            name="exhibit_number",
            regex=r"\b[Ee]xhibit\s+[A-Z0-9]{1,4}\b",
            score=0.80,
        ),
    ]

    CONTEXT_WORDS = ["production", "document", "exhibit", "discovery", "review"]

    def __init__(self):
        super().__init__(
            supported_entity="BATES_NUMBER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class ExecutiveNameRecognizer(PatternRecognizer):
    """Detects executive titles paired with names."""

    PATTERNS = [
        Pattern(
            name="c_suite_title",
            regex=r"\b(CEO|CFO|COO|CTO|CIO|CISO|CLO|CMO|CPO)\s+(?-i:[A-Z][a-z]+)\b",
            score=0.90,
        ),
        Pattern(
            name="general_counsel_name",
            regex=r"\b[Gg]eneral\s+[Cc]ounsel\s+(?-i:[A-Z][a-z]+(\s+[A-Z][a-z]+)?)\b",
            score=0.92,
        ),
        Pattern(
            name="managing_partner",
            regex=r"\b[Mm]anaging\s+[Pp]artner\s+(?-i:[A-Z][a-z]+(\s+[A-Z][a-z]+)?)\b",
            score=0.90,
        ),
        Pattern(
            name="executive_titles",
            regex=(
                r"\b(Chairman|President|Vice\s+President|Director|Secretary|Treasurer)"
                r"\s+(?-i:[A-Z][a-z]+(\s+[A-Z][a-z]+)?)\b"
            ),
            score=0.80,
        ),
    ]

    CONTEXT_WORDS = ["officer", "executive", "board", "management", "company"]

    def __init__(self):
        super().__init__(
            supported_entity="EXECUTIVE_NAME",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )
