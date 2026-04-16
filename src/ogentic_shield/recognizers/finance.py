"""Finance domain recognizers for MNPI, deal terms, and fund-sensitive information."""

from presidio_analyzer import Pattern, PatternRecognizer


class MnpiMarkerRecognizer(PatternRecognizer):
    """Detects material non-public information markers."""

    PATTERNS = [
        Pattern(
            name="mnpi_explicit",
            regex=r"\bMNPI\b",
            score=0.97,
        ),
        Pattern(
            name="material_nonpublic",
            regex=r"\b[Mm]aterial\s+[Nn]on[\s-]?[Pp]ublic(\s+[Ii]nformation)?\b",
            score=0.97,
        ),
        Pattern(
            name="confidential_marker",
            regex=r"\bCONFIDENTIAL\b",
            score=0.80,
        ),
        Pattern(
            name="strictly_confidential",
            regex=r"\bstrictly\s+confidential\b",
            score=0.90,
        ),
    ]

    CONTEXT_WORDS = ["trading", "restricted", "insider", "material", "disclosure"]

    def __init__(self):
        super().__init__(
            supported_entity="MNPI_MARKER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class MaActivityRecognizer(PatternRecognizer):
    """Detects merger and acquisition activity references."""

    PATTERNS = [
        Pattern(
            name="acquiring",
            regex=r"\b(acquiring|acquisition\s+of|to\s+acquire)\b",
            score=0.88,
        ),
        Pattern(
            name="merger",
            regex=r"\bmerger\s+(with|between|of|agreement)\b",
            score=0.90,
        ),
        Pattern(
            name="takeover",
            regex=r"\b(takeover|take[\s-]over)\s*(bid|offer|target|attempt)?\b",
            score=0.90,
        ),
        Pattern(
            name="tender_offer",
            regex=r"\btender\s+offer\b",
            score=0.92,
        ),
        Pattern(
            name="going_private",
            regex=r"\bgoing[\s-]private\s+(transaction|deal)?\b",
            score=0.90,
        ),
    ]

    CONTEXT_WORDS = ["deal", "transaction", "target", "buyer", "seller", "shareholder"]

    def __init__(self):
        super().__init__(
            supported_entity="MA_ACTIVITY",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class DealValueRecognizer(PatternRecognizer):
    """Detects deal values, price per share, and financial commitments."""

    PATTERNS = [
        Pattern(
            name="per_share",
            regex=r"\$\d+(\.\d{1,2})?\s*/?\s*share\b",
            score=0.93,
        ),
        Pattern(
            name="dollar_billion",
            regex=r"\$\d+(\.\d{1,2})?\s*(billion|B)\b",
            score=0.92,
        ),
        Pattern(
            name="dollar_million",
            regex=r"\$\d+(\.\d{1,2})?\s*(million|M)\b",
            score=0.90,
        ),
        Pattern(
            name="commitment_amount",
            regex=r"\$[\d,]+(\.\d{1,2})?\s*(commitment|investment|allocation)\b",
            score=0.88,
        ),
        Pattern(
            name="valuation",
            regex=r"\b(valuation|enterprise\s+value)\s+(of\s+)?\$[\d,.]+\s*(B|M|billion|million)?\b",
            score=0.90,
        ),
    ]

    CONTEXT_WORDS = ["deal", "price", "offer", "bid", "valuation", "commitment"]

    def __init__(self):
        super().__init__(
            supported_entity="DEAL_VALUE",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class LeverageRatioRecognizer(PatternRecognizer):
    """Detects leverage ratios and financial multiples."""

    PATTERNS = [
        Pattern(
            name="ebitda_multiple",
            regex=r"\b\d+(\.\d)?x\s*(EBITDA|ebitda|Ebitda)\b",
            score=0.93,
        ),
        Pattern(
            name="revenue_multiple",
            regex=r"\b\d+(\.\d)?x\s*(revenue|Revenue|sales)\b",
            score=0.90,
        ),
        Pattern(
            name="leverage_ratio",
            regex=r"\b(leverage|debt)\s+ratio\s+(of\s+)?\d+(\.\d)?x\b",
            score=0.92,
        ),
        Pattern(
            name="turns_of_leverage",
            regex=r"\b\d+(\.\d)?\s+turns?\s+of\s+(leverage|debt)\b",
            score=0.90,
        ),
    ]

    CONTEXT_WORDS = ["leverage", "debt", "EBITDA", "multiple", "financing"]

    def __init__(self):
        super().__init__(
            supported_entity="LEVERAGE_RATIO",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class FundInformationRecognizer(PatternRecognizer):
    """Detects fund names, LP allocations, and co-investment references."""

    PATTERNS = [
        Pattern(
            name="fund_number",
            regex=r"\b[Ff]und\s+(I{1,3}V?|IV|V|VI{0,3}|[1-9]\d?)\b",
            score=0.88,
        ),
        Pattern(
            name="lp_allocation",
            regex=r"\bLP\s+(allocation|commitment|interest)\b",
            score=0.90,
        ),
        Pattern(
            name="co_invest",
            regex=r"\bco[\s-]invest(ment)?\b",
            score=0.85,
        ),
        Pattern(
            name="limited_partner",
            regex=r"\b[Ll]imited\s+[Pp]artner(ship|s)?\b",
            score=0.82,
        ),
        Pattern(
            name="general_partner",
            regex=r"\b[Gg]eneral\s+[Pp]artner(ship)?\b",
            score=0.82,
        ),
    ]

    CONTEXT_WORDS = ["fund", "LP", "GP", "allocation", "vintage", "commitment"]

    def __init__(self):
        super().__init__(
            supported_entity="FUND_INFORMATION",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class InstitutionNameRecognizer(PatternRecognizer):
    """Detects names of major financial institutions (banks, PE firms)."""

    PATTERNS = [
        Pattern(
            name="major_banks_pe",
            regex=(
                r"\b("
                r"Goldman\s+Sachs|Morgan\s+Stanley|JPMorgan|J\.?P\.?\s*Morgan|"
                r"Blackstone|KKR|Apollo|Carlyle|Warburg\s+Pincus|"
                r"Bain\s+Capital|TPG|Advent|Silver\s+Lake|Thoma\s+Bravo|"
                r"Vista\s+Equity|Ares\s+Management|Cerberus|"
                r"Lazard|Evercore|Moelis|Centerview|PJT\s+Partners|"
                r"Blackrock|BlackRock|Vanguard|Fidelity|State\s+Street|"
                r"Citadel|Bridgewater|Two\s+Sigma|DE\s+Shaw|Point72|"
                r"Bank\s+of\s+America|Citigroup|Citi|Wells\s+Fargo|"
                r"Deutsche\s+Bank|Barclays|Credit\s+Suisse|UBS|HSBC|"
                r"BNP\s+Paribas|Societe\s+Generale|Nomura|"
                r"Macquarie|Jefferies|Raymond\s+James|"
                r"Brookfield|GIC|Temasek|CPPIB|"
                r"Permira|CVC|EQT|Hellman\s+&?\s*Friedman|"
                r"Leonard\s+Green|Genstar|Insight\s+Partners|"
                r"General\s+Atlantic|Tiger\s+Global"
                r")\b"
            ),
            score=0.92,
        ),
    ]

    CONTEXT_WORDS = ["bank", "advisor", "underwriter", "fund", "portfolio", "capital"]

    def __init__(self):
        super().__init__(
            supported_entity="INSTITUTION_NAME",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class FinancialTermsRecognizer(PatternRecognizer):
    """Detects financial covenants, term sheets, and deal structure terms."""

    PATTERNS = [
        Pattern(
            name="covenant",
            regex=r"\b(financial\s+)?covenant[s]?\b",
            score=0.82,
        ),
        Pattern(
            name="dscr",
            regex=r"\bDSCR\b",
            score=0.90,
        ),
        Pattern(
            name="term_sheet",
            regex=r"\bterm\s+sheet\b",
            score=0.88,
        ),
        Pattern(
            name="waterfall",
            regex=r"\b(distribution\s+)?waterfall\b",
            score=0.82,
        ),
        Pattern(
            name="credit_agreement",
            regex=r"\bcredit\s+(agreement|facility)\b",
            score=0.85,
        ),
    ]

    CONTEXT_WORDS = ["financing", "debt", "terms", "structure", "agreement"]

    def __init__(self):
        super().__init__(
            supported_entity="FINANCIAL_TERMS",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class DistributionRestrictionRecognizer(PatternRecognizer):
    """Detects distribution restriction markers."""

    PATTERNS = [
        Pattern(
            name="do_not_distribute",
            regex=r"\bdo\s+not\s+distribute\b",
            score=0.95,
        ),
        Pattern(
            name="internal_use_only",
            regex=r"\b(for\s+)?internal\s+use\s+only\b",
            score=0.90,
        ),
        Pattern(
            name="not_for_distribution",
            regex=r"\bnot\s+for\s+(public\s+)?distribution\b",
            score=0.93,
        ),
        Pattern(
            name="restricted_distribution",
            regex=r"\brestricted\s+distribution\b",
            score=0.90,
        ),
    ]

    CONTEXT_WORDS = ["confidential", "proprietary", "restricted", "internal"]

    def __init__(self):
        super().__init__(
            supported_entity="DISTRIBUTION_RESTRICTION",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class InsiderMarkerRecognizer(PatternRecognizer):
    """Detects insider trading markers and blackout period references."""

    PATTERNS = [
        Pattern(
            name="insider_explicit",
            regex=r"\binsider\s+(information|trading|list)\b",
            score=0.93,
        ),
        Pattern(
            name="non_public_info",
            regex=r"\bnon[\s-]?public\s+information\b",
            score=0.90,
        ),
        Pattern(
            name="blackout_period",
            regex=r"\bblackout\s+period\b",
            score=0.93,
        ),
        Pattern(
            name="restricted_list",
            regex=r"\brestricted\s+(list|securities)\b",
            score=0.88,
        ),
        Pattern(
            name="trading_window",
            regex=r"\btrading\s+(window|restriction|ban)\b",
            score=0.88,
        ),
    ]

    CONTEXT_WORDS = ["insider", "trading", "restricted", "compliance", "blackout"]

    def __init__(self):
        super().__init__(
            supported_entity="INSIDER_MARKER",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


class CarryTermsRecognizer(PatternRecognizer):
    """Detects carried interest terms and hurdle rate references."""

    PATTERNS = [
        Pattern(
            name="carry_percentage",
            regex=r"\b\d{1,2}%\s*carry\b",
            score=0.93,
        ),
        Pattern(
            name="carried_interest",
            regex=r"\bcarried\s+interest\b",
            score=0.90,
        ),
        Pattern(
            name="reduced_carry",
            regex=r"\breduced\s+carry\b",
            score=0.90,
        ),
        Pattern(
            name="hurdle_rate",
            regex=r"\bhurdle\s+rate\b",
            score=0.88,
        ),
        Pattern(
            name="preferred_return",
            regex=r"\bpreferred\s+return\b",
            score=0.85,
        ),
        Pattern(
            name="catch_up",
            regex=r"\bcatch[\s-]up\s+(provision|clause|period)\b",
            score=0.85,
        ),
    ]

    CONTEXT_WORDS = ["carry", "interest", "GP", "hurdle", "fund", "economics"]

    def __init__(self):
        super().__init__(
            supported_entity="CARRY_TERMS",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )
