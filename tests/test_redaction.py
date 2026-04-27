"""Tests for the category-aware redaction wrapper (OGE-308 + OGE-309).

Covers the round-trip API, per-profile defaults, custom category overrides,
within-call token determinism, cross-call salt uniqueness, and the
"detection ≠ redaction" principle (numbers stay; identifiers go).
"""

from __future__ import annotations

import re

import pytest

from ogentic_shield import (
    DEFAULT_REDACT_CATEGORIES,
    PROFILE_REDACT_CATEGORIES,
    RedactionMapping,
    Shield,
)
from ogentic_shield.models import CategoryGroup, DetectedEntity, DetectionLayer
from ogentic_shield.redaction import (
    _expand_entity_types,
    _label_for,
    _resolve_categories,
    redact_text,
    unredact_text,
)

TOKEN_RE = re.compile(r"\[[A-Za-z]+_[0-9a-f]{6}\]")


# ─── Round-trip per profile ──────────────────────────────────────────────────

class TestRoundTripPerProfile:
    def test_finance_round_trip_preserves_dollar_amounts(self, finance_shield: Shield):
        text = (
            "Goldman Sachs is advising John Smith on the acquisition at $47/share, "
            "representing a 5.2x EBITDA multiple. Contact: john@example.com."
        )
        redacted, mapping = finance_shield.redact(text)

        assert "Goldman Sachs" not in redacted
        assert "John Smith" not in redacted
        assert "john@example.com" not in redacted
        # Numbers must survive — model needs them for math
        assert "$47/share" in redacted
        assert "5.2x EBITDA" in redacted

        restored = Shield.unredact(redacted, mapping)
        assert restored == text

    def test_legal_round_trip_masks_case_and_firm(self, legal_shield: Shield):
        text = (
            "Davis Polk represents the company in Case No. 25-cr-00503. "
            "CEO Williams has been advised by General Counsel Martinez. "
            "Settlement for $4.2M is privileged and confidential."
        )
        redacted, mapping = legal_shield.redact(text)

        assert "Davis Polk" not in redacted
        assert "25-cr-00503" not in redacted
        # Privilege markers (text, not identifiers) stay
        assert "privileged and confidential" in redacted
        # Settlement amount stays
        assert "$4.2M" in redacted

        restored = Shield.unredact(redacted, mapping)
        assert restored == text

    def test_therapy_round_trip_masks_phi_identifiers(self, therapy_shield: Shield):
        text = (
            "Patient name: Mary Smith. DOB: 03/15/1988. "
            "Insurance ID: UHC-8847291. SSN: 123-45-6789. "
            "Session 12 progress note."
        )
        redacted, mapping = therapy_shield.redact(text)

        assert "Mary Smith" not in redacted
        assert "03/15/1988" not in redacted
        assert "UHC-8847291" not in redacted
        assert "123-45-6789" not in redacted
        # Clinical session marker — content, not identifier — survives
        assert "Session 12" in redacted

        restored = Shield.unredact(redacted, mapping)
        assert restored == text


# ─── Detection vs redaction principle ────────────────────────────────────────

class TestDetectionVsRedaction:
    def test_finance_default_does_not_redact_dollar_amounts(self, finance_shield: Shield):
        text = "Acquisition value $5M by Apollo and contact alice@example.com."
        redacted, _ = finance_shield.redact(text)
        assert "$5M" in redacted, "Dollar amounts must survive default finance redaction"
        assert "alice@example.com" not in redacted
        assert "Apollo" not in redacted

    def test_finance_default_does_not_redact_leverage_ratios(self, finance_shield: Shield):
        text = "5.2x EBITDA multiple, 20% carry, 8% hurdle. Sponsored by KKR."
        redacted, _ = finance_shield.redact(text)
        assert "5.2x EBITDA" in redacted
        assert "20% carry" in redacted
        assert "KKR" not in redacted

    def test_therapy_default_preserves_diagnosis_and_medication(self, therapy_shield: Shield):
        # Diagnosis/medication are clinical content — not in default redact set,
        # the model needs them to reason about treatment.
        text = (
            "Patient John Doe diagnosed with F33.1, prescribed Sertraline 100mg daily."
        )
        redacted, _ = therapy_shield.redact(text)
        assert "John Doe" not in redacted
        assert "F33.1" in redacted
        assert "Sertraline" in redacted


# ─── Token format ────────────────────────────────────────────────────────────

class TestTokenFormat:
    def test_tokens_match_expected_format(self, finance_shield: Shield):
        text = "John Smith from Goldman Sachs emailed me at john@goldman.com."
        redacted, mapping = finance_shield.redact(text)
        tokens = TOKEN_RE.findall(redacted)
        assert len(tokens) >= 1
        for tok in tokens:
            assert tok in mapping.tokens
            assert mapping.tokens[tok]  # original value non-empty

    def test_repeated_value_within_call_gets_same_token(self, finance_shield: Shield):
        text = (
            "John Smith met with the CEO. "
            "John Smith then emailed Apollo. "
            "John Smith signed the term sheet."
        )
        redacted, mapping = finance_shield.redact(text)
        tokens_for_john = [tok for tok, val in mapping.tokens.items() if val == "John Smith"]
        assert len(tokens_for_john) == 1, "Same value in same call must reuse token"
        assert redacted.count(tokens_for_john[0]) == 3

    def test_different_calls_produce_different_tokens(self, finance_shield: Shield):
        text = "John Smith works at Apollo."
        _, mapping_a = finance_shield.redact(text)
        _, mapping_b = finance_shield.redact(text)
        # Same originals, but salt differs → different tokens
        assert set(mapping_a.tokens.keys()) != set(mapping_b.tokens.keys())


# ─── redact_categories override ──────────────────────────────────────────────

class TestRedactCategoriesOverride:
    def test_explicit_categories_beat_profile_defaults(self, legal_shield: Shield):
        # Legal default includes CaseNumber; override to Email-only.
        text = "Case No. 25-cr-00503 — contact alice@law.com for details."
        redacted, mapping = legal_shield.redact(text, redact_categories=["Email"])
        assert "alice@law.com" not in redacted
        assert "25-cr-00503" in redacted
        assert mapping.categories_redacted == ["Email"]

    def test_empty_categories_returns_text_unchanged(self, finance_shield: Shield):
        text = "John Smith and Apollo and john@apollo.com."
        redacted, mapping = finance_shield.redact(text, redact_categories=[])
        assert redacted == text
        assert mapping.tokens == {}

    def test_unknown_categories_logged_and_skipped(
        self, finance_shield: Shield, caplog: pytest.LogCaptureFixture
    ):
        with caplog.at_level("WARNING"):
            redacted, mapping = finance_shield.redact(
                "John Smith works here.",
                redact_categories=["NotARealCategory"],
            )
        assert any("Unknown redaction categories" in m for m in caplog.messages)
        # Nothing valid → nothing redacted
        assert redacted == "John Smith works here."
        assert mapping.tokens == {}

    def test_raw_entity_type_accepted_as_escape_hatch(self, finance_shield: Shield):
        # Power-user: pass an underlying entity type directly.
        text = "Contact Goldman Sachs about the deal."
        redacted, mapping = finance_shield.redact(
            text, redact_categories=["INSTITUTION_NAME"],
        )
        assert "Goldman Sachs" not in redacted
        assert any("Goldman Sachs" == v for v in mapping.tokens.values())


# ─── Profile-specific defaults (OGE-309) ─────────────────────────────────────

class TestProfileSpecificDefaults:
    def test_legal_defaults_include_case_and_bates(self):
        cats = PROFILE_REDACT_CATEGORIES["shield-legal"]
        assert "CaseNumber" in cats
        assert "BatesNumber" in cats
        assert set(DEFAULT_REDACT_CATEGORIES).issubset(set(cats))

    def test_therapy_defaults_include_dob_and_insurance(self):
        cats = PROFILE_REDACT_CATEGORIES["shield-therapy"]
        assert "DateOfBirth" in cats
        assert "InsuranceId" in cats
        assert "MedicalLicense" in cats
        assert set(DEFAULT_REDACT_CATEGORIES).issubset(set(cats))

    def test_finance_defaults_match_global_default(self):
        assert PROFILE_REDACT_CATEGORIES["shield-finance"] == DEFAULT_REDACT_CATEGORIES

    def test_resolve_uses_caller_override_first(self):
        cats = _resolve_categories("shield-finance", ["Email"])
        assert cats == ["Email"]

    def test_resolve_uses_profile_default_when_no_override(self):
        cats = _resolve_categories("shield-therapy", None)
        assert "DateOfBirth" in cats

    def test_resolve_falls_back_to_global_default(self):
        cats = _resolve_categories(None, None)
        assert cats == list(DEFAULT_REDACT_CATEGORIES)


# ─── Mapping shape + audit fields ────────────────────────────────────────────

class TestMapping:
    def test_mapping_records_profile_and_categories(self, finance_shield: Shield):
        text = "John Smith from Apollo."
        _, mapping = finance_shield.redact(text)
        assert mapping.profile_id == "shield-finance"
        assert mapping.categories_redacted == DEFAULT_REDACT_CATEGORIES
        assert mapping.text_hash.startswith("sha256:")
        assert mapping.created_at  # ISO timestamp set

    def test_unredact_with_empty_mapping_is_identity(self):
        m = RedactionMapping()
        assert unredact_text("anything", m) == "anything"

    def test_unredact_skips_missing_tokens(self):
        m = RedactionMapping(tokens={"[Person_aaaaaa]": "Alice"})
        # Token absent → text passes through unchanged
        assert unredact_text("just plain text", m) == "just plain text"


# ─── Pure-function entry points (no Shield needed) ───────────────────────────

class TestPureRedactText:
    def test_redact_text_with_synthetic_entities(self):
        text = "Hello Alice, please email bob@example.com."
        entities = [
            DetectedEntity(
                text="Alice",
                category="PERSON",
                category_group=CategoryGroup.PII,
                confidence=0.9,
                detection_layer=DetectionLayer.NER,
                start=6,
                end=11,
            ),
            DetectedEntity(
                text="bob@example.com",
                category="EMAIL_ADDRESS",
                category_group=CategoryGroup.PII,
                confidence=0.99,
                detection_layer=DetectionLayer.REGEX,
                start=26,
                end=41,
            ),
        ]
        redacted, mapping = redact_text(text, entities, profile_id=None)
        assert "Alice" not in redacted
        assert "bob@example.com" not in redacted
        assert unredact_text(redacted, mapping) == text

    def test_overlapping_entities_keep_longer_span(self):
        # "John Smith" (PERSON, 0..10) overlaps a fake nested PERSON "John" (0..4).
        text = "John Smith called."
        entities = [
            DetectedEntity(
                text="John Smith", category="PERSON", category_group=CategoryGroup.PII,
                confidence=0.95, detection_layer=DetectionLayer.NER, start=0, end=10,
            ),
            DetectedEntity(
                text="John", category="PERSON", category_group=CategoryGroup.PII,
                confidence=0.85, detection_layer=DetectionLayer.NER, start=0, end=4,
            ),
        ]
        redacted, mapping = redact_text(text, entities, profile_id=None)
        # Only one token, for the longer span
        assert len(mapping.tokens) == 1
        assert "John Smith" in mapping.tokens.values()
        assert " called." in redacted


# ─── Internal helpers ────────────────────────────────────────────────────────

class TestInternals:
    def test_expand_entity_types_handles_labels_and_raw_types(self):
        out = _expand_entity_types(["Person", "EMAIL_ADDRESS"])
        assert "PERSON" in out
        assert "EXECUTIVE_NAME" in out
        assert "EMAIL_ADDRESS" in out

    def test_label_for_known_entity(self):
        assert _label_for("EXECUTIVE_NAME") == "Person"
        assert _label_for("INSTITUTION_NAME") == "Sponsor"

    def test_label_for_unknown_entity_falls_back_to_titlecase(self):
        assert _label_for("UNKNOWN_THING") == "UnknownThing"
