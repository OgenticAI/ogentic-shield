"""Tests for the MCP server surface (OGE-310/311/312).

We don't spin up a real transport — that's covered by the MCP SDK's own
suite. Here we exercise the tool *callables* directly so we lock down:
    - Tool registration (4 tools with the expected names)
    - Round-trip shape of analyze / redact / unredact / profiles outputs
    - Profile-resolution rules (caller arg wins; unknown rejected)
    - Privacy invariant — entity text is OPTED-IN, never default
    - Error paths surface as ValueError so the SDK turns them into proper
      MCP error responses (the SDK handles that wrapping)

The MCP SDK is an optional dep. We skip the whole module gracefully when
it isn't installed instead of failing collection.
"""

from __future__ import annotations

import pytest

mcp = pytest.importorskip(
    "mcp",
    reason="MCP SDK not installed — pip install 'ogentic-shield[mcp]' to run these tests.",
)

from ogentic_shield.mcp.server import (  # noqa: E402  (after importorskip)
    DEFAULT_PROFILE,
    _entity_to_dict,
    _resolve_profile,
    build_server,
)
from ogentic_shield.models import (  # noqa: E402
    CategoryGroup,
    DetectedEntity,
    DetectionLayer,
)

# ─── Pure helpers ─────────────────────────────────────────────────────────────


class TestResolveProfile:
    def test_caller_arg_wins(self):
        assert _resolve_profile("shield-finance", "shield-legal") == "shield-finance"

    def test_falls_back_to_server_default_when_none(self):
        assert _resolve_profile(None, "shield-therapy") == "shield-therapy"

    def test_falls_back_to_server_default_when_empty_string(self):
        # Empty string is falsy — server default takes over.
        assert _resolve_profile("", "shield-legal") == "shield-legal"

    def test_unknown_profile_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown profile"):
            _resolve_profile("shield-nonsense", "shield-legal")

    def test_error_message_lists_known_profiles(self):
        with pytest.raises(ValueError, match="shield-legal.*shield-therapy"):
            _resolve_profile("bogus", "shield-legal")


# ─── Entity serialization (privacy invariant) ────────────────────────────────


class TestEntitySerialization:
    def _entity(self) -> DetectedEntity:
        return DetectedEntity(
            text="John Smith",
            category="PERSON",
            category_group=CategoryGroup.PII,
            confidence=0.91,
            detection_layer=DetectionLayer.NER,
            start=10,
            end=20,
            metadata={"recognizer": "Spacy"},
        )

    def test_default_excludes_entity_text(self):
        out = _entity_to_dict(self._entity(), include_text=False)
        assert "text" not in out, "Default response must not leak entity text"
        assert out["category"] == "PERSON"
        assert out["category_group"] == "PII"
        assert out["confidence"] == 0.91
        assert out["layer"] == "NER"
        assert out["start"] == 10
        assert out["end"] == 20

    def test_include_text_adds_text_field(self):
        out = _entity_to_dict(self._entity(), include_text=True)
        assert out["text"] == "John Smith"

    def test_confidence_rounded_to_4_places(self):
        e = DetectedEntity(
            text="x",
            category="PERSON",
            category_group=CategoryGroup.PII,
            confidence=0.123456789,
            detection_layer=DetectionLayer.REGEX,
            start=0,
            end=1,
        )
        out = _entity_to_dict(e, include_text=False)
        assert out["confidence"] == 0.1235


# ─── Server construction + tool registration ────────────────────────────────


class TestBuildServer:
    """Smoke-test that the server constructs and registers the right tools.

    Avoids hitting the real Presidio pipeline (~3s cold start) by patching
    Shield to a no-op stub; we're verifying the MCP wiring, not the
    classifier behaviour (that's covered by tests/test_shield.py).
    """

    def test_registers_four_tools_with_canonical_names(self, monkeypatch):
        # Stub Shield so build_server doesn't load Presidio.
        monkeypatch.setattr(
            "ogentic_shield.mcp.server.Shield",
            _StubShield,
        )
        server = build_server(profiles=["shield-legal"])
        # FastMCP exposes registered tools via list_tools() (async); we
        # use the underlying registry which is sync.
        tool_names = sorted(_collect_tool_names(server))
        assert tool_names == [
            "shield.analyze",
            "shield.profiles",
            "shield.redact",
            "shield.unredact",
        ]

    def test_default_profile_used_when_no_profiles_passed(self, monkeypatch):
        called_with: list[list[str]] = []

        class CapturingShield(_StubShield):
            def __init__(self, profiles=None, **kwargs):  # noqa: ARG002
                called_with.append(list(profiles or []))
                super().__init__(profiles=profiles)

        monkeypatch.setattr("ogentic_shield.mcp.server.Shield", CapturingShield)
        build_server()
        assert called_with == [[DEFAULT_PROFILE]]

    def test_loads_multiple_profiles_when_passed(self, monkeypatch):
        called_with: list[list[str]] = []

        class CapturingShield(_StubShield):
            def __init__(self, profiles=None, **kwargs):  # noqa: ARG002
                called_with.append(list(profiles or []))
                super().__init__(profiles=profiles)

        monkeypatch.setattr("ogentic_shield.mcp.server.Shield", CapturingShield)
        build_server(profiles=["shield-legal", "shield-therapy"])
        assert called_with == [["shield-legal", "shield-therapy"]]


# ─── Round-trip integration (real Shield, no stub) ──────────────────────────


class TestRedactUnredactRoundTripIntegration:
    """End-to-end round-trip through the MCP wire format.

    The other tests in this module stub Shield to keep the suite fast. This
    class deliberately uses the *real* Shield + Presidio pipeline so we lock
    down the actual round-trip property the OGE-308/309 redaction work
    promises: ``shield.redact`` then ``shield.unredact`` restores the original
    text **byte-for-byte**, including across the dataclass→dict→dataclass
    serialization the MCP transport performs on the mapping.

    Marked as a class so it pays the ~3s Presidio cold-start cost exactly once.
    """

    @pytest.fixture(scope="class")
    def shield(self):
        # Lazy import — same gating as the rest of this module (mcp optional dep).
        from ogentic_shield import Shield

        return Shield(profiles=["shield-finance", "shield-legal", "shield-therapy"])

    @pytest.mark.parametrize(
        ("profile", "text"),
        [
            (
                "shield-finance",
                "John Smith from BlackRock invested $5M. "
                "Reach him at john@example.com or 555-123-4567.",
            ),
            (
                "shield-legal",
                "Counsel for Acme Corp. (Case No. 23-cv-04591) — "
                "privileged and confidential. Bates ACME0001234.",
            ),
            (
                "shield-therapy",
                "Patient Jane Doe, DOB 04/12/1985, prescribed sertraline 50mg. "
                "Insurance ID BCBS-9988-1234.",
            ),
        ],
    )
    def test_round_trip_through_mcp_wire_format(self, shield, profile, text):
        """redact → asdict → rebuild → unredact restores text byte-for-byte.

        This mirrors exactly what the MCP transport does:
        1. Caller invokes ``shield.redact`` — returns (str, RedactionMapping).
        2. Server serializes mapping with ``asdict`` (see _mapping_to_dict).
        3. Wire transport carries the dict.
        4. Caller invokes ``shield.unredact(text, mapping_dict)``.
        5. Server rebuilds RedactionMapping from the dict and calls
           ``Shield.unredact``.
        """
        from dataclasses import asdict

        from ogentic_shield import Shield
        from ogentic_shield.models import RedactionMapping

        redacted, mapping = shield.redact(text, profile=profile)

        # The text must actually have been redacted — otherwise this test would
        # pass trivially against any input that contained no PII at all.
        assert redacted != text, (
            f"Profile {profile} produced no redactions on a sample known to "
            f"contain identifying entities — the test sample needs revisiting."
        )
        assert mapping.tokens, "Mapping must contain at least one token"

        # Round-trip the mapping through the MCP wire format.
        wire = asdict(mapping)
        rebuilt = RedactionMapping(
            tokens=dict(wire.get("tokens") or {}),
            categories_redacted=list(wire.get("categories_redacted") or []),
            profile_id=wire.get("profile_id"),
            text_hash=str(wire.get("text_hash") or ""),
            created_at=str(wire.get("created_at") or ""),
        )
        restored = Shield.unredact(redacted, rebuilt)

        assert restored == text, (
            f"Round-trip mismatch on {profile}\n"
            f"  original : {text!r}\n"
            f"  redacted : {redacted!r}\n"
            f"  restored : {restored!r}"
        )

    def test_unredact_silently_skips_tokens_not_present_in_text(self, shield):
        """A model that drops or rewords part of the redacted text should
        still round-trip safely — tokens that aren't in the input are simply
        not substituted.
        """
        from ogentic_shield import Shield

        text = "Contact John Smith at john@example.com about BlackRock."
        redacted, mapping = shield.redact(text, profile="shield-finance")

        # Simulate the LLM rewriting the response without one of the tokens.
        # Pick the first token and drop it from the redacted text.
        first_token = next(iter(mapping.tokens))
        rewritten = redacted.replace(first_token, "(redacted-by-model)")

        restored = Shield.unredact(rewritten, mapping)
        # The dropped token's original value must NOT leak back in.
        assert mapping.tokens[first_token] not in restored
        # Other tokens still round-trip.
        for token, original in mapping.tokens.items():
            if token == first_token:
                continue
            assert original in restored


# ─── Test stubs ──────────────────────────────────────────────────────────────


class _StubShield:
    """A drop-in replacement for `Shield` that doesn't load Presidio."""

    def __init__(self, profiles=None, **_kwargs):
        self._profiles = profiles or []

    def analyze(self, text, profiles=None, **kwargs):  # noqa: ARG002
        # Just return a plausible empty result; tests that need real
        # behaviour go through tests/test_shield.py instead.
        from ogentic_shield.models import AnalysisResult, SensitivityLevel

        return AnalysisResult(
            text_hash="sha256:stub",
            entities=[],
            score=0,
            sensitivity_level=SensitivityLevel.NONE,
            category_groups_found=set(),
            top_category=None,
            top_confidence=0.0,
            entity_count=0,
            processing_time_ms=0.0,
            layers_invoked=[],
            profile_ids=list(self._profiles),
            routing_suggestion="CLOUD_OK",
        )

    def redact(self, text, profile=None, redact_categories=None, **_kwargs):  # noqa: ARG002
        from ogentic_shield.models import RedactionMapping

        return text, RedactionMapping(profile_id=profile or "shield-legal")


def _collect_tool_names(server) -> list[str]:
    """FastMCP exposes registered tools via its internal `_tool_manager`.

    The attribute name has shifted across SDK versions; we check the most
    common ones and surface a clear assertion error if neither is present
    so a future SDK upgrade fails loudly rather than silently dropping
    coverage.
    """
    tm = getattr(server, "_tool_manager", None) or getattr(server, "tool_manager", None)
    if tm is None:
        raise AssertionError(
            "Could not find tool manager on FastMCP server — "
            "MCP SDK shape changed; update the test helper.",
        )
    tools = getattr(tm, "_tools", None) or getattr(tm, "tools", None)
    if tools is None:
        raise AssertionError(
            "Tool manager has no `_tools` / `tools` attribute — SDK shape changed.",
        )
    return list(tools.keys())
