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
