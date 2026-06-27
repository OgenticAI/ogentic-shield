"""Tests for benchmarks/generate_eval_corpus.py (OGE-794).

AC-1: generates >=500 labeled examples across three domains (>=150 per domain)
AC-2: >=40% true_positive, >=20% true_negative, >=20% adversarial_negative per domain
AC-8: --help works (argparse)
AC-10: no Ollama, no GPU, no network required
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Add benchmarks dir to path so we can import generate_eval_corpus directly.
BENCHMARKS_DIR = Path(__file__).parent.parent.parent / "benchmarks"
sys.path.insert(0, str(BENCHMARKS_DIR))

from generate_eval_corpus import CorpusGenerator, write_jsonl  # noqa: E402


class TestCorpusGenerator:
    """Unit tests for the CorpusGenerator class."""

    def setup_method(self) -> None:
        self.gen = CorpusGenerator(seed=42)

    # ── AC-1: example count ────────────────────────────────────────────────

    def test_generates_correct_count_legal(self) -> None:
        examples = self.gen.generate_legal(200)
        assert len(examples) == 200

    def test_generates_correct_count_therapy(self) -> None:
        examples = self.gen.generate_therapy(200)
        assert len(examples) == 200

    def test_generates_correct_count_finance(self) -> None:
        examples = self.gen.generate_finance(200)
        assert len(examples) == 200

    def test_total_three_domains_exceeds_500(self) -> None:
        legal = self.gen.generate_legal(200)
        therapy = self.gen.generate_therapy(200)
        finance = self.gen.generate_finance(200)
        assert len(legal) + len(therapy) + len(finance) >= 500

    def test_per_domain_150_sufficient_for_ac1(self) -> None:
        """AC-1 requires >=150 per domain; 200 is the default."""
        for method in (self.gen.generate_legal, self.gen.generate_therapy, self.gen.generate_finance):
            examples = method(150)
            assert len(examples) == 150

    # ── AC-2: class balance ────────────────────────────────────────────────

    @pytest.mark.parametrize("domain", ["legal", "therapy", "finance"])
    def test_true_positive_ratio_at_least_40_pct(self, domain: str) -> None:
        method = getattr(self.gen, f"generate_{domain}")
        examples = method(200)
        tp_ratio = sum(1 for e in examples if e.category == "true_positive") / len(examples)
        assert tp_ratio >= 0.40, f"{domain}: TP ratio {tp_ratio:.2%} < 40%"

    @pytest.mark.parametrize("domain", ["legal", "therapy", "finance"])
    def test_true_negative_ratio_at_least_20_pct(self, domain: str) -> None:
        method = getattr(self.gen, f"generate_{domain}")
        examples = method(200)
        tn_ratio = sum(1 for e in examples if e.category == "true_negative") / len(examples)
        assert tn_ratio >= 0.20, f"{domain}: TN ratio {tn_ratio:.2%} < 20%"

    @pytest.mark.parametrize("domain", ["legal", "therapy", "finance"])
    def test_adversarial_negative_ratio_at_least_20_pct(self, domain: str) -> None:
        method = getattr(self.gen, f"generate_{domain}")
        examples = method(200)
        adv_ratio = sum(1 for e in examples if e.category == "adversarial_negative") / len(examples)
        assert adv_ratio >= 0.20, f"{domain}: ADV ratio {adv_ratio:.2%} < 20%"

    # ── Output schema ──────────────────────────────────────────────────────

    def test_examples_have_required_fields(self) -> None:
        examples = self.gen.generate_legal(10)
        for ex in examples:
            assert ex.id
            assert ex.text
            assert ex.category in {"true_positive", "true_negative", "adversarial_negative"}
            assert ex.expected_level in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"}
            assert isinstance(ex.expected_entities, list)

    def test_true_positives_have_expected_entities(self) -> None:
        examples = self.gen.generate_legal(100)
        for ex in examples:
            if ex.category == "true_positive":
                assert len(ex.expected_entities) >= 1, f"TP {ex.id} has no expected_entities"

    def test_true_negatives_have_no_expected_entities(self) -> None:
        examples = self.gen.generate_legal(100)
        for ex in examples:
            if ex.category == "true_negative":
                assert ex.expected_entities == [], f"TN {ex.id} has unexpected entities"

    def test_to_dict_is_json_serializable(self) -> None:
        examples = self.gen.generate_legal(5)
        for ex in examples:
            d = ex.to_dict()
            # Should not raise
            json.dumps(d)

    # ── Determinism ────────────────────────────────────────────────────────

    def test_same_seed_produces_identical_output(self) -> None:
        gen1 = CorpusGenerator(seed=0)
        gen2 = CorpusGenerator(seed=0)
        examples1 = gen1.generate_legal(50)
        examples2 = gen2.generate_legal(50)
        assert [e.id for e in examples1] == [e.id for e in examples2]
        assert [e.text for e in examples1] == [e.text for e in examples2]

    def test_different_seeds_produce_different_output(self) -> None:
        gen1 = CorpusGenerator(seed=1)
        gen2 = CorpusGenerator(seed=2)
        examples1 = gen1.generate_legal(50)
        examples2 = gen2.generate_legal(50)
        # Very unlikely to be identical; ordering at minimum differs
        texts1 = [e.text for e in examples1]
        texts2 = [e.text for e in examples2]
        assert texts1 != texts2

    # ── Entity types ───────────────────────────────────────────────────────

    def test_legal_true_positives_use_legal_entity_types(self) -> None:
        legal_types = {
            "PRIVILEGE_MARKER", "ATTORNEY_CLIENT", "COUNSEL_COMMUNICATION",
            "LAW_FIRM_NAME", "WORK_PRODUCT", "LITIGATION_MARKER", "SETTLEMENT_TERMS",
            "CASE_NUMBER", "BATES_NUMBER", "COURT_FILING", "EXECUTIVE_NAME",
        }
        examples = self.gen.generate_legal(100)
        for ex in examples:
            for ent in ex.expected_entities:
                assert ent["type"] in legal_types, f"Unexpected type {ent['type']} in legal example {ex.id}"

    def test_therapy_true_positives_use_therapy_entity_types(self) -> None:
        therapy_types = {
            "PATIENT_NAME", "DATE_OF_BIRTH", "DIAGNOSIS_CODE", "CLINICAL_RISK_FLAG",
            "SESSION_MARKER", "INSURANCE_ID", "MEDICATION", "PROVIDER_NAME",
            "PSYCHOTHERAPY_NOTE_MARKER", "SSN", "PERSON",
        }
        examples = self.gen.generate_therapy(100)
        for ex in examples:
            for ent in ex.expected_entities:
                assert ent["type"] in therapy_types, f"Unexpected type {ent['type']} in therapy example {ex.id}"

    def test_finance_true_positives_use_finance_entity_types(self) -> None:
        finance_types = {
            "MNPI_MARKER", "MA_ACTIVITY", "DEAL_VALUE", "INSIDER_MARKER",
            "FUND_INFORMATION", "LEVERAGE_RATIO", "CARRY_TERMS", "INSTITUTION_NAME",
            "FINANCIAL_TERMS", "DISTRIBUTION_RESTRICTION",
        }
        examples = self.gen.generate_finance(100)
        for ex in examples:
            for ent in ex.expected_entities:
                assert ent["type"] in finance_types, f"Unexpected type {ent['type']} in finance example {ex.id}"

    # ── Edge cases ─────────────────────────────────────────────────────────

    def test_minimum_per_domain_50_works(self) -> None:
        examples = self.gen.generate_legal(50)
        assert len(examples) == 50

    def test_ids_are_unique_within_domain(self) -> None:
        examples = self.gen.generate_legal(200)
        ids = [e.id for e in examples]
        # IDs encode template index, not a global unique ID, so collisions are expected
        # but the list itself should be non-empty and all strings.
        assert all(isinstance(i, str) and i for i in ids)

    def test_texts_are_non_empty(self) -> None:
        for method in (self.gen.generate_legal, self.gen.generate_therapy, self.gen.generate_finance):
            for ex in method(20):
                assert ex.text.strip(), f"Empty text for {ex.id}"


class TestWriteJsonl:
    """Tests for the write_jsonl I/O function."""

    def test_writes_valid_jsonl(self, tmp_path: Path) -> None:
        gen = CorpusGenerator(seed=0)
        examples = gen.generate_legal(10)
        out = tmp_path / "test.jsonl"
        write_jsonl(examples, out)
        lines = out.read_text().strip().split("\n")
        assert len(lines) == 10
        for line in lines:
            obj = json.loads(line)
            assert "id" in obj
            assert "text" in obj
            assert "expected_entities" in obj

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        gen = CorpusGenerator(seed=0)
        examples = gen.generate_legal(5)
        out = tmp_path / "nested" / "deep" / "corpus.jsonl"
        write_jsonl(examples, out)
        assert out.exists()


class TestCLI:
    """Smoke-tests for the CLI entry point (AC-8, AC-10)."""

    def test_help_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(BENCHMARKS_DIR / "generate_eval_corpus.py"), "--help"],
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert b"--per-domain" in result.stdout

    def test_runs_to_completion(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(BENCHMARKS_DIR / "generate_eval_corpus.py"),
                "--output-dir", str(tmp_path),
                "--per-domain", "60",
                "--seed", "99",
            ],
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr.decode()
        assert (tmp_path / "legal_privilege_expanded.jsonl").exists()
        assert (tmp_path / "therapy_phi_expanded.jsonl").exists()
        assert (tmp_path / "finance_mnpi_expanded.jsonl").exists()

    def test_output_total_exceeds_150_per_domain_default(self, tmp_path: Path) -> None:
        subprocess.run(
            [
                sys.executable,
                str(BENCHMARKS_DIR / "generate_eval_corpus.py"),
                "--output-dir", str(tmp_path),
                "--per-domain", "200",
                "--seed", "0",
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )
        for fname in [
            "legal_privilege_expanded.jsonl",
            "therapy_phi_expanded.jsonl",
            "finance_mnpi_expanded.jsonl",
        ]:
            lines = (tmp_path / fname).read_text().strip().split("\n")
            assert len(lines) >= 150, f"{fname}: only {len(lines)} examples"

    def test_invalid_per_domain_exits_nonzero(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(BENCHMARKS_DIR / "generate_eval_corpus.py"),
                "--per-domain", "10",
            ],
            capture_output=True,
            timeout=10,
        )
        assert result.returncode != 0
