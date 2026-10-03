"""SSNs are detected under every built-in profile, not only shield-therapy.

Before 0.6.2 only shield-therapy registered SsnRecognizer, so an SSN in legal
or financial text passed through shield-legal / shield-finance undetected.
"""

from __future__ import annotations

import pytest

from ogentic_shield import Shield

PROFILES = ["shield-legal", "shield-finance", "shield-therapy", "shield-therapy-pro"]


def _ssn_hits(profile: str, text: str) -> list[tuple[str, str]]:
    result = Shield(profiles=[profile]).analyze(text)
    return [(e.category, e.text) for e in result.entities if e.category in ("SSN", "US_SSN")]


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(
    "text, expected",
    [
        ("Client SSN 412-71-3359 on file.", ("SSN", "SSN 412-71-3359")),
        ("Borrower's number is 412-71-3359.", ("SSN", "412-71-3359")),
        ("Social Security number: 412 71 3359", ("SSN", "Social Security number: 412 71 3359")),
        # Presidio's validated US_SSN covers space-separated numbers without a label.
        ("Guarantor 412 71 3359 signed.", ("US_SSN", "412 71 3359")),
    ],
)
def test_ssn_detected_in_every_profile(profile: str, text: str, expected: tuple[str, str]) -> None:
    assert _ssn_hits(profile, text) == [expected]


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(
    "text",
    [
        "Call 415-555-0182 for the deal room.",
        "Case No. 25-cr-00503 was filed in 2024.",
        "Wire $4,200,000 by 2026-10-02 per the term sheet.",
        "Account 4121-7133-5900 is restricted.",
    ],
)
def test_ssn_recognizer_adds_no_noise(profile: str, text: str) -> None:
    assert _ssn_hits(profile, text) == []
