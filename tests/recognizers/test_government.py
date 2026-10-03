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


class TestUsStreetAddressRecognizer:
    """Tests for ADDRESS detection (US street addresses)."""

    def test_whole_address_wins_over_ner_person(self, gov_shield):
        # NER alone tags the street name as a PERSON and drops the number.
        result = gov_shield.analyze("a home address at 88 Larkmead Terrace, Reston, Virginia.")
        assert [e.text for e in categories(result, "ADDRESS")] == ["88 Larkmead Terrace"]
        assert not [e for e in categories(result, "PERSON") if "Larkmead" in e.text]

    def test_directionals_and_unit(self, gov_shield):
        result = gov_shield.analyze("She moved to 1600 Pennsylvania Ave NW, Apt 4B last year.")
        assert [e.text for e in categories(result, "ADDRESS")] == ["1600 Pennsylvania Ave NW, Apt 4B"]
        result = gov_shield.analyze("Mail it to 42 W. Elm Street.")
        assert [e.text for e in categories(result, "ADDRESS")] == ["42 W. Elm Street"]

    def test_prose_with_numbers_is_not_an_address(self, gov_shield):
        result = gov_shield.analyze("We reviewed 88 pages per court order and replied 12 days later.")
        assert categories(result, "ADDRESS") == []


class TestLabelledIdentifiers:
    """Identifiers found by the label in front of them; only the value is boxed."""

    @pytest.mark.parametrize(
        ("text", "category", "value"),
        [
            ("His date of birth is 3 February 1979.", "DATE_OF_BIRTH", "3 February 1979"),
            ("Bartholomew Achterberg, born April 30, 1975.", "DATE_OF_BIRTH", "April 30, 1975"),
            ("Date of birth:    22 August 1984", "DATE_OF_BIRTH", "22 August 1984"),
            ("from an account number 7730019942 at the bank", "US_BANK_NUMBER", "7730019942"),
            ("came in on their form: account 004417729813 at", "US_BANK_NUMBER", "004417729813"),
            ("his Maryland driver's license is B-261-447-903-118.", "US_DRIVER_LICENSE", "B-261-447-903-118"),
            ("ID: PA DL 33 418 207", "US_DRIVER_LICENSE", "33 418 207"),
            ("ID: Passport 548120377", "US_PASSPORT", "548120377"),
            ("Employer ID (EIN):    84-2271093", "US_EIN", "84-2271093"),
            ("medical record number SARMC-0098812, treated", "MEDICAL_RECORD_NUMBER", "SARMC-0098812"),
            ("Claim number:     OBA-DEN-2024-118207", "CLAIM_NUMBER", "OBA-DEN-2024-118207"),
            ("Employee ID:      FGB-0048213", "EMPLOYEE_ID", "FGB-0048213"),
        ],
    )
    def test_value_after_label(self, gov_shield, text, category, value):
        assert [e.text for e in categories(gov_shield.analyze(text), category)] == [value]

    def test_licence_does_not_run_onto_the_next_line(self, gov_shield):
        found = categories(gov_shield.analyze("ID: PA DL 33 418 207\n09/09    Rajiv"), "US_DRIVER_LICENSE")
        assert [e.text for e in found] == ["33 418 207"]

    def test_bare_values_are_not_flagged(self, gov_shield):
        result = gov_shield.analyze("The meeting on 3 February 1979 counted 7730019942 tonnes and 84-2271093 items.")
        for category in ("DATE_OF_BIRTH", "US_BANK_NUMBER", "US_EIN"):
            assert categories(result, category) == []


class TestCommercialPricingRecognizer:
    """(b)(4) prices and margins, only in a commercial context."""

    def test_bid_and_rate_are_flagged(self, gov_shield):
        result = gov_shield.analyze("Northgate bid $4,218,600 with a labor rate of $87.40 per hour.")
        assert [e.text for e in categories(result, "COMMERCIAL_PRICING")] == ["$4,218,600", "$87.40 per hour"]

    def test_settlement_and_overpayment_amounts_are_not(self, gov_shield):
        result = gov_shield.analyze(
            "The Department will pay the Claimant $187,500. We approved a partial waiver of $4,000.00."
        )
        assert categories(result, "COMMERCIAL_PRICING") == []
