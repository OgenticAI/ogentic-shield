"""shield-gov profile: recognizers, rules, and scoring for federal records review.

Built for FOIA and Privacy Act processing. It detects the two things a records
officer needs and the other profiles do not give together:

* the **personal identifiers** that drive (b)(6) and (b)(7)(C) withholdings —
  inherited from the base recognizers plus `SsnRecognizer`;
* the **markers** that decide which exemption applies at all — classification
  and CUI banners, confidential sources, investigative techniques, deliberative
  material, and exemption citations already asserted in the document.

Privilege detection is shared with `shield-legal`, because attorney-client and
work-product material is withheld under (b)(5) in exactly the same way.
"""

import re

from ogentic_shield.models import CategoryGroup, Rule, ShieldProfile
from ogentic_shield.recognizers.government import (
    ClassificationMarkingRecognizer,
    ConfidentialSourceRecognizer,
    CuiMarkingRecognizer,
    DeliberativeMarkerRecognizer,
    FoiaRequestNumberRecognizer,
    InvestigativeTechniqueRecognizer,
    LawEnforcementRecordRecognizer,
    StatutoryExemptionRecognizer,
)
from ogentic_shield.recognizers.legal import (
    CaseNumberRecognizer,
    CounselCommunicationRecognizer,
    PrivilegeMarkerRecognizer,
    WorkProductRecognizer,
)
from ogentic_shield.recognizers.therapy import SsnRecognizer

PROFILE_ID = "shield-gov"
PROFILE_VERSION = "0.1.0"

RECOGNIZERS = [
    # Federal records markers
    ClassificationMarkingRecognizer(),
    CuiMarkingRecognizer(),
    ConfidentialSourceRecognizer(),
    InvestigativeTechniqueRecognizer(),
    DeliberativeMarkerRecognizer(),
    LawEnforcementRecordRecognizer(),
    FoiaRequestNumberRecognizer(),
    StatutoryExemptionRecognizer(),
    # Shared with shield-legal: (b)(5) covers the same material
    PrivilegeMarkerRecognizer(),
    WorkProductRecognizer(),
    CounselCommunicationRecognizer(),
    CaseNumberRecognizer(),
    # SSNs appear in any domain
    SsnRecognizer(),
]

RULES = [
    Rule(
        id="gov-law-enforcement-privacy-boost",
        name="Law Enforcement Privacy Boost",
        description=(
            "A name in a record compiled for law enforcement purposes is a (b)(7)(C) "
            "question rather than a plain (b)(6) one, so raise confidence when "
            "law-enforcement context is nearby."
        ),
        pattern=r"\b(Special\s+Agent|Case\s+Agent|investigation|subject\s+of\s+the\s+investigation)\b",
        flags=re.IGNORECASE,
        category="LAW_ENFORCEMENT_MARKER",
        category_group=CategoryGroup.CONFIDENTIAL,
        confidence=0.90,
        context_patterns=["interview", "witness", "suspect", "informant", "case file"],
        context_window=300,
        context_confidence_boost=0.07,
    ),
    Rule(
        id="gov-source-protection-boost",
        name="Confidential Source Protection Boost",
        description="Raise confidence when a source reference sits near confidentiality language.",
        pattern=r"\bconfidential\s+(source|informant)\b",
        flags=re.IGNORECASE,
        category="CONFIDENTIAL_SOURCE",
        category_group=CategoryGroup.PII,
        confidence=0.95,
        context_patterns=["identity", "must not be disclosed", "protect", "anonymity"],
        context_window=300,
        context_confidence_boost=0.04,
    ),
    Rule(
        id="gov-deliberative-boost",
        name="Deliberative Process Boost",
        description="Raise confidence for deliberative markers near decision-making language.",
        pattern=r"\b(pre[\s-]?decisional|deliberative)\b",
        flags=re.IGNORECASE,
        category="DELIBERATIVE_MARKER",
        category_group=CategoryGroup.PRIVILEGE,
        confidence=0.93,
        context_patterns=["recommendation", "draft", "decision", "policy", "option"],
        context_window=300,
        context_confidence_boost=0.05,
    ),
    Rule(
        id="gov-classified-stop",
        name="Classification Marking",
        description=(
            "A classification banner is not a redaction — it means the document does "
            "not belong on an unaccredited workstation at all. Scored high so it "
            "surfaces first."
        ),
        pattern=r"(?-i:\b(TOP\s+SECRET|SECRET|CONFIDENTIAL)\s*//)",
        flags=0,  # case-sensitive: banners are upper case, "secret" in prose is not
        category="CLASSIFICATION_MARKING",
        category_group=CategoryGroup.CONFIDENTIAL,
        confidence=0.98,
        context_patterns=["classified by", "declassify on", "derived from", "noforn"],
        context_window=400,
        context_confidence_boost=0.02,
    ),
]

SCORING_WEIGHTS = {
    # A classification or source marker outranks everything: it changes what may
    # be processed, not just what is blacked out.
    CategoryGroup.CONFIDENTIAL: 30,
    CategoryGroup.PRIVILEGE: 25,
    CategoryGroup.PII: 20,
}


def create_profile() -> ShieldProfile:
    return ShieldProfile(
        id=PROFILE_ID,
        name="Government Records (FOIA / Privacy Act)",
        version=PROFILE_VERSION,
        description=(
            "Detects the personal identifiers and the exemption markers a federal "
            "records officer withholds on: classification and CUI banners, confidential "
            "sources, investigative techniques, deliberative material, privilege, and "
            "FOIA tracking numbers."
        ),
        recognizers=RECOGNIZERS,
        rules=RULES,
        scoring_weights=SCORING_WEIGHTS,
        supported_entities=[r.supported_entities[0] for r in RECOGNIZERS],
    )
