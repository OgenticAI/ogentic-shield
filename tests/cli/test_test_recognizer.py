"""Tests for the ``ogentic-shield test-recognizer`` CLI command (OGE-322)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from ogentic_shield.cli.main import cli

# A minimal but valid recognizer module written to a tmp_path. Kept here
# (rather than under ``tests/fixtures/``) because every test wants its
# own fresh file — module reloading + sys.path mutation is the kind of
# state that bites when fixtures are shared.
RECOGNIZER_SRC = textwrap.dedent("""
    from presidio_analyzer import Pattern, PatternRecognizer

    class FixtureIdRecognizer(PatternRecognizer):
        '''Detects FIXTURE-prefixed 5-digit IDs.'''
        PATTERNS = [
            Pattern(name="fixture_id", regex=r"\\bFIXTURE-\\d{5}\\b", score=0.95),
        ]
        CONTEXT_WORDS = ["fixture", "test"]

        def __init__(self):
            super().__init__(
                supported_entity="FIXTURE_ID",
                patterns=self.PATTERNS,
                context=self.CONTEXT_WORDS,
                supported_language="en",
            )

    SAMPLE_TEXTS = [
        "The fixture FIXTURE-12345 was logged.",
        "No identifiers in this string.",
    ]
""").strip()


@pytest.fixture()
def recognizer_path(tmp_path: Path) -> Path:
    path = tmp_path / "fixture_recognizer.py"
    path.write_text(RECOGNIZER_SRC)
    return path


class TestTestRecognizerCommand:
    """End-to-end tests for the ``test-recognizer`` CLI command."""

    def test_runs_against_sample_texts(self, recognizer_path: Path):
        runner = CliRunner()
        result = runner.invoke(cli, ["test-recognizer", str(recognizer_path)])
        assert result.exit_code == 0, result.output
        assert "FixtureIdRecognizer" in result.output
        assert "FIXTURE_ID" in result.output
        # The positive sample should produce a match; the negative one shouldn't.
        assert "FIXTURE-12345" in result.output
        assert "no matches" in result.output
        # The summary footer reports the total.
        assert "1 match" in result.output

    def test_runs_against_inline_text(self, recognizer_path: Path):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "test-recognizer",
                str(recognizer_path),
                "--text",
                "Tracking FIXTURE-99999 today",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "FIXTURE-99999" in result.output

    def test_runs_against_text_file(self, recognizer_path: Path, tmp_path: Path):
        text_file = tmp_path / "input.txt"
        text_file.write_text("File contains FIXTURE-77777 inline.")
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "test-recognizer",
                str(recognizer_path),
                "--text-file",
                str(text_file),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "FIXTURE-77777" in result.output
        assert "input.txt" in result.output

    def test_min_confidence_filters_matches(self, recognizer_path: Path):
        # Score is 0.95 so a threshold above that drops everything.
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "test-recognizer",
                str(recognizer_path),
                "--text",
                "Tracking FIXTURE-00001",
                "--min-confidence",
                "0.99",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "no matches" in result.output

    def test_errors_if_no_recognizer_classes(self, tmp_path: Path):
        empty = tmp_path / "empty_module.py"
        empty.write_text("# nothing here\nx = 1\n")
        runner = CliRunner()
        result = runner.invoke(cli, ["test-recognizer", str(empty)])
        assert result.exit_code != 0
        assert "No PatternRecognizer subclasses" in result.output

    def test_errors_if_no_text_supplied(self, tmp_path: Path):
        # Recognizer with no SAMPLE_TEXTS and no --text/--text-file.
        path = tmp_path / "no_samples.py"
        path.write_text(textwrap.dedent("""
            from presidio_analyzer import Pattern, PatternRecognizer
            class BareRecognizer(PatternRecognizer):
                PATTERNS = [Pattern(name="x", regex=r"\\bX\\b", score=0.9)]
                def __init__(self):
                    super().__init__(
                        supported_entity="X",
                        patterns=self.PATTERNS,
                        supported_language="en",
                    )
        """).strip())
        runner = CliRunner()
        result = runner.invoke(cli, ["test-recognizer", str(path)])
        assert result.exit_code != 0
        assert "No text to analyze" in result.output

    def test_errors_on_import_failure(self, tmp_path: Path):
        broken = tmp_path / "broken.py"
        broken.write_text("import nonexistent_module_xyz\n")
        runner = CliRunner()
        result = runner.invoke(cli, ["test-recognizer", str(broken)])
        assert result.exit_code != 0
        assert "Failed to import" in result.output

    def test_errors_when_recognizer_needs_args(self, tmp_path: Path):
        path = tmp_path / "needs_args.py"
        path.write_text(textwrap.dedent("""
            from presidio_analyzer import Pattern, PatternRecognizer
            class NeedsArgsRecognizer(PatternRecognizer):
                PATTERNS = [Pattern(name="x", regex=r"\\bX\\b", score=0.9)]
                def __init__(self, required_arg):
                    super().__init__(
                        supported_entity="X",
                        patterns=self.PATTERNS,
                        supported_language="en",
                    )
        """).strip())
        runner = CliRunner()
        result = runner.invoke(
            cli, ["test-recognizer", str(path), "--text", "X"],
        )
        assert result.exit_code != 0
        assert "constructor arguments" in result.output

    def test_template_example_runs(self):
        """The shipped template module must work out-of-the-box."""
        repo_root = Path(__file__).parent.parent.parent
        template = repo_root / "examples" / "recognizer_template.py"
        assert template.exists(), f"missing {template}"
        runner = CliRunner()
        result = runner.invoke(cli, ["test-recognizer", str(template)])
        assert result.exit_code == 0, result.output
        assert "ExampleNumberRecognizer" in result.output

    def test_gdpr_example_runs(self):
        """The shipped GDPR example must detect every positive sample."""
        repo_root = Path(__file__).parent.parent.parent
        gdpr = repo_root / "examples" / "gdpr_recognizer.py"
        assert gdpr.exists(), f"missing {gdpr}"
        runner = CliRunner()
        result = runner.invoke(cli, ["test-recognizer", str(gdpr)])
        assert result.exit_code == 0, result.output
        # Three recognizers loaded.
        assert "UkNinoRecognizer" in result.output
        assert "DeSteuerIdRecognizer" in result.output
        assert "EuVatNumberRecognizer" in result.output
        # Each positive sample produces a match.
        assert "AB123456C" in result.output  # NINO labelled
        assert "12 345 678 901" in result.output  # Steuer-ID
        assert "DE123456789" in result.output  # VAT
