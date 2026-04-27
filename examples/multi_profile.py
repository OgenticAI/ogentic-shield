"""Multi-profile — compose shield-legal + shield-finance on one input.

A single message can be sensitive in multiple regulatory frames at once:
an executive email about an SEC investigation simultaneously triggers
attorney-client privilege concerns (legal) AND material non-public
information concerns (finance). Composing profiles lets you detect both
in a single pass.

Run from the project root:

    python examples/multi_profile.py

Expected output:

    ─── Single profile: shield-legal ─────────────────────────────────
    Score:        72 / 100
    Level:        HIGH
    Routing:      LOCAL_ONLY
    Categories:   PRIVILEGE
    ...

    ─── Single profile: shield-finance ───────────────────────────────
    Score:        68 / 100
    Level:        HIGH
    Routing:      LOCAL_ONLY
    Categories:   MNPI
    ...

    ─── Composed: shield-legal + shield-finance ──────────────────────
    Score:        92 / 100
    Level:        CRITICAL
    Routing:      LOCAL_ONLY
    Categories:   PRIVILEGE, MNPI
    ...
"""

from __future__ import annotations

from ogentic_shield import Shield


def main() -> None:
    # An email that's sensitive on BOTH legal AND finance axes.
    # Privileged: outside counsel, settlement language.
    # MNPI: pre-announcement deal value, SEC investigation, insider markers.
    text = (
        "Privileged & Confidential — Attorney Work Product. "
        "Outside counsel Davis Polk has reviewed our position on the SEC "
        "investigation into Meridian Holdings; pending the August 14 "
        "earnings call, we plan to disclose the proposed $4.2B acquisition "
        "of TechCorp. Insider trading restrictions apply until disclosure."
    )

    # 1. shield-legal alone — picks up privilege markers, counsel, settlement.
    legal_only = Shield(profiles=["shield-legal"])
    result = legal_only.analyze(text)
    _print_result("Single profile: shield-legal", result)

    # 2. shield-finance alone — picks up MNPI markers, deal value, SEC/insider.
    finance_only = Shield(profiles=["shield-finance"])
    result = finance_only.analyze(text)
    _print_result("Single profile: shield-finance", result)

    # 3. Composed — one Shield instance with both profiles. Every text
    # is run through every profile's recognizers + rules; results are
    # merged + scored together. This is the recommended setup for
    # corporate M&A / IR teams whose communications are sensitive on
    # multiple axes simultaneously.
    composed = Shield(profiles=["shield-legal", "shield-finance"])
    result = composed.analyze(text)
    _print_result("Composed: shield-legal + shield-finance", result)


def _print_result(label: str, result) -> None:  # noqa: ANN001
    print(f"\n─── {label} {'─' * (60 - len(label))}")
    print(f"Score:        {result.score} / 100")
    print(f"Level:        {result.sensitivity_level.value}")
    print(f"Routing:      {result.routing_suggestion}")
    print(f"Profiles:     {', '.join(result.profile_ids)}")
    categories = ", ".join(g.value for g in result.category_groups_found) or "(none)"
    print(f"Categories:   {categories}")
    print(f"Entities:     {result.entity_count}")
    for entity in result.entities[:10]:
        snippet = entity.text if len(entity.text) <= 40 else entity.text[:37] + "..."
        print(
            f"  [{entity.category_group.value}/{entity.category}] "
            f"{snippet}   confidence={entity.confidence:.2f}"
        )


if __name__ == "__main__":
    main()
