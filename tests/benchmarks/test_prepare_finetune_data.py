"""Tests for benchmarks/bakeoff/prepare_finetune_data.py (OGE-794 AC-3).

AC-3: prepare_finetune_data.py converts eval corpus to Together AI / Fireworks format.
AC-8: --help works.
AC-10: no network, no GPU.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

BENCHMARKS_DIR = Path(__file__).parent.parent.parent / "benchmarks"
BAKEOFF_DIR = BENCHMARKS_DIR / "bakeoff"

sys.path.insert(0, str(BENCHMARKS_DIR))
sys.path.insert(0, str(BAKEOFF_DIR))

from generate_eval_corpus import CorpusGenerator, write_jsonl  # noqa: E402
from prepare_finetune_data import (  # noqa: E402
    SYSTEM_PROMPTS,
    convert_domain,
    convert_example,
)


@pytest.fixture
def small_corpus(tmp_path: Path) -> dict[str, Path]:
    """Write a small legal corpus to a temp dir and return paths."""
    gen = CorpusGenerator(seed=7)
    legal = gen.generate_legal(60)
    p = tmp_path / "legal_privilege_expanded.jsonl"
    write_jsonl(legal, p)
    return {"legal_privilege": p}


class TestConvertExample:
    """Unit tests for convert_example()."""

    def _make_example(self, category: str, entities: list[dict]) -> dict:
        return {
            "id": "test-001",
            "text": "Privileged memo from outside counsel.",
            "expected_entities": entities,
            "expected_level": "CRITICAL" if entities else "NONE",
            "category": category,
            "notes": "test",
        }

    def test_true_positive_has_non_empty_detections(self) -> None:
        ex = self._make_example("true_positive", [{"type": "PRIVILEGE_MARKER"}])
        result = convert_example(ex, SYSTEM_PROMPTS["legal"], "together")
        messages = result["messages"]
        assistant_content = json.loads(messages[-1]["content"])
        assert len(assistant_content["detections"]) >= 1

    def test_true_negative_has_empty_detections(self) -> None:
        ex = self._make_example("true_negative", [])
        result = convert_example(ex, SYSTEM_PROMPTS["legal"], "together")
        messages = result["messages"]
        assistant_content = json.loads(messages[-1]["content"])
        assert assistant_content["detections"] == []

    def test_adversarial_negative_has_empty_detections(self) -> None:
        ex = self._make_example("adversarial_negative", [])
        result = convert_example(ex, SYSTEM_PROMPTS["legal"], "fireworks")
        messages = result["messages"]
        assistant_content = json.loads(messages[-1]["content"])
        assert assistant_content["detections"] == []

    def test_output_has_three_messages(self) -> None:
        ex = self._make_example("true_positive", [{"type": "PRIVILEGE_MARKER"}])
        result = convert_example(ex, SYSTEM_PROMPTS["legal"], "together")
        assert len(result["messages"]) == 3

    def test_messages_have_correct_roles(self) -> None:
        ex = self._make_example("true_positive", [{"type": "PRIVILEGE_MARKER"}])
        result = convert_example(ex, SYSTEM_PROMPTS["legal"], "together")
        roles = [m["role"] for m in result["messages"]]
        assert roles == ["system", "user", "assistant"]

    def test_user_message_contains_original_text(self) -> None:
        ex = self._make_example("true_positive", [{"type": "PRIVILEGE_MARKER"}])
        result = convert_example(ex, SYSTEM_PROMPTS["legal"], "together")
        assert result["messages"][1]["content"] == ex["text"]

    def test_system_message_contains_system_prompt(self) -> None:
        ex = self._make_example("true_positive", [{"type": "PRIVILEGE_MARKER"}])
        sys_prompt = SYSTEM_PROMPTS["legal"]
        result = convert_example(ex, sys_prompt, "together")
        assert result["messages"][0]["content"] == sys_prompt

    def test_invalid_provider_raises(self) -> None:
        ex = self._make_example("true_positive", [{"type": "PRIVILEGE_MARKER"}])
        with pytest.raises(ValueError, match="Unknown provider"):
            convert_example(ex, SYSTEM_PROMPTS["legal"], "openai")

    def test_output_is_json_serializable(self) -> None:
        ex = self._make_example("true_positive", [{"type": "PRIVILEGE_MARKER"}])
        result = convert_example(ex, SYSTEM_PROMPTS["legal"], "together")
        json.dumps(result)  # must not raise


class TestConvertDomain:
    """Integration tests for convert_domain()."""

    def test_creates_train_and_val_files(self, small_corpus: dict, tmp_path: Path) -> None:
        train_n, val_n = convert_domain(
            "legal_privilege",
            small_corpus["legal_privilege"],
            tmp_path / "out",
            "together",
        )
        assert (tmp_path / "out" / "legal_privilege_together_train.jsonl").exists()
        assert (tmp_path / "out" / "legal_privilege_together_val.jsonl").exists()

    def test_split_ratio_respected(self, small_corpus: dict, tmp_path: Path) -> None:
        train_n, val_n = convert_domain(
            "legal_privilege",
            small_corpus["legal_privilege"],
            tmp_path / "out",
            "together",
            split_ratio=0.8,
        )
        total = train_n + val_n
        assert train_n == int(total * 0.8)

    def test_train_lines_are_valid_jsonl(self, small_corpus: dict, tmp_path: Path) -> None:
        convert_domain(
            "legal_privilege",
            small_corpus["legal_privilege"],
            tmp_path / "out",
            "together",
        )
        train_path = tmp_path / "out" / "legal_privilege_together_train.jsonl"
        for line in train_path.read_text().strip().split("\n"):
            obj = json.loads(line)
            assert "messages" in obj
            assert len(obj["messages"]) == 3

    def test_fireworks_format_same_as_together(self, small_corpus: dict, tmp_path: Path) -> None:
        convert_domain("legal_privilege", small_corpus["legal_privilege"], tmp_path / "together", "together")
        convert_domain("legal_privilege", small_corpus["legal_privilege"], tmp_path / "fireworks", "fireworks")
        # Both formats use the same message structure
        together_path = tmp_path / "together" / "legal_privilege_together_train.jsonl"
        fireworks_path = tmp_path / "fireworks" / "legal_privilege_fireworks_train.jsonl"
        together_lines = together_path.read_text().strip().split("\n")
        fireworks_lines = fireworks_path.read_text().strip().split("\n")
        assert len(together_lines) == len(fireworks_lines)


class TestSystemPrompts:
    """Tests for the system prompt content."""

    def test_all_domains_have_system_prompts(self) -> None:
        for domain in ["legal", "therapy", "finance"]:
            assert SYSTEM_PROMPTS[domain], f"Missing system prompt for {domain}"

    def test_legal_prompt_mentions_privilege(self) -> None:
        assert "privilege" in SYSTEM_PROMPTS["legal"].lower()

    def test_therapy_prompt_mentions_phi(self) -> None:
        assert "phi" in SYSTEM_PROMPTS["therapy"].lower() or "hipaa" in SYSTEM_PROMPTS["therapy"].lower()

    def test_finance_prompt_mentions_mnpi(self) -> None:
        assert "mnpi" in SYSTEM_PROMPTS["finance"].lower()

    def test_all_prompts_contain_schema_reminder(self) -> None:
        for domain, prompt in SYSTEM_PROMPTS.items():
            assert "detections" in prompt, f"{domain} prompt missing 'detections' schema"


class TestCLI:
    """CLI smoke tests for prepare_finetune_data.py (AC-8)."""

    def test_help_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(BAKEOFF_DIR / "prepare_finetune_data.py"), "--help"],
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert b"--provider" in result.stdout or b"provider" in result.stdout

    def test_missing_input_dir_skips_gracefully(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(BAKEOFF_DIR / "prepare_finetune_data.py"),
                "--input-dir", str(tmp_path / "nonexistent"),
                "--output-dir", str(tmp_path / "out"),
            ],
            capture_output=True,
            timeout=10,
        )
        # Should exit 0 (skip) not crash
        assert result.returncode == 0
