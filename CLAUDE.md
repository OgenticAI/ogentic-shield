# ogentic-shield — Architecture & Conventions (CLAUDE.md)

This file defines how the codebase is structured, how code is written, and how decisions are made. Claude Code reads this file and generates code that is coherent with these rules on the first pass.

---

## 1. Project Structure

```
ogentic-shield/
├── pyproject.toml                 # Package config, dependencies, entry points
├── README.md                      # Usage docs, install, examples
├── LICENSE                        # Apache 2.0
├── ogentic-shield.yaml            # Default config (shipped with package)
├── src/
│   └── ogentic_shield/
│       ├── __init__.py            # Public API: Shield, AnalysisResult, DetectedEntity
│       ├── shield.py              # Shield class — main entry point
│       ├── models.py              # All dataclasses and enums (from PRD §3)
│       ├── config.py              # Config loading (YAML → dataclass)
│       ├── scoring.py             # Score calculation + sensitivity level + routing suggestion
│       ├── pipeline.py            # Orchestrates layers 1 → 2 → 3 in sequence
│       ├── layers/
│       │   ├── __init__.py
│       │   ├── regex_ner.py       # Layer 1: Presidio + custom recognizers
│       │   ├── rules.py           # Layer 2: Context-aware rules engine
│       │   └── llm.py             # Layer 3: Local LLM classification (stub in v0.1)
│       ├── profiles/
│       │   ├── __init__.py        # Profile loading + registry
│       │   ├── base.py            # ShieldProfile dataclass + loader
│       │   ├── legal.py           # shield-legal: recognizers + rules + weights
│       │   ├── therapy.py         # shield-therapy: recognizers + rules + weights
│       │   └── finance.py         # shield-finance: recognizers + rules + weights
│       ├── recognizers/
│       │   ├── __init__.py
│       │   ├── base.py            # Base class extending Presidio's EntityRecognizer
│       │   ├── legal.py           # All legal-domain recognizers
│       │   ├── therapy.py         # All therapy/PHI recognizers
│       │   └── finance.py         # All finance/MNPI recognizers
│       └── cli/
│           ├── __init__.py
│           ├── main.py            # Click CLI app entry point
│           ├── analyze.py         # `ogentic-shield analyze` command
│           ├── profiles_cmd.py    # `ogentic-shield profiles` command
│           └── formatters.py      # JSON, table, summary output formatters
├── tests/
│   ├── conftest.py                # Shared fixtures: sample texts, shield instances
│   ├── test_models.py             # Model creation, serialization
│   ├── test_shield.py             # Integration tests for Shield.analyze()
│   ├── test_scoring.py            # Scoring algorithm tests
│   ├── test_pipeline.py           # Pipeline orchestration tests
│   ├── test_config.py             # Config loading tests
│   ├── recognizers/
│   │   ├── test_legal.py          # Legal recognizer tests (≥5 per recognizer)
│   │   ├── test_therapy.py        # Therapy recognizer tests
│   │   └── test_finance.py        # Finance recognizer tests
│   ├── layers/
│   │   ├── test_regex_ner.py      # Layer 1 tests
│   │   └── test_rules.py          # Layer 2 tests
│   ├── profiles/
│   │   ├── test_legal_profile.py  # Full integration: legal text → expected result
│   │   ├── test_therapy_profile.py
│   │   └── test_finance_profile.py
│   └── cli/
│       └── test_cli.py            # CLI invocation tests
├── benchmarks/
│   ├── legal_privilege.jsonl      # Labeled test data
│   ├── therapy_phi.jsonl
│   ├── finance_mnpi.jsonl
│   └── run_benchmarks.py          # Precision/recall/F1 runner
└── examples/
    ├── basic_usage.py
    ├── custom_profile.py
    └── multi_profile.py
```

---

## 2. Naming Conventions

### Python
- **Package name**: `ogentic_shield` (underscores, PEP 8)
- **Import path**: `from ogentic_shield import Shield, AnalysisResult`
- **CLI name**: `ogentic-shield` (hyphenated, as installed entry point)
- **Classes**: PascalCase — `Shield`, `AnalysisResult`, `DetectedEntity`, `ShieldProfile`
- **Functions**: snake_case — `analyze`, `calculate_score`, `suggest_routing`
- **Constants**: UPPER_SNAKE — `DEFAULT_MIN_CONFIDENCE = 0.5`
- **Private methods**: single underscore prefix — `_run_layer`, `_deduplicate_entities`
- **Test files**: `test_` prefix — `test_legal.py`, `test_shield.py`
- **Test functions**: `test_` prefix, descriptive — `test_detects_privilege_marker_in_memo`

### Entity Categories
- UPPER_SNAKE_CASE: `ATTORNEY_CLIENT_PRIVILEGE`, `PATIENT_NAME`, `MNPI_MARKER`
- Prefixed by domain when ambiguous: `LEGAL_` for legal, `THERAPY_` for therapy, `FINANCE_` for finance
- Presidio built-in entities keep their names: `PERSON`, `PHONE_NUMBER`, `EMAIL_ADDRESS`

### Profile IDs
- Hyphenated lowercase: `shield-legal`, `shield-therapy`, `shield-finance`
- Custom profiles: `shield-` prefix encouraged but not required

### Recognizer IDs
- Hyphenated, domain-prefixed: `legal-privilege-marker`, `therapy-diagnosis-code`, `finance-mnpi-marker`

---

## 3. Architecture Decisions

### AD-01: Presidio as Foundation, Not Wrapper
We extend Presidio, not wrap it. Our recognizers implement `presidio_analyzer.EntityRecognizer`. Our analyzer IS a `presidio_analyzer.AnalyzerEngine` with custom recognizers added. This means:
- All Presidio built-in recognizers (50+ PII types) are available by default
- Our custom recognizers are first-class citizens in the Presidio pipeline
- We inherit Presidio's deduplication, scoring, and NER infrastructure
- Any tool that integrates with Presidio can use our recognizers

### AD-02: Profiles Are Python Modules, Not Just YAML
Each shield profile (`legal.py`, `therapy.py`, `finance.py`) is a Python module that:
- Defines recognizer instances with their patterns
- Defines rule instances with context patterns
- Defines scoring weights
- Exports a `create_profile() -> ShieldProfile` function

External custom profiles CAN be YAML (for non-developers), but the built-in profiles are code because:
- Recognizers sometimes need logic beyond regex (e.g., NER post-processing)
- Code is testable; YAML patterns are not directly testable
- IDE support, type checking, refactoring work on code

### AD-03: Layers Are Strictly Ordered
Layer 1 (regex + NER) always runs first. Layer 2 (rules) always runs second and can modify Layer 1 results (boost confidence, add context). Layer 3 (LLM) runs last and only if enabled + score is in the ambiguous range. A layer never depends on a later layer's output.

### AD-04: Entities Are Immutable After Creation
Once a `DetectedEntity` is created, its fields don't change. If the rules engine boosts confidence, it creates a new entity replacing the old one. This makes debugging straightforward — you can trace exactly which layer produced which entity.

### AD-05: Scoring Is Profile-Driven, Not Hardcoded
The score algorithm uses weights from the active profiles. If `shield-legal` weights PRIVILEGE at 30 and `shield-finance` weights MNPI at 30, both are applied. When profiles conflict on a weight for the same category group, the higher weight wins (max, not sum).

### AD-06: Routing Suggestions Are Advisory
`ogentic-shield` suggests a routing decision but does NOT enforce it. The consumer (Sotto, ogentic-router, or a custom app) makes the actual routing call. This separation of concerns means shield can be used in contexts where routing means something different.

### AD-07: No Network Calls in Default Mode
Layers 1 and 2 are fully offline. Layer 3 (LLM) calls localhost Ollama only — never an external API. The default config has LLM disabled. A user must explicitly opt in. This means `ogentic-shield` can run in air-gapped environments by default.

### AD-08: Click for CLI, Rich for Output
CLI uses Click (standard, well-tested, auto-generates --help). Output formatting uses Rich for the table format (colored, boxed tables in terminal). JSON and summary formats are plain stdout for piping.

---

## 4. Patterns & Conventions

### 4.1 Recognizer Pattern

Every recognizer follows this structure:

```python
# src/ogentic_shield/recognizers/legal.py

from presidio_analyzer import Pattern, PatternRecognizer

class CounselCommunicationRecognizer(PatternRecognizer):
    """Detects references to communications with legal counsel."""

    PATTERNS = [
        Pattern(
            name="outside_counsel",
            regex=r"\b(outside|external|legal|in-house)\s+counsel\b",
            score=0.93,
        ),
        Pattern(
            name="attorney_client",
            regex=r"\battorney[\s-]client\b",
            score=0.95,
        ),
    ]

    CONTEXT_WORDS = ["privileged", "confidential", "advice", "legal"]

    def __init__(self):
        super().__init__(
            supported_entity="COUNSEL_COMMUNICATION",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )
```

Rules:
- One class per logical recognizer (can have multiple patterns)
- Class name = entity type + "Recognizer" in PascalCase
- PATTERNS as class-level constant
- CONTEXT_WORDS as class-level constant (Presidio uses these to boost scores)
- Constructor calls super() with supported_entity, patterns, context
- Docstring on the class explaining what it detects

### 4.2 Profile Pattern

```python
# src/ogentic_shield/profiles/legal.py

from ogentic_shield.models import ShieldProfile, CategoryGroup, Rule
from ogentic_shield.recognizers.legal import (
    CounselCommunicationRecognizer,
    PrivilegeMarkerRecognizer,
    WorkProductRecognizer,
    # ... all legal recognizers
)

PROFILE_ID = "shield-legal"
PROFILE_VERSION = "0.1.0"

RECOGNIZERS = [
    CounselCommunicationRecognizer(),
    PrivilegeMarkerRecognizer(),
    WorkProductRecognizer(),
    # ...
]

RULES = [
    Rule(
        id="legal-privilege-context-boost",
        name="Privilege Context Boost",
        description="Boost confidence when privilege markers co-occur with counsel references",
        pattern=r"\bprivileged?\b",
        flags=re.IGNORECASE,
        category="PRIVILEGE_MARKER",
        category_group=CategoryGroup.PRIVILEGE,
        confidence=0.97,
        context_patterns=["counsel", "attorney", "legal advice"],
        context_window=300,
        context_confidence_boost=0.08,
    ),
    # ...
]

SCORING_WEIGHTS = {
    CategoryGroup.PRIVILEGE: 30,
    CategoryGroup.PII: 15,
    CategoryGroup.CONFIDENTIAL: 10,
}


def create_profile() -> ShieldProfile:
    return ShieldProfile(
        id=PROFILE_ID,
        name="Legal Privilege Protection",
        version=PROFILE_VERSION,
        description="Detects attorney-client privilege, work product, and litigation-sensitive content.",
        recognizers=RECOGNIZERS,
        rules=RULES,
        scoring_weights=SCORING_WEIGHTS,
        supported_entities=[r.supported_entities[0] for r in RECOGNIZERS],
    )
```

### 4.3 Test Pattern

```python
# tests/recognizers/test_legal.py

import pytest
from ogentic_shield import Shield

@pytest.fixture
def legal_shield():
    return Shield(profiles=["shield-legal"])


class TestCounselCommunicationRecognizer:
    """Tests for COUNSEL_COMMUNICATION detection."""

    # ── True Positives ──────────────────────────────────

    def test_detects_outside_counsel(self, legal_shield):
        result = legal_shield.analyze("We spoke with outside counsel about the matter.")
        entities = [e for e in result.entities if e.category == "COUNSEL_COMMUNICATION"]
        assert len(entities) >= 1
        assert entities[0].text == "outside counsel"
        assert entities[0].confidence >= 0.90

    def test_detects_legal_counsel(self, legal_shield):
        result = legal_shield.analyze("Legal counsel advised against disclosure.")
        entities = [e for e in result.entities if e.category == "COUNSEL_COMMUNICATION"]
        assert len(entities) >= 1

    def test_detects_in_house_counsel(self, legal_shield):
        result = legal_shield.analyze("In-house counsel reviewed the contract.")
        entities = [e for e in result.entities if e.category == "COUNSEL_COMMUNICATION"]
        assert len(entities) >= 1

    # ── True Negatives ──────────────────────────────────

    def test_ignores_general_counsel_word(self, legal_shield):
        """'counsel' alone without legal context should not match at high confidence."""
        result = legal_shield.analyze("I counsel my students to study hard.")
        privilege_entities = [e for e in result.entities if e.category_group.value == "PRIVILEGE"]
        assert len(privilege_entities) == 0

    def test_ignores_unrelated_text(self, legal_shield):
        result = legal_shield.analyze("The weather is nice today.")
        assert result.score < 10
        assert result.routing_suggestion == "CLOUD_OK"

    # ── Edge Cases ──────────────────────────────────────

    def test_handles_mixed_case(self, legal_shield):
        result = legal_shield.analyze("OUTSIDE COUNSEL confirmed the timeline.")
        entities = [e for e in result.entities if e.category == "COUNSEL_COMMUNICATION"]
        assert len(entities) >= 1
```

Rules:
- One test class per recognizer
- Class name = `Test` + recognizer class name
- Methods grouped: true positives, true negatives, edge cases
- Each test is self-contained (no test ordering dependencies)
- Assert on specific entity category, not just entity count
- Assert confidence ranges, not exact values (recognizer tuning should not break tests)

### 4.4 Error Handling Pattern

```python
# Never raise generic exceptions. Use specific types.
class ShieldError(Exception):
    """Base exception for ogentic-shield."""
    pass

class ProfileNotFoundError(ShieldError):
    """Raised when a requested profile doesn't exist."""
    pass

class ProfileValidationError(ShieldError):
    """Raised when a profile YAML is malformed."""
    pass

class ConfigError(ShieldError):
    """Raised when config file is invalid."""
    pass

# In code:
def load_profile(profile_id: str) -> ShieldProfile:
    if profile_id not in PROFILE_REGISTRY:
        raise ProfileNotFoundError(
            f"Profile '{profile_id}' not found. "
            f"Available: {', '.join(PROFILE_REGISTRY.keys())}"
        )
```

### 4.5 Logging Pattern

Use Python's `logging` module. Logger name = module path.

```python
import logging

logger = logging.getLogger("ogentic_shield.layers.regex_ner")

# In functions:
logger.debug("Running %d recognizers against %d chars", len(recognizers), len(text))
logger.info("Layer 1 complete: %d entities in %.1fms", len(entities), elapsed_ms)
logger.warning("Overlapping entities at positions %d-%d, keeping highest confidence", start, end)
```

No print() statements anywhere. Ever. CLI output goes through Click's `click.echo()` or Rich's console.

---

## 5. Dependencies & Versions

```toml
[project]
name = "ogentic-shield"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "presidio-analyzer>=2.2",
    "presidio-anonymizer>=2.2",
    "pyyaml>=6.0",
    "click>=8.0",
    "rich>=13.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
server = ["fastapi>=0.100", "uvicorn>=0.20"]
mcp = ["mcp>=1.0"]
llm = ["ollama>=0.3"]
all = ["ogentic-shield[server,mcp,llm]"]
dev = ["pytest>=8.0", "pytest-cov>=5.0", "ruff>=0.4", "mypy>=1.10"]

[project.scripts]
ogentic-shield = "ogentic_shield.cli.main:cli"
```

### Dependency Rules
- **No transitive cloud dependencies.** Nothing that phones home by default.
- **Presidio is the only heavy dependency.** It pulls spaCy + a language model (~500MB). This is acceptable because Presidio is the industry standard for PII detection.
- **Optional deps are truly optional.** The core library + CLI work without FastAPI, MCP, or Ollama installed. Import guards at the top of optional modules.

---

## 6. Security Constraints

- **No secrets in code.** No API keys, tokens, or credentials anywhere in the repo.
- **No network calls in default mode.** Layers 1 and 2 are fully offline.
- **No telemetry.** No usage tracking, no analytics, no phone-home behavior.
- **No eval() or exec().** Regex patterns are compiled, never evaluated as code.
- **Input sanitization.** Text input is treated as untrusted. No injection vectors through entity text or config values.
- **YAML safe loading.** Always use `yaml.safe_load()`, never `yaml.load()`.

---

## 7. Git Conventions

- **Branch naming**: `feat/`, `fix/`, `docs/`, `test/`, `refactor/` prefixes
- **Commit messages**: Conventional Commits — `feat: add shield-therapy profile`, `fix: overlap resolution for nested entities`, `test: add edge cases for MNPI detection`
- **PR requirements**: All tests pass, ruff lint clean, mypy clean, coverage ≥ 85%
- **No force pushes to main.**
- **Tag releases**: `v0.1.0`, `v0.2.0` etc.

---

## 8. Build & Run Commands

```bash
# Install in dev mode
pip install -e ".[dev]"

# Download spaCy model (required for Presidio NER)
python -m spacy download en_core_web_lg

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=ogentic_shield --cov-report=term-missing

# Lint
ruff check src/ tests/

# Type check
mypy src/ogentic_shield/

# Run benchmarks
python benchmarks/run_benchmarks.py

# CLI usage
ogentic-shield analyze "text here" --profiles shield-legal --output table
ogentic-shield profiles list

# Run all quality checks (CI equivalent)
ruff check src/ tests/ && mypy src/ogentic_shield/ && pytest tests/ -v --cov=ogentic_shield
```

---

## 9. What Claude Code Should Build First

When this file and PRD.md are provided, build in this order:

1. **pyproject.toml** — Package config with all dependencies and entry points
2. **src/ogentic_shield/models.py** — All dataclasses and enums exactly as specified in PRD §3
3. **src/ogentic_shield/recognizers/base.py** — Base recognizer extending Presidio
4. **src/ogentic_shield/recognizers/legal.py** — All 10 legal recognizers
5. **src/ogentic_shield/recognizers/therapy.py** — All 10 therapy recognizers
6. **src/ogentic_shield/recognizers/finance.py** — All 10 finance recognizers
7. **src/ogentic_shield/profiles/base.py** — ShieldProfile loader
8. **src/ogentic_shield/profiles/legal.py** — shield-legal profile
9. **src/ogentic_shield/profiles/therapy.py** — shield-therapy profile
10. **src/ogentic_shield/profiles/finance.py** — shield-finance profile
11. **src/ogentic_shield/layers/regex_ner.py** — Layer 1 implementation
12. **src/ogentic_shield/layers/rules.py** — Layer 2 implementation
13. **src/ogentic_shield/layers/llm.py** — Layer 3 stub (raises NotImplementedError if called without ollama)
14. **src/ogentic_shield/scoring.py** — Score calculation, level, routing suggestion
15. **src/ogentic_shield/pipeline.py** — Orchestrates layers in order
16. **src/ogentic_shield/config.py** — YAML config loading
17. **src/ogentic_shield/shield.py** — Shield class (main entry point, delegates to pipeline)
18. **src/ogentic_shield/__init__.py** — Public API exports
19. **src/ogentic_shield/cli/main.py** — Click CLI entry point
20. **src/ogentic_shield/cli/analyze.py** — analyze command
21. **src/ogentic_shield/cli/profiles_cmd.py** — profiles command
22. **src/ogentic_shield/cli/formatters.py** — Output formatters (JSON, table, summary)
23. **tests/conftest.py** — Fixtures
24. **tests/recognizers/test_legal.py** — Legal recognizer tests
25. **tests/recognizers/test_therapy.py** — Therapy recognizer tests
26. **tests/recognizers/test_finance.py** — Finance recognizer tests
27. **tests/test_shield.py** — Integration tests
28. **tests/test_scoring.py** — Scoring tests
29. **tests/cli/test_cli.py** — CLI tests
30. **README.md** — Install, usage, examples
31. **LICENSE** — Apache 2.0
32. **ogentic-shield.yaml** — Default config

Run `ruff check` and `pytest` after building. Fix any issues.
