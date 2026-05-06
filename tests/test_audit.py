"""Tests for audit event emission (OGE-316) and the AuditBackend contract (OGE-317).

Covers:
* Event factory shape — every required field, no raw text leakage
* Backend protocol — Null/Stderr/File/Callback/Fanout
* Shield wiring — analyze() emits ``shield.analyze``, redact() emits ``shield.redact``
* Error swallowing — backend exceptions never propagate to the caller
* Config parsing — YAML ``audit`` block produces the right backend
"""

from __future__ import annotations

import json
import logging
from io import StringIO

import pytest

from ogentic_shield import (
    AuditBackend,
    CallbackAuditBackend,
    FanoutAuditBackend,
    FileAuditBackend,
    NullAuditBackend,
    Shield,
    ShieldAuditEvent,
    StderrAuditBackend,
)
from ogentic_shield._version import __version__
from ogentic_shield.audit import build_event, event_to_json, hash_text, safe_emit
from ogentic_shield.config import (
    AuditConfig,
    ShieldConfig,
    build_audit_backend,
    load_config,
)
from ogentic_shield.models import (
    AnalysisResult,
    CategoryGroup,
    ConfigError,
    DetectedEntity,
    DetectionLayer,
    SensitivityLevel,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_result(text: str = "Hello world") -> AnalysisResult:
    """Build a synthetic AnalysisResult for event-shape tests."""
    return AnalysisResult(
        text_hash=hash_text(text),
        entities=[
            DetectedEntity(
                text="Alice",
                category="PERSON",
                category_group=CategoryGroup.PII,
                confidence=0.91,
                detection_layer=DetectionLayer.NER,
                start=6,
                end=11,
            ),
        ],
        score=42,
        sensitivity_level=SensitivityLevel.MEDIUM,
        category_groups_found={CategoryGroup.PII},
        top_category="PERSON",
        top_confidence=0.91,
        entity_count=1,
        processing_time_ms=12.3,
        layers_invoked=[DetectionLayer.REGEX, DetectionLayer.NER],
        profile_ids=["shield-finance"],
        routing_suggestion="REDACT_CLOUD",
    )


# ─── Event factory ───────────────────────────────────────────────────────────


class TestBuildEvent:
    def test_analyze_event_shape(self):
        result = _make_result()
        event = build_event("shield.analyze", result, shield_version=__version__)

        assert event.event_type == "shield.analyze"
        assert event.input_hash.startswith("sha256:")
        assert event.profile == "shield-finance"
        assert event.score == 42
        assert event.level == "MEDIUM"
        assert event.routing == "REDACT_CLOUD"
        assert event.entity_count == 1
        assert event.layers_invoked == ["REGEX", "NER"]
        assert event.shield_version == __version__
        # Redaction fields default to off when no mapping is passed
        assert event.redaction_applied is False
        assert event.categories_redacted == []
        assert event.tokens_emitted == 0
        assert event.model_used is None

    def test_event_payload_contains_no_raw_text(self):
        """Critical privacy invariant: the event must never carry entity text."""
        result = _make_result(text="My SSN is 123-45-6789")
        event = build_event("shield.analyze", result, shield_version=__version__)
        payload = event_to_json(event)

        # The detected entity 'Alice' must not appear in the serialized event
        assert "Alice" not in payload, "Entity text leaked into audit event"
        # Hash present, raw input absent
        assert event.input_hash.startswith("sha256:")
        # Each entity record carries shape only
        for ent in event.entities_detected:
            assert "text" not in ent, "Per-entity text field must not be present"
            assert {"category", "category_group", "confidence", "layer"}.issubset(ent.keys())

    def test_redact_event_records_categories_and_token_count(self):
        from ogentic_shield.models import RedactionMapping

        mapping = RedactionMapping(
            tokens={"[Person_aaaaaa]": "Alice"},
            categories_redacted=["Person", "Email"],
            profile_id="shield-finance",
            text_hash="sha256:abc",
            created_at="2026-04-27T08:00:00+00:00",
        )
        event = build_event(
            "shield.redact",
            _make_result(),
            shield_version=__version__,
            redaction=mapping,
        )
        assert event.event_type == "shield.redact"
        assert event.redaction_applied is True
        assert event.categories_redacted == ["Person", "Email"]
        assert event.tokens_emitted == 1

    def test_event_to_json_is_single_line(self):
        event = build_event("shield.analyze", _make_result(), shield_version=__version__)
        line = event_to_json(event)
        assert "\n" not in line, "JSON-lines output must not contain newlines"
        # Round-trips through json
        parsed = json.loads(line)
        assert parsed["event_type"] == "shield.analyze"


# ─── Backends ────────────────────────────────────────────────────────────────


class TestNullBackend:
    def test_null_swallows_silently(self):
        NullAuditBackend().emit(_make_event())  # no exception, no output


class TestStderrBackend:
    def test_writes_json_line(self):
        buf = StringIO()
        backend = StderrAuditBackend(stream=buf)
        backend.emit(_make_event())

        output = buf.getvalue()
        assert output.endswith("\n")
        line = output.rstrip("\n")
        parsed = json.loads(line)
        assert parsed["event_type"] == "shield.analyze"


class TestFileBackend:
    def test_appends_json_lines(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        backend = FileAuditBackend(path)
        backend.emit(_make_event())
        backend.emit(_make_event())

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            assert json.loads(line)["event_type"] == "shield.analyze"

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "audit.jsonl"
        backend = FileAuditBackend(path)
        backend.emit(_make_event())
        assert path.exists()


class TestCallbackBackend:
    def test_invokes_callback(self):
        captured: list[ShieldAuditEvent] = []
        backend = CallbackAuditBackend(captured.append)
        backend.emit(_make_event())
        assert len(captured) == 1
        assert captured[0].event_type == "shield.analyze"


class TestFanoutBackend:
    def test_broadcasts_to_all_children(self):
        a: list[ShieldAuditEvent] = []
        b: list[ShieldAuditEvent] = []
        backend = FanoutAuditBackend([
            CallbackAuditBackend(a.append),
            CallbackAuditBackend(b.append),
        ])
        backend.emit(_make_event())
        assert len(a) == 1 and len(b) == 1

    def test_one_failing_child_does_not_starve_others(
        self, caplog: pytest.LogCaptureFixture
    ):
        delivered: list[ShieldAuditEvent] = []

        def fail(_event):
            raise RuntimeError("boom")

        backend = FanoutAuditBackend([
            CallbackAuditBackend(fail),
            CallbackAuditBackend(delivered.append),
        ])
        with caplog.at_level(logging.ERROR, logger="ogentic_shield.audit"):
            backend.emit(_make_event())
        assert len(delivered) == 1
        assert any("raised" in m for m in caplog.messages)


class TestProtocolConformance:
    def test_runtime_check_passes_for_shipping_backends(self):
        # The Protocol is runtime-checkable; concrete backends must satisfy it.
        assert isinstance(NullAuditBackend(), AuditBackend)
        assert isinstance(StderrAuditBackend(), AuditBackend)
        assert isinstance(CallbackAuditBackend(lambda _e: None), AuditBackend)


# ─── Safe emit wrapper ───────────────────────────────────────────────────────


class TestSafeEmit:
    def test_none_backend_is_a_noop(self):
        safe_emit(None, _make_event())  # no exception

    def test_swallows_backend_exceptions(self, caplog: pytest.LogCaptureFixture):
        def boom(_event):
            raise RuntimeError("audit pipe failed")

        backend = CallbackAuditBackend(boom)
        with caplog.at_level(logging.ERROR, logger="ogentic_shield.audit"):
            safe_emit(backend, _make_event())  # must not raise
        assert any("dropped" in m for m in caplog.messages)


# ─── Shield wiring ───────────────────────────────────────────────────────────


class TestShieldEmitsOnAnalyze:
    def test_default_shield_uses_null_backend(self, finance_shield: Shield):
        # No audit_backend passed and no config file → Null
        assert isinstance(finance_shield.audit_backend, NullAuditBackend)

    def test_analyze_emits_one_analyze_event(self):
        captured: list[ShieldAuditEvent] = []
        shield = Shield(
            profiles=["shield-finance"],
            audit_backend=CallbackAuditBackend(captured.append),
        )
        shield.analyze("Goldman Sachs is acquiring TargetCo at $5M.")
        assert len(captured) == 1
        assert captured[0].event_type == "shield.analyze"
        assert captured[0].profile == "shield-finance"
        assert captured[0].redaction_applied is False

    def test_redact_emits_one_redact_event_not_analyze(self):
        captured: list[ShieldAuditEvent] = []
        shield = Shield(
            profiles=["shield-finance"],
            audit_backend=CallbackAuditBackend(captured.append),
        )
        shield.redact("Goldman Sachs is acquiring TargetCo from John Smith at $5M.")
        # Exactly one event, of type shield.redact (not shield.analyze)
        assert len(captured) == 1
        event = captured[0]
        assert event.event_type == "shield.redact"
        assert event.redaction_applied is True
        assert event.categories_redacted  # at least one category masked

    def test_audit_backend_failure_does_not_break_analyze(
        self, caplog: pytest.LogCaptureFixture
    ):
        def boom(_event):
            raise RuntimeError("downstream is on fire")

        shield = Shield(
            profiles=["shield-finance"],
            audit_backend=CallbackAuditBackend(boom),
        )
        with caplog.at_level(logging.ERROR, logger="ogentic_shield.audit"):
            result = shield.analyze("Hello world.")
        # Caller still got a result; only the audit pipe failed
        assert result.entity_count >= 0

    def test_audit_event_input_hash_does_not_match_other_inputs(self):
        captured: list[ShieldAuditEvent] = []
        shield = Shield(
            profiles=["shield-finance"],
            audit_backend=CallbackAuditBackend(captured.append),
        )
        shield.analyze("text one")
        shield.analyze("a totally different text")
        assert captured[0].input_hash != captured[1].input_hash


# ─── Config parsing ──────────────────────────────────────────────────────────


class TestConfigParsing:
    def test_default_config_uses_null_backend(self):
        cfg = ShieldConfig()
        assert cfg.audit.backend == "null"
        assert build_audit_backend(cfg.audit) is None

    def test_stderr_backend_built_from_config(self):
        backend = build_audit_backend(AuditConfig(backend="stderr"))
        assert isinstance(backend, StderrAuditBackend)

    def test_file_backend_built_with_path(self, tmp_path):
        backend = build_audit_backend(
            AuditConfig(backend="file", path=str(tmp_path / "a.jsonl")),
        )
        assert isinstance(backend, FileAuditBackend)
        assert backend.path == tmp_path / "a.jsonl"

    def test_file_backend_without_path_raises(self):
        with pytest.raises(ConfigError, match="audit.path"):
            build_audit_backend(AuditConfig(backend="file", path=None))

    def test_unknown_backend_raises(self):
        with pytest.raises(ConfigError, match="Unknown audit.backend"):
            build_audit_backend(AuditConfig(backend="bogus"))

    def test_yaml_audit_block_parsed(self, tmp_path):
        yaml_path = tmp_path / "ogentic-shield.yaml"
        yaml_path.write_text(
            "version: '0.1'\n"
            "profiles: [shield-finance]\n"
            "audit:\n"
            "  backend: file\n"
            f"  path: {tmp_path / 'audit.jsonl'}\n",
            encoding="utf-8",
        )
        cfg = load_config(yaml_path)
        assert cfg.audit.backend == "file"
        backend = build_audit_backend(cfg.audit)
        assert isinstance(backend, FileAuditBackend)


# ─── Internal helper kept here for reuse ─────────────────────────────────────


def _make_event() -> ShieldAuditEvent:
    return build_event("shield.analyze", _make_result(), shield_version=__version__)
