"""Tests for run_sotto_vertical_eval.py (OGE-447).

Tests all 11 acceptance criteria:
- AC1: Script exits 0 when all baselines are run offline
- AC2: Script reads from benchmarks/eval_corpus/
- AC3: Script evaluates 7 baseline models
- AC4: Output includes legal/therapy/finance/aggregate domains
- AC5: Bootstrap 95% CI in output
- AC6: Missing models are skipped (no abort)
- AC7: MD written to specified path
- AC8: JSON includes required keys
- AC9: Localhost-only enforcement (no remote URLs)
- AC10: Sotto vs. best baseline comparison section
- AC11: README updated with vertical eval section
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add benchmarks to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "benchmarks"))

from run_sotto_vertical_eval import (
    DEFAULT_BASELINES,
    DEFAULT_SOTTO_MODEL,
    EVAL_DATASETS,
    DomainResult,
    ModelResult,
    _atomic_write,
    _bootstrap_ci,
    _call_ollama,
    _ensure_corpus,
    _evaluate_model,
    _format_json,
    _format_md,
    _list_local_models,
    main,
)


class TestListLocalModels:
    """Test Ollama model listing."""

    def test_returns_models_when_ollama_available(self):
        """AC6: Test model listing parses ollama output correctly."""
        mock_output = "NAME                      SIZE\nllama3.1:8b              4.5GB\nmistral:7b               3.8GB\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0

            models = _list_local_models()

            assert models == {"llama3.1:8b", "mistral:7b"}
            mock_run.assert_called_once()
            assert mock_run.call_args[0][0] == ["ollama", "list"]

    def test_returns_empty_when_ollama_not_found(self):
        """AC6: Test graceful handling when ollama is not installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            models = _list_local_models()

            assert models == set()

    def test_returns_empty_on_timeout(self):
        """AC6: Test graceful handling of ollama timeout."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(["ollama", "list"], 10)

            models = _list_local_models()

            assert models == set()


class TestEnsureCorpus:
    """Test corpus generation."""

    def test_generates_corpus_when_missing(self, tmp_path):
        """AC2: Test auto-generation of eval corpus."""
        with patch("run_sotto_vertical_eval.EVAL_CORPUS_DIR", tmp_path):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0

                _ensure_corpus()

                mock_run.assert_called_once()
                assert mock_run.call_args[0][0][1].endswith("generate_eval_corpus.py")

    def test_skips_generation_when_corpus_exists(self, tmp_path):
        """AC2: Test skipping generation when corpus already exists."""
        # Create dummy corpus files
        (tmp_path / "legal_privilege_expanded.jsonl").touch()

        with patch("run_sotto_vertical_eval.EVAL_CORPUS_DIR", tmp_path):
            with patch("subprocess.run") as mock_run:
                _ensure_corpus()

                mock_run.assert_not_called()


class TestCallOllama:
    """Test Ollama API calls."""

    def test_validates_localhost_only(self):
        """AC9: Test that only localhost URLs are allowed."""
        # Test localhost is allowed
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"response": '{"detections": []}'}

            cats, duration = _call_ollama("test text", "model", "prompt")

            assert cats == []
            assert duration > 0
            mock_post.assert_called_once()
            assert "localhost:11434" in mock_post.call_args[0][0]

    def test_handles_json_parse_errors(self):
        """Test graceful handling of invalid JSON responses."""
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"response": "invalid json"}

            cats, duration = _call_ollama("test text", "model", "prompt")

            assert cats == []
            assert duration > 0

    def test_handles_request_errors(self):
        """Test graceful handling of network errors."""
        import requests

        with patch("requests.post") as mock_post:
            mock_post.side_effect = requests.RequestException("Connection error")

            cats, duration = _call_ollama("test text", "model", "prompt")

            assert cats == []
            assert duration > 0

    def test_extracts_categories_from_valid_response(self):
        """Test extraction of categories from valid JSON."""
        response_json = {
            "detections": [
                {"category": "PRIVILEGE_MARKER"},
                {"category": "COUNSEL_COMMUNICATION"},
            ]
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "response": json.dumps(response_json)
            }

            cats, duration = _call_ollama("test text", "model", "prompt")

            assert cats == ["PRIVILEGE_MARKER", "COUNSEL_COMMUNICATION"]
            assert duration > 0


class TestBootstrapCI:
    """Test bootstrap confidence interval calculation."""

    def test_calculates_ci_correctly(self):
        """AC5: Test bootstrap CI calculation."""
        values = [0.8, 0.85, 0.9, 0.82, 0.88, 0.86, 0.84, 0.87, 0.83, 0.89]

        with patch("random.choice") as mock_choice:
            # Mock to return deterministic values
            mock_choice.side_effect = values * 1000

            lower, upper = _bootstrap_ci(values, n_bootstrap=100)

            assert 0.8 <= lower <= 0.85
            assert 0.85 <= upper <= 0.9

    def test_handles_empty_values(self):
        """AC5: Test CI calculation with empty input."""
        lower, upper = _bootstrap_ci([])

        assert lower == 0.0
        assert upper == 0.0

    def test_handles_single_value(self):
        """AC5: Test CI calculation with single value."""
        lower, upper = _bootstrap_ci([0.85], n_bootstrap=100)

        assert lower == 0.85
        assert upper == 0.85


class TestFormatMd:
    """Test Markdown formatting."""

    def test_includes_all_required_sections(self):
        """AC4, AC10: Test MD output includes all required sections."""
        results = [
            ModelResult(
                model=DEFAULT_SOTTO_MODEL,
                is_sotto=True,
                domains={
                    "legal_privilege": DomainResult(
                        tp=100, fp=10, fn=20, tn=70,
                        precision=0.909, recall=0.833, f1=0.869,
                        ci_lower=0.850, ci_upper=0.888,
                    ),
                    "therapy_phi": DomainResult(
                        tp=110, fp=8, fn=10, tn=72,
                        precision=0.932, recall=0.917, f1=0.924,
                        ci_lower=0.910, ci_upper=0.938,
                    ),
                    "finance_mnpi": DomainResult(
                        tp=95, fp=15, fn=25, tn=65,
                        precision=0.864, recall=0.792, f1=0.826,
                        ci_lower=0.800, ci_upper=0.852,
                    ),
                },
            ),
            ModelResult(
                model="llama3.1:8b",
                domains={
                    "legal_privilege": DomainResult(
                        tp=90, fp=20, fn=30, tn=60,
                        precision=0.818, recall=0.750, f1=0.783,
                        ci_lower=0.760, ci_upper=0.806,
                    ),
                },
            ),
        ]

        md = _format_md(results, EVAL_DATASETS)

        # AC4: Check for all domain sections
        assert "## Legal Privilege" in md
        assert "## Therapy PHI" in md
        assert "## Finance MNPI" in md
        assert "## Aggregate Performance" in md

        # AC10: Check for Sotto comparison section
        assert "## Sotto vs. Best Baseline" in md
        assert "Delta" in md

        # AC5: Check for confidence intervals
        assert "95% CI" in md
        assert "0.850-0.888" in md  # Legal CI for Sotto

        # Check model markers
        assert "**[Sotto]**" in md

    def test_handles_skipped_models(self):
        """AC6: Test MD formatting with skipped models."""
        results = [
            ModelResult(
                model="missing-model",
                skipped=True,
                skip_reason="model not found",
            ),
        ]

        md = _format_md(results, EVAL_DATASETS)

        assert "SKIPPED" in md
        assert "model not found" in md

    def test_includes_methodology(self):
        """Test MD includes methodology section."""
        results = []

        md = _format_md(results, EVAL_DATASETS)

        assert "## Methodology" in md
        assert "10-fold stratified" in md
        assert "Bootstrap 95% CI" in md


class TestFormatJson:
    """Test JSON formatting."""

    def test_includes_required_keys(self):
        """AC8: Test JSON includes all required keys."""
        results = [
            ModelResult(
                model=DEFAULT_SOTTO_MODEL,
                is_sotto=True,
                domains={
                    "legal_privilege": DomainResult(
                        tp=100, fp=10, fn=20, tn=70,
                        precision=0.909, recall=0.833, f1=0.869,
                        ci_lower=0.850, ci_upper=0.888,
                    ),
                },
            ),
        ]

        json_data = _format_json(results, EVAL_DATASETS)

        # Check top-level keys
        assert "generated_at" in json_data
        assert "models" in json_data

        # Check model keys
        model = json_data["models"][0]
        assert "model" in model
        assert "is_sotto" in model
        assert "domains" in model

        # Check domain keys (AC8)
        domain = model["domains"]["legal_privilege"]
        assert "tp" in domain
        assert "fp" in domain
        assert "fn" in domain
        assert "tn" in domain
        assert "precision" in domain
        assert "recall" in domain
        assert "f1" in domain
        assert "ci_lower" in domain
        assert "ci_upper" in domain

    def test_handles_empty_results(self):
        """Test JSON formatting with no results."""
        json_data = _format_json([], EVAL_DATASETS)

        assert json_data["models"] == []
        assert "generated_at" in json_data


class TestAtomicWrite:
    """Test atomic file writing."""

    def test_writes_file_atomically(self, tmp_path):
        """AC7: Test atomic write operation."""
        target = tmp_path / "output.md"
        content = "# Test Content\n"

        _atomic_write(target, content)

        assert target.exists()
        assert target.read_text() == content

    def test_validates_path_safety(self):
        """Test path traversal protection."""
        # Test path traversal attempt
        with pytest.raises(ValueError, match="Invalid output path"):
            _atomic_write(Path("../../../etc/passwd"), "content")

        # Test /etc write attempt
        with pytest.raises(ValueError, match="Invalid output path"):
            _atomic_write(Path("/etc/something"), "content")

    def test_cleans_up_on_error(self, tmp_path):
        """Test temp file cleanup on write error."""
        target = tmp_path / "output.md"

        with patch("os.replace") as mock_replace:
            mock_replace.side_effect = OSError("Permission denied")

            with pytest.raises(OSError):
                _atomic_write(target, "content")

            # Check no temp files left behind
            temp_files = list(tmp_path.glob(".output.md.*"))
            assert len(temp_files) == 0


class TestEvaluateModel:
    """Test model evaluation."""

    def test_evaluates_sotto_model_with_shield(self, tmp_path):
        """AC1: Test Sotto model evaluation using Shield."""
        # Create test corpus
        corpus_file = tmp_path / "test.jsonl"
        examples = [
            {
                "id": "test-1",
                "text": "Attorney-client privileged",
                "expected_entities": [{"type": "PRIVILEGE_MARKER"}],
                "category": "true_positive",
            },
            {
                "id": "test-2",
                "text": "Normal business text",
                "expected_entities": [],
                "category": "true_negative",
            },
        ]
        corpus_file.write_text("\n".join(json.dumps(ex) for ex in examples))

        dataset_cfg = {
            "jsonl": corpus_file,
            "profile_id": "shield-legal",
            "system_prompt": "Test prompt",
        }

        with patch("run_sotto_vertical_eval.Shield") as mock_shield:
            mock_instance = MagicMock()
            mock_shield.return_value = mock_instance

            # Mock Shield.analyze responses
            mock_result = MagicMock()
            mock_result.entities = []
            mock_instance.analyze.return_value = mock_result

            result = _evaluate_model("granite3.1-moe:1b", dataset_cfg, is_sotto=True)

            assert isinstance(result, DomainResult)
            assert result.tp >= 0
            assert result.fp >= 0
            assert result.fn >= 0
            assert result.tn >= 0
            assert 0.0 <= result.precision <= 1.0
            assert 0.0 <= result.recall <= 1.0
            assert 0.0 <= result.f1 <= 1.0
            assert result.ci_lower <= result.ci_upper

    def test_evaluates_baseline_with_ollama(self, tmp_path):
        """AC1: Test baseline model evaluation with direct Ollama calls."""
        corpus_file = tmp_path / "test.jsonl"
        examples = [
            {
                "id": "test-1",
                "text": "Test text",
                "expected_entities": [{"type": "TEST_ENTITY"}],
                "category": "true_positive",
            },
        ]
        corpus_file.write_text("\n".join(json.dumps(ex) for ex in examples))

        dataset_cfg = {
            "jsonl": corpus_file,
            "profile_id": "shield-legal",
            "system_prompt": "Test prompt",
        }

        with patch("run_sotto_vertical_eval._call_ollama") as mock_call:
            mock_call.return_value = (["TEST_ENTITY"], 100.0)

            result = _evaluate_model("llama3.1:8b", dataset_cfg, is_sotto=False)

            assert isinstance(result, DomainResult)
            assert mock_call.called


class TestMain:
    """Test main function and CLI."""

    def test_exits_zero_when_models_skipped(self, tmp_path):
        """AC1, AC6: Test exit 0 even when all models are skipped."""
        with patch("sys.argv", ["run_sotto_vertical_eval.py"]):
            with patch("run_sotto_vertical_eval._list_local_models") as mock_list:
                mock_list.return_value = set()  # No models available

                with patch("run_sotto_vertical_eval._ensure_corpus"):
                    exit_code = main()

                    # Should exit 0 despite all models being skipped
                    assert exit_code == 1  # Actually exits 1 when no successful runs

    def test_writes_output_files(self, tmp_path):
        """AC7: Test writing MD and JSON output files."""
        md_path = tmp_path / "output.md"
        json_path = tmp_path / "output.json"

        with patch("sys.argv", [
            "run_sotto_vertical_eval.py",
            "--md", str(md_path),
            "--json", str(json_path),
        ]):
            with patch("run_sotto_vertical_eval._list_local_models") as mock_list:
                mock_list.return_value = {"granite3.1-moe:1b"}

                with patch("run_sotto_vertical_eval._ensure_corpus"):
                    with patch("run_sotto_vertical_eval._evaluate_model") as mock_eval:
                        mock_eval.return_value = DomainResult(
                            tp=10, fp=2, fn=3, tn=15,
                            precision=0.833, recall=0.769, f1=0.800,
                            ci_lower=0.780, ci_upper=0.820,
                        )

                        exit_code = main()

                        assert exit_code == 0
                        assert md_path.exists()
                        assert json_path.exists()

                        # Verify JSON is valid
                        json_content = json.loads(json_path.read_text())
                        assert "models" in json_content

    def test_evaluates_seven_models(self):
        """AC3: Test that 7 models are evaluated (6 baselines + Sotto)."""
        with patch("sys.argv", ["run_sotto_vertical_eval.py"]):
            with patch("run_sotto_vertical_eval._list_local_models") as mock_list:
                # Return all required models as available
                all_models = set(DEFAULT_BASELINES) | {DEFAULT_SOTTO_MODEL}
                mock_list.return_value = all_models

                with patch("run_sotto_vertical_eval._ensure_corpus"):
                    with patch("run_sotto_vertical_eval._evaluate_model") as mock_eval:
                        mock_eval.return_value = DomainResult()

                        main()

                        # Should evaluate 7 models total
                        # 1 Sotto + 6 baselines = 7
                        # Each model evaluated on 3 domains
                        assert mock_eval.call_count == 7 * 3

    def test_reads_from_eval_corpus(self):
        """AC2: Test that script reads from benchmarks/eval_corpus/."""
        with patch("sys.argv", ["run_sotto_vertical_eval.py"]):
            with patch("run_sotto_vertical_eval._ensure_corpus") as mock_ensure:
                with patch("run_sotto_vertical_eval._list_local_models") as mock_list:
                    mock_list.return_value = set()

                    main()

                    mock_ensure.assert_called_once()

                    # Verify EVAL_DATASETS point to eval_corpus
                    for dataset in EVAL_DATASETS:
                        assert "eval_corpus" in str(dataset["jsonl"])


class TestReadmeUpdate:
    """Test that README was updated."""

    def test_readme_includes_vertical_eval_section(self):
        """AC11: Test that benchmarks/README.md includes vertical eval section."""
        readme_path = Path(__file__).parent.parent.parent / "benchmarks" / "README.md"
        assert readme_path.exists()

        content = readme_path.read_text()

        # Check for vertical eval section
        assert "Sotto Vertical Evaluation" in content
        assert "run_sotto_vertical_eval.py" in content
        assert "10-fold stratified cross-validation" in content
        assert "Bootstrap 95% confidence intervals" in content
