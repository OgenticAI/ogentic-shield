"""Custom recognizer template (OGE-322).

Copy this file, rename it, and fill in the patterns for your domain.
Use it with the test harness:

    ogentic-shield test-recognizer path/to/your_recognizer.py
    ogentic-shield test-recognizer path/to/your_recognizer.py --text "Try me"

The test harness:
  1. Imports the file as a Python module.
  2. Discovers every ``PatternRecognizer`` subclass defined in the file.
  3. Instantiates each, runs it against the SAMPLE_TEXTS below (and any
     ``--text`` / ``--text-file`` you pass), and prints what was detected.

Once your recognizer is happy, register it in a profile (see
``src/ogentic_shield/profiles/`` for the built-in ones) and add the
entity type to ``src/ogentic_shield/layers/regex_ner.py`` so its
detections route into the right ``CategoryGroup``.

Conventions (mirrors ``CLAUDE.md`` §4.1):

- One class per logical recognizer; multiple ``Pattern`` entries OK.
- Class name = ``<EntityType>Recognizer`` in PascalCase.
- ``PATTERNS`` and ``CONTEXT_WORDS`` as class-level constants.
- Constructor calls ``super().__init__`` with ``supported_entity``,
  ``patterns``, ``context``, and ``supported_language="en"``.
- Docstring on the class explaining what the recognizer detects.
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class ExampleNumberRecognizer(PatternRecognizer):
    """Detects an example numeric identifier — a 6-digit ID labelled ``ID:``.

    Replace this docstring + the patterns with your own. The test harness
    uses the docstring as the recognizer's display name.
    """

    # Each Pattern: a name (debugging-only), a regex, and a base confidence
    # score in [0, 1]. Higher score = higher trust before context boosting.
    # Use ``\b`` to anchor to word boundaries — bare numeric patterns are
    # the #1 source of false positives.
    PATTERNS = [
        Pattern(
            name="example_id_labelled",
            regex=r"\bID:\s*\d{6}\b",
            score=0.90,
        ),
    ]

    # Words that, when present near a match, justify boosting the
    # confidence score. Presidio's NER scorer uses these. Keep the list
    # short — 3-6 unambiguous domain words is usually right.
    CONTEXT_WORDS = ["customer", "account", "record"]

    def __init__(self) -> None:
        super().__init__(
            # The entity type label that shows up in detection results.
            # By convention, UPPER_SNAKE_CASE, prefixed by domain when
            # ambiguous (e.g. ``LEGAL_PRIVILEGE_MARKER``). For ``ogentic-shield``
            # built-ins, see ``CLAUDE.md`` §2 for the naming guide.
            supported_entity="EXAMPLE_ID",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )


# Optional. The ``test-recognizer`` CLI runs the recognizer against each
# string here and prints the detections. If you also pass ``--text``, both
# the CLI input and these samples are evaluated. If this list is omitted,
# the CLI just runs your ``--text``.
SAMPLE_TEXTS: list[str] = [
    # Should match.
    "Customer record updated. ID: 123456 archived.",
    # Should NOT match — context shouldn't matter for the negative case.
    "The lottery winning numbers were 1 2 3 4 5 6.",
]
