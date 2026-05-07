# Contributing to ogentic-shield

Thank you for your interest in contributing! We welcome contributions from everyone. This document outlines the guidelines for how to contribute effectively.

---

## Types of Contributions We Welcome

We appreciate various kinds of contributions, including but not limited to:

- **Recognizer patterns** &mdash; new regex patterns for detecting sensitive content in legal, clinical, or financial domains
- **Test cases** &mdash; especially edge cases, false positives/negatives, and real-world text patterns
- **Domain expertise** &mdash; if you work in law, therapy, finance, or compliance, your knowledge of what constitutes sensitive content is invaluable
- **Bug fixes** &mdash; issues with detection accuracy, scoring, or CLI behavior
- **Performance improvements** &mdash; faster pattern matching, reduced memory usage
- **Documentation** &mdash; usage examples, integration guides, API docs
- **New shield profiles** &mdash; healthcare, accounting, government, or other regulated domains

---

## How to Ask Questions

If you have questions:

1. Check the [README](./README.md) and existing [issues](https://github.com/OgenticAI/ogentic-shield/issues) first.
2. If your question hasn't been addressed, open a new issue with the `question` label.

---

## How to Report Bugs

When reporting a bug, please include:

- A clear and descriptive title
- The text input that produced unexpected results
- Expected vs. actual detection output (entities, score, routing)
- Your `ogentic-shield` version (`ogentic-shield --version`)
- Python version and OS
- Any relevant configuration from `ogentic-shield.yaml`

---

## How to Suggest a Feature

To suggest a new feature:

1. Search existing issues to avoid duplicates.
2. Open a new issue describing your idea, use cases, and the regulatory context it addresses.
3. For new recognizer patterns, include example text that should match and text that should not.

---

## How to Contribute Code

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) or pip
- Git

### Step-by-Step Process

1. **Fork** the repository.

2. **Clone** your fork:

   ```bash
   git clone https://github.com/your-username/ogentic-shield.git
   cd ogentic-shield
   ```

3. **Create a feature branch:**

   ```bash
   git checkout -b feat/my-feature
   ```

   Branch prefixes: `feat/`, `fix/`, `test/`, `docs/`, `refactor/`

4. **Install in development mode:**

   ```bash
   pip install -e ".[dev]"
   python -m spacy download en_core_web_lg
   ```

5. **Make your changes** following the patterns in [CLAUDE.md](./CLAUDE.md):

   - **Recognizers**: one class per entity type, `PATTERNS` and `CONTEXT_WORDS` as class constants
   - **Tests**: one test class per recognizer, 3+ true positives, 2+ true negatives, edge cases
   - **Profiles**: register recognizers, rules, and scoring weights via `create_profile()`
   - **No `print()` statements** &mdash; use `logging` or Click's `click.echo()`

6. **Run quality checks:**

   ```bash
   ruff check src/ tests/
   pytest tests/ -v
   ```

   Both must pass before submitting a PR.

7. **Push** your branch:

   ```bash
   git push origin feat/my-feature
   ```

8. **Open a Pull Request** against the `main` branch with a clear description of what you changed and why.

---

## Adding a New Recognizer

This is the most common contribution. There are two paths depending on
whether the recognizer ships with `ogentic-shield` (built-in) or lives
in your own codebase (custom).

### Path A — Custom recognizer (your own codebase)

If you're building a recognizer for your domain or a downstream
application, you don't need to fork `ogentic-shield`. Use the SDK:

1. **Copy the template** &mdash; [`examples/recognizer_template.py`](./examples/recognizer_template.py) has the canonical structure with inline docs.

2. **Iterate with the test harness:**

   ```bash
   ogentic-shield test-recognizer path/to/your_recognizer.py
   ogentic-shield test-recognizer path/to/your_recognizer.py --text "Try me"
   ogentic-shield test-recognizer path/to/your_recognizer.py --text-file fixtures/sample.txt
   ```

   The harness imports your file, finds every `PatternRecognizer`
   subclass defined in it, runs them against `--text` / `--text-file`
   inputs (and any `SAMPLE_TEXTS` list you defined in the module), and
   prints the matches.

3. **Worked example** &mdash; [`examples/gdpr_recognizer.py`](./examples/gdpr_recognizer.py) ships three production-shape EU recognizers (UK NINO, German Steuer-ID, EU VAT number) you can crib from.

4. **Plug into a Shield instance** by registering your recognizer in a
   custom profile and passing the profile to `Shield`:

   ```python
   from ogentic_shield import Shield, register_profile
   from ogentic_shield.models import CategoryGroup, ShieldProfile
   from your_module import MyNewRecognizer

   profile = ShieldProfile(
       id="my-profile",
       name="My custom profile",
       version="0.1.0",
       description="...",
       recognizers=[MyNewRecognizer()],
       rules=[],
       scoring_weights={CategoryGroup.PII: 15},
       supported_entities=["MY_ENTITY_TYPE"],
   )
   register_profile(profile)
   shield = Shield(profiles=["my-profile"])
   ```

### Path B — Built-in recognizer (this repo)

If you want your recognizer to ship with `ogentic-shield` for everyone:

#### 1. Add the recognizer class

```python
# src/ogentic_shield/recognizers/<domain>.py

from presidio_analyzer import Pattern, PatternRecognizer

class MyNewRecognizer(PatternRecognizer):
    """Detects <what it detects>."""

    PATTERNS = [
        Pattern(name="pattern_name", regex=r"\byour regex\b", score=0.90),
    ]

    CONTEXT_WORDS = ["word1", "word2"]

    def __init__(self):
        super().__init__(
            supported_entity="MY_ENTITY_TYPE",
            patterns=self.PATTERNS,
            context=self.CONTEXT_WORDS,
            supported_language="en",
        )
```

#### 2. Register it in the profile

Add the recognizer instance to the appropriate profile in `src/ogentic_shield/profiles/<domain>.py`.

#### 3. Map the entity type

Add the entity type to the `_ENTITY_CATEGORY_GROUP` dict in `src/ogentic_shield/layers/regex_ner.py`.

#### 4. Write tests

```python
# tests/recognizers/test_<domain>.py

class TestMyNewRecognizer:
    # 3+ true positives
    def test_detects_example_one(self, shield):
        ...

    # 2+ true negatives
    def test_ignores_unrelated(self, shield):
        ...

    # Edge cases
    def test_handles_mixed_case(self, shield):
        ...
```

---

## Coding Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) conventions
- Use [ruff](https://docs.astral.sh/ruff/) for linting (configured in `pyproject.toml`)
- Type hints on all public functions
- Docstrings on all classes and public methods
- No `print()` &mdash; use `logging` or `click.echo()`
- No `eval()` or `exec()` &mdash; regex patterns are compiled, never evaluated as code
- Always use `yaml.safe_load()`, never `yaml.load()`

---

## Commit Message Guidelines

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short summary>
```

Types:

| Type | Use for |
|------|---------|
| `feat` | New feature or recognizer |
| `fix` | Bug fix |
| `test` | Adding or updating tests |
| `docs` | Documentation changes |
| `refactor` | Code restructuring without behavior change |
| `perf` | Performance improvement |

Examples:

```
feat: add healthcare PHI recognizer for medical record numbers
fix: false positive on "complaint" in non-legal context
test: add edge cases for MNPI marker detection
docs: add integration example with LangChain
```

---

## PR Requirements

Before a PR can be merged:

- `ruff check src/ tests/` passes with zero errors
- `pytest tests/ -v` passes with all tests green
- New recognizers have at least 5 test cases (3 positive, 2 negative)
- No secrets, API keys, or credentials in code
- Commit messages follow conventional format

---

## Code of Conduct

Be respectful and constructive. We're building tools that protect people's most sensitive information &mdash; the work matters, and so does how we treat each other while doing it.

---

## Questions?

Open an issue or start a discussion. We're happy to help you get started.

Thank you for helping make AI safer for regulated professionals.
