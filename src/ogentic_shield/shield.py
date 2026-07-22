"""Shield class — main entry point for ogentic-shield."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ogentic_shield.config import ShieldConfig, load_config
from ogentic_shield.documents import (
    DEFAULT_CHUNK_CHARS,
    ChunkResult,
    DocumentAnalysisResult,
    DocumentRedactionResult,
    aggregate_chunk_results,
    chunk_text,
    extract_text,
)
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
            ner_model=self._config.ner_model,
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

    def classify_batch(
        self,
        texts: list[str],
        *,
        profile: str | None = None,
    ) -> list[AnalysisResult | BatchItemError]:
        """Analyze multiple texts serially, returning one result per input.

        This is the simple, single-profile sibling of :meth:`analyze_batch`.
        Key differences:

        - **Serial execution**: items are processed one at a time in input
          order. No threading. Use this when ordering semantics, memory
          footprint, or test determinism matter more than throughput.
        - **Single profile shorthand**: ``profile`` accepts one profile ID
          string; it is expanded to ``profiles=[profile]`` before the
          :meth:`analyze` call. Pass ``None`` (the default) to inherit the
          profiles this Shield was initialized with.
        - **Per-item fault isolation**: any exception raised during a single
          item's analysis is caught and returned as a
          :class:`~ogentic_shield.models.BatchItemError` at that index,
          keeping the rest of the batch alive.
        - **Empty-list fast path**: ``classify_batch([])`` returns ``[]``
          without touching the pipeline.

        Args:
            texts: Inputs to analyze. Empty list returns ``[]``.
            profile: Optional single profile ID (e.g. ``"shield-legal"``).
                When provided, overrides the Shield's configured profiles for
                every item in the batch. ``None`` uses the instance profiles.

        Returns:
            List of :class:`~ogentic_shield.models.AnalysisResult` (success)
            or :class:`~ogentic_shield.models.BatchItemError` (failure), one
            per input, in input order.
        """
        if not texts:
            return []

        profiles = [profile] if profile is not None else None
        results: list[AnalysisResult | BatchItemError] = []

        for idx, text in enumerate(texts):
            try:
                results.append(self.analyze(text, profiles=profiles))
            except Exception as exc:  # noqa: BLE001 — per-item containment is the contract
                logger.warning("classify_batch item %d failed: %s", idx, exc.__class__.__name__)
                logger.debug("classify_batch item %d exception detail: %s", idx, exc)
                results.append(
                    BatchItemError(
                        index=idx,
                        error=str(exc),
                        error_type=exc.__class__.__name__,
                    )
                )

        return results

    def analyze_document(
        self,
        path: str | Path,
        *,
        profiles: list[str] | None = None,
        layers: list[DetectionLayer] | None = None,
        min_confidence: float | None = None,
        chunk_chars: int = DEFAULT_CHUNK_CHARS,
    ) -> DocumentAnalysisResult:
        """Analyze a document file for regulatory sensitivity (OGE-398, Phase 1).

        Pass a path; get back a :class:`~ogentic_shield.documents.DocumentAnalysisResult`
        with a whole-document aggregate plus per-chunk breakdowns. Identical
        analysis semantics to :meth:`analyze` — same profiles, same layers,
        same scoring; we just take care of extracting and chunking the file
        in front of the pipeline.

        Phase 1 supports the plain-text family (``.txt``, ``.md``, ``.log``).
        Other formats recognized but not yet implemented (PDF, DOCX, XLSX,
        EML, MSG, HTML) raise
        :class:`~ogentic_shield.documents.UnsupportedDocumentFormatError`
        with the install hint for the Phase-2 ``[documents]`` extra.

        Args:
            path: File path to analyze.
            profiles: Override profile IDs for this call (default: the
                profiles this Shield was initialized with).
            layers: Override which detection layers to run.
            min_confidence: Override minimum confidence threshold.
            chunk_chars: Maximum chunk size in characters; chunks split on
                paragraph boundaries where possible. Default 10,000
                (≈2.5k tokens — comfortably under any Layer 3 context).

        Returns:
            :class:`DocumentAnalysisResult` with:

            - ``path`` / ``format`` (the dispatcher's resolution).
            - ``aggregate``: whole-document :class:`AnalysisResult`.
              ``score`` is ``max`` across chunks (a single CRITICAL chunk
              makes the whole document CRITICAL); ``entities`` are
              concatenated with global offsets; ``category_groups_found``
              is the union.
            - ``chunks``: ordered list of :class:`ChunkResult` so callers
              can drill into per-page / per-section findings.
            - ``extraction_warnings``: empty in Phase 1; Phase 2's PDF
              extractor will surface scanned-page warnings here.

        Raises:
            FileNotFoundError: ``path`` doesn't exist.
            UnsupportedDocumentFormatError: format isn't supported (yet).
        """
        text, fmt = extract_text(path)
        active_profile_ids = list(profiles) if profiles else list(self._profile_ids)

        # Chunk, then run the existing string-analysis pipeline per chunk.
        # We reuse self.analyze so layers / config / Layer 3 gating remain
        # identical to what string callers get.
        chunk_specs = chunk_text(text, chunk_chars=chunk_chars)
        chunk_results: list[ChunkResult] = []
        for idx, (chunk_str, label, offset) in enumerate(chunk_specs):
            result = self.analyze(
                chunk_str,
                profiles=active_profile_ids,
                layers=layers,
                min_confidence=min_confidence,
            )
            chunk_results.append(
                ChunkResult(index=idx, label=label, text_offset=offset, result=result)
            )

        aggregate = aggregate_chunk_results(
            chunk_results,
            full_text=text,
            profile_ids=active_profile_ids,
        )

        return DocumentAnalysisResult(
            path=str(path),
            format=fmt,
            aggregate=aggregate,
            chunks=chunk_results,
            extraction_warnings=[],  # Phase 2 extractors will populate this.
        )

    def redact_document(
        self,
        path: str | Path,
        *,
        profile: str | None = None,
        profiles: list[str] | None = None,
        redact_categories: list[str] | None = None,
        layers: list[DetectionLayer] | None = None,
        min_confidence: float | None = None,
        chunk_chars: int = DEFAULT_CHUNK_CHARS,
    ) -> DocumentRedactionResult:
        """Redact regulatory-sensitive content from a document (OGE-792).

        The document-level pair to :meth:`redact` — same redaction engine,
        same per-profile defaults, same token format
        (``[Label_abc123]``), but takes a file path and returns a
        :class:`~ogentic_shield.documents.DocumentRedactionResult` carrying
        the original text, the redacted text, the mapping (for
        :meth:`unredact`), and the full :class:`DocumentAnalysisResult`
        that drove the redaction.

        Composes :meth:`analyze_document` and
        :func:`~ogentic_shield.redaction.redact_text` — no duplicate
        parsing or scoring logic; aggregation semantics are identical to
        what :meth:`analyze_document` returns.

        Phase 1 supports the plain-text family (``.txt``, ``.md``,
        ``.log``); Phase-2 extensions raise
        :class:`~ogentic_shield.documents.UnsupportedDocumentFormatError`
        with the install hint (delegated to :func:`extract_text`).

        Args:
            path: File path to redact.
            profile: Single profile ID (e.g. ``"shield-legal"``). Mutually
                exclusive with ``profiles``; if both are ``None``, falls
                back to the first profile this Shield was initialized
                with. Selects which per-profile defaults
                :func:`redact_text` uses when ``redact_categories`` is
                also ``None``.
            profiles: Multiple profile IDs to run through analysis. The
                first is used as the redaction-defaults selector when
                ``profile`` is ``None``.
            redact_categories: Override category labels (or raw entity
                types) to mask. ``None`` → per-profile defaults from
                :data:`~ogentic_shield.redaction.PROFILE_REDACT_CATEGORIES`.
            layers: Override which detection layers to run during
                analysis.
            min_confidence: Override minimum confidence threshold for
                detection.
            chunk_chars: Maximum chunk size in characters passed through
                to :meth:`analyze_document`.

        Returns:
            :class:`DocumentRedactionResult` with ``path``, ``format``,
            ``original_text``, ``redacted_text``, ``mapping``, and the
            driving ``analysis``. ``unredact_text(redacted_text, mapping)``
            round-trips to ``original_text`` for the redacted tokens.

        Raises:
            FileNotFoundError: ``path`` doesn't exist.
            UnsupportedDocumentFormatError: format isn't supported (yet).
        """
        # Run analysis through the existing document pipeline — gives us
        # extraction, chunking, per-chunk analysis, and a single aggregate
        # AnalysisResult with entity offsets already rebased to the full
        # extracted text. We re-extract to recover ``text`` (cheap for the
        # Phase-1 plain-text family; Phase 2 may want a shared helper).
        active_profiles = list(profiles) if profiles else (
            [profile] if profile else None
        )
        analysis = self.analyze_document(
            path,
            profiles=active_profiles,
            layers=layers,
            min_confidence=min_confidence,
            chunk_chars=chunk_chars,
        )
        text, fmt = extract_text(path)

        # Pick the profile that drives redaction-category defaults. Caller's
        # explicit ``profile`` wins; otherwise first of ``profiles`` /
        # Shield-init profiles.
        defaults_profile = profile or (
            active_profiles[0] if active_profiles else self._profile_ids[0]
        )
        redacted_text, mapping = redact_text(
            text,
            analysis.aggregate.entities,
            defaults_profile,
            redact_categories,
        )

        return DocumentRedactionResult(
            path=str(path),
            format=fmt,
            original_text=text,
            redacted_text=redacted_text,
            mapping=mapping,
            analysis=analysis,
        )

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
