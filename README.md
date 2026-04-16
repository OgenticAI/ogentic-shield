<p align="center">
  <strong>ogentic-shield</strong><br>
  <em>Regulatory sensitivity detection for AI applications</em>
</p>

<p align="center">
  <a href="https://github.com/OgenticAI/ogentic-shield/actions"><img src="https://img.shields.io/github/actions/workflow/status/OgenticAI/ogentic-shield/ci.yml?branch=main&label=tests" alt="Tests"></a>
  <a href="https://pypi.org/project/ogentic-shield/"><img src="https://img.shields.io/pypi/v/ogentic-shield?color=blue" alt="PyPI"></a>
  <a href="https://github.com/OgenticAI/ogentic-shield/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
</p>

---

## Why This Exists

On February 10, 2026, *US v. Heppner* (S.D.N.Y.) established that sending content to public AI tools waives attorney-client privilege. The same reasoning extends to therapist-patient confidentiality under HIPAA, material non-public information under SEC/FINRA rules, and every regulated profession with a duty of confidentiality.

**30+ million US professionals** use AI daily. 71% of law firms have no AI policy. 43% of therapists have entered patient data into public AI. There is no open-source tool that answers a simple question before text reaches a model: *does this content contain something that should never leave this device?*

Microsoft Presidio handles general PII well (names, SSNs, credit cards). It knows nothing about attorney-client privilege markers, psychotherapy note indicators, MNPI signals, or work product doctrine. `ogentic-shield` fills that gap.

---

## About OgenticAI

[OgenticAI](https://ogentic.ai) is building **trust infrastructure for regulated industries** &mdash; the tools that make AI safe for professionals who can't afford to get it wrong.

`ogentic-shield` is the first release in a series of open-source projects that together form the foundation for privacy-first AI:

| Project | Purpose | Status |
|---------|---------|--------|
| **`ogentic-shield`** | Detect privileged, clinical, and financial sensitivity in text | **v0.1.0 &mdash; Available now** |
| `ogentic-audit` | Cryptographic, tamper-evident audit trails for AI usage | Coming soon |
| `ogentic-router` | Privacy-aware LLM routing (sensitive &rarr; local, safe &rarr; cloud) | Coming soon |
| `ogentic-redact` | Structure-aware document redaction for legal proceedings | Planned |
| `ogentic-vault` | Local-first, encrypted knowledge management per matter/patient | Planned |
| `ogentic-legal-mcp` | MCP servers for legal document intelligence and research | Planned |
| `ogentic-legal-bench` | Open benchmarks for legal AI trustworthiness | Planned |

These projects are designed to compose. `ogentic-shield` classifies content. `ogentic-router` uses that classification to decide where to send it. `ogentic-audit` logs every decision. `ogentic-redact` strips what shouldn't leave. Together they form a complete open-source stack for privilege-protected AI &mdash; and the foundation for [Privy](https://ogentic.ai), OgenticAI's commercial product for regulated professionals.

All `ogentic-*` projects are Apache 2.0 licensed.

---

## What It Does

`ogentic-shield` extends Microsoft Presidio with **30 domain-specific recognizers** across three regulated professions, then layers a configurable rules engine on top:

```
Input Text
    |
    v
[ Layer 1: Regex + NER ]     <50ms
  Presidio built-in PII (50+ types)
  + 30 custom recognizers
    |
    v
[ Layer 2: Rules Engine ]     <10ms
  Context-aware confidence boosting
  Co-occurrence detection
    |
    v
[ Layer 3: Local LLM ]        opt-in, v0.2
  Ollama classification
  for ambiguous content
    |
    v
Score (0-100) + Sensitivity Level + Routing Suggestion
```

The output is a score, a sensitivity level, and an advisory routing suggestion &mdash; **not an enforcement decision**. Your application decides what to do with it.

---

## Install

```bash
pip install ogentic-shield
```

Presidio requires a spaCy language model:

```bash
python -m spacy download en_core_web_lg
```

## Quick Start

```python
from ogentic_shield import Shield

shield = Shield(profiles=["shield-legal"])

result = shield.analyze(
    "Per our conversation with outside counsel at Davis Polk "
    "regarding the SEC investigation, this is privileged and confidential."
)

print(result.score)               # 94
print(result.sensitivity_level)   # CRITICAL
print(result.routing_suggestion)  # LOCAL_ONLY
print(result.entities[0].category)  # COUNSEL_COMMUNICATION
```

## Profiles

Each profile adds a set of recognizers, rules, and scoring weights for a specific domain. Profiles are **composable** &mdash; load multiple for cross-domain work (e.g., a law firm handling healthcare litigation).

### `shield-legal` &mdash; Attorney-Client Privilege

Detects privilege markers, counsel communications, work product doctrine, settlement terms, case numbers, law firm names (AmLaw 200), litigation holds, court filings, Bates numbers, and executive names.

### `shield-therapy` &mdash; HIPAA PHI & Clinical Risk

Detects patient names, dates of birth, ICD-10 diagnosis codes, clinical risk flags (suicidal ideation, self-harm), session markers, insurance IDs, psychiatric medications (50+ drugs), provider names, SSNs, and psychotherapy note indicators.

### `shield-finance` &mdash; MNPI & Deal Terms

Detects MNPI markers, M&A activity, deal values (per-share, $M/$B), leverage ratios, fund information (LP/GP, co-invest), institution names (50+ banks/PE firms), financial covenants, distribution restrictions, insider markers, and carried interest terms.

### Scoring & Routing

| Score | Level | Routing Suggestion |
|-------|-------|--------------------|
| 0 | NONE | `CLOUD_OK` |
| 1&ndash;20 | LOW | `CLOUD_OK` |
| 21&ndash;50 | MEDIUM | `REDACT_CLOUD` |
| 51&ndash;80 | HIGH | `REDACT_CLOUD` or `LOCAL_ONLY` |
| 81&ndash;100 | CRITICAL | `LOCAL_ONLY` |

Privilege (`PRIVILEGE`) or MNPI (`MNPI`) entities always trigger `LOCAL_ONLY`, regardless of score. PHI entities trigger `REDACT_CLOUD` at minimum.

---

## CLI

```bash
# Analyze text
ogentic-shield analyze "privileged and confidential" \
  --profiles shield-legal --output json

# Analyze a file
ogentic-shield analyze --file memo.txt \
  --profiles shield-legal shield-finance

# Pipe from stdin
cat brief.txt | ogentic-shield analyze --profiles shield-legal

# Output formats: json, table, summary
ogentic-shield analyze "..." --output table
ogentic-shield analyze "..." --output summary

# List available profiles
ogentic-shield profiles list

# Show profile details
ogentic-shield profiles show shield-legal
```

### Example Output

**Summary** (`--output summary`):

```
CRITICAL (94) | LOCAL_ONLY | 6 entities | COUNSEL_COMMUNICATION (0.93) | 12.4ms
```

**JSON** (`--output json`):

```json
{
  "score": 94,
  "sensitivity_level": "CRITICAL",
  "routing_suggestion": "LOCAL_ONLY",
  "entity_count": 6,
  "entities": [
    {
      "text": "outside counsel",
      "category": "COUNSEL_COMMUNICATION",
      "category_group": "PRIVILEGE",
      "confidence": 0.93,
      "detection_layer": "REGEX"
    }
  ]
}
```

---

## Python API

```python
from ogentic_shield import Shield, DetectionLayer

# Multiple profiles
shield = Shield(profiles=["shield-legal", "shield-therapy"])

# Full analysis with options
result = shield.analyze(
    text,
    profiles=["shield-legal"],           # override for this call
    layers=[DetectionLayer.REGEX, DetectionLayer.NER],  # skip rules
    min_confidence=0.7,                  # filter low-confidence
)

# Inspect results
for entity in result.entities:
    print(f"{entity.text} -> {entity.category} ({entity.confidence:.2f})")

# Available profiles
Shield.list_profiles()
Shield.get_profile("shield-legal")
```

---

## Configuration

Create an `ogentic-shield.yaml` in your project root:

```yaml
version: "0.1"

profiles:
  - shield-legal
  - shield-therapy

layers:
  regex: true
  ner: true
  rules: true
  llm:
    enabled: false         # opt-in only; requires ollama
    model: llama3.1:8b
    endpoint: http://localhost:11434

scoring:
  min_confidence: 0.5
```

---

## Offline by Default

Layers 1 and 2 make **zero network calls**. No telemetry, no analytics, no cloud APIs. Everything runs on your machine. Layer 3 (LLM, coming in v0.2) calls localhost Ollama only &mdash; never an external endpoint.

This means `ogentic-shield` works in air-gapped environments out of the box.

---

## Development

```bash
# Clone and install
git clone https://github.com/OgenticAI/ogentic-shield.git
cd ogentic-shield
pip install -e ".[dev]"
python -m spacy download en_core_web_lg

# Run tests (198 tests)
pytest tests/ -v

# Lint
ruff check src/ tests/

# Type check
mypy src/ogentic_shield/
```

---

## Contributing

We welcome contributions &mdash; especially new recognizer patterns, test cases for edge cases, and domain expertise in legal, clinical, or financial regulation.

1. Fork the repo
2. Create a branch (`feat/`, `fix/`, `test/`)
3. Follow the patterns in `CLAUDE.md` (recognizer structure, test structure, naming conventions)
4. Ensure `ruff check` and `pytest` pass
5. Open a PR

See `PRD.md` for the full product specification and `CLAUDE.md` for architecture decisions and code conventions.

---

## Roadmap

### v0.1.0 (current)
- 30 recognizers across legal, therapy, and finance
- 3-layer detection pipeline (regex/NER + rules + LLM stub)
- Configurable scoring with profile-driven weights
- CLI with JSON, table, and summary output
- 198 passing tests

### v0.2.0 (planned)
- Layer 3: Local LLM classification via Ollama
- MCP server mode (`ogentic-shield serve --mcp`)
- HTTP API server (`ogentic-shield serve --http`)
- Custom profile loading from YAML
- Expanded recognizer patterns based on community feedback

---

## License

Apache 2.0 &mdash; see [LICENSE](LICENSE).

Built by [OgenticAI](https://ogentic.ai). Trust is not a policy &mdash; it's infrastructure.
