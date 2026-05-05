"""Shield class — main entry point for ogentic-shield."""

from __future__ import annotations

import logging

from ogentic_shield._version import __version__
from ogentic_shield.audit import (
    AuditBackend,
    NullAuditBackend,
    build_event,
    safe_emit,
)
from ogentic_shield.config import ShieldConfig, build_audit_backend, load_config
from ogentic_shield.models import (
    AnalysisResult,
    DetectionLayer,
    RedactionMapping,
    ShieldProfile,
)
from ogentic_shield.pipeline import run_pipeline
from ogentic_shield.profiles import get_profile
from ogentic_shield.profiles import list_profiles as _list_profiles
from ogentic_shield.redaction import redact_text, unredact_text

logger = logging.getLogger("ogentic_shield")


class Shield:
    """Main entry point for text sensitivity analysis.

    Initialize with one or more profile IDs, then call analyze() on text.
    """

    def __init__(
        self,
        profiles: list[str] | None = None,
        config: ShieldConfig | None = None,
        audit_backend: AuditBackend | None = None,
    ):
        self._config = config or load_config()
        profile_ids = profiles or self._config.profiles
        self._profiles: list[ShieldProfile] = [get_profile(pid) for pid in profile_ids]
        self._profile_ids = profile_ids
        # Caller-provided backend wins; otherwise build from config; otherwise no-op.
        self._audit_backend: AuditBackend = (
            audit_backend
            if audit_backend is not None
            else build_audit_backend(self._config.audit)
            or NullAuditBackend()
        )

        logger.info(
            "Shield initialized with profiles: %s | audit: %s",
            ", ".join(profile_ids),
            type(self._audit_backend).__name__,
        )

    @property
    def audit_backend(self) -> AuditBackend:
        """The audit backend currently receiving events from this Shield."""
        return self._audit_backend

    def _run_analysis(
        self,
        text: str,
        profiles: list[str] | None,
        layers: list[DetectionLayer] | None,
        min_confidence: float | None,
    ) -> AnalysisResult:
        """Internal: runs the pipeline without emitting an audit event.

        Public methods (``analyze``, ``redact``) wrap this and emit the
        appropriate event type, ensuring exactly one event per public call.
        """
        active_profiles = self._profiles
        if profiles:
            active_profiles = [get_profile(pid) for pid in profiles]

        effective_min_confidence = min_confidence or self._config.scoring.min_confidence

        if layers is None:
            layers = []
            if self._config.layers_regex:
                layers.append(DetectionLayer.REGEX)
            if self._config.layers_ner:
                layers.append(DetectionLayer.NER)
            if self._config.layers_rules:
                layers.append(DetectionLayer.RULES)
            if self._config.llm.enabled:
                layers.append(DetectionLayer.LLM)

        llm_config = {
            "enabled": self._config.llm.enabled,
            "provider": self._config.llm.provider,
            "model": self._config.llm.model,
            "endpoint": self._config.llm.endpoint,
            "timeout_ms": self._config.llm.timeout_ms,
            "ambiguous_score_range": self._config.llm.ambiguous_score_range,
        }

        return run_pipeline(
            text=text,
            profiles=active_profiles,
            layers=layers,
            min_confidence=effective_min_confidence,
            llm_config=llm_config,
        )

    def analyze(
        self,
        text: str,
        profiles: list[str] | None = None,
        layers: list[DetectionLayer] | None = None,
        min_confidence: float | None = None,
        include_context: bool = False,  # noqa: ARG002
    ) -> AnalysisResult:
        """Analyze text for regulatory sensitivity.

        Args:
            text: Input text to analyze.
            profiles: Override profile IDs for this call.
            layers: Override which detection layers to run.
            min_confidence: Override minimum confidence threshold.
            include_context: Include surrounding text in entity metadata.

        Returns:
            AnalysisResult with detected entities, score, and routing suggestion.
        """
        result = self._run_analysis(text, profiles, layers, min_confidence)
        model_used = (
            self._config.llm.model
            if self._config.llm.enabled and DetectionLayer.LLM in result.layers_invoked
            else None
        )
        safe_emit(
            self._audit_backend,
            build_event(
                "shield.analyze",
                result,
                shield_version=__version__,
                model_used=model_used,
            ),
        )
        return result

    def redact(
        self,
        text: str,
        profile: str | None = None,
        redact_categories: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> tuple[str, RedactionMapping]:
        """Substitute identifying entities with deterministic tokens.

        Use this before sending text to an external LLM — it masks "who" while
        preserving "how big" (numbers, ratios, percentages stay intact). Pair
        with :py:meth:`unredact` to restore originals from the LLM response.

        Args:
            text: Input text.
            profile: Profile ID (e.g. ``"shield-finance"``). Defaults to the
                first profile this Shield was initialized with.
            redact_categories: Override category labels to redact (e.g.
                ``["Person", "Email"]``). ``None`` → per-profile defaults from
                :data:`ogentic_shield.redaction.PROFILE_REDACT_CATEGORIES`.
            min_confidence: Minimum entity confidence threshold for masking.

        Returns:
            ``(redacted_text, mapping)``. Pass ``mapping`` to ``unredact()``.
        """
        profile_id = profile or self._profile_ids[0]
        result = self._run_analysis(
            text, profiles=[profile_id], layers=None, min_confidence=min_confidence,
        )
        redacted, mapping = redact_text(text, result.entities, profile_id, redact_categories)
        model_used = (
            self._config.llm.model
            if self._config.llm.enabled and DetectionLayer.LLM in result.layers_invoked
            else None
        )
        safe_emit(
            self._audit_backend,
            build_event(
                "shield.redact",
                result,
                shield_version=__version__,
                redaction=mapping,
                model_used=model_used,
            ),
        )
        return redacted, mapping

    @staticmethod
    def unredact(text: str, mapping: RedactionMapping) -> str:
        """Restore tokens in ``text`` to their original values using ``mapping``."""
        return unredact_text(text, mapping)

    @staticmethod
    def list_profiles() -> list[ShieldProfile]:
        """List all available shield profiles."""
        return _list_profiles()

    @staticmethod
    def get_profile(profile_id: str) -> ShieldProfile:
        """Get a specific profile by ID."""
        return get_profile(profile_id)
