"""Audit event emission — pluggable backends for chain-of-custody tracking.

Shield emits a :class:`ShieldAuditEvent` on every ``analyze()`` and ``redact()``
call. Events carry the *shape* of what was detected (categories, scores,
routing) but **never** the original text — only its sha256 hash.

Design principles
-----------------
* **Pluggable**: any object implementing :class:`AuditBackend` can receive events.
* **Non-blocking**: backend exceptions are caught and logged, never raised
  to the caller — audit must not break the application.
* **No raw content**: backends only see the event payload. Implementors of
  external backends (ogentic-audit, narrow Vault, Gyri) inherit this guarantee.

Shipping backends
-----------------
* :class:`NullAuditBackend` — silent no-op (default).
* :class:`StderrAuditBackend` — JSON to stderr (development).
* :class:`FileAuditBackend` — JSON-lines to a file (production).
* :class:`CallbackAuditBackend` — wraps an arbitrary ``Callable``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import sys
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Protocol, runtime_checkable

from ogentic_shield.models import (
    AnalysisResult,
    DetectedEntity,
    RedactionMapping,
    ShieldAuditEvent,
)

logger = logging.getLogger("ogentic_shield.audit")


# ─── Backend protocol ────────────────────────────────────────────────────────


@runtime_checkable
class AuditBackend(Protocol):
    """Receives :class:`ShieldAuditEvent` instances.

    Implementations MUST NOT raise — Shield catches and logs exceptions, but
    well-behaved backends fail closed: drop the event rather than crash the
    pipeline. The protocol is sync for the v0.2 surface; async fanout is
    planned but not required for any v0.2 consumer.
    """

    def emit(self, event: ShieldAuditEvent) -> None: ...


# ─── Event factory ───────────────────────────────────────────────────────────


def _entity_shape(entity: DetectedEntity) -> dict[str, Any]:
    """Strip raw text from an entity, leaving only the shape."""
    return {
        "category": entity.category,
        "category_group": entity.category_group.value,
        "confidence": round(entity.confidence, 4),
        "layer": entity.detection_layer.value,
        "start": entity.start,
        "end": entity.end,
    }


def build_event(
    event_type: str,
    result: AnalysisResult,
    *,
    shield_version: str,
    redaction: RedactionMapping | None = None,
    model_used: str | None = None,
) -> ShieldAuditEvent:
    """Build a :class:`ShieldAuditEvent` from an :class:`AnalysisResult`.

    Args:
        event_type: ``"shield.analyze"`` or ``"shield.redact"``.
        result: The analysis result that produced this event.
        shield_version: Stamped into the event for forward-compat triage.
        redaction: If present, the event records that redaction was applied
            and which categories were masked.
        model_used: LLM model identifier if Layer 3 fired.
    """
    profile = result.profile_ids[0] if result.profile_ids else None
    return ShieldAuditEvent(
        event_type=event_type,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        input_hash=result.text_hash,
        profile=profile,
        score=result.score,
        level=result.sensitivity_level.value,
        routing=result.routing_suggestion,
        entity_count=result.entity_count,
        entities_detected=[_entity_shape(e) for e in result.entities],
        layers_invoked=[layer.value for layer in result.layers_invoked],
        processing_time_ms=result.processing_time_ms,
        redaction_applied=redaction is not None,
        categories_redacted=list(redaction.categories_redacted) if redaction else [],
        tokens_emitted=len(redaction.tokens) if redaction else 0,
        model_used=model_used,
        shield_version=shield_version,
    )


def event_to_json(event: ShieldAuditEvent) -> str:
    """Serialize an event to a single-line JSON string (for JSON-lines output)."""
    return json.dumps(dataclasses.asdict(event), separators=(",", ":"))


def hash_text(text: str) -> str:
    """Hash arbitrary text the same way Shield hashes input — for downstream joins."""
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


# ─── Concrete backends ───────────────────────────────────────────────────────


class NullAuditBackend:
    """Drops every event. Default when no backend is configured."""

    def emit(self, event: ShieldAuditEvent) -> None:  # noqa: ARG002
        return None


class StderrAuditBackend:
    """Writes one JSON object per line to ``sys.stderr``.

    Cheap default for development and CI. Use :class:`FileAuditBackend` in
    production — stderr can be lossy under heavy load and is harder to ship.
    """

    def __init__(self, stream: IO[str] | None = None) -> None:
        self._stream = stream if stream is not None else sys.stderr

    def emit(self, event: ShieldAuditEvent) -> None:
        self._stream.write(event_to_json(event) + "\n")
        self._stream.flush()


class FileAuditBackend:
    """Appends events as JSON-lines to a file.

    The parent directory is created if missing. Each ``emit()`` opens the
    file in append mode and flushes — durable but not high-throughput. For
    production volumes pipe through a dedicated audit consumer (ogentic-audit).
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def emit(self, event: ShieldAuditEvent) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(event_to_json(event) + "\n")


class CallbackAuditBackend:
    """Forwards each event to a user-supplied callable.

    Use this to bridge Shield into existing observability systems
    (OpenTelemetry, Datadog, custom log routers) without writing a full
    backend class.
    """

    def __init__(self, callback: Callable[[ShieldAuditEvent], None]) -> None:
        self._callback = callback

    def emit(self, event: ShieldAuditEvent) -> None:
        self._callback(event)


class FanoutAuditBackend:
    """Broadcasts each event to multiple backends.

    Each child backend's exceptions are caught individually so one failing
    sink cannot starve the others.
    """

    def __init__(self, backends: Iterable[AuditBackend]) -> None:
        self._backends = list(backends)

    def emit(self, event: ShieldAuditEvent) -> None:
        for backend in self._backends:
            try:
                backend.emit(event)
            except Exception:  # noqa: BLE001
                logger.exception("Audit backend %s raised; event dropped", type(backend).__name__)


# ─── Safe emit wrapper ───────────────────────────────────────────────────────


def safe_emit(backend: AuditBackend | None, event: ShieldAuditEvent) -> None:
    """Emit ``event`` to ``backend``, swallowing and logging any exception.

    Shield calls this on the hot path; an audit failure must never abort the
    user's analyze/redact call. Pass ``None`` (or :class:`NullAuditBackend`)
    to disable emission.
    """
    if backend is None:
        return
    try:
        backend.emit(event)
    except Exception:  # noqa: BLE001
        logger.exception("Audit backend %s raised; event dropped", type(backend).__name__)
