"""shield-finance profile: recognizers, rules, and scoring weights for MNPI detection."""

import re

from ogentic_shield.models import CategoryGroup, Rule, ShieldProfile
from ogentic_shield.recognizers.finance import (
    CarryTermsRecognizer,
    DealValueRecognizer,
    DistributionRestrictionRecognizer,
    FinancialTermsRecognizer,
    FundInformationRecognizer,
    InsiderMarkerRecognizer,
    InstitutionNameRecognizer,
    LeverageRatioRecognizer,
    MaActivityRecognizer,
    MnpiMarkerRecognizer,
)

PROFILE_ID = "shield-finance"
PROFILE_VERSION = "0.1.0"

RECOGNIZERS = [
    MnpiMarkerRecognizer(),
    MaActivityRecognizer(),
    DealValueRecognizer(),
    LeverageRatioRecognizer(),
    FundInformationRecognizer(),
    InstitutionNameRecognizer(),
    FinancialTermsRecognizer(),
    DistributionRestrictionRecognizer(),
    InsiderMarkerRecognizer(),
    CarryTermsRecognizer(),
]

RULES = [
    Rule(
        id="finance-mnpi-deal-context",
        name="MNPI Deal Context",
        description="Boost confidence when MNPI markers appear near deal terms",
        pattern=r"\b(MNPI|[Mm]aterial\s+[Nn]on[\s-]?[Pp]ublic)\b",
        flags=re.IGNORECASE,
        category="MNPI_MARKER",
        category_group=CategoryGroup.MNPI,
        confidence=0.97,
        context_patterns=["acquisition", "merger", "deal", "transaction"],
        context_window=300,
        context_confidence_boost=0.03,
    ),
    Rule(
        id="finance-insider-trading-boost",
        name="Insider Trading Context",
        description="Boost confidence for insider markers in trading context",
        pattern=r"\binsider\b",
        flags=re.IGNORECASE,
        category="INSIDER_MARKER",
        category_group=CategoryGroup.MNPI,
        confidence=0.93,
        context_patterns=["trading", "restricted", "blackout", "compliance"],
        context_window=200,
        context_confidence_boost=0.05,
    ),
    Rule(
        id="finance-deal-value-context",
        name="Deal Value Context Boost",
        description="Boost deal value confidence in M&A context",
        pattern=r"\$[\d,.]+\s*(M|B|million|billion)",
        flags=re.IGNORECASE,
        category="DEAL_VALUE",
        category_group=CategoryGroup.MNPI,
        confidence=0.92,
        context_patterns=["acquisition", "merger", "offer", "bid", "valuation"],
        context_window=300,
        context_confidence_boost=0.05,
    ),
    Rule(
        id="finance-restriction-boost",
        name="Distribution Restriction Boost",
        description="Boost restriction markers in financial context",
        pattern=r"\b(do\s+not\s+distribute|internal\s+use\s+only)\b",
        flags=re.IGNORECASE,
        category="DISTRIBUTION_RESTRICTION",
        category_group=CategoryGroup.CONFIDENTIAL,
        confidence=0.93,
        context_patterns=["confidential", "MNPI", "material", "restricted"],
        context_window=200,
        context_confidence_boost=0.05,
    ),
]

SCORING_WEIGHTS = {
    CategoryGroup.MNPI: 30,
    CategoryGroup.PII: 12,
    CategoryGroup.CONFIDENTIAL: 10,
}


def create_profile() -> ShieldProfile:
    return ShieldProfile(
        id=PROFILE_ID,
        name="Finance MNPI Protection",
        version=PROFILE_VERSION,
        description="Detects MNPI, deal terms, and fund-sensitive information.",
        recognizers=RECOGNIZERS,
        rules=RULES,
        scoring_weights=SCORING_WEIGHTS,
        supported_entities=[r.supported_entities[0] for r in RECOGNIZERS],
    )
