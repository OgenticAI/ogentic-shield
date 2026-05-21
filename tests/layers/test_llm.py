"""Tests for Layer 3 LLM orchestration (OGE-313 + OGE-314).

All tests run without a real Ollama install — the ``_FakeOllama`` module
fixture monkeypatches ``ollama.Client`` so we exercise every branch of
:func:`ogentic_shield.layers.llm.run_layer3` and the
:class:`ogentic_shield.layers.llm_client.OllamaClient` retry/fallback paths
deterministically.
"""

from __future__ import annotations

import json
import sys
import types
from typing import Any

import pytest

from ogentic_shield.config import LlmConfig
from ogentic_shield.layers import llm as llm_module
from ogentic_shield.layers import llm_client as llm_client_module
from ogentic_shield.layers.llm import run_layer3
from ogentic_shield.layers.llm_client import (
    LocalhostOnlyError,
    OllamaClient,
    _validate_localhost,
)
from ogentic_shield.layers.llm_schema import LlmResponse
from ogentic_shield.models import (
    CategoryGroup,
    ConfigError,
    DetectedEntity,
    DetectionLayer,
)
from ogentic_shield.profiles import get_profile

# ── Fake ollama module ──────────────────────────────────────────────────────


class _FakeOllamaResponse:
    def __init__(self, content: str):
        self.message = types.SimpleNamespace(content=content)


class _FakeOllamaClient:
    """Stand-in for ollama.Client that yields a scripted sequence of responses.

    Each item in ``responses`` is either a JSON string (returned verbatim)
    or an Exception (raised on .chat()). Tests script responses per-call.
    """

    def __init__(self, responses: list[str | Exception]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(self, *, model: str, messages: list[dict[str, str]], format: Any, options: dict[str, Any]) -> Any:
        self.calls.append(
            {"model": model, "messages": messages, "format": format, "options": options}
        )
        if not self._responses:
            raise RuntimeError("FakeOllamaClient exhausted — test script too short")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeOllamaResponse(item)


def _install_fake_ollama(monkeypatch: pytest.MonkeyPatch, fake_client: _FakeOllamaClient) -> None:
    """Inject a fake `ollama` module into sys.modules and rebuild OllamaClient hooks."""
    fake_module = types.ModuleType("ollama")
    fake_module.Client = lambda host, timeout: fake_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ollama", fake_module)


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[str | Exception],
    *,
    max_retries: int = 2,
    endpoint: str = "http://localhost:11434",
) -> tuple[OllamaClient, _FakeOllamaClient]:
    fake = _FakeOllamaClient(responses)
    _install_fake_ollama(monkeypatch, fake)
    client = OllamaClient(
        endpoint=endpoint,
        model="granite3.1-moe:1b",
        timeout_ms=1000,
        max_retries=max_retries,
    )
    return client, fake


# ── Localhost validator ─────────────────────────────────────────────────────


class TestLocalhostInvariant:
    @pytest.mark.parametrize(
        "endpoint",
        ["http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434"],
    )
    def test_accepts_localhost(self, endpoint: str):
        _validate_localhost(endpoint)  # no raise

    @pytest.mark.parametrize(
        "endpoint",
        [
            "http://api.openai.com",
            "https://example.com",
            "http://192.168.1.50:11434",
            "http://my-ollama.internal",
            "ftp://localhost:11434",
        ],
    )
    def test_rejects_non_localhost(self, endpoint: str):
        with pytest.raises(LocalhostOnlyError):
            _validate_localhost(endpoint)

    def test_constructor_rejects_non_localhost(self):
        with pytest.raises(LocalhostOnlyError):
            OllamaClient(endpoint="http://api.openai.com", model="x")

    def test_config_rejects_non_localhost_when_enabled(self):
        with pytest.raises(ConfigError):
            LlmConfig(enabled=True, endpoint="http://example.com")

    def test_config_allows_non_localhost_when_disabled(self):
        # Disabled means we never connect — allow the value to sit in the
        # config so `enabled: false` users aren't penalized for typos that
        # don't matter yet.
        LlmConfig(enabled=False, endpoint="http://example.com")  # no raise


# ── OllamaClient.classify ───────────────────────────────────────────────────


class TestOllamaClientClassify:
    def test_returns_none_when_ollama_missing(self, monkeypatch: pytest.MonkeyPatch):
        # No fake module installed — import inside _build_client fails.
        monkeypatch.setitem(sys.modules, "ollama", None)
        client = OllamaClient(endpoint="http://localhost:11434", model="x", timeout_ms=100)
        assert client.classify("prompt", LlmResponse) is None

    def test_parses_valid_response(self, monkeypatch: pytest.MonkeyPatch):
        payload = json.dumps(
            {
                "detections": [
                    {
                        "category": "PRIVILEGE_MARKER",
                        "span_text": "privileged",
                        "confidence": 0.9,
                        "reasoning": "test",
                    }
                ]
            }
        )
        client, _ = _make_client(monkeypatch, [payload])
        response = client.classify("prompt", LlmResponse)
        assert response is not None
        assert len(response.detections) == 1
        assert response.detections[0].category == "PRIVILEGE_MARKER"

    def test_retries_on_invalid_json_then_succeeds(self, monkeypatch: pytest.MonkeyPatch):
        valid = json.dumps({"detections": []})
        client, fake = _make_client(monkeypatch, ["not-json", valid])
        response = client.classify("prompt", LlmResponse)
        assert response is not None
        assert len(fake.calls) == 2

    def test_returns_none_after_exhausting_retries(self, monkeypatch: pytest.MonkeyPatch):
        client, fake = _make_client(monkeypatch, ["bad", "still-bad", "nope"], max_retries=2)
        assert client.classify("prompt", LlmResponse) is None
        assert len(fake.calls) == 3

    def test_returns_none_on_connection_error(self, monkeypatch: pytest.MonkeyPatch):
        class FakeConnectError(Exception):
            pass

        # Class name contains "connect" → treated as transport-level failure.
        FakeConnectError.__name__ = "ConnectError"
        client, fake = _make_client(monkeypatch, [FakeConnectError("boom")])
        assert client.classify("prompt", LlmResponse) is None
        # Should NOT retry — connection errors short-circuit.
        assert len(fake.calls) == 1


# ── run_layer3 orchestration ────────────────────────────────────────────────


@pytest.fixture
def legal_profile_list():
    return [get_profile("shield-legal")]


def _enabled_config(model: str = "granite3.1-moe:1b", **overrides: Any) -> dict[str, Any]:
    base = {
        "enabled": True,
        "endpoint": "http://localhost:11434",
        "model": model,
        "timeout_ms": 1000,
        "max_retries": 0,
        "quality": "fast",
        "ambiguous_score_range": [20, 60],
    }
    base.update(overrides)
    return base


class TestRunLayer3:
    def test_disabled_returns_existing_unchanged(self, legal_profile_list):
        existing = [
            DetectedEntity(
                text="x",
                category="CASE_NUMBER",
                category_group=CategoryGroup.CONFIDENTIAL,
                confidence=0.5,
                detection_layer=DetectionLayer.REGEX,
                start=0,
                end=1,
            )
        ]
        result = run_layer3(
            "x",
            existing,
            legal_profile_list,
            score=30,
            config={"enabled": False},
        )
        assert result is existing

    def test_no_config_returns_existing_unchanged(self, legal_profile_list):
        result = run_layer3("text", [], legal_profile_list, 30, None)
        assert result == []

    def test_non_localhost_endpoint_returns_existing(self, legal_profile_list):
        existing: list[DetectedEntity] = []
        result = run_layer3(
            "text",
            existing,
            legal_profile_list,
            30,
            _enabled_config(endpoint="http://api.openai.com"),
        )
        assert result is existing  # falls back, doesn't raise

    def test_appends_new_entities_from_llm(
        self, monkeypatch: pytest.MonkeyPatch, legal_profile_list
    ):
        text = (
            "Note from outside counsel: please retain this work product "
            "in anticipation of litigation."
        )
        payload = json.dumps(
            {
                "detections": [
                    {
                        "category": "WORK_PRODUCT",
                        "span_text": "work product",
                        "confidence": 0.9,
                        "reasoning": "doctrine term",
                    }
                ]
            }
        )
        _make_client(monkeypatch, [payload])

        result = run_layer3(text, [], legal_profile_list, 30, _enabled_config())

        assert len(result) == 1
        entity = result[0]
        assert entity.detection_layer == DetectionLayer.LLM
        assert entity.category == "WORK_PRODUCT"
        assert entity.category_group == CategoryGroup.PRIVILEGE
        assert entity.start == text.index("work product")
        assert entity.end == entity.start + len("work product")
        # Layer 3 emits raw confidence; the central pipeline calibration in
        # build_analysis_result handles per-layer scaling (OGE-321).
        assert entity.confidence == pytest.approx(0.9)
        assert entity.metadata["model"] == "granite3.1-moe:1b"
        assert entity.metadata["profile"] == "shield-legal"

    def test_drops_hallucinated_span(
        self, monkeypatch: pytest.MonkeyPatch, legal_profile_list
    ):
        # span_text isn't in the input — must be dropped silently.
        payload = json.dumps(
            {
                "detections": [
                    {
                        "category": "PRIVILEGE_MARKER",
                        "span_text": "this exact phrase is not in the text",
                        "confidence": 0.99,
                        "reasoning": "fabricated",
                    }
                ]
            }
        )
        _make_client(monkeypatch, [payload])

        result = run_layer3(
            "An ambiguous note about a meeting.",
            [],
            legal_profile_list,
            30,
            _enabled_config(),
        )
        assert result == []

    def test_drops_unknown_category(
        self, monkeypatch: pytest.MonkeyPatch, legal_profile_list
    ):
        payload = json.dumps(
            {
                "detections": [
                    {
                        "category": "TOTALLY_INVENTED_CATEGORY",
                        "span_text": "meeting",
                        "confidence": 0.9,
                        "reasoning": "wrong",
                    }
                ]
            }
        )
        _make_client(monkeypatch, [payload])
        result = run_layer3(
            "An ambiguous note about a meeting.",
            [],
            legal_profile_list,
            30,
            _enabled_config(),
        )
        assert result == []

    def test_does_not_duplicate_existing_span(
        self, monkeypatch: pytest.MonkeyPatch, legal_profile_list
    ):
        text = "Note about counsel meeting."
        # An existing entity already covers (0..4, "Note") with category COUNSEL_COMMUNICATION.
        existing = [
            DetectedEntity(
                text="Note",
                category="COUNSEL_COMMUNICATION",
                category_group=CategoryGroup.PRIVILEGE,
                confidence=0.7,
                detection_layer=DetectionLayer.RULES,
                start=0,
                end=4,
            )
        ]
        payload = json.dumps(
            {
                "detections": [
                    {
                        "category": "COUNSEL_COMMUNICATION",
                        "span_text": "Note",
                        "confidence": 0.95,
                        "reasoning": "duplicate",
                    }
                ]
            }
        )
        _make_client(monkeypatch, [payload])

        result = run_layer3(text, existing, legal_profile_list, 30, _enabled_config())
        # Only the original — duplicate suppressed.
        assert result == existing

    def test_resolves_model_from_registry_when_unset(
        self, monkeypatch: pytest.MonkeyPatch, legal_profile_list
    ):
        payload = json.dumps({"detections": []})
        _, fake = _make_client(monkeypatch, [payload])
        config = _enabled_config()
        config["model"] = ""  # force registry fallback
        run_layer3("hi", [], legal_profile_list, 30, config)
        assert fake.calls[0]["model"] == "granite3.1-moe:1b"

    def test_returns_existing_when_llm_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, legal_profile_list
    ):
        # Empty response sequence → classify exhausts, returns None.
        # Our orchestrator should return existing entities unchanged.
        existing = [
            DetectedEntity(
                text="x",
                category="CASE_NUMBER",
                category_group=CategoryGroup.CONFIDENTIAL,
                confidence=0.6,
                detection_layer=DetectionLayer.REGEX,
                start=0,
                end=1,
            )
        ]

        # No fake — make ollama unavailable so classify returns None.
        monkeypatch.setitem(sys.modules, "ollama", None)
        result = run_layer3("x", existing, legal_profile_list, 30, _enabled_config())
        assert result == existing

    def test_per_profile_prompts_used(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        # Two profiles → two LLM calls, each receiving its own prompt body.
        payload = json.dumps({"detections": []})
        _, fake = _make_client(monkeypatch, [payload, payload])
        profiles = [get_profile("shield-legal"), get_profile("shield-finance")]

        run_layer3("ambiguous text", [], profiles, 30, _enabled_config())

        assert len(fake.calls) == 2
        legal_prompt = fake.calls[0]["messages"][0]["content"]
        finance_prompt = fake.calls[1]["messages"][0]["content"]
        assert "legal-privilege classifier" in legal_prompt
        assert "Material Non-Public Information" in finance_prompt

    def test_unknown_profile_skips_llm_call(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        # Custom profile registered ad-hoc — no built-in prompt template.
        from ogentic_shield import register_profile
        from ogentic_shield.models import ShieldProfile

        custom = ShieldProfile(
            id="shield-custom-test",
            name="Custom Test Profile",
            version="0.0.1",
            description="No prompt template",
            recognizers=[],
            rules=[],
            scoring_weights={},
            supported_entities=[],
        )
        register_profile(custom)

        # No responses scripted — would raise RuntimeError if classify() called.
        _make_client(monkeypatch, [])
        result = run_layer3("text", [], [custom], 30, _enabled_config())
        assert result == []


# ── OGE-396: Layer 3 as a complementary classifier ─────────────────────────


class TestNarrowAllowedCategories:
    """Unit tests for the per-call allow-list scoping helper."""

    def test_returns_full_set_when_no_existing_entities(self):
        from ogentic_shield.layers.llm_prompts import (
            PROMPTS,
            narrow_allowed_categories,
        )

        narrowed = narrow_allowed_categories("shield-legal", [])
        assert set(narrowed) == set(PROMPTS["shield-legal"].allowed_categories)

    def test_drops_categories_already_covered_by_l1l2(self):
        from ogentic_shield.layers.llm_prompts import narrow_allowed_categories

        existing = [
            DetectedEntity(
                text="outside counsel",
                category="COUNSEL_COMMUNICATION",
                category_group=CategoryGroup.PRIVILEGE,
                confidence=0.9,
                detection_layer=DetectionLayer.REGEX,
                start=0,
                end=15,
            ),
            DetectedEntity(
                text="work product",
                category="WORK_PRODUCT",
                category_group=CategoryGroup.PRIVILEGE,
                confidence=0.85,
                detection_layer=DetectionLayer.REGEX,
                start=20,
                end=32,
            ),
        ]
        narrowed = narrow_allowed_categories("shield-legal", existing)
        # Covered categories stripped.
        assert "COUNSEL_COMMUNICATION" not in narrowed
        assert "WORK_PRODUCT" not in narrowed
        # Other allowed categories preserved.
        assert "CASE_NUMBER" in narrowed
        assert "BATES_NUMBER" in narrowed

    def test_returns_empty_when_every_category_covered(self):
        from ogentic_shield.layers.llm_prompts import (
            PROMPTS,
            narrow_allowed_categories,
        )

        # Synthesize an existing entity for every allowed category.
        existing = [
            DetectedEntity(
                text=f"hit-{i}",
                category=cat,
                category_group=CategoryGroup.PRIVILEGE,  # group is irrelevant here
                confidence=0.5,
                detection_layer=DetectionLayer.REGEX,
                start=i * 10,
                end=i * 10 + 5,
            )
            for i, cat in enumerate(PROMPTS["shield-legal"].allowed_categories)
        ]
        assert narrow_allowed_categories("shield-legal", existing) == ()

    def test_unknown_profile_returns_empty(self):
        from ogentic_shield.layers.llm_prompts import narrow_allowed_categories

        assert narrow_allowed_categories("shield-nonsense", []) == ()


class TestBuildPromptNarrowing:
    """The prompt itself must reflect the narrowed allow-list + covered list."""

    def test_prompt_lists_only_uncovered_categories(self):
        from ogentic_shield.layers.llm_prompts import build_prompt

        existing = [
            DetectedEntity(
                text="outside counsel",
                category="COUNSEL_COMMUNICATION",
                category_group=CategoryGroup.PRIVILEGE,
                confidence=0.9,
                detection_layer=DetectionLayer.REGEX,
                start=0,
                end=15,
            ),
        ]
        prompt = build_prompt("shield-legal", "outside counsel said no", existing)
        assert prompt is not None
        # Covered-categories block names the L1+L2 category.
        assert "ALREADY COVERED" in prompt
        assert "- COUNSEL_COMMUNICATION" in prompt
        # Narrowed-categories block omits the covered one.
        narrowed_section = prompt.split("Allowed categories for THIS call")[1]
        assert "COUNSEL_COMMUNICATION" not in narrowed_section
        # …but still lists uncovered categories.
        assert "WORK_PRODUCT" in narrowed_section
        assert "CASE_NUMBER" in narrowed_section

    def test_prompt_short_circuits_when_all_categories_covered(self):
        from ogentic_shield.layers.llm_prompts import (
            PROMPTS,
            build_prompt,
        )

        existing = [
            DetectedEntity(
                text=f"hit-{i}",
                category=cat,
                category_group=CategoryGroup.PRIVILEGE,
                confidence=0.5,
                detection_layer=DetectionLayer.REGEX,
                start=i * 10,
                end=i * 10 + 5,
            )
            for i, cat in enumerate(PROMPTS["shield-legal"].allowed_categories)
        ]
        assert build_prompt("shield-legal", "irrelevant text", existing) is None

    def test_empty_existing_renders_none_covered_block(self):
        from ogentic_shield.layers.llm_prompts import build_prompt

        prompt = build_prompt("shield-legal", "some text", [])
        assert prompt is not None
        assert "ALREADY COVERED by Layer 1+2 — do NOT re-emit:\n(none)" in prompt


class TestRunLayer3PostFilter:
    """The run_layer3 post-filter drops re-emitted (covered, overlapping)
    detections but keeps truly novel spans of a covered category."""

    def test_drops_reemitted_overlapping_span_in_covered_category(
        self, monkeypatch: pytest.MonkeyPatch, legal_profile_list
    ):
        text = "outside counsel reviewed the matter on 2026-05-21."
        existing = [
            DetectedEntity(
                text="outside counsel",
                category="COUNSEL_COMMUNICATION",
                category_group=CategoryGroup.PRIVILEGE,
                confidence=0.9,
                detection_layer=DetectionLayer.REGEX,
                start=0,
                end=15,
            ),
        ]
        # Model re-emits the same category overlapping the existing span —
        # exactly the failure mode OGE-396 is targeting.
        payload = json.dumps(
            {
                "detections": [
                    {
                        "category": "COUNSEL_COMMUNICATION",
                        "span_text": "outside counsel",
                        "confidence": 0.85,
                        "reasoning": "duplicate emission",
                    }
                ]
            }
        )
        _make_client(monkeypatch, [payload])

        result = run_layer3(text, existing, legal_profile_list, 30, _enabled_config())
        # The existing entity is preserved; no new LLM duplicate appended.
        assert result == existing

    def test_keeps_novel_span_even_in_covered_category(
        self, monkeypatch: pytest.MonkeyPatch, legal_profile_list
    ):
        # Two distinct mentions of counsel: the first is caught by L1+L2,
        # the second is what the LLM legitimately surfaces. The post-filter
        # must NOT drop the second because it doesn't overlap the first.
        text = (
            "outside counsel reviewed in March. Separately, in-house counsel "
            "advised on the related Q3 matter."
        )
        # Note: the "in-house counsel" span starts at a non-overlapping offset.
        novel_start = text.index("in-house counsel")
        existing = [
            DetectedEntity(
                text="outside counsel",
                category="COUNSEL_COMMUNICATION",
                category_group=CategoryGroup.PRIVILEGE,
                confidence=0.9,
                detection_layer=DetectionLayer.REGEX,
                start=0,
                end=len("outside counsel"),
            ),
        ]
        payload = json.dumps(
            {
                "detections": [
                    {
                        "category": "COUNSEL_COMMUNICATION",
                        "span_text": "in-house counsel",
                        "confidence": 0.88,
                        "reasoning": "L1+L2 missed this second mention",
                    }
                ]
            }
        )
        _make_client(monkeypatch, [payload])

        result = run_layer3(text, existing, legal_profile_list, 30, _enabled_config())
        # Existing kept + LLM added the truly-novel non-overlapping span.
        assert len(result) == 2
        novel = result[1]
        assert novel.category == "COUNSEL_COMMUNICATION"
        assert novel.start == novel_start
        assert novel.detection_layer == DetectionLayer.LLM

    def test_short_circuits_llm_call_when_no_categories_remain(
        self, monkeypatch: pytest.MonkeyPatch, legal_profile_list
    ):
        # Existing entities cover every allowed category for shield-legal.
        # run_layer3 should never call the LLM — the prompt builder returns
        # None and the loop skips the profile.
        from ogentic_shield.layers.llm_prompts import PROMPTS

        existing = [
            DetectedEntity(
                text=f"hit-{i}",
                category=cat,
                category_group=CategoryGroup.PRIVILEGE,
                confidence=0.5,
                detection_layer=DetectionLayer.REGEX,
                start=i * 20,
                end=i * 20 + 5,
            )
            for i, cat in enumerate(PROMPTS["shield-legal"].allowed_categories)
        ]
        # Script the fake to raise if called — would error the test if we
        # accidentally invoked the LLM.
        client, fake = _make_client(
            monkeypatch,
            [RuntimeError("LLM should not be called when no categories remain")],
        )
        del client, fake

        result = run_layer3(
            "text containing nothing new",
            existing,
            legal_profile_list,
            30,
            _enabled_config(),
        )
        # No new entities, no exception — proves the short-circuit fired.
        assert result == existing


# ── Module-level invariants ─────────────────────────────────────────────────


class TestLayerModuleInvariants:
    def test_module_exports_run_layer3(self):
        assert callable(llm_module.run_layer3)
        assert "run_layer3" in llm_module.__all__

    def test_llm_client_no_longer_exposes_calibration_constant(self):
        # OGE-321 removed the hardcoded multiplier in favor of the central
        # calibration framework. Make sure nothing re-imports it.
        assert not hasattr(llm_client_module, "CONFIDENCE_CALIBRATION_FACTOR")
