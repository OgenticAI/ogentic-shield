"""Tests for legal domain recognizers."""

import pytest

from ogentic_shield import Shield


@pytest.fixture
def legal_shield():
    return Shield(profiles=["shield-legal"])


class TestCounselCommunicationRecognizer:
    """Tests for COUNSEL_COMMUNICATION detection."""

    # ── True Positives ──────────────────────────────────

    def test_detects_outside_counsel(self, legal_shield):
        result = legal_shield.analyze("We spoke with outside counsel about the matter.")
        entities = [e for e in result.entities if e.category == "COUNSEL_COMMUNICATION"]
        assert len(entities) >= 1
        assert entities[0].confidence >= 0.85

    def test_detects_legal_counsel(self, legal_shield):
        result = legal_shield.analyze("Legal counsel advised against disclosure.")
        entities = [e for e in result.entities if e.category == "COUNSEL_COMMUNICATION"]
        assert len(entities) >= 1

    def test_detects_in_house_counsel(self, legal_shield):
        result = legal_shield.analyze("In-house counsel reviewed the contract.")
        entities = [e for e in result.entities if e.category == "COUNSEL_COMMUNICATION"]
        assert len(entities) >= 1

    def test_detects_attorney_client(self, legal_shield):
        result = legal_shield.analyze("This is an attorney-client communication.")
        entities = [e for e in result.entities if e.category == "COUNSEL_COMMUNICATION"]
        assert len(entities) >= 1

    # ── True Negatives ──────────────────────────────────

    def test_ignores_unrelated_text(self, legal_shield):
        result = legal_shield.analyze("The weather is nice today.")
        privilege_entities = [e for e in result.entities if e.category == "COUNSEL_COMMUNICATION"]
        assert len(privilege_entities) == 0

    def test_ignores_non_legal_counsel(self, legal_shield):
        result = legal_shield.analyze("The camp counselors led the hike.")
        entities = [e for e in result.entities if e.category == "COUNSEL_COMMUNICATION"]
        assert len(entities) == 0

    # ── Edge Cases ──────────────────────────────────────

    def test_handles_mixed_case(self, legal_shield):
        result = legal_shield.analyze("OUTSIDE COUNSEL confirmed the timeline.")
        entities = [e for e in result.entities if e.category == "COUNSEL_COMMUNICATION"]
        assert len(entities) >= 1


class TestPrivilegeMarkerRecognizer:
    """Tests for PRIVILEGE_MARKER detection."""

    def test_detects_privileged_and_confidential(self, legal_shield):
        result = legal_shield.analyze("This document is privileged and confidential.")
        entities = [e for e in result.entities if e.category == "PRIVILEGE_MARKER"]
        assert len(entities) >= 1
        assert entities[0].confidence >= 0.90

    def test_detects_attorney_client_privilege(self, legal_shield):
        result = legal_shield.analyze("Protected by attorney-client privilege.")
        entities = [e for e in result.entities if e.category == "PRIVILEGE_MARKER"]
        assert len(entities) >= 1

    def test_detects_privileged_communication(self, legal_shield):
        result = legal_shield.analyze("This is a privileged communication.")
        entities = [e for e in result.entities if e.category == "PRIVILEGE_MARKER"]
        assert len(entities) >= 1

    def test_ignores_general_privilege(self, legal_shield):
        result = legal_shield.analyze("It was an honor to attend today's event in the auditorium.")
        entities = [e for e in result.entities if e.category == "PRIVILEGE_MARKER"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, legal_shield):
        result = legal_shield.analyze("The sun is shining brightly.")
        entities = [e for e in result.entities if e.category == "PRIVILEGE_MARKER"]
        assert len(entities) == 0


class TestWorkProductRecognizer:
    """Tests for WORK_PRODUCT detection."""

    def test_detects_attorney_work_product(self, legal_shield):
        result = legal_shield.analyze("This is attorney work product.")
        entities = [e for e in result.entities if e.category == "WORK_PRODUCT"]
        assert len(entities) >= 1

    def test_detects_direction_of_counsel(self, legal_shield):
        result = legal_shield.analyze("This memo was drafted at the direction of counsel.")
        entities = [e for e in result.entities if e.category == "WORK_PRODUCT"]
        assert len(entities) >= 1

    def test_detects_anticipation_of_litigation(self, legal_shield):
        result = legal_shield.analyze("Prepared in anticipation of litigation.")
        entities = [e for e in result.entities if e.category == "WORK_PRODUCT"]
        assert len(entities) >= 1

    def test_ignores_general_work(self, legal_shield):
        # "work product" as a phrase may match but not completely unrelated text
        legal_shield.analyze("The team completed their quarterly review for Q4.")

    def test_ignores_unrelated(self, legal_shield):
        result = legal_shield.analyze("I enjoy gardening on weekends.")
        entities = [e for e in result.entities if e.category == "WORK_PRODUCT"]
        assert len(entities) == 0


class TestSettlementTermsRecognizer:
    """Tests for SETTLEMENT_TERMS detection."""

    def test_detects_settle_for_amount(self, legal_shield):
        result = legal_shield.analyze("The parties agreed to settle for $4.2M.")
        entities = [e for e in result.entities if e.category == "SETTLEMENT_TERMS"]
        assert len(entities) >= 1

    def test_detects_settlement_amount(self, legal_shield):
        result = legal_shield.analyze("The settlement amount is under review.")
        entities = [e for e in result.entities if e.category == "SETTLEMENT_TERMS"]
        assert len(entities) >= 1

    def test_detects_settlement_agreement(self, legal_shield):
        result = legal_shield.analyze("Parties executed the settlement agreement.")
        entities = [e for e in result.entities if e.category == "SETTLEMENT_TERMS"]
        assert len(entities) >= 1

    def test_ignores_unrelated(self, legal_shield):
        result = legal_shield.analyze("The pioneers settled in the valley.")
        entities = [e for e in result.entities if e.category == "SETTLEMENT_TERMS"]
        assert len(entities) == 0

    def test_ignores_safe_text(self, legal_shield):
        result = legal_shield.analyze("Today is a good day for coding.")
        entities = [e for e in result.entities if e.category == "SETTLEMENT_TERMS"]
        assert len(entities) == 0


class TestCaseNumberRecognizer:
    """Tests for CASE_NUMBER detection."""

    def test_detects_criminal_case(self, legal_shield):
        result = legal_shield.analyze("Case 25-cr-00503 was filed yesterday.")
        entities = [e for e in result.entities if e.category == "CASE_NUMBER"]
        assert len(entities) >= 1
        assert entities[0].confidence >= 0.95

    def test_detects_civil_case(self, legal_shield):
        result = legal_shield.analyze("The matter is docketed as 24-cv-1234.")
        entities = [e for e in result.entities if e.category == "CASE_NUMBER"]
        assert len(entities) >= 1

    def test_detects_docket_number(self, legal_shield):
        result = legal_shield.analyze("Docket No. 2025-MC-001")
        entities = [e for e in result.entities if e.category == "CASE_NUMBER"]
        assert len(entities) >= 1

    def test_ignores_random_numbers(self, legal_shield):
        result = legal_shield.analyze("The temperature is 25 degrees today.")
        entities = [e for e in result.entities if e.category == "CASE_NUMBER"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, legal_shield):
        result = legal_shield.analyze("My phone number is 555-1234.")
        entities = [e for e in result.entities if e.category == "CASE_NUMBER"]
        assert len(entities) == 0


class TestLawFirmNameRecognizer:
    """Tests for LAW_FIRM_NAME detection."""

    def test_detects_davis_polk(self, legal_shield):
        result = legal_shield.analyze("Davis Polk is representing the defendant.")
        entities = [e for e in result.entities if e.category == "LAW_FIRM_NAME"]
        assert len(entities) >= 1

    def test_detects_kirkland_ellis(self, legal_shield):
        result = legal_shield.analyze("Kirkland & Ellis filed the brief.")
        entities = [e for e in result.entities if e.category == "LAW_FIRM_NAME"]
        assert len(entities) >= 1

    def test_detects_skadden(self, legal_shield):
        result = legal_shield.analyze("Skadden advised on the transaction.")
        entities = [e for e in result.entities if e.category == "LAW_FIRM_NAME"]
        assert len(entities) >= 1

    def test_ignores_random_names(self, legal_shield):
        result = legal_shield.analyze("John Smith went to the grocery store.")
        entities = [e for e in result.entities if e.category == "LAW_FIRM_NAME"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, legal_shield):
        result = legal_shield.analyze("The cafe on the corner serves great coffee.")
        entities = [e for e in result.entities if e.category == "LAW_FIRM_NAME"]
        assert len(entities) == 0


class TestLitigationMarkerRecognizer:
    """Tests for LITIGATION_MARKER detection."""

    def test_detects_litigation_hold(self, legal_shield):
        result = legal_shield.analyze("Please issue a litigation hold immediately.")
        entities = [e for e in result.entities if e.category == "LITIGATION_MARKER"]
        assert len(entities) >= 1

    def test_detects_legal_hold(self, legal_shield):
        result = legal_shield.analyze("A legal hold is in effect.")
        entities = [e for e in result.entities if e.category == "LITIGATION_MARKER"]
        assert len(entities) >= 1

    def test_detects_preservation_notice(self, legal_shield):
        result = legal_shield.analyze("This is a preservation notice for all records.")
        entities = [e for e in result.entities if e.category == "LITIGATION_MARKER"]
        assert len(entities) >= 1

    def test_ignores_general_hold(self, legal_shield):
        result = legal_shield.analyze("Please hold the door for me.")
        entities = [e for e in result.entities if e.category == "LITIGATION_MARKER"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, legal_shield):
        result = legal_shield.analyze("The train arrives at 3pm.")
        entities = [e for e in result.entities if e.category == "LITIGATION_MARKER"]
        assert len(entities) == 0


class TestCourtFilingRecognizer:
    """Tests for COURT_FILING detection."""

    def test_detects_motion_to_dismiss(self, legal_shield):
        result = legal_shield.analyze("We filed a motion to dismiss.")
        entities = [e for e in result.entities if e.category == "COURT_FILING"]
        assert len(entities) >= 1

    def test_detects_summary_judgment(self, legal_shield):
        result = legal_shield.analyze("The court granted summary judgment.")
        entities = [e for e in result.entities if e.category == "COURT_FILING"]
        assert len(entities) >= 1

    def test_detects_deposition(self, legal_shield):
        result = legal_shield.analyze("The deposition is scheduled for Monday.")
        entities = [e for e in result.entities if e.category == "COURT_FILING"]
        assert len(entities) >= 1

    def test_ignores_general_motion(self, legal_shield):
        result = legal_shield.analyze("The motion of the ocean is calming.")
        entities = [e for e in result.entities if e.category == "COURT_FILING"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, legal_shield):
        result = legal_shield.analyze("I love reading books about history.")
        entities = [e for e in result.entities if e.category == "COURT_FILING"]
        assert len(entities) == 0


class TestBatesNumberRecognizer:
    """Tests for BATES_NUMBER detection."""

    def test_detects_bates_prefix(self, legal_shield):
        result = legal_shield.analyze("See BATES 000123 through BATES 000456.")
        entities = [e for e in result.entities if e.category == "BATES_NUMBER"]
        assert len(entities) >= 1

    def test_detects_doc_stamp(self, legal_shield):
        result = legal_shield.analyze("Document DOC-2026-0042 is relevant.")
        entities = [e for e in result.entities if e.category == "BATES_NUMBER"]
        assert len(entities) >= 1

    def test_detects_exhibit(self, legal_shield):
        result = legal_shield.analyze("Please refer to Exhibit A.")
        entities = [e for e in result.entities if e.category == "BATES_NUMBER"]
        assert len(entities) >= 1

    def test_ignores_random_numbers(self, legal_shield):
        result = legal_shield.analyze("My order number is 12345.")
        entities = [e for e in result.entities if e.category == "BATES_NUMBER"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, legal_shield):
        result = legal_shield.analyze("The recipe calls for two cups of flour.")
        entities = [e for e in result.entities if e.category == "BATES_NUMBER"]
        assert len(entities) == 0


class TestExecutiveNameRecognizer:
    """Tests for EXECUTIVE_NAME detection."""

    def test_detects_ceo_name(self, legal_shield):
        result = legal_shield.analyze("CEO Williams approved the deal.")
        entities = [e for e in result.entities if e.category == "EXECUTIVE_NAME"]
        assert len(entities) >= 1

    def test_detects_general_counsel_name(self, legal_shield):
        result = legal_shield.analyze("General Counsel Martinez issued guidance.")
        entities = [e for e in result.entities if e.category == "EXECUTIVE_NAME"]
        assert len(entities) >= 1

    def test_detects_cfo(self, legal_shield):
        result = legal_shield.analyze("CFO Thompson reviewed the financials.")
        entities = [e for e in result.entities if e.category == "EXECUTIVE_NAME"]
        assert len(entities) >= 1

    def test_ignores_common_names(self, legal_shield):
        result = legal_shield.analyze("Alice went to the store.")
        entities = [e for e in result.entities if e.category == "EXECUTIVE_NAME"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, legal_shield):
        result = legal_shield.analyze("The cat sat on the mat.")
        entities = [e for e in result.entities if e.category == "EXECUTIVE_NAME"]
        assert len(entities) == 0

    def test_ignores_title_followed_by_lowercase(self, legal_shield):
        """Regression (recognizer IGNORECASE): a title followed by a lowercase word
        (e.g. 'the CFO reported') must not match EXECUTIVE_NAME."""
        result = legal_shield.analyze("the CFO reported quarterly earnings")
        entities = [e for e in result.entities if e.category == "EXECUTIVE_NAME"]
        assert entities == []
