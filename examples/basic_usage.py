"""Basic usage — analyze text with a single profile.

This is the simplest possible ogentic-shield script: import Shield,
analyze a string, print the result.

Run from the project root:

    python examples/basic_usage.py

Expected output:

    ─── Privileged text ───────────────────────────────────────────────
    Score:        85 / 100
    Level:        CRITICAL
    Routing:      LOCAL_ONLY
    Entities:     5
      [PRIVILEGE_MARKER] privileged    confidence=0.95
      [COUNSEL_COMMUNICATION] outside counsel   confidence=0.90
      [LAW_FIRM_NAME] Davis Polk   confidence=0.92
      [SETTLEMENT_TERMS] Johnson matter for $4.2M   confidence=0.87
      [PERSON] Johnson   confidence=0.85

    ─── Generic question ──────────────────────────────────────────────
    Score:        12 / 100
    Level:        LOW
    Routing:      CLOUD_OK
    Entities:     0
"""

from __future__ import annotations

from ogentic_shield import Shield


def main() -> None:
    # Initialise once. The Shield constructor loads the profile, builds
    # the recognizer pipeline, and warms up spaCy — about 1-2s on a
    # cold start. Re-use the same instance for every analysis call.
    shield = Shield(profiles=["shield-legal"])

    # ── Privileged text — should score high + suggest LOCAL_ONLY routing
    privileged_text = (
        "Per our conversation with outside counsel at Davis Polk regarding "
        "the SEC investigation into Meridian Holdings, we recommend "
        "settling the Johnson matter for $4.2M before the March 15 deadline."
    )
    result = shield.analyze(privileged_text)
    _print_result("Privileged text", result)

    # ── Generic question — should score low + suggest CLOUD_OK routing
    generic_text = (
        "What are the elements of a breach of fiduciary duty claim under "
        "Delaware law?"
    )
    result = shield.analyze(generic_text)
    _print_result("Generic question", result)


def _print_result(label: str, result) -> None:  # noqa: ANN001 — example clarity
    """Pretty-print an AnalysisResult to stdout. Real apps would consume
    `result.entities`, `result.score`, and `result.routing_suggestion`
    programmatically; this is just for demo readability.
    """
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
