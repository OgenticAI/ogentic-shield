"""Document-analysis surface for Shield (OGE-398, Phase 1).

Real-world regulated content lives in documents, not strings. Asking every
Sotto / Zashboard integrator to write their own PDF / DOCX / XLSX
extraction loop before they can call ``Shield.analyze`` is the wrong
architectural choice — it duplicates work, fragments the privacy contract
(each integrator's extractor is now an audit surface), and locks out
non-Python consumers from the MCP server.

This module ships the *architecture* for ``Shield.analyze_document``:

- :class:`DocumentAnalysisResult` — the document-shaped return type that
  wraps an aggregate :class:`~ogentic_shield.models.AnalysisResult` plus per-
  chunk breakdowns.
- :class:`ChunkResult` — one analyzed segment with a human-readable label
  (page number, sheet name, paragraph index).
- :class:`UnsupportedDocumentFormatError` — clean error when a format isn't
  yet implemented; carries the ``pip install`` hint a caller would need.
- :func:`extract_text` — the format dispatcher. Phase 1 handles the
  text-like extensions (``.txt``, ``.md``, ``.log``) end-to-end. PDF, DOCX,
  XLSX, EML, MSG, and HTML raise :class:`UnsupportedDocumentFormatError`
  with the ``pip install 'ogentic-shield[documents]'`` hint until Phase 2
  wires in the per-format libraries (``pdfplumber``, ``python-docx``,
  ``openpyxl``, ``extract-msg``, ``trafilatura``).
- :func:`chunk_text` — pure splitter that respects paragraph boundaries
  where possible and never produces a chunk longer than ``chunk_chars``.
- :func:`aggregate_chunk_results` — builds the document-level rollup
  (max score, union groups, entities with offsets adjusted to the
  concatenated text).

The :class:`~ogentic_shield.shield.Shield` entry point lives in
``shield.py`` and is a thin wrapper that calls ``extract_text`` →
``chunk_text`` → per-chunk ``analyze`` → ``aggregate_chunk_results``.

Privacy invariants (same as ``analyze``):
- All extraction runs in-process; no library in the Phase-2 dep list phones home.
- The text the model sees is the same text Shield analyses — there's no
  out-of-band "send to OCR cloud" surprise.
- Audit events on document analysis stay shape-only via the existing
  ``audit.py`` discipline; only chunk labels (e.g. ``"page 3"``) and offsets
  cross into telemetry, never raw extracted text.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from ogentic_shield.models import (
    AnalysisResult,
    CategoryGroup,
    DetectedEntity,
    DetectionLayer,
    RedactionMapping,
    SensitivityLevel,
    ShieldError,
)

# ─── Public dataclasses ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChunkResult:
    """One chunk's analysis result, with its position in the doc."""

    index: int
    """Zero-based position in the per-document chunk sequence."""

    label: str
    """Human-readable origin (e.g. ``"page 3"``, ``"paragraph 12"``,
    ``"Sheet 'Q3' row 42"``, ``"line 1-200"``). Useful in audit events
    and UI surfaces. Phase 1 only emits ``"chunk N"`` style labels for
    plain-text formats; Phase 2 extractors will emit format-specific ones."""

    text_offset: int
    """Byte/character offset into the concatenated extracted text.
    Entities inside the chunk's ``result`` carry chunk-local offsets;
    :func:`aggregate_chunk_results` rebases them to document-global
    offsets using this field."""

    result: AnalysisResult


@dataclass(frozen=True)
class DocumentAnalysisResult:
    """Document-shaped analysis return."""

    path: str
    """The original path the caller passed (str, not Path)."""

    format: str
    """The format detected — ``"text"`` / ``"markdown"`` / ``"pdf"`` / etc.
    Phase 1 emits ``"text"`` and ``"markdown"`` only; other formats raise
    :class:`UnsupportedDocumentFormatError` until Phase 2."""

    aggregate: AnalysisResult
    """Whole-document rollup. Score is ``max(chunk.score)``;
    ``category_groups_found`` is the union; ``entities`` is the
    concatenation with offsets rebased to the full extracted text;
    ``routing_suggestion`` follows whatever ``suggest_routing`` returns
    for the aggregate."""

    chunks: list[ChunkResult]
    """Per-chunk breakdowns, ordered by ``index``."""

    extraction_warnings: list[str] = field(default_factory=list)
    """Non-fatal extraction notes (e.g. ``"page 14: no extractable text —
    likely scanned"``). Phase 1 extractors produce none of these; Phase 2's
    PDF path will."""


@dataclass(frozen=True)
class DocumentRedactionResult:
    """Document-shaped redaction return (OGE-792).

    The natural pair to :class:`DocumentAnalysisResult` — same format
    coverage, same chunking semantics, but the substantive output is the
    *redacted* document text plus a :class:`RedactionMapping` the caller
    can pass to :func:`~ogentic_shield.redaction.unredact_text` to restore
    originals after a round-trip through an external LLM.

    Carries the full :class:`DocumentAnalysisResult` that drove the
    redaction so audit consumers can see *what* was found alongside *what
    was masked* without re-running the pipeline.
    """

    path: str
    """The original path the caller passed (str, not Path)."""

    format: str
    """The format detected — same vocabulary as
    :attr:`DocumentAnalysisResult.format` (``"text"`` / ``"markdown"`` /
    etc.). Phase 1 emits ``"text"`` and ``"markdown"`` only."""

    original_text: str
    """The extracted, pre-redaction text. Useful for diff displays and
    for any downstream audit row that needs a hash of the input. Not the
    same object as ``analysis.aggregate.entities[*].text`` — that's per-
    entity; this is the full document."""

    redacted_text: str
    """The substantive output. Entities matching the active redaction
    categories have been substituted with deterministic tokens of the
    form ``[Label_abc123]`` (per the existing
    :func:`~ogentic_shield.redaction.redact_text` engine).
    Non-redacted text is byte-identical to ``original_text``."""

    mapping: RedactionMapping
    """Token → original-value mapping. Pass to
    :func:`~ogentic_shield.redaction.unredact_text` after the LLM returns
    to restore originals. Never logged or audit-emitted — the mapping
    leaks the very thing redaction was protecting."""

    analysis: DocumentAnalysisResult
    """The analysis that drove the redaction — same shape
    :meth:`Shield.analyze_document` returns. Use it to inspect *what was
    found* (per-chunk breakdowns, score, category groups) without
    re-running the pipeline."""


# ─── Errors ─────────────────────────────────────────────────────────────────


class UnsupportedDocumentFormatError(ShieldError):
    """Raised when a path's format isn't supported (yet).

    Carries the exact ``pip install`` line the caller needs, or the issue
    number where support is tracked. The reviewer (and tests) inspect the
    ``install_hint`` attribute so it stays machine-readable.
    """

    def __init__(self, path: str, ext: str, *, install_hint: str | None = None):
        self.path = path
        self.ext = ext
        self.install_hint = install_hint
        msg = f"Document format {ext!r} (path={path!r}) is not supported in this build."
        if install_hint:
            msg = f"{msg} {install_hint}"
        super().__init__(msg)


# ─── Format dispatch + extractors ───────────────────────────────────────────

# Plain-text family — handled in-process with builtin ``open()``.
_PLAIN_TEXT_EXTS = {".txt", ".log"}
_MARKDOWN_EXTS = {".md", ".markdown", ".mdown"}

# Phase 2 — these extensions are recognized but raise
# :class:`UnsupportedDocumentFormatError` until the format's library is
# wired in. Keys map to the optional-extra group that ships the dep.
_PHASE_2_EXTS: dict[str, tuple[str, str]] = {
    ".pdf": ("documents", "pdfplumber"),
    ".docx": ("documents", "python-docx"),
    ".xlsx": ("documents", "openpyxl"),
    ".eml": ("documents", "(stdlib email)"),
    ".msg": ("documents", "extract-msg"),
    ".html": ("documents", "trafilatura"),
    ".htm": ("documents", "trafilatura"),
}


def _detect_format(path: Path) -> str:
    """Return the canonical format name for ``path``.

    Phase 1 maps the text family to ``"text"`` / ``"markdown"``. Phase 2
    extensions return the canonical name (``"pdf"`` etc.) so the caller
    can include it in the error before raising. Unknown extensions return
    ``"unknown"`` and the caller decides whether to fall through to a
    magic-byte sniff (Phase 2) or raise.
    """
    ext = path.suffix.lower()
    if ext in _PLAIN_TEXT_EXTS:
        return "text"
    if ext in _MARKDOWN_EXTS:
        return "markdown"
    if ext in _PHASE_2_EXTS:
        return ext.lstrip(".")  # "pdf", "docx", …
    return "unknown"


def extract_text(path: str | Path) -> tuple[str, str]:
    """Extract text from ``path``. Returns ``(text, format)``.

    Phase 1: handles ``.txt`` / ``.log`` / ``.md`` (+ aliases). Other
    extensions raise :class:`UnsupportedDocumentFormatError`. Path doesn't
    exist → :class:`FileNotFoundError` (standard).

    The contract for Phase 2 extractors will mirror this signature so the
    dispatcher can route by extension and the caller sees the same shape.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Document not found: {p}")
    fmt = _detect_format(p)

    if fmt in ("text", "markdown"):
        # ``errors="replace"`` keeps a single garbled byte from killing
        # the whole analysis. Privacy contract: still in-process.
        return p.read_text(encoding="utf-8", errors="replace"), fmt

    if fmt == "unknown":
        raise UnsupportedDocumentFormatError(
            path=str(p),
            ext=p.suffix.lower() or "(no extension)",
            install_hint=(
                "Phase 1 supports .txt / .md / .log only. Magic-byte sniffing "
                "for unknown extensions ships in Phase 2 — see OGE-398."
            ),
        )

    # Phase 2 path: known extension, no extractor yet.
    extra, lib = _PHASE_2_EXTS[p.suffix.lower()]
    raise UnsupportedDocumentFormatError(
        path=str(p),
        ext=fmt,
        install_hint=(
            f"Format .{fmt} is recognized but its extractor lands in Phase 2 of OGE-398. "
            f"Install hint when ready: `pip install 'ogentic-shield[{extra}]'` (uses {lib})."
        ),
    )


# ─── Chunking ────────────────────────────────────────────────────────────────


DEFAULT_CHUNK_CHARS = 10_000
"""≈2.5k tokens — comfortably under any realistic Layer 3 context window."""


def chunk_text(
    text: str,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
) -> list[tuple[str, str, int]]:
    """Split ``text`` into ``(chunk_text, label, offset)`` triples.

    Phase 1 splits on double-newline (paragraph) boundaries where possible
    and falls back to hard length splits when a single "paragraph" exceeds
    ``chunk_chars``. The label is a 1-indexed ``"chunk N"`` string; Phase 2
    extractors will produce format-specific labels (e.g. ``"page 3"``) and
    pass them through to :class:`ChunkResult`.

    ``offset`` is the character index into the original ``text`` so callers
    rebasing entities to document-global coordinates can do
    ``entity.start + offset``.

    Returns ``[("", "chunk 1", 0)]`` for empty inputs so callers still get a
    chunk to feed analyze (which will produce an empty result).
    """
    if chunk_chars <= 0:
        raise ValueError(f"chunk_chars must be positive, got {chunk_chars}")
    if not text:
        return [("", "chunk 1", 0)]

    out: list[tuple[str, str, int]] = []
    cursor = 0
    n = len(text)
    chunk_idx = 1
    while cursor < n:
        # Try to end the chunk on a paragraph boundary within chunk_chars.
        end = min(cursor + chunk_chars, n)
        if end < n:
            # Look back for the last "\n\n" inside [cursor, end].
            split = text.rfind("\n\n", cursor, end)
            if split > cursor + chunk_chars // 4:
                # Don't accept a paragraph break in the first 25 %; that
                # would produce tiny prefix chunks. Better to take the hard
                # length split.
                end = split + 2  # include the blank line in the prior chunk
        out.append((text[cursor:end], f"chunk {chunk_idx}", cursor))
        cursor = end
        chunk_idx += 1
    return out


# ─── Aggregation ────────────────────────────────────────────────────────────


def aggregate_chunk_results(
    chunks: list[ChunkResult],
    *,
    full_text: str,
    profile_ids: list[str],
) -> AnalysisResult:
    """Roll per-chunk :class:`AnalysisResult`s up to a document-level one.

    Semantics (per OGE-398 ACs):

    - ``score``: ``max`` across chunks. A single CRITICAL chunk makes the
      whole document CRITICAL.
    - ``sensitivity_level``: derived from the max score using the chunk that
      attained it (we keep the level the scorer would assign for that score
      bracket, which lives on the contributing chunk).
    - ``category_groups_found``: union across chunks.
    - ``entities``: concatenation; each entity's ``start`` / ``end`` rebased
      from chunk-local to document-global using the chunk's ``text_offset``.
    - ``top_category`` / ``top_confidence``: pick the entity with the
      highest confidence across all chunks (ties broken by first appearance).
    - ``layers_invoked``: union across chunks (preserves order of first
      appearance).
    - ``processing_time_ms``: sum across chunks (wall-clock estimate).
    - ``routing_suggestion``: whatever the chunk that contributed the max
      score recommended — the most cautious recommendation wins by virtue
      of the score being the gate.
    - ``text_hash``: SHA-256 of the concatenated extracted text, prefixed
      ``"sha256:"`` to match the existing ``analyze`` convention.
    """
    if not chunks:
        # Empty document → return a clean zero-result.
        return AnalysisResult(
            text_hash="sha256:" + hashlib.sha256(b"").hexdigest(),
            entities=[],
            score=0,
            sensitivity_level=SensitivityLevel.NONE,
            category_groups_found=set(),
            top_category=None,
            top_confidence=0.0,
            entity_count=0,
            processing_time_ms=0.0,
            layers_invoked=[],
            profile_ids=list(profile_ids),
            routing_suggestion="CLOUD_OK",
        )

    # Find the chunk with the highest score for derived fields.
    top_chunk = max(chunks, key=lambda c: c.result.score)

    # Concatenate entities with rebased offsets.
    entities: list[DetectedEntity] = []
    for chunk in chunks:
        for e in chunk.result.entities:
            entities.append(
                DetectedEntity(
                    text=e.text,
                    category=e.category,
                    category_group=e.category_group,
                    confidence=e.confidence,
                    detection_layer=e.detection_layer,
                    start=e.start + chunk.text_offset,
                    end=e.end + chunk.text_offset,
                    metadata=e.metadata,
                )
            )

    # Union of category groups + layers (preserving first-appearance order).
    groups: set[CategoryGroup] = set()
    layers: list[DetectionLayer] = []
    for chunk in chunks:
        groups |= chunk.result.category_groups_found
        for layer in chunk.result.layers_invoked:
            if layer not in layers:
                layers.append(layer)

    # Pick the highest-confidence entity for top_category/confidence.
    top_entity = max(entities, key=lambda e: e.confidence, default=None)
    top_category = top_entity.category if top_entity else None
    top_confidence = top_entity.confidence if top_entity else 0.0

    return AnalysisResult(
        text_hash="sha256:" + hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
        entities=entities,
        score=top_chunk.result.score,
        sensitivity_level=top_chunk.result.sensitivity_level,
        category_groups_found=groups,
        top_category=top_category,
        top_confidence=top_confidence,
        entity_count=len(entities),
        processing_time_ms=sum(c.result.processing_time_ms for c in chunks),
        layers_invoked=layers,
        profile_ids=list(profile_ids),
        routing_suggestion=top_chunk.result.routing_suggestion,
    )


__all__ = [
    "DEFAULT_CHUNK_CHARS",
    "ChunkResult",
    "DocumentAnalysisResult",
    "UnsupportedDocumentFormatError",
    "aggregate_chunk_results",
    "chunk_text",
    "extract_text",
]
