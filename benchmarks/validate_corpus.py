#!/usr/bin/env python3
"""
Validate corpus completeness for OGE-397 without requiring pytest.
"""

import json
from pathlib import Path
from collections import Counter, defaultdict


# Expected entity types per profile
LEGAL_ENTITIES = {
    "COUNSEL_COMMUNICATION", "PRIVILEGE_MARKER", "WORK_PRODUCT",
    "SETTLEMENT_TERMS", "CASE_NUMBER", "LAW_FIRM_NAME",
    "LITIGATION_MARKER", "COURT_FILING", "BATES_NUMBER", "EXECUTIVE_NAME"
}

THERAPY_ENTITIES = {
    "PATIENT_NAME", "DATE_OF_BIRTH", "DIAGNOSIS_CODE", "CLINICAL_RISK_FLAG",
    "SESSION_MARKER", "INSURANCE_ID", "MEDICATION", "PROVIDER_NAME",
    "SSN", "PSYCHOTHERAPY_NOTE_MARKER", "PERSON"
}

THERAPY_PRO_ENTITIES = THERAPY_ENTITIES | {
    "DSM5_DIAGNOSIS", "CPT_CODE", "MINOR_CLIENT_MARKER", "TRAUMA_INDICATOR"
}

FINANCE_ENTITIES = {
    "MNPI_MARKER", "MA_ACTIVITY", "DEAL_VALUE", "LEVERAGE_RATIO",
    "FUND_INFORMATION", "INSTITUTION_NAME", "FINANCIAL_TERMS",
    "DISTRIBUTION_RESTRICTION", "INSIDER_MARKER", "CARRY_TERMS", "EXECUTIVE_NAME"
}

CORPORA = {
    "legal_privilege.jsonl": LEGAL_ENTITIES,
    "therapy_phi.jsonl": THERAPY_ENTITIES,
    "therapy_phi_pro.jsonl": THERAPY_PRO_ENTITIES,
    "finance_mnpi.jsonl": FINANCE_ENTITIES,
}


def load_jsonl(filepath):
    """Load and parse JSONL file."""
    examples = []
    with open(filepath) as f:
        for line_num, line in enumerate(f, 1):
            try:
                examples.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"ERROR: {filepath}:{line_num} - Invalid JSON: {e}")
                return None
    return examples


def validate_corpus(filename, expected_entities):
    """Validate a single corpus file."""
    print(f"\n{'='*60}")
    print(f"Validating {filename}")
    print('='*60)

    filepath = Path(__file__).parent / filename

    if not filepath.exists():
        print(f"❌ File not found: {filepath}")
        return False

    examples = load_jsonl(filepath)
    if examples is None:
        return False

    # Check size
    total = len(examples)
    print(f"Total examples: {total}")
    if total < 200:
        print(f"❌ Requires ≥200 examples (has {total})")
        return False
    else:
        print(f"✓ Size requirement met (≥200)")

    # Check ratios
    categories = Counter(ex["category"] for ex in examples)
    tp_count = categories.get("true_positive", 0)
    tn_count = categories.get("true_negative", 0)
    adv_count = categories.get("adversarial_negative", 0)

    tp_percent = (tp_count / total) * 100
    neg_percent = ((tn_count + adv_count) / total) * 100
    adv_percent = (adv_count / total) * 100

    print(f"\nCategory distribution:")
    print(f"  True positives: {tp_count} ({tp_percent:.1f}%)")
    print(f"  True negatives: {tn_count} ({(tn_count/total)*100:.1f}%)")
    print(f"  Adversarial:    {adv_count} ({adv_percent:.1f}%)")

    ratio_ok = True
    if tp_percent < 60:
        print(f"❌ True positives {tp_percent:.1f}% < 60%")
        ratio_ok = False
    else:
        print(f"✓ True positive ratio met (≥60%)")

    if neg_percent > 40:
        print(f"❌ Total negatives {neg_percent:.1f}% > 40%")
        ratio_ok = False
    else:
        print(f"✓ Negative ratio met (≤40%)")

    if adv_percent < 20:
        print(f"❌ Adversarial {adv_percent:.1f}% < 20%")
        ratio_ok = False
    else:
        print(f"✓ Adversarial ratio met (≥20%)")

    # Check entity coverage
    entity_counts = defaultdict(int)
    for ex in examples:
        if ex["category"] == "true_positive":
            for entity in ex.get("expected_entities", []):
                entity_type = entity.get("type")
                if entity_type:
                    entity_counts[entity_type] += 1

    print(f"\nEntity type coverage (true positives):")
    core_entities = expected_entities - {"PERSON"}  # PERSON comes from Presidio

    for entity_type in sorted(core_entities):
        count = entity_counts.get(entity_type, 0)
        if count == 0:
            print(f"  ⚠️  {entity_type}: NO EXAMPLES")
        elif count < 5:
            print(f"  ⚠️  {entity_type}: {count} examples (recommend ≥5)")
        else:
            print(f"  ✓  {entity_type}: {count} examples")

    # Check for old entity types that should be fixed
    forbidden_types = {"ATTORNEY_CLIENT", "US_SSN", "PSYCHOTHERAPY_NOTE_INDICATOR"}
    found_forbidden = set()
    for ex in examples:
        for entity in ex.get("expected_entities", []):
            entity_type = entity.get("type")
            if entity_type in forbidden_types:
                found_forbidden.add(entity_type)

    if found_forbidden:
        print(f"\n❌ Found old entity types that should be fixed: {found_forbidden}")
        return False
    else:
        print(f"\n✓ No old entity type mismatches found")

    # Check unique IDs
    ids = [ex["id"] for ex in examples]
    duplicates = [id for id, count in Counter(ids).items() if count > 1]
    if duplicates:
        print(f"❌ Duplicate IDs found: {duplicates[:5]}...")  # Show first 5
        return False
    else:
        print(f"✓ All IDs are unique")

    return ratio_ok


def main():
    """Run validation on all corpus files."""
    print("OGE-397 Corpus Validation")
    print("=" * 60)

    all_valid = True
    for filename, expected_entities in CORPORA.items():
        if not validate_corpus(filename, expected_entities):
            all_valid = False

    print("\n" + "=" * 60)
    if all_valid:
        print("✅ ALL CORPUS FILES MEET REQUIREMENTS")
    else:
        print("⚠️  SOME REQUIREMENTS NOT MET (see warnings above)")
        print("Note: Entity coverage warnings are informational")
    print("=" * 60)


if __name__ == "__main__":
    main()