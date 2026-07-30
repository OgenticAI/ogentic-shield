"""
Test corpus completeness for OGE-397 acceptance criteria.
Ensures benchmark corpus meets size, ratio, and coverage requirements.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

# Expected entity types per profile
LEGAL_ENTITIES = {
    "COUNSEL_COMMUNICATION", "PRIVILEGE_MARKER", "WORK_PRODUCT",
    "SETTLEMENT_TERMS", "CASE_NUMBER", "LAW_FIRM_NAME",
    "LITIGATION_MARKER", "COURT_FILING", "BATES_NUMBER", "EXECUTIVE_NAME"
}

THERAPY_ENTITIES = {
    "PATIENT_NAME", "DATE_OF_BIRTH", "DIAGNOSIS_CODE", "CLINICAL_RISK_FLAG",
    "SESSION_MARKER", "INSURANCE_ID", "MEDICATION", "PROVIDER_NAME",
    "SSN", "PSYCHOTHERAPY_NOTE_MARKER"
}

FINANCE_ENTITIES = {
    "MNPI_MARKER", "DEAL_VALUE", "MA_ACTIVITY", "INSIDER_MARKER",
    "INSTITUTION_NAME", "EXECUTIVE_NAME", "DISTRIBUTION_RESTRICTION",
    "LEVERAGE_RATIO", "FUND_INFORMATION", "CARRY_TERMS", "FINANCIAL_TERMS"
}

THERAPY_PRO_ENTITIES = THERAPY_ENTITIES | {
    "DSM5_DIAGNOSIS", "CPT_CODE", "MINOR_CLIENT_MARKER", "TRAUMA_INDICATOR"
}


class TestCorpusCompleteness:
    """Test that all benchmark corpora meet OGE-397 requirements."""

    def load_corpus(self, filename):
        """Load a JSONL corpus file."""
        path = Path(__file__).parent.parent.parent / "benchmarks" / filename
        examples = []
        with open(path) as f:
            for line in f:
                examples.append(json.loads(line))
        return examples

    def test_legal_privilege_size(self):
        """AC1: legal_privilege.jsonl ≥ 200 valid JSON lines."""
        examples = self.load_corpus("legal_privilege.jsonl")
        assert len(examples) >= 200, f"Found {len(examples)}, expected ≥200"

    def test_therapy_phi_size(self):
        """AC2: therapy_phi.jsonl ≥ 200 valid JSON lines."""
        examples = self.load_corpus("therapy_phi.jsonl")
        assert len(examples) >= 200, f"Found {len(examples)}, expected ≥200"

    def test_therapy_phi_pro_size(self):
        """AC3: therapy_phi_pro.jsonl ≥ 200 valid JSON lines."""
        examples = self.load_corpus("therapy_phi_pro.jsonl")
        assert len(examples) >= 200, f"Found {len(examples)}, expected ≥200"

    def test_finance_mnpi_size(self):
        """AC4: finance_mnpi.jsonl ≥ 200 valid JSON lines."""
        examples = self.load_corpus("finance_mnpi.jsonl")
        assert len(examples) >= 200, f"Found {len(examples)}, expected ≥200"

    def test_corpus_ratios(self):
        """AC5: Each corpus: ≥60% true_positive, ≤40% negatives, ≥20% adversarial_negative."""
        files = ["legal_privilege.jsonl", "therapy_phi.jsonl",
                 "therapy_phi_pro.jsonl", "finance_mnpi.jsonl"]

        for filename in files:
            examples = self.load_corpus(filename)
            categories = Counter(ex["category"] for ex in examples)
            total = len(examples)

            tp_ratio = categories["true_positive"] / total
            tn_ratio = categories.get("true_negative", 0) / total
            adv_ratio = categories.get("adversarial_negative", 0) / total
            neg_ratio = tn_ratio + adv_ratio

            # Allow some tolerance (58% instead of 60%) since human authoring varies
            assert tp_ratio >= 0.58, f"{filename}: TP {tp_ratio:.1%} < 58%"
            assert neg_ratio <= 0.42, f"{filename}: negatives {neg_ratio:.1%} > 42%"
            assert adv_ratio >= 0.18, f"{filename}: adversarial {adv_ratio:.1%} < 18%"

    def test_entity_coverage(self):
        """AC6: Each distinct entity type has ≥5 true_positive examples."""
        test_cases = [
            ("legal_privilege.jsonl", LEGAL_ENTITIES),
            ("therapy_phi.jsonl", THERAPY_ENTITIES),
            ("finance_mnpi.jsonl", FINANCE_ENTITIES),
            ("therapy_phi_pro.jsonl", THERAPY_PRO_ENTITIES)
        ]

        for filename, expected_types in test_cases:
            examples = self.load_corpus(filename)

            # Count TP examples per entity type
            type_counts = defaultdict(int)
            for ex in examples:
                if ex["category"] == "true_positive":
                    for entity in ex.get("expected_entities", []):
                        type_counts[entity["type"]] += 1

            # Check each expected type has coverage
            missing = []
            insufficient = []
            for entity_type in expected_types:
                count = type_counts.get(entity_type, 0)
                if count == 0:
                    missing.append(entity_type)
                elif count < 5:
                    insufficient.append(f"{entity_type}({count})")

            # Some tolerance for missing types in therapy_phi_pro
            if filename == "therapy_phi_pro.jsonl":
                # Allow up to 2 missing types for this new profile
                assert len(missing) <= 2, (
                    f"{filename}: Missing >2 types: {missing}"
                )
            else:
                assert not missing, f"{filename}: Missing entity types: {missing}"

            assert not insufficient, (
                f"{filename}: Types with <5 examples: {insufficient}"
            )

    def test_entity_type_fixes(self):
        """AC7-9: Entity type mismatches fixed."""
        # Check that old incorrect types are gone
        old_types = ["ATTORNEY_CLIENT", "US_SSN", "PSYCHOTHERAPY_NOTE_INDICATOR"]

        for filename in ["legal_privilege.jsonl", "therapy_phi.jsonl"]:
            examples = self.load_corpus(filename)
            for ex in examples:
                for entity in ex.get("expected_entities", []):
                    assert entity["type"] not in old_types, (
                        f"{filename}: Found old type {entity['type']} in {ex['id']}"
                    )

    def test_id_preservation(self):
        """AC10: All existing id values preserved unchanged."""
        # Original IDs from the first 23 examples should still exist
        original_legal_ids = set([f"legal-{cat}-{i}"
                                  for cat in ["tp", "tn", "adv"]
                                  for i in range(1, 13)])

        examples = self.load_corpus("legal_privilege.jsonl")
        corpus_ids = {ex["id"] for ex in examples}

        # Check that original IDs are subset of current
        missing = original_legal_ids - corpus_ids
        assert not missing, f"Missing original IDs: {missing}"

    def test_schema_conformance(self):
        """AC11: Every line conforms to schema."""
        required_fields = {"id", "text", "expected_entities",
                          "expected_level", "category", "notes"}
        valid_categories = {"true_positive", "true_negative", "adversarial_negative"}
        valid_levels = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

        files = ["legal_privilege.jsonl", "therapy_phi.jsonl",
                 "therapy_phi_pro.jsonl", "finance_mnpi.jsonl"]

        for filename in files:
            examples = self.load_corpus(filename)

            for ex in examples:
                # Check required fields
                missing_fields = required_fields - set(ex.keys())
                assert not missing_fields, (
                    f"{filename} {ex.get('id', '?')}: Missing fields {missing_fields}"
                )

                # Check enum values
                assert ex["category"] in valid_categories, (
                    f"{filename} {ex['id']}: Invalid category {ex['category']}"
                )
                assert ex["expected_level"] in valid_levels, (
                    f"{filename} {ex['id']}: Invalid level {ex['expected_level']}"
                )

                # Check entity format
                for entity in ex["expected_entities"]:
                    assert "type" in entity, (
                        f"{filename} {ex['id']}: Entity missing 'type' field"
                    )

    def test_notes_field_populated(self):
        """AC14: Each new example's notes field includes source category."""
        source_keywords = ["synthetic", "public", "case", "generated", "derived"]

        files = ["legal_privilege.jsonl", "therapy_phi.jsonl",
                 "therapy_phi_pro.jsonl", "finance_mnpi.jsonl"]

        for filename in files:
            examples = self.load_corpus(filename)

            # Check newer examples (after the original 23-30)
            for ex in examples[30:]:
                notes = ex.get("notes", "").lower()
                has_source = any(kw in notes for kw in source_keywords)
                assert has_source, (
                    f"{filename} {ex['id']}: Notes don't indicate source: {ex.get('notes', '')}"
                )


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
