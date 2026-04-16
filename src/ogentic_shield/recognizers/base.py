"""Base recognizer extending Presidio's EntityRecognizer."""

from presidio_analyzer import PatternRecognizer


class ShieldPatternRecognizer(PatternRecognizer):
    """Base class for ogentic-shield custom recognizers.

    Extends Presidio's PatternRecognizer with defaults for English language
    support and a consistent initialization pattern.
    """

    PATTERNS = []
    CONTEXT_WORDS = []

    def __init__(self, supported_entity: str, **kwargs):
        super().__init__(
            supported_entity=supported_entity,
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
            **kwargs,
        )
