"""shield-legal profile: recognizers, rules, and scoring weights for legal privilege detection."""

import re

from ogentic_shield.models import CategoryGroup, Rule, ShieldProfile
from ogentic_shield.recognizers.legal import (
    BatesNumberRecognizer,
    CaseNumberRecognizer,
    CounselCommunicationRecognizer,
    CourtFilingRecognizer,
    ExecutiveNameRecognizer,
    LawFirmNameRecognizer,
    LitigationMarkerRecognizer,
    PrivilegeMarkerRecognizer,
    SettlementTermsRecognizer,
    WorkProductRecognizer,
)

PROFILE_ID = "shield-legal"
PROFILE_VERSION = "0.1.0"

RECOGNIZERS = [
    CounselCommunicationRecognizer(),
    PrivilegeMarkerRecognizer(),
    WorkProductRecognizer(),
    SettlementTermsRecognizer(),
    CaseNumberRecognizer(),
    LawFirmNameRecognizer(),
    LitigationMarkerRecognizer(),
    CourtFilingRecognizer(),
    BatesNumberRecognizer(),
    ExecutiveNameRecognizer(),
]

RULES = [
    Rule(
        id="legal-privilege-context-boost",
        name="Privilege Context Boost",
        description="Boost confidence when privilege markers co-occur with counsel references",
        pattern=r"\bprivileged?\b",
        flags=re.IGNORECASE,
        category="PRIVILEGE_MARKER",
        category_group=CategoryGroup.PRIVILEGE,
        confidence=0.97,
        context_patterns=["counsel", "attorney", "legal advice"],
        context_window=300,
        context_confidence_boost=0.08,
    ),
    Rule(
        id="legal-work-product-context-boost",
        name="Work Product Context Boost",
        description="Boost confidence when work product markers appear near litigation terms",
        pattern=r"\bwork[\s-]product\b",
        flags=re.IGNORECASE,
        category="WORK_PRODUCT",
        category_group=CategoryGroup.PRIVILEGE,
        confidence=0.95,
        context_patterns=["litigation", "trial", "counsel", "attorney"],
        context_window=300,
        context_confidence_boost=0.05,
    ),
    Rule(
        id="legal-settlement-confidentiality",
        name="Settlement Confidentiality",
        description="Boost settlement confidence when confidentiality markers are nearby",
        pattern=r"\bsettlement\b",
        flags=re.IGNORECASE,
        category="SETTLEMENT_TERMS",
        category_group=CategoryGroup.CONFIDENTIAL,
        confidence=0.88,
        context_patterns=["confidential", "privileged", "non-disclosure"],
        context_window=300,
        context_confidence_boost=0.07,
    ),
    Rule(
        id="legal-litigation-hold-boost",
        name="Litigation Hold Boost",
        description="Boost litigation hold confidence in presence of preservation language",
        pattern=r"\b(litigation|legal)\s+hold\b",
        flags=re.IGNORECASE,
        category="LITIGATION_MARKER",
        category_group=CategoryGroup.PRIVILEGE,
        confidence=0.95,
        context_patterns=["preserve", "retain", "do not destroy"],
        context_window=200,
        context_confidence_boost=0.05,
    ),
]

SCORING_WEIGHTS = {
    CategoryGroup.PRIVILEGE: 30,
    CategoryGroup.PII: 15,
    CategoryGroup.CONFIDENTIAL: 10,
}


def create_profile() -> ShieldProfile:
    return ShieldProfile(
        id=PROFILE_ID,
        name="Legal Privilege Protection",
        version=PROFILE_VERSION,
        description="Detects attorney-client privilege, work product, and litigation-sensitive content.",
        recognizers=RECOGNIZERS,
        rules=RULES,
        scoring_weights=SCORING_WEIGHTS,
        supported_entities=[r.supported_entities[0] for r in RECOGNIZERS],
    )
