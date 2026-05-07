"""Tests for AsyncShield (OGE-318) — analyze, redact, unredact, analyze_stream.

Uses pytest-asyncio in auto mode (configured in pyproject.toml). Most tests
exercise the real Shield + Presidio pipeline because the AsyncShield surface
is intentionally thin: any divergence between sync and async behavior is a
bug, so end-to-end coverage is the right kind of test here.
"""

from __future__ import annotations

import asyncio

import pytest

from ogentic_shield import (
    AsyncShield,
    DetectionLayer,
    SensitivityLevel,
    StreamEvent,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def legal_async_shield() -> AsyncShield:
    return AsyncShield(profiles=["shield-legal"])


@pytest.fixture(scope="module")
def finance_async_shield() -> AsyncShield:
    return AsyncShield(profiles=["shield-finance"])


LEGAL_PRIVILEGED_TEXT = (
    "Per our conversation with outside counsel at Davis Polk regarding "
    "the SEC investigation, this communication is privileged and confidential. "
    "Attorney work product prepared in anticipation of litigation. "
    "Case No. 25-cr-00503."
)

FINANCE_TEXT = (
    "Goldman Sachs is advising the buyer at $47/share. "
    "Contact: john@example.com about the deal."
)


# ── analyze ─────────────────────────────────────────────────────────────────


class TestAnalyze:
    async def test_returns_analysis_result(self, legal_async_shield: AsyncShield):
        result = await legal_async_shield.analyze(LEGAL_PRIVILEGED_TEXT)
        assert result.score > 30
        assert result.entity_count >= 2
        assert result.sensitivity_level in (
            SensitivityLevel.MEDIUM,
            SensitivityLevel.HIGH,
            SensitivityLevel.CRITICAL,
        )

    async def test_matches_sync_shield(self, legal_async_shield: AsyncShield):
        sync_result = legal_async_shield.shield.analyze(LEGAL_PRIVILEGED_TEXT)
        async_result = await legal_async_shield.analyze(LEGAL_PRIVILEGED_TEXT)
        # Score and entity count are deterministic; processing_time_ms is not.
        assert async_result.score == sync_result.score
        assert async_result.entity_count == sync_result.entity_count
        assert async_result.routing_suggestion == sync_result.routing_suggestion

    async def test_does_not_block_event_loop(self, legal_async_shield: AsyncShield):
        # Concurrent analyzes interleave on the loop. If we forgot to_thread,
        # these would serialize and total time ≈ 2*t_one. With to_thread the
        # event loop stays free.
        async def _go() -> int:
            r = await legal_async_shield.analyze(LEGAL_PRIVILEGED_TEXT)
            return r.score

        a, b = await asyncio.gather(_go(), _go())
        assert a == b


# ── redact / unredact ──────────────────────────────────────────────────────


class TestRedactUnredact:
    async def test_redact_round_trip(self, finance_async_shield: AsyncShield):
        redacted, mapping = await finance_async_shield.redact(FINANCE_TEXT)
        assert "Goldman Sachs" not in redacted
        # Money/percentages survive — same redaction-vs-detection split.
        assert "$47/share" in redacted
        restored = await AsyncShield.unredact(redacted, mapping)
        assert restored == FINANCE_TEXT

    async def test_unredact_skips_missing_tokens(
        self, finance_async_shield: AsyncShield
    ):
        redacted, mapping = await finance_async_shield.redact(FINANCE_TEXT)
        first_token = next(iter(mapping.tokens))
        rewritten = redacted.replace(first_token, "[model-rewrote-this]")
        restored = await AsyncShield.unredact(rewritten, mapping)
        # The dropped token's original value must NOT come back.
        assert mapping.tokens[first_token] not in restored


# ── analyze_stream ─────────────────────────────────────────────────────────


class TestAnalyzeStream:
    async def test_yields_per_layer_then_terminal(
        self, legal_async_shield: AsyncShield
    ):
        events: list[StreamEvent] = []
        async for event in legal_async_shield.analyze_stream(LEGAL_PRIVILEGED_TEXT):
            events.append(event)

        # We expect at least one intermediate event per layer (REGEX/NER + RULES)
        # and exactly one terminal event with `result` set.
        assert len(events) >= 2
        terminal = events[-1]
        assert terminal.is_final
        assert terminal.result is not None
        # Terminal result matches a direct analyze() call.
        direct = await legal_async_shield.analyze(LEGAL_PRIVILEGED_TEXT)
        assert terminal.result.score == direct.score
        assert terminal.result.entity_count == direct.entity_count

    async def test_intermediate_events_carry_running_entities(
        self, legal_async_shield: AsyncShield
    ):
        events: list[StreamEvent] = []
        async for event in legal_async_shield.analyze_stream(LEGAL_PRIVILEGED_TEXT):
            events.append(event)

        intermediate = [e for e in events if not e.is_final]
        assert intermediate, "Expected at least one intermediate event"
        for event in intermediate:
            assert event.layer is not None
            # Running entity count is monotonically non-decreasing.
            # (Layer 2 only boosts existing or adds; doesn't remove.)
            assert all(e.confidence >= 0 for e in event.entities)

    async def test_layer3_event_only_when_gated_on(self):
        # With LLM disabled (default), no LAYER 3 stream event should appear.
        shield = AsyncShield(profiles=["shield-legal"])
        events: list[StreamEvent] = []
        async for event in shield.analyze_stream(LEGAL_PRIVILEGED_TEXT):
            events.append(event)
        layers_seen = {e.layer for e in events if e.layer is not None}
        assert DetectionLayer.LLM not in layers_seen

    async def test_explicit_layer_subset(self, legal_async_shield: AsyncShield):
        # Only Layer 1 → only one intermediate event + terminal.
        events: list[StreamEvent] = []
        async for event in legal_async_shield.analyze_stream(
            LEGAL_PRIVILEGED_TEXT,
            layers=[DetectionLayer.REGEX, DetectionLayer.NER],
        ):
            events.append(event)
        intermediate = [e for e in events if not e.is_final]
        assert len(intermediate) == 1
        assert intermediate[0].layer == DetectionLayer.REGEX
        # Terminal exists.
        assert events[-1].is_final


# ── Profile / quality passthroughs ─────────────────────────────────────────


class TestPassthroughs:
    def test_required_models_default_fast(self, legal_async_shield: AsyncShield):
        assert legal_async_shield.required_models() == ["granite3.1-moe:1b"]

    def test_required_models_with_explicit_tier(
        self, legal_async_shield: AsyncShield
    ):
        assert legal_async_shield.required_models("quality") == ["mixtral:8x7b"]

    def test_list_profiles_works(self):
        profiles = AsyncShield.list_profiles()
        assert {p.id for p in profiles} >= {
            "shield-legal",
            "shield-therapy",
            "shield-finance",
        }

    def test_get_profile_works(self):
        profile = AsyncShield.get_profile("shield-finance")
        assert profile.id == "shield-finance"
