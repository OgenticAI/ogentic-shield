"""Tests for the government-domain recognizers used by shield-gov."""

import pytest

from ogentic_shield import Shield


@pytest.fixture(scope="module")
def gov_shield():
    return Shield(profiles=["shield-gov"])


def categories(result, name):
    return [e for e in result.entities if e.category == name]


class TestClassificationMarkingRecognizer:
    """Tests for CLASSIFICATION_MARKING detection."""

    # ── True Positives ──────────────────────────────────

    def test_detects_top_secret_banner(self, gov_shield):
        result = gov_shield.analyze("TOP SECRET//SI//NOFORN")
        found = categories(result, "CLASSIFICATION_MARKING")
        assert len(found) >= 1
        assert found[0].confidence >= 0.90

    def test_detects_secret_with_compartment(self, gov_shield):
        result = gov_shield.analyze("SECRET//REL TO USA, FVEY")
        assert len(categories(result, "CLASSIFICATION_MARKING")) >= 1

    def test_detects_classified_by_line(self, gov_shield):
        result = gov_shield.analyze("Classified By: Director, Office of Intelligence")
        assert len(categories(result, "CLASSIFICATION_MARKING")) >= 1

    def test_detects_declassify_on_line(self, gov_shield):
        result = gov_shield.analyze("Declassify On: 20491231")
        assert len(categories(result, "CLASSIFICATION_MARKING")) >= 1

    def test_detects_portion_marking_with_compartment(self, gov_shield):
        result = gov_shield.analyze("(TS//SI) The collection began in March.")
        assert len(categories(result, "CLASSIFICATION_MARKING")) >= 1

    # ── True Negatives ──────────────────────────────────
    #
    # Presidio compiles recognizer patterns case-insensitively, so these are the
    # cases that made a benign paragraph score 69/HIGH before the patterns were
    # pinned to upper case.

    def test_ignores_the_word_secret_in_prose(self, gov_shield):
        result = gov_shield.analyze("The secret ingredient in the recipe is paprika.")
        assert categories(result, "CLASSIFICATION_MARKING") == []

    def test_ignores_outline_lettering(self, gov_shield):
        result = gov_shield.analyze("See section (c) and subsection (s) of the appendix.")
        assert categories(result, "CLASSIFICATION_MARKING") == []

    def test_ignores_bare_single_letter_in_parentheses(self, gov_shield):
        """Bare (S) and (C) are indistinguishable from outline lettering."""
        result = gov_shield.analyze("Item (S) was delivered and item (C) was cancelled.")
        assert categories(result, "CLASSIFICATION_MARKING") == []

    def test_ignores_confidential_in_ordinary_sentence(self, gov_shield):
        result = gov_shield.analyze("He kept the conversation confidential between friends.")
        assert categories(result, "CLASSIFICATION_MARKING") == []


class TestCuiMarkingRecognizer:
    """Tests for CUI_MARKING detection."""

    def test_detects_cui_banner(self, gov_shield):
        result = gov_shield.analyze("CUI//PRIV")
        assert len(categories(result, "CUI_MARKING")) >= 1

    def test_detects_spelled_out_cui(self, gov_shield):
        result = gov_shield.analyze("CONTROLLED UNCLASSIFIED INFORMATION")
        assert len(categories(result, "CUI_MARKING")) >= 1

    def test_detects_legacy_fouo(self, gov_shield):
        result = gov_shield.analyze("FOR OFFICIAL USE ONLY — internal distribution.")
        assert len(categories(result, "CUI_MARKING")) >= 1

    def test_ignores_lowercase_cui_word(self, gov_shield):
        result = gov_shield.analyze("The chef prepared a delicate cui style dish.")
        assert categories(result, "CUI_MARKING") == []


class TestConfidentialSourceRecognizer:
    """Tests for CONFIDENTIAL_SOURCE detection — FOIA (b)(7)(D)."""

    def test_detects_confidential_source(self, gov_shield):
        result = gov_shield.analyze("A confidential source provided the material.")
        assert len(categories(result, "CONFIDENTIAL_SOURCE")) >= 1

    def test_detects_confidential_informant(self, gov_shield):
        result = gov_shield.analyze("The confidential informant was interviewed twice.")
        assert len(categories(result, "CONFIDENTIAL_SOURCE")) >= 1

    def test_detects_source_identity(self, gov_shield):
        result = gov_shield.analyze("The source's identity must not be disclosed.")
        assert len(categories(result, "CONFIDENTIAL_SOURCE")) >= 1

    def test_detects_express_assurance(self, gov_shield):
        result = gov_shield.analyze("Provided under an express assurance of confidentiality.")
        assert len(categories(result, "CONFIDENTIAL_SOURCE")) >= 1

    def test_ignores_ordinary_source_reference(self, gov_shield):
        result = gov_shield.analyze("The report cites its source in a footnote.")
        assert categories(result, "CONFIDENTIAL_SOURCE") == []


class TestInvestigativeTechniqueRecognizer:
    """Tests for INVESTIGATIVE_TECHNIQUE detection — FOIA (b)(7)(E)."""

    def test_detects_investigative_technique(self, gov_shield):
        result = gov_shield.analyze("The memo describes investigative techniques in detail.")
        assert len(categories(result, "INVESTIGATIVE_TECHNIQUE")) >= 1

    def test_detects_surveillance_method(self, gov_shield):
        result = gov_shield.analyze("The surveillance method relied on static posts.")
        assert len(categories(result, "INVESTIGATIVE_TECHNIQUE")) >= 1

    def test_detects_undercover_operation(self, gov_shield):
        result = gov_shield.analyze("An undercover operation was authorised.")
        assert len(categories(result, "INVESTIGATIVE_TECHNIQUE")) >= 1

    def test_detects_pen_register(self, gov_shield):
        result = gov_shield.analyze("A pen register was installed on the line.")
        assert len(categories(result, "INVESTIGATIVE_TECHNIQUE")) >= 1

    def test_ignores_ordinary_investigation_word(self, gov_shield):
        result = gov_shield.analyze("We began an investigation into the delay.")
        assert categories(result, "INVESTIGATIVE_TECHNIQUE") == []


class TestDeliberativeMarkerRecognizer:
    """Tests for DELIBERATIVE_MARKER detection — FOIA (b)(5)."""

    def test_detects_pre_decisional(self, gov_shield):
        result = gov_shield.analyze("This draft is pre-decisional.")
        assert len(categories(result, "DELIBERATIVE_MARKER")) >= 1

    def test_detects_pre_decisional_without_hyphen(self, gov_shield):
        result = gov_shield.analyze("The analysis is predecisional and internal.")
        assert len(categories(result, "DELIBERATIVE_MARKER")) >= 1

    def test_detects_deliberative_process(self, gov_shield):
        result = gov_shield.analyze("Protected by the deliberative process privilege.")
        assert len(categories(result, "DELIBERATIVE_MARKER")) >= 1

    def test_ignores_ordinary_draft_word(self, gov_shield):
        result = gov_shield.analyze("Please review the draft agenda before Friday.")
        assert categories(result, "DELIBERATIVE_MARKER") == []


class TestLawEnforcementRecordRecognizer:
    """Tests for LAW_ENFORCEMENT_MARKER — what makes (b)(7) apply at all."""

    def test_detects_compiled_for_law_enforcement(self, gov_shield):
        result = gov_shield.analyze("These records were compiled for law enforcement purposes.")
        found = categories(result, "LAW_ENFORCEMENT_MARKER")
        assert len(found) >= 1
        assert found[0].confidence >= 0.90

    def test_detects_special_agent(self, gov_shield):
        result = gov_shield.analyze("Special Agent Rivera conducted the interview.")
        assert len(categories(result, "LAW_ENFORCEMENT_MARKER")) >= 1

    def test_detects_grand_jury(self, gov_shield):
        result = gov_shield.analyze("Material presented to the grand jury.")
        assert len(categories(result, "LAW_ENFORCEMENT_MARKER")) >= 1

    def test_ignores_ordinary_agent_word(self, gov_shield):
        result = gov_shield.analyze("Our travel agent booked the flights.")
        assert categories(result, "LAW_ENFORCEMENT_MARKER") == []


class TestFoiaRequestNumberRecognizer:
    """Tests for FOIA_REQUEST_NUMBER — detected so it is *not* mistaken for PII."""

    def test_detects_tracking_number(self, gov_shield):
        result = gov_shield.analyze("Request 2024-FOIA-0881 is assigned to the complex track.")
        assert len(categories(result, "FOIA_REQUEST_NUMBER")) >= 1

    def test_detects_request_number_phrasing(self, gov_shield):
        result = gov_shield.analyze("FOIA request no. 24-1182 was received on Monday.")
        assert len(categories(result, "FOIA_REQUEST_NUMBER")) >= 1

    def test_ignores_ordinary_reference_number(self, gov_shield):
        result = gov_shield.analyze("Invoice 2024-114 was paid in full.")
        assert categories(result, "FOIA_REQUEST_NUMBER") == []


class TestStatutoryExemptionRecognizer:
    """Tests for STATUTORY_EXEMPTION — an exemption already asserted in the text."""

    def test_detects_full_citation(self, gov_shield):
        result = gov_shield.analyze("Withheld under 5 U.S.C. § 552(b)(7)(C).")
        found = categories(result, "STATUTORY_EXEMPTION")
        assert len(found) >= 1
        assert found[0].confidence >= 0.90

    def test_detects_exempt_from_disclosure(self, gov_shield):
        result = gov_shield.analyze("This paragraph is exempt from disclosure.")
        assert len(categories(result, "STATUTORY_EXEMPTION")) >= 1

    def test_ignores_contract_subclause(self, gov_shield):
        """A bare "(b)(2)" is a contract clause as often as a FOIA exemption."""
        result = gov_shield.analyze("See clause (b)(2) of the appendix for the schedule.")
        assert categories(result, "STATUTORY_EXEMPTION") == []
