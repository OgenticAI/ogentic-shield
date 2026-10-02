"""US phone numbers are detected without a context word (0.6.2).

Presidio's PhoneRecognizer scores 0.4 and needs context to clear 0.5, but its
"call" context word is a spaCy stopword that never matches, so these were
dropped entirely.
"""

from __future__ import annotations

import pytest

from ogentic_shield import Shield


def _phones(text: str) -> list[str]:
    result = Shield(profiles=["shield-legal"]).analyze(text)
    return [e.text for e in result.entities if e.category == "PHONE_NUMBER"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("call 415-555-0182 today", "415-555-0182"),
        ("reach me at the office or (415) 555-0182", "(415) 555-0182"),
        ("cell (415) 555-0182", "(415) 555-0182"),
        ("Dial +1 415-555-0182 ext. 4", "+1 415-555-0182"),
        ("Fax 415.555.0182.", "415.555.0182"),
    ],
)
def test_us_phone_detected_without_context(text: str, expected: str) -> None:
    assert _phones(text) == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "SSN 412-71-3359 on file.",  # 3-2-4 is an SSN, not a phone
        "Reference 123-456-7890 (invalid area code).",
        "Account 4121-7133-5900 is restricted.",
        "Filed 2026-10-02 in Case No. 25-cr-00503.",
        "Invoice INV-415-555-0182 is overdue.",
        "Ship to ZIP 94105-1234.",
        "Wire ref 4155550182 cleared.",  # bare digit run: left to Presidio's context rule
    ],
)
def test_no_phone_false_positives(text: str) -> None:
    assert _phones(text) == []
