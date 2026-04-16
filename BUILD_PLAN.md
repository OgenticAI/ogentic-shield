# ogentic-shield — Build Plan

## The Jim Okonma Pipeline Applied to ogentic-shield

This follows the 8-layer "AI-Coherence" methodology. The architecture lives in the docs. Claude Code builds the empire.

---

## Layer 1: The Blueprint (Planning) ✅ DONE

Two files:

- **PRD.md** — The "What." Data models, API contracts, CLI specs, shield profiles, detection pipeline, scoring algorithm, test requirements, packaging. Every entity type, every regex pattern, every confidence score is specified.

- **CLAUDE.md** — The "How." File structure, naming conventions, 9 architecture decisions, code patterns for recognizers/profiles/tests/errors/logging, dependency rules, security constraints, git conventions, and the exact build order (32 steps).

These two files are the complete specification. Claude Code should not need to make architectural decisions — they're made.

---

## Layer 2: Source of Truth (Design)

Not applicable for a library (no UI). Skip.

---

## Layer 3: The Bridge (Frontend)

Not applicable for v0.1.0. The CLI IS the interface. Rich library handles table formatting. When the HTTP server and web demo come in v0.2, this layer activates.

---

## Layer 4: The Engine (Backend) — TONIGHT'S BUILD

This is where Claude Code does the heavy lifting. Feed it both files:

```bash
# In the ogentic-shield directory, with PRD.md and CLAUDE.md present:
claude

# Then paste:
Read PRD.md and CLAUDE.md in this directory. These are the complete specification 
for ogentic-shield, a Python library for regulatory sensitivity detection. 

Build the entire project following CLAUDE.md §9 (build order). Create every file 
specified. Implement all 30 recognizers (10 legal, 10 therapy, 10 finance) with 
the exact patterns from PRD.md §5. Follow every naming convention, architecture 
decision, and code pattern from CLAUDE.md.

After building, run: ruff check src/ tests/ && pytest tests/ -v

Fix any issues until all checks pass.
```

**What Claude Code produces:**
- 32 source files in the exact structure from CLAUDE.md §1
- 30 recognizers implementing Presidio's EntityRecognizer
- 3 shield profiles with scoring weights
- 2-layer detection pipeline (regex+NER → rules engine)
- Scoring algorithm with configurable weights
- Full CLI with `analyze` and `profiles` commands
- JSON / table / summary output formatters
- 75+ test cases (≥5 per recognizer)
- Integration tests per profile
- README, LICENSE, pyproject.toml

---

## Layer 5: The Safety Net (Testing)

Tests are generated alongside the code (CLAUDE.md §9 steps 23-29). But verify:

```bash
# Run full test suite
pytest tests/ -v --cov=ogentic_shield --cov-report=term-missing

# Run only recognizer tests (the critical ones)
pytest tests/recognizers/ -v

# Run integration tests
pytest tests/test_shield.py -v

# Check: do the example texts from PRD §4.3 produce the expected output?
ogentic-shield analyze "Per our conversation with outside counsel at Davis Polk regarding the SEC investigation into Meridian Holdings, we recommend settling the Johnson matter for \$4.2M before the March 15 deadline." --profiles shield-legal --output json
```

**Expected**: Score ≥ 80, Level CRITICAL, Routing LOCAL_ONLY, 5+ entities detected.

```bash
# Safe text should score low
ogentic-shield analyze "What are the elements of a breach of fiduciary duty claim under Delaware law?" --profiles shield-legal --output summary
```

**Expected**: Score < 20, Level LOW or NONE, Routing CLOUD_OK.

---

## Layer 6: The Guardrails (Security)

Already encoded in CLAUDE.md §6:
- No secrets in code
- No network calls in default mode
- No telemetry
- No eval/exec
- YAML safe_load only
- Input treated as untrusted

Claude Code enforces these because they're declared in the architecture doc.

---

## Layer 7: The Gatekeeper (CI/CD)

For tonight, manual. The CI equivalent:

```bash
ruff check src/ tests/ && mypy src/ogentic_shield/ && pytest tests/ -v --cov=ogentic_shield
```

Tomorrow, set up GitHub Actions:

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: python -m spacy download en_core_web_lg
      - run: ruff check src/ tests/
      - run: mypy src/ogentic_shield/
      - run: pytest tests/ -v --cov=ogentic_shield --cov-report=xml
```

---

## Layer 8: The Destination (Deploy)

**Tonight**: Works locally. `pip install -e .` and the CLI runs.

**This week**:
- Push to `github.com/OgenticAI/ogentic-shield`
- GitHub Actions CI green
- README with badges

**Month 1 (May)**:
- Publish to PyPI: `pip install ogentic-shield`
- Docker image: `docker run ogentic/shield analyze "..."`
- Blog post: "We're Open-Sourcing Privilege Protection"

**Month 2 (June)**:
- MCP server mode (plug into Goose, Claude, any MCP client)
- HTTP API with OpenAPI docs
- Submit to Goose extension registry

---

## What Makes This Impressive

This isn't a demo. It's the real first product. When you show the team:

1. `pip install -e .` — it installs like a real package
2. `ogentic-shield analyze "..." --output table` — it runs like a real CLI, with colored output, real Presidio NER, real entity detection
3. `pytest tests/ -v` — 75+ tests pass, all green
4. Show the source: 30 recognizers, each with documented patterns, each with 5+ tests
5. `ogentic-shield profiles list` — three shield profiles, ready to compose
6. The PRD and CLAUDE.md files — this is how we build everything from here

The team doesn't see a visualization of what Sotto would do. They see the actual detection engine, working, tested, documented, and ready to open-source. And they see the methodology (Jim Okonma's pipeline) that means everything else gets built the same way.

**The message**: "I built the core of ogentic-shield last night. 30 recognizers, 3 profiles, 75+ tests, full CLI. This is the engine inside Sotto. And I built it by writing two docs and letting Claude Code do the rest. This is how we build everything."

---

## File Checklist

```
ogentic-shield/
├── PRD.md            ✅ Created
├── CLAUDE.md         ✅ Created
├── BUILD_PLAN.md     ✅ This file
├── pyproject.toml    ⬜ Claude Code builds
├── README.md         ⬜ Claude Code builds
├── LICENSE           ⬜ Claude Code builds
├── src/              ⬜ Claude Code builds (18 source files)
├── tests/            ⬜ Claude Code builds (8 test files, 75+ tests)
├── benchmarks/       ⬜ Claude Code builds
└── examples/         ⬜ Claude Code builds
```
