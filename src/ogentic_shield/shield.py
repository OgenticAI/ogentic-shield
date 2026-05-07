"""Shield class — main entry point for ogentic-shield."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from ogentic_shield.config import ShieldConfig, load_config
from ogentic_shield.models import (
    AnalysisResult,
    BatchItemError,
    DetectionLayer,
    RedactionMapping,
    ShieldProfile,
)
from ogentic_shield.pipeline import run_pipeline
from ogentic_shield.profiles import get_profile
from ogentic_shield.profiles import list_profiles as _list_profiles
from ogentic_shield.redaction import redact_text, unredact_text
from ogentic_shield.registry import ROLE_CLASSIFICATION, ModelRegistry, ModelTier

logger = logging.getLogger("ogentic_shield")


class Shield:
    """Main entry point for text sensitivity analysis.

    Initialize with one or more profile IDs, then call analyze() on text.
    """

    def __init__(
        self,
        profiles: list[str] | None = None,
        config: ShieldConfig | None = None,
        quality: str | ModelTier | None = None,
        model_override: dict[str, str] | None = None,
    ):
        self._config = config or load_config()
        profile_ids = profiles or self._config.profiles
        self._profiles: list[ShieldProfile] = [get_profile(pid) for pid in profile_ids]
        self._profile_ids = profile_ids

        # Quality/registry resolution: explicit kwarg wins; otherwise inherit
        # from LlmConfig.quality (which itself defaults to "fast"). The
        # registry is held on the instance so consumers can call
        # ``shield.required_models()`` without re-deriving overrides.
        self._quality = quality if quality is not None else self._config.llm.quality
        self._registry = ModelRegistry(overrides=model_override)

        logger.info("Shield initialized with profiles: %s", ", ".join(profile_ids))

    def analyze(
        self,
        text: str,
        profiles: list[str] | None = None,
        layers: list[DetectionLayer] | None = None,
        min_confidence: float | None = None,
        include_context: bool = False,
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

        # Resolve model: explicit `LlmConfig.model` overrides registry pick.
        resolved_model = self._config.llm.model or self._registry.get(
            ROLE_CLASSIFICATION, self._quality
        )
        llm_config = {
            "enabled": self._config.llm.enabled,
            "provider": self._config.llm.provider,
            "model": resolved_model,
            "endpoint": self._config.llm.endpoint,
            "timeout_ms": self._config.llm.timeout_ms,
            "max_retries": self._config.llm.max_retries,
            "quality": self._quality,
            "ambiguous_score_range": self._config.llm.ambiguous_score_range,
        }

        return run_pipeline(
            text=text,
            profiles=active_profiles,
            layers=layers,
            min_confidence=effective_min_confidence,
            llm_config=llm_config,
        )

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
        result = self.analyze(
            text,
            profiles=[profile_id],
            min_confidence=min_confidence,
        )
        return redact_text(text, result.entities, profile_id, redact_categories)

    @staticmethod
    def unredact(text: str, mapping: RedactionMapping) -> str:
        """Restore tokens in ``text`` to their original values using ``mapping``."""
        return unredact_text(text, mapping)

    def analyze_batch(
        self,
        texts: list[str],
        profiles: list[str] | None = None,
        layers: list[DetectionLayer] | None = None,
        min_confidence: float | None = None,
        max_workers: int = 4,
    ) -> list[AnalysisResult | BatchItemError]:
        """Analyze multiple texts in parallel, preserving input order.

        Per OGE-319: results align positionally with ``texts``; an exception
        on any single input is captured as :class:`BatchItemError` at that
        index instead of aborting the batch.

        Args:
            texts: Inputs to analyze. Empty list returns ``[]``.
            profiles: Profile-id override applied to every text in the batch.
            layers: Detection-layer override applied to every text.
            min_confidence: Minimum entity confidence override.
            max_workers: ThreadPoolExecutor worker count. Layers 1+2 are
                CPU-bound but spaCy / Presidio release the GIL during their
                C-extension hot paths, so threads still help. Use a value
                near your physical core count for best throughput.

        Returns:
            List of :class:`AnalysisResult` (success) or
            :class:`BatchItemError` (failure), one per input.
        """
        if not texts:
            return []
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")

        results: list[AnalysisResult | BatchItemError] = [None] * len(texts)  # type: ignore[list-item]

        def _one(index: int, text: str) -> AnalysisResult | BatchItemError:
            try:
                return self.analyze(
                    text,
                    profiles=profiles,
                    layers=layers,
                    min_confidence=min_confidence,
                )
            except Exception as exc:  # noqa: BLE001 — per-item containment is the contract
                logger.warning("analyze_batch item %d failed: %s", index, exc)
                return BatchItemError(
                    index=index,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_one, idx, text): idx
                for idx, text in enumerate(texts)
            }
            for future in futures:
                idx = futures[future]
                results[idx] = future.result()
        return results

    def required_models(self, tier: str | ModelTier | None = None) -> list[str]:
        """List Ollama models a consumer should ``ollama pull`` before enabling Layer 3.

        Defaults to the ``quality`` chosen at Shield init. Substitutes any
        ``model_override`` passed at construction time. Used by downstream
        consumers (Sotto Desktop, Zing Browser, Zashboard, Gyri) so model
        selection logic lives in exactly one place.
        """
        return self._registry.required_models(tier if tier is not None else self._quality)

    @staticmethod
    def list_profiles() -> list[ShieldProfile]:
        """List all available shield profiles."""
        return _list_profiles()

    @staticmethod
    def get_profile(profile_id: str) -> ShieldProfile:
        """Get a specific profile by ID."""
        return get_profile(profile_id)
