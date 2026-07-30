"""Tests for v0.5.0 deprecation warnings (OGE-1010).

Ensures the old method names still work but emit DeprecationWarning,
pointing users to ogentic-redact for production workflows.
"""

from __future__ import annotations

import warnings

import pytest

from ogentic_shield import Shield, redact_text, unredact_text
from ogentic_shield.models import CategoryGroup, DetectedEntity, DetectionLayer


class TestShieldMethodDeprecation:
    """Tests for Shield method deprecations."""

    def test_redact_deprecated_warning(self):
        shield = Shield(profiles=["shield-finance"])
        text = "Contact john@example.com about the merger."

        with pytest.warns(DeprecationWarning, match="Shield.redact.*is deprecated.*v1.0.*redact_simple_text"):
            redacted, mapping = shield.redact(text)

        # Verify it still works
        assert "john@example.com" not in redacted
        assert mapping.tokens

    def test_redact_text_deprecated_warning(self):
        shield = Shield(profiles=["shield-finance"])
        text = "Contact john@example.com about the merger."

        with pytest.warns(DeprecationWarning, match="Shield.redact_text.*is deprecated.*v1.0.*redact_simple_text"):
            redacted, mapping = shield.redact_text(text)

        # Verify it still works
        assert "john@example.com" not in redacted
        assert mapping.tokens

    def test_unredact_deprecated_warning(self):
        shield = Shield(profiles=["shield-finance"])
        text = "Contact john@example.com"
        redacted, mapping = shield.redact_simple_text(text)

        with pytest.warns(DeprecationWarning, match="Shield.unredact.*is deprecated.*v1.0.*unredact_simple"):
            restored = Shield.unredact(redacted, mapping)

        # Verify it still works
        assert restored == text

    def test_redact_document_deprecated_warning(self, tmp_path):
        shield = Shield(profiles=["shield-legal"])
        doc = tmp_path / "test.txt"
        doc.write_text("Email alice@example.com for details.")

        with pytest.warns(
            DeprecationWarning,
            match="Shield.redact_document.*is deprecated.*v1.0.*redact_simple_document"
        ):
            result = shield.redact_document(doc)

        # Verify it still works
        assert "alice@example.com" not in result.redacted_text
        assert result.mapping.tokens

    def test_new_methods_no_warning(self):
        """New method names should not emit warnings."""
        shield = Shield(profiles=["shield-finance"])
        text = "Contact john@example.com"

        with warnings.catch_warnings():
            warnings.simplefilter("error")  # Turn warnings into errors
            # These should not raise
            redacted, mapping = shield.redact_simple_text(text)
            restored = Shield.unredact_simple(redacted, mapping)
            assert restored == text


class TestModuleFunctionDeprecation:
    """Tests for module-level function deprecations."""

    def test_redact_text_function_deprecated(self):
        text = "Hello Alice"
        entities = [
            DetectedEntity(
                text="Alice",
                category="PERSON",
                category_group=CategoryGroup.PII,
                confidence=0.9,
                detection_layer=DetectionLayer.NER,
                start=6,
                end=11,
            )
        ]

        with pytest.warns(DeprecationWarning, match="redact_text.*is deprecated.*v1.0.*redact_simple_text"):
            redacted, mapping = redact_text(text, entities)

        # Verify it still works
        assert "Alice" not in redacted
        assert mapping.tokens

    def test_unredact_text_function_deprecated(self):
        from ogentic_shield import RedactionMapping

        mapping = RedactionMapping(tokens={"[Person_aaaaaa]": "Alice"})
        text = "Hello [Person_aaaaaa]"

        with pytest.warns(DeprecationWarning, match="unredact_text.*is deprecated.*v1.0.*unredact_simple_text"):
            restored = unredact_text(text, mapping)

        # Verify it still works
        assert restored == "Hello Alice"


class TestAsyncShieldDeprecation:
    """Tests for AsyncShield method deprecations."""

    @pytest.mark.asyncio
    async def test_async_redact_deprecated(self):
        from ogentic_shield import AsyncShield

        shield = AsyncShield(profiles=["shield-finance"])
        text = "Contact john@example.com"

        with pytest.warns(DeprecationWarning, match="AsyncShield.redact.*is deprecated.*v1.0.*redact_simple_text"):
            redacted, mapping = await shield.redact(text)

        # Verify it still works
        assert "john@example.com" not in redacted
        assert mapping.tokens

    @pytest.mark.asyncio
    async def test_async_redact_text_deprecated(self):
        from ogentic_shield import AsyncShield

        shield = AsyncShield(profiles=["shield-finance"])
        text = "Contact john@example.com"

        with pytest.warns(DeprecationWarning, match="AsyncShield.redact_text.*is deprecated.*v1.0.*redact_simple_text"):
            redacted, mapping = await shield.redact_text(text)

        # Verify it still works
        assert "john@example.com" not in redacted
        assert mapping.tokens

    @pytest.mark.asyncio
    async def test_async_unredact_deprecated(self):
        from ogentic_shield import AsyncShield

        shield = AsyncShield(profiles=["shield-finance"])
        text = "Contact john@example.com"
        redacted, mapping = await shield.redact_simple_text(text)

        with pytest.warns(DeprecationWarning, match="AsyncShield.unredact.*is deprecated.*v1.0.*unredact_simple"):
            restored = await AsyncShield.unredact(redacted, mapping)

        # Verify it still works
        assert restored == text
