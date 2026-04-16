"""Shared fixtures for ogentic-shield tests."""

import pytest

from ogentic_shield import Shield


@pytest.fixture
def legal_shield():
    """Shield instance with legal profile only."""
    return Shield(profiles=["shield-legal"])


@pytest.fixture
def therapy_shield():
    """Shield instance with therapy profile only."""
    return Shield(profiles=["shield-therapy"])


@pytest.fixture
def finance_shield():
    """Shield instance with finance profile only."""
    return Shield(profiles=["shield-finance"])


@pytest.fixture
def all_profiles_shield():
    """Shield instance with all profiles loaded."""
    return Shield(profiles=["shield-legal", "shield-therapy", "shield-finance"])


LEGAL_PRIVILEGED_TEXT = (
    "Per our conversation with outside counsel at Davis Polk regarding "
    "the SEC investigation, this communication is privileged and confidential. "
    "Attorney work product prepared in anticipation of litigation. "
    "Case No. 25-cr-00503. CEO Williams has been advised by General Counsel Martinez "
    "to issue a litigation hold on all related documents. Settlement terms are "
    "confidential — the parties agreed to settle for $4.2M."
)

THERAPY_PHI_TEXT = (
    "Patient: Jane D. DOB: 03/15/1988. Session 12 progress note. "
    "Diagnosis Code: F33.1 (Major Depressive Disorder, recurrent, moderate). "
    "Patient reports suicidal ideation with no active plan. Safety plan reviewed. "
    "Prescribed Sertraline 100mg daily. Insurance ID: UHC-8847291. "
    "Therapist Sarah Johnson, LCSW. Process notes: countertransference noted "
    "regarding patient's therapeutic alliance concerns. SSN: 123-45-6789."
)

FINANCE_MNPI_TEXT = (
    "CONFIDENTIAL — MATERIAL NON-PUBLIC INFORMATION. Do not distribute. "
    "Goldman Sachs is advising on the acquisition of TargetCo at $47/share, "
    "representing a 5.2x EBITDA multiple. Fund III LP allocation is $200M commitment. "
    "Term sheet includes 20% carry with 8% hurdle rate. "
    "Blackout period in effect — insider trading restrictions apply. "
    "DSCR covenant at 1.5x. Internal use only."
)

SAFE_TEXT = "The weather is nice today. I went for a walk in the park with my dog."
