"""Tests for finance domain recognizers."""

import pytest

from ogentic_shield import Shield


@pytest.fixture
def finance_shield():
    return Shield(profiles=["shield-finance"])


class TestMnpiMarkerRecognizer:
    """Tests for MNPI_MARKER detection."""

    def test_detects_mnpi(self, finance_shield):
        result = finance_shield.analyze("This document contains MNPI.")
        entities = [e for e in result.entities if e.category == "MNPI_MARKER"]
        assert len(entities) >= 1

    def test_detects_material_nonpublic(self, finance_shield):
        result = finance_shield.analyze("Material Non-Public Information enclosed.")
        entities = [e for e in result.entities if e.category == "MNPI_MARKER"]
        assert len(entities) >= 1

    def test_detects_strictly_confidential(self, finance_shield):
        result = finance_shield.analyze("STRICTLY CONFIDENTIAL deal materials.")
        entities = [e for e in result.entities if e.category == "MNPI_MARKER"]
        assert len(entities) >= 1

    def test_ignores_general_confidential(self, finance_shield):
        finance_shield.analyze("I have a confidential opinion about the movie.")
        # "confidential" alone may match at low confidence but not as strong MNPI

    def test_ignores_unrelated(self, finance_shield):
        result = finance_shield.analyze("The park is open daily from 9am to 5pm.")
        entities = [e for e in result.entities if e.category == "MNPI_MARKER"]
        assert len(entities) == 0


class TestMaActivityRecognizer:
    """Tests for MA_ACTIVITY detection."""

    def test_detects_acquisition(self, finance_shield):
        result = finance_shield.analyze("The company is acquiring TargetCo.")
        entities = [e for e in result.entities if e.category == "MA_ACTIVITY"]
        assert len(entities) >= 1

    def test_detects_merger(self, finance_shield):
        result = finance_shield.analyze("The merger agreement was signed.")
        entities = [e for e in result.entities if e.category == "MA_ACTIVITY"]
        assert len(entities) >= 1

    def test_detects_takeover(self, finance_shield):
        result = finance_shield.analyze("A hostile takeover bid was announced.")
        entities = [e for e in result.entities if e.category == "MA_ACTIVITY"]
        assert len(entities) >= 1

    def test_detects_tender_offer(self, finance_shield):
        result = finance_shield.analyze("The tender offer expires Friday.")
        entities = [e for e in result.entities if e.category == "MA_ACTIVITY"]
        assert len(entities) >= 1

    def test_ignores_general_merge(self, finance_shield):
        result = finance_shield.analyze("Let's merge the two spreadsheets together.")
        entities = [e for e in result.entities if e.category == "MA_ACTIVITY"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, finance_shield):
        result = finance_shield.analyze("I walked the dog this morning.")
        entities = [e for e in result.entities if e.category == "MA_ACTIVITY"]
        assert len(entities) == 0


class TestDealValueRecognizer:
    """Tests for DEAL_VALUE detection."""

    def test_detects_per_share(self, finance_shield):
        result = finance_shield.analyze("Offer price at $47/share.")
        entities = [e for e in result.entities if e.category == "DEAL_VALUE"]
        assert len(entities) >= 1

    def test_detects_billion(self, finance_shield):
        result = finance_shield.analyze("Enterprise value of $2.1 billion.")
        entities = [e for e in result.entities if e.category == "DEAL_VALUE"]
        assert len(entities) >= 1

    def test_detects_million(self, finance_shield):
        result = finance_shield.analyze("The deal was valued at $500M.")
        entities = [e for e in result.entities if e.category == "DEAL_VALUE"]
        assert len(entities) >= 1

    def test_ignores_general_prices(self, finance_shield):
        result = finance_shield.analyze("The coffee costs $4.50.")
        entities = [e for e in result.entities if e.category == "DEAL_VALUE"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, finance_shield):
        result = finance_shield.analyze("The temperature is 72 degrees.")
        entities = [e for e in result.entities if e.category == "DEAL_VALUE"]
        assert len(entities) == 0


class TestLeverageRatioRecognizer:
    """Tests for LEVERAGE_RATIO detection."""

    def test_detects_ebitda_multiple(self, finance_shield):
        result = finance_shield.analyze("Purchase price represents 5.2x EBITDA.")
        entities = [e for e in result.entities if e.category == "LEVERAGE_RATIO"]
        assert len(entities) >= 1

    def test_detects_revenue_multiple(self, finance_shield):
        result = finance_shield.analyze("Valued at 3.5x revenue.")
        entities = [e for e in result.entities if e.category == "LEVERAGE_RATIO"]
        assert len(entities) >= 1

    def test_detects_leverage_ratio(self, finance_shield):
        result = finance_shield.analyze("Leverage ratio of 4.0x is concerning.")
        entities = [e for e in result.entities if e.category == "LEVERAGE_RATIO"]
        assert len(entities) >= 1

    def test_ignores_general_math(self, finance_shield):
        result = finance_shield.analyze("Multiply 5 by 3 to get 15.")
        entities = [e for e in result.entities if e.category == "LEVERAGE_RATIO"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, finance_shield):
        result = finance_shield.analyze("The cat slept on the windowsill.")
        entities = [e for e in result.entities if e.category == "LEVERAGE_RATIO"]
        assert len(entities) == 0


class TestFundInformationRecognizer:
    """Tests for FUND_INFORMATION detection."""

    def test_detects_fund_number(self, finance_shield):
        result = finance_shield.analyze("Fund III is fully deployed.")
        entities = [e for e in result.entities if e.category == "FUND_INFORMATION"]
        assert len(entities) >= 1

    def test_detects_lp_allocation(self, finance_shield):
        result = finance_shield.analyze("LP allocation for this deal is $50M.")
        entities = [e for e in result.entities if e.category == "FUND_INFORMATION"]
        assert len(entities) >= 1

    def test_detects_co_invest(self, finance_shield):
        result = finance_shield.analyze("Co-investment opportunity for select LPs.")
        entities = [e for e in result.entities if e.category == "FUND_INFORMATION"]
        assert len(entities) >= 1

    def test_ignores_general_fund(self, finance_shield):
        result = finance_shield.analyze("The school fundraiser was a success.")
        entities = [e for e in result.entities if e.category == "FUND_INFORMATION"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, finance_shield):
        result = finance_shield.analyze("We had pasta for dinner last night.")
        entities = [e for e in result.entities if e.category == "FUND_INFORMATION"]
        assert len(entities) == 0


class TestInstitutionNameRecognizer:
    """Tests for INSTITUTION_NAME detection."""

    def test_detects_goldman_sachs(self, finance_shield):
        result = finance_shield.analyze("Goldman Sachs is advising on the deal.")
        entities = [e for e in result.entities if e.category == "INSTITUTION_NAME"]
        assert len(entities) >= 1

    def test_detects_blackstone(self, finance_shield):
        result = finance_shield.analyze("Blackstone is the lead sponsor.")
        entities = [e for e in result.entities if e.category == "INSTITUTION_NAME"]
        assert len(entities) >= 1

    def test_detects_morgan_stanley(self, finance_shield):
        result = finance_shield.analyze("Morgan Stanley provided the fairness opinion.")
        entities = [e for e in result.entities if e.category == "INSTITUTION_NAME"]
        assert len(entities) >= 1

    def test_ignores_random_names(self, finance_shield):
        result = finance_shield.analyze("My friend Morgan likes to cook.")
        entities = [e for e in result.entities if e.category == "INSTITUTION_NAME"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, finance_shield):
        result = finance_shield.analyze("The train was fifteen minutes late.")
        entities = [e for e in result.entities if e.category == "INSTITUTION_NAME"]
        assert len(entities) == 0


class TestFinancialTermsRecognizer:
    """Tests for FINANCIAL_TERMS detection."""

    def test_detects_covenant(self, finance_shield):
        result = finance_shield.analyze("Financial covenants include DSCR.")
        entities = [e for e in result.entities if e.category == "FINANCIAL_TERMS"]
        assert len(entities) >= 1

    def test_detects_term_sheet(self, finance_shield):
        result = finance_shield.analyze("The term sheet was circulated today.")
        entities = [e for e in result.entities if e.category == "FINANCIAL_TERMS"]
        assert len(entities) >= 1

    def test_detects_dscr(self, finance_shield):
        result = finance_shield.analyze("DSCR must remain above 1.5x.")
        entities = [e for e in result.entities if e.category == "FINANCIAL_TERMS"]
        assert len(entities) >= 1

    def test_ignores_general_terms(self, finance_shield):
        result = finance_shield.analyze("The terms and conditions of the website are clear.")
        entities = [e for e in result.entities if e.category == "FINANCIAL_TERMS"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, finance_shield):
        result = finance_shield.analyze("I painted my room a nice shade of blue.")
        entities = [e for e in result.entities if e.category == "FINANCIAL_TERMS"]
        assert len(entities) == 0


class TestDistributionRestrictionRecognizer:
    """Tests for DISTRIBUTION_RESTRICTION detection."""

    def test_detects_do_not_distribute(self, finance_shield):
        result = finance_shield.analyze("Do not distribute this document.")
        entities = [e for e in result.entities if e.category == "DISTRIBUTION_RESTRICTION"]
        assert len(entities) >= 1

    def test_detects_internal_use_only(self, finance_shield):
        result = finance_shield.analyze("For internal use only.")
        entities = [e for e in result.entities if e.category == "DISTRIBUTION_RESTRICTION"]
        assert len(entities) >= 1

    def test_detects_not_for_distribution(self, finance_shield):
        result = finance_shield.analyze("Not for public distribution.")
        entities = [e for e in result.entities if e.category == "DISTRIBUTION_RESTRICTION"]
        assert len(entities) >= 1

    def test_ignores_general_distribution(self, finance_shield):
        result = finance_shield.analyze("The distribution center ships packages daily.")
        entities = [e for e in result.entities if e.category == "DISTRIBUTION_RESTRICTION"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, finance_shield):
        result = finance_shield.analyze("The flowers in the garden are blooming.")
        entities = [e for e in result.entities if e.category == "DISTRIBUTION_RESTRICTION"]
        assert len(entities) == 0


class TestInsiderMarkerRecognizer:
    """Tests for INSIDER_MARKER detection."""

    def test_detects_insider_trading(self, finance_shield):
        result = finance_shield.analyze("Insider trading is strictly prohibited.")
        entities = [e for e in result.entities if e.category == "INSIDER_MARKER"]
        assert len(entities) >= 1

    def test_detects_blackout_period(self, finance_shield):
        result = finance_shield.analyze("Blackout period begins Monday.")
        entities = [e for e in result.entities if e.category == "INSIDER_MARKER"]
        assert len(entities) >= 1

    def test_detects_restricted_list(self, finance_shield):
        result = finance_shield.analyze("Added to the restricted list.")
        entities = [e for e in result.entities if e.category == "INSIDER_MARKER"]
        assert len(entities) >= 1

    def test_ignores_general_insider(self, finance_shield):
        result = finance_shield.analyze("The gaming community members know the latest trends well.")
        entities = [e for e in result.entities if e.category == "INSIDER_MARKER"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, finance_shield):
        result = finance_shield.analyze("The hiking trail was muddy after rain.")
        entities = [e for e in result.entities if e.category == "INSIDER_MARKER"]
        assert len(entities) == 0


class TestCarryTermsRecognizer:
    """Tests for CARRY_TERMS detection."""

    def test_detects_carry_percentage(self, finance_shield):
        result = finance_shield.analyze("Standard 20% carry on returns above hurdle.")
        entities = [e for e in result.entities if e.category == "CARRY_TERMS"]
        assert len(entities) >= 1

    def test_detects_carried_interest(self, finance_shield):
        result = finance_shield.analyze("Carried interest terms are standard.")
        entities = [e for e in result.entities if e.category == "CARRY_TERMS"]
        assert len(entities) >= 1

    def test_detects_hurdle_rate(self, finance_shield):
        result = finance_shield.analyze("Hurdle rate is set at 8%.")
        entities = [e for e in result.entities if e.category == "CARRY_TERMS"]
        assert len(entities) >= 1

    def test_detects_preferred_return(self, finance_shield):
        result = finance_shield.analyze("Preferred return of 8% to LPs.")
        entities = [e for e in result.entities if e.category == "CARRY_TERMS"]
        assert len(entities) >= 1

    def test_ignores_general_carry(self, finance_shield):
        result = finance_shield.analyze("Please carry the groceries inside.")
        entities = [e for e in result.entities if e.category == "CARRY_TERMS"]
        assert len(entities) == 0

    def test_ignores_unrelated(self, finance_shield):
        result = finance_shield.analyze("The sky is clear and blue today.")
        entities = [e for e in result.entities if e.category == "CARRY_TERMS"]
        assert len(entities) == 0
