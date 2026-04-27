"""Custom profile — define rules in YAML, register, analyze.

ogentic-shield ships with three first-class profiles (shield-legal,
shield-therapy, shield-finance). For domain-specific deployments you
often need a fourth: HR pay data, investor-relations material, internal
project codenames, etc. This example shows the full custom-profile
workflow:

  1. Write a YAML profile spec (rules + scoring weights).
  2. `load_profile_from_yaml()` parses it into a ShieldProfile.
  3. `register_profile()` adds it to the global registry.
  4. `Shield(profiles=[<custom-id>])` uses it like a built-in.

Run from the project root:

    python examples/custom_profile.py

Expected output:

    Available profiles before register:
      - shield-legal, shield-therapy, shield-finance

    Available profiles after register:
      - shield-legal, shield-therapy, shield-finance, shield-hr

    ─── HR-sensitive text ────────────────────────────────────────────
    Score:        35 / 100
    Level:        MEDIUM
    Routing:      LOCAL_PREFERRED
    Entities:     2
      [SALARY_MENTION]    base salary of $185,000   confidence=0.85
      [TERMINATION_TERM]  performance improvement plan   confidence=0.85
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ogentic_shield import (
    Shield,
    list_profiles,
    load_profile_from_yaml,
    register_profile,
)

# ── A custom profile — written inline as YAML for a self-contained example.
# In real deployments you'd ship this file alongside the app and load it
# at startup; here we write it to a tempfile so the example is runnable
# without any external setup.
CUSTOM_PROFILE_YAML = """
id: shield-hr
name: HR Sensitive Information
version: 0.1.0
description: |
  Detects HR-sensitive content (compensation data, termination language,
  internal performance markers) that should NOT be sent to public AI
  tools. Apache 2.0 — adapt freely for your org's HR policies.

rules:
  - id: hr-salary-mention
    name: Salary Mention
    description: Any explicit salary / compensation figure
    pattern: '\\b(base\\s+salary|annual\\s+salary|comp(?:ensation)?\\s+package)\\s+of\\s+\\$[\\d,]+'
    category: SALARY_MENTION
    category_group: CONFIDENTIAL
    confidence: 0.85
    context_patterns: [employee, hire, offer, raise]
    context_window: 200

  - id: hr-termination-term
    name: Termination / PIP Language
    description: Performance improvement, termination, or severance language
    pattern: '\\b(performance\\s+improvement\\s+plan|PIP|termination|severance|laid\\s+off)\\b'
    category: TERMINATION_TERM
    category_group: CONFIDENTIAL
    confidence: 0.85
    context_patterns: [employee, manager, HR, hr]
    context_window: 200

  - id: hr-grievance-marker
    name: Grievance / Complaint Marker
    description: Internal HR grievance / complaint markers
    pattern: '\\b(harassment|discrimination|hostile\\s+work\\s+environment|EEOC\\s+complaint)\\b'
    category: GRIEVANCE_MARKER
    category_group: CONFIDENTIAL
    confidence: 0.92
    context_patterns: [reported, filed, investigation]
    context_window: 300

scoring_weights:
  CONFIDENTIAL: 25
  PII: 15
"""


def main() -> None:
    # 1. Show the registry BEFORE we register the custom profile.
    print("Available profiles before register:")
    print("  - " + ", ".join(p.id for p in list_profiles()))

    # 2. Write the YAML to a tempfile + load it. In production this would
    # be a checked-in file under your-app/profiles/shield-hr.yaml.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(CUSTOM_PROFILE_YAML)
        yaml_path = Path(f.name)
    try:
        custom_profile = load_profile_from_yaml(yaml_path)

        # 3. Register so Shield can find it by id. Re-registering an
        # existing id silently replaces — keep ids unique.
        register_profile(custom_profile)
        print("\nAvailable profiles after register:")
        print("  - " + ", ".join(p.id for p in list_profiles()))

        # 4. Use the custom profile like a built-in.
        shield = Shield(profiles=["shield-hr"])
        result = shield.analyze(
            "I wanted to flag a concern about Sarah's recent comp package: "
            "her base salary of $185,000 is significantly below her peers, "
            "and her manager has mentioned a performance improvement plan "
            "without any prior conversations."
        )
        _print_result("HR-sensitive text", result)

    finally:
        # Clean up the tempfile so re-running doesn't leak files.
        yaml_path.unlink(missing_ok=True)


def _print_result(label: str, result) -> None:  # noqa: ANN001
    print(f"\n─── {label} {'─' * (60 - len(label))}")
    print(f"Score:        {result.score} / 100")
    print(f"Level:        {result.sensitivity_level.value}")
    print(f"Routing:      {result.routing_suggestion}")
    print(f"Entities:     {result.entity_count}")
    for entity in result.entities[:10]:
        snippet = entity.text if len(entity.text) <= 40 else entity.text[:37] + "..."
        print(
            f"  [{entity.category}] {snippet}   "
            f"confidence={entity.confidence:.2f}"
        )


if __name__ == "__main__":
    main()
