"""Integration tests for shield-gov: a realistic federal record in, the full result out."""

import pytest

from ogentic_shield import PROFILE_REDACT_CATEGORIES, Shield
from ogentic_shield.profiles import get_profile, list_profiles

FOIA_MEMO = """
From: Marcus Elwood, Senior Analyst (marcus.elwood@example.gov)
Subject: Request 2024-FOIA-0881 — responsive material, matter 24-CV-1184

Hannah Heppner submitted the complaint. Her SSN 412-71-3359 is on the intake form
and her direct line is (415) 555-0182.

Special Agent R. Castellanos conducted the interview. A confidential source
provided corroborating material; the source's identity must not be disclosed.
These records were compiled for law enforcement purposes and describe
investigative techniques used during the operation.

This draft is pre-decisional and deliberative, and reflects attorney work product.
Portions are exempt from disclosure under 5 U.S.C. § 552(b)(7)(C).
"""

BENIGN_MEMO = """
The quarterly newsletter goes out on Friday. The secret ingredient in the office
chilli is smoked paprika. See section (c) of the handbook and clause (b)(2) of the
appendix for the leave policy. Our results were strong and the team is growing.
"""


@pytest.fixture(scope="module")
def gov_shield():
    return Shield(profiles=["shield-gov"])


class TestGovernmentProfileRegistration:

    def test_profile_is_registered(self):
        profile = get_profile("shield-gov")
        assert profile.id == "shield-gov"
        assert profile.version

    def test_profile_appears_in_listing(self):
        assert "shield-gov" in {p.id for p in list_profiles()}

    def test_profile_declares_its_entities(self):
        profile = get_profile("shield-gov")
        for entity in (
            "CLASSIFICATION_MARKING",
            "CUI_MARKING",
            "CONFIDENTIAL_SOURCE",
            "INVESTIGATIVE_TECHNIQUE",
            "DELIBERATIVE_MARKER",
            "LAW_ENFORCEMENT_MARKER",
            "FOIA_REQUEST_NUMBER",
            "STATUTORY_EXEMPTION",
        ):
            assert entity in profile.supported_entities

    def test_redaction_defaults_cover_identifiers_only(self):
        """Markers explain why a page is sensitive; blacking them out protects nothing."""
        categories = PROFILE_REDACT_CATEGORIES["shield-gov"]
        assert "Person" in categories
        assert "Ssn" in categories
        assert "CLASSIFICATION_MARKING" not in categories
        assert "DELIBERATIVE_MARKER" not in categories


class TestGovernmentProfileOnARealRecord:

    def test_finds_the_personal_identifiers(self, gov_shield):
        result = gov_shield.analyze(FOIA_MEMO)
        found = {e.category for e in result.entities}
        assert "PERSON" in found
        assert "EMAIL_ADDRESS" in found
        assert "SSN" in found

    def test_finds_the_exemption_markers(self, gov_shield):
        result = gov_shield.analyze(FOIA_MEMO)
        found = {e.category for e in result.entities}
        assert "CONFIDENTIAL_SOURCE" in found      # (b)(7)(D)
        assert "INVESTIGATIVE_TECHNIQUE" in found  # (b)(7)(E)
        assert "DELIBERATIVE_MARKER" in found      # (b)(5)
        assert "LAW_ENFORCEMENT_MARKER" in found   # makes (b)(7) apply
        assert "STATUTORY_EXEMPTION" in found

    def test_separates_the_request_number_from_the_case_number(self, gov_shield):
        """The FOIA tracking number is the request's own id, not something to withhold."""
        result = gov_shield.analyze(FOIA_MEMO)
        found = {e.category for e in result.entities}
        assert "FOIA_REQUEST_NUMBER" in found
        assert "CASE_NUMBER" in found

    def test_scores_the_record_as_sensitive(self, gov_shield):
        result = gov_shield.analyze(FOIA_MEMO)
        assert result.score >= 70

    def test_entity_offsets_match_the_text(self, gov_shield):
        """Offsets are code points into the input; a consumer draws boxes from them."""
        result = gov_shield.analyze(FOIA_MEMO)
        for entity in result.entities:
            assert FOIA_MEMO[entity.start:entity.end] == entity.text


class TestGovernmentProfileOnOrdinaryText:

    def test_benign_memo_raises_nothing(self, gov_shield):
        result = gov_shield.analyze(BENIGN_MEMO)
        assert result.entities == []

    def test_benign_memo_scores_zero(self, gov_shield):
        result = gov_shield.analyze(BENIGN_MEMO)
        assert result.score == 0
