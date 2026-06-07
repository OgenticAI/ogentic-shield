"""Tests for the document-analysis surface (OGE-398, Phase 1).

Phase 1 ships:
- The dataclasses (DocumentAnalysisResult / ChunkResult).
- The format dispatcher (.txt, .md, .log handled; PDF/DOCX/XLSX/EML/MSG/
  HTML recognized + cleanly errored until Phase 2).
- The chunker.
- The aggregator (max-score rollup with global offsets).
- The Shield.analyze_document API.

These tests pin down all of those without needing any Phase 2 libraries
installed (no pdfplumber, no python-docx, etc.).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ogentic_shield import (
    ChunkResult,
    DocumentAnalysisResult,
    DocumentRedactionResult,
    Shield,
    UnsupportedDocumentFormatError,
    unredact_text,
)
from ogentic_shield.documents import (
    DEFAULT_CHUNK_CHARS,
    aggregate_chunk_results,
    chunk_text,
    extract_text,
)
from ogentic_shield.models import (
    AnalysisResult,
    CategoryGroup,
    DetectedEntity,
    DetectionLayer,
    SensitivityLevel,
)

FIXTURES = Path(__file__).parent / "fixtures" / "documents"
LEGAL_MEMO = FIXTURES / "legal_memo.txt"
WELLNESS_BLOG = FIXTURES / "wellness_blog.md"


# ─── extract_text ───────────────────────────────────────────────────────────


class TestExtractText:
    def test_reads_txt_file(self):
        text, fmt = extract_text(LEGAL_MEMO)
        assert fmt == "text"
        assert "outside counsel" in text.lower()
        assert "Bates ACME0001234" in text

    def test_reads_md_file_as_markdown(self):
        text, fmt = extract_text(WELLNESS_BLOG)
        assert fmt == "markdown"
        assert "# Five Habits" in text

    def test_accepts_path_string(self):
        text, fmt = extract_text(str(LEGAL_MEMO))
        assert fmt == "text"
        assert text.startswith("From: General Counsel")

    def test_missing_file_raises_filenotfound(self):
        with pytest.raises(FileNotFoundError):
            extract_text(FIXTURES / "does-not-exist.txt")

    def test_unknown_extension_raises_unsupported_with_hint(self, tmp_path: Path):
        weird = tmp_path / "evidence.xyz"
        weird.write_text("anything")
        with pytest.raises(UnsupportedDocumentFormatError) as exc:
            extract_text(weird)
        assert exc.value.ext == ".xyz"
        assert exc.value.install_hint  # has a hint
        assert "Phase 2" in str(exc.value)  # mentions Phase 2

    @pytest.mark.parametrize(
        "ext,fmt_name",
        [
            (".pdf", "pdf"),
            (".docx", "docx"),
            (".xlsx", "xlsx"),
            (".eml", "eml"),
            (".msg", "msg"),
            (".html", "html"),
        ],
    )
    def test_known_phase2_extensions_raise_with_install_hint(
        self, tmp_path: Path, ext: str, fmt_name: str
    ):
        # Each Phase-2-recognized extension should raise with a clear install
        # hint mentioning the [documents] extra.
        f = tmp_path / f"sample{ext}"
        f.write_bytes(b"%PDF-fake-header-or-similar")
        with pytest.raises(UnsupportedDocumentFormatError) as exc:
            extract_text(f)
        assert exc.value.ext == fmt_name
        assert "ogentic-shield[documents]" in (exc.value.install_hint or "")


# ─── chunk_text ─────────────────────────────────────────────────────────────


class TestChunkText:
    def test_empty_input_returns_single_empty_chunk(self):
        chunks = chunk_text("")
        assert chunks == [("", "chunk 1", 0)]

    def test_short_input_returns_single_chunk(self):
        chunks = chunk_text("Hello world.\n\nSecond paragraph.")
        assert len(chunks) == 1
        assert chunks[0][1] == "chunk 1"
        assert chunks[0][2] == 0

    def test_splits_at_paragraph_boundary_when_within_chunk_size(self):
        text = "A" * 400 + "\n\n" + "B" * 400
        chunks = chunk_text(text, chunk_chars=500)
        # Should split on the paragraph boundary at offset 402 rather than
        # taking a hard cut at 500.
        assert len(chunks) == 2
        assert chunks[0][0].endswith("\n\n")
        assert chunks[1][0] == "B" * 400

    def test_falls_back_to_hard_split_when_no_paragraph_boundary(self):
        text = "A" * 1200  # no \n\n anywhere
        chunks = chunk_text(text, chunk_chars=500)
        assert len(chunks) == 3
        assert sum(len(c[0]) for c in chunks) == len(text)

    def test_offsets_are_correct(self):
        text = "First chunk content.\n\n" + "x" * 600
        chunks = chunk_text(text, chunk_chars=200)
        assert chunks[0][2] == 0
        for prev, curr in zip(chunks, chunks[1:]):
            assert curr[2] == prev[2] + len(prev[0])

    def test_rejects_non_positive_chunk_chars(self):
        with pytest.raises(ValueError):
            chunk_text("foo", chunk_chars=0)

    def test_default_chunk_size_is_10k(self):
        assert DEFAULT_CHUNK_CHARS == 10_000


# ─── aggregate_chunk_results ────────────────────────────────────────────────


def _make_chunk_result(
    index: int,
    offset: int,
    score: int,
    entities: list[DetectedEntity] | None = None,
    layers: list[DetectionLayer] | None = None,
    groups: set[CategoryGroup] | None = None,
    routing: str = "CLOUD_OK",
    level: SensitivityLevel = SensitivityLevel.NONE,
) -> ChunkResult:
    ar = AnalysisResult(
        text_hash="sha256:chunk-stub",
        entities=entities or [],
        score=score,
        sensitivity_level=level,
        category_groups_found=groups or set(),
        top_category=None,
        top_confidence=0.0,
        entity_count=len(entities or []),
        processing_time_ms=1.0,
        layers_invoked=layers or [DetectionLayer.REGEX],
        profile_ids=["shield-legal"],
        routing_suggestion=routing,
    )
    return ChunkResult(index=index, label=f"chunk {index+1}", text_offset=offset, result=ar)


def _entity(start: int, end: int, *, category: str = "PRIVILEGE_MARKER", confidence: float = 0.9) -> DetectedEntity:
    return DetectedEntity(
        text="x",
        category=category,
        category_group=CategoryGroup.PRIVILEGE,
        confidence=confidence,
        detection_layer=DetectionLayer.REGEX,
        start=start,
        end=end,
    )


class TestAggregateChunkResults:
    def test_empty_chunks_returns_zero_result(self):
        ar = aggregate_chunk_results([], full_text="", profile_ids=["shield-legal"])
        assert ar.score == 0
        assert ar.sensitivity_level == SensitivityLevel.NONE
        assert ar.entities == []
        assert ar.entity_count == 0
        assert ar.routing_suggestion == "CLOUD_OK"
        assert ar.text_hash == "sha256:" + hashlib.sha256(b"").hexdigest()

    def test_score_is_max_across_chunks(self):
        # A single CRITICAL chunk makes the whole doc CRITICAL.
        chunks = [
            _make_chunk_result(0, 0, score=10, level=SensitivityLevel.LOW, routing="CLOUD_OK"),
            _make_chunk_result(
                1, 500, score=92, level=SensitivityLevel.CRITICAL, routing="LOCAL_ONLY"
            ),
            _make_chunk_result(2, 1000, score=40, level=SensitivityLevel.MEDIUM, routing="REDACT_THEN_CLOUD"),
        ]
        ar = aggregate_chunk_results(chunks, full_text="x" * 1500, profile_ids=["shield-legal"])
        assert ar.score == 92
        assert ar.sensitivity_level == SensitivityLevel.CRITICAL
        # Routing follows the top-scoring chunk — most cautious wins by virtue
        # of being the max score.
        assert ar.routing_suggestion == "LOCAL_ONLY"

    def test_category_groups_are_union(self):
        chunks = [
            _make_chunk_result(0, 0, score=10, groups={CategoryGroup.PII}),
            _make_chunk_result(1, 500, score=20, groups={CategoryGroup.PRIVILEGE}),
            _make_chunk_result(2, 1000, score=15, groups={CategoryGroup.PII, CategoryGroup.PHI}),
        ]
        ar = aggregate_chunk_results(chunks, full_text="x" * 1500, profile_ids=["shield-legal"])
        assert ar.category_groups_found == {
            CategoryGroup.PII,
            CategoryGroup.PRIVILEGE,
            CategoryGroup.PHI,
        }

    def test_entity_offsets_rebased_to_document(self):
        chunks = [
            _make_chunk_result(0, 0, score=10, entities=[_entity(5, 10)]),
            _make_chunk_result(1, 500, score=20, entities=[_entity(3, 7)]),  # chunk-local
            _make_chunk_result(2, 1000, score=30, entities=[_entity(0, 4)]),
        ]
        ar = aggregate_chunk_results(chunks, full_text="x" * 1500, profile_ids=["shield-legal"])
        assert len(ar.entities) == 3
        # Chunk-local offsets shifted by the chunk's text_offset.
        starts_ends = [(e.start, e.end) for e in ar.entities]
        assert starts_ends == [(5, 10), (503, 507), (1000, 1004)]

    def test_top_category_picks_highest_confidence(self):
        chunks = [
            _make_chunk_result(
                0,
                0,
                score=20,
                entities=[
                    _entity(0, 5, category="A", confidence=0.6),
                    _entity(10, 15, category="B", confidence=0.95),  # winner
                ],
            ),
            _make_chunk_result(
                1, 500, score=10, entities=[_entity(0, 5, category="C", confidence=0.8)]
            ),
        ]
        ar = aggregate_chunk_results(chunks, full_text="x" * 800, profile_ids=["shield-legal"])
        assert ar.top_category == "B"
        assert ar.top_confidence == 0.95

    def test_layers_invoked_union_preserves_first_order(self):
        chunks = [
            _make_chunk_result(
                0, 0, score=5, layers=[DetectionLayer.REGEX, DetectionLayer.NER]
            ),
            _make_chunk_result(
                1, 500, score=5, layers=[DetectionLayer.RULES, DetectionLayer.REGEX]
            ),
        ]
        ar = aggregate_chunk_results(chunks, full_text="x" * 800, profile_ids=["shield-legal"])
        assert ar.layers_invoked == [
            DetectionLayer.REGEX,
            DetectionLayer.NER,
            DetectionLayer.RULES,
        ]

    def test_text_hash_is_sha256_of_full_text(self):
        full = "Hello, document."
        chunks = [_make_chunk_result(0, 0, score=0)]
        ar = aggregate_chunk_results(chunks, full_text=full, profile_ids=["shield-legal"])
        assert ar.text_hash == "sha256:" + hashlib.sha256(full.encode("utf-8")).hexdigest()


# ─── Shield.analyze_document end-to-end ─────────────────────────────────────


class TestShieldAnalyzeDocument:
    """End-to-end through the real pipeline — slower than the helpers above
    (one Presidio cold start) but proves the wiring works."""

    @pytest.fixture(scope="class")
    def shield(self):
        return Shield(profiles=["shield-legal"])

    def test_returns_document_analysis_result_for_txt(self, shield):
        result = shield.analyze_document(LEGAL_MEMO)
        assert isinstance(result, DocumentAnalysisResult)
        assert result.format == "text"
        assert result.path == str(LEGAL_MEMO)
        assert len(result.chunks) >= 1
        # The legal memo is privileged-and-confidential and references
        # outside counsel + work product — must surface as elevated risk.
        assert result.aggregate.score > 0
        assert result.aggregate.category_groups_found  # at least one group
        # Aggregate's entities concatenated and rebased — never empty for
        # this fixture (legal recognizers fire on the explicit markers).
        assert result.aggregate.entity_count >= 1

    def test_markdown_is_recognized_as_markdown(self, shield):
        result = shield.analyze_document(WELLNESS_BLOG)
        assert result.format == "markdown"
        # Wellness blog is a true negative — score should stay low/zero.
        # (We don't pin an exact value; the scoring engine may evolve.
        # The key property: no privileged categories detected.)
        assert CategoryGroup.PRIVILEGE not in result.aggregate.category_groups_found
        assert CategoryGroup.PHI not in result.aggregate.category_groups_found

    def test_unsupported_format_raises_with_install_hint(self, shield, tmp_path: Path):
        pdf_like = tmp_path / "term_sheet.pdf"
        pdf_like.write_bytes(b"%PDF-1.4 fake")
        with pytest.raises(UnsupportedDocumentFormatError) as exc:
            shield.analyze_document(pdf_like)
        assert exc.value.ext == "pdf"
        assert "ogentic-shield[documents]" in (exc.value.install_hint or "")

    def test_missing_file_raises_filenotfound(self, shield, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            shield.analyze_document(tmp_path / "nope.txt")

    def test_chunk_chars_override_is_honored(self, shield, tmp_path: Path):
        # Synthesize a longer document that will produce multiple chunks
        # under a small chunk_chars setting.
        big = tmp_path / "big.txt"
        big.write_text("This is a paragraph.\n\n" * 50)
        result = shield.analyze_document(big, chunk_chars=200)
        assert len(result.chunks) > 1
        # Chunk offsets must be monotonically non-decreasing.
        offsets = [c.text_offset for c in result.chunks]
        assert offsets == sorted(offsets)


# ─── Shield.redact_document end-to-end (OGE-792) ────────────────────────────


class TestShieldRedactDocument:
    """End-to-end through the redaction pipeline.

    Same shape as ``TestShieldAnalyzeDocument`` — one Presidio cold start
    per class via the ``shield`` fixture, then several light tests that
    exercise the document-redaction contract.
    """

    @pytest.fixture(scope="class")
    def shield(self):
        return Shield(profiles=["shield-legal"])

    def test_returns_document_redaction_result(self, shield):
        result = shield.redact_document(LEGAL_MEMO)
        assert isinstance(result, DocumentRedactionResult)
        assert result.format == "text"
        assert result.path == str(LEGAL_MEMO)
        # The aggregate analysis must drive redaction — we expose it on
        # the result so audit consumers don't have to re-run the pipeline.
        assert isinstance(result.analysis, DocumentAnalysisResult)
        # original_text is the unredacted extraction; redacted_text is
        # the substantive output. They must differ because the legal
        # memo contains entities (people, organisations, dates).
        assert result.original_text  # non-empty
        assert result.original_text == LEGAL_MEMO.read_text(encoding="utf-8")
        assert result.redacted_text != result.original_text
        # At least one entity got tokenised — mapping populated.
        assert result.mapping.tokens

    def test_markdown_is_redacted(self, shield):
        result = shield.redact_document(WELLNESS_BLOG)
        assert result.format == "markdown"
        # Wellness blog is a true negative for the legal profile — no
        # entities matching the default redaction categories. Redacted
        # text should equal the original (no-op redaction).
        assert result.redacted_text == result.original_text
        assert not result.mapping.tokens

    def test_unredact_round_trip(self, shield):
        result = shield.redact_document(LEGAL_MEMO)
        # Mirror the audit-row privacy lock — no original entity text
        # leaks into ``redacted_text``. We sample the mapping's originals
        # and assert each is absent from the redacted output. This is the
        # load-bearing privacy contract for redact_document.
        for original in result.mapping.tokens.values():
            assert original not in result.redacted_text, (
                f"redacted_text still contains original entity {original!r}"
            )
        # And the inverse: unredact restores the original byte-for-byte.
        restored = unredact_text(result.redacted_text, result.mapping)
        assert restored == result.original_text

    def test_unsupported_format_raises_with_install_hint(
        self, shield, tmp_path: Path
    ):
        pdf_like = tmp_path / "term_sheet.pdf"
        pdf_like.write_bytes(b"%PDF-1.4 fake")
        with pytest.raises(UnsupportedDocumentFormatError) as exc:
            shield.redact_document(pdf_like)
        # Same dispatcher as analyze_document → same hint.
        assert exc.value.ext == "pdf"
        assert "ogentic-shield[documents]" in (exc.value.install_hint or "")

    def test_missing_file_raises_filenotfound(self, shield, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            shield.redact_document(tmp_path / "nope.txt")

    def test_redact_categories_override_is_honored(
        self, shield, tmp_path: Path
    ):
        # Author a minimal document with a clearly-detectable entity and
        # request a category override that wouldn't catch it. The result
        # should be a no-op redaction, proving the override flowed
        # through to redact_text rather than getting silently dropped.
        doc = tmp_path / "tiny.txt"
        doc.write_text("Email me at alice@example.com about the merger.")
        # Override to a category that won't match an email address.
        result = shield.redact_document(
            doc, redact_categories=["NonexistentCategory"]
        )
        assert result.redacted_text == result.original_text
        assert not result.mapping.tokens
