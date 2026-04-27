"""Base recognizer extending Presidio's EntityRecognizer."""

from typing import Any

from presidio_analyzer import Pattern, PatternRecognizer


class ShieldPatternRecognizer(PatternRecognizer):
    """Base class for ogentic-shield custom recognizers.

    Extends Presidio's PatternRecognizer with defaults for English language
    support and a consistent initialization pattern.
    """

    PATTERNS: list[Pattern] = []
    CONTEXT_WORDS: list[str] = []

    def __init__(self, supported_entity: str, **kwargs: Any) -> None:
        super().__init__(
            supported_entity=supported_entity,
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
            **kwargs,
        )
