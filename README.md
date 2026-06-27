<!-- AI-AGENT-SUMMARY
name: ogentic-shield
category: regulatory sensitivity detection, privilege classification, PII/PHI/MNPI detection
license: Apache-2.0
solves: [detect attorney-client privilege before text reaches AI, detect HIPAA PHI in clinical content, detect financial MNPI/insider information, classify regulatory sensitivity with scoring and routing suggestions]
input: text content (strings, files, stdin)
output: JSON (entities with confidence, score, sensitivity level, routing suggestion), table, summary
sdk: Python
requirements: Python 3.10+, spaCy en_core_web_lg model
pricing: open-source (Apache 2.0), no enterprise tier
key-differentiators: [extends Presidio with 30 domain-specific recognizers, 4-layer pipeline (regex/NER + rules + localhost-Ollama LLM), composable profiles for legal/therapy/finance, fully offline — zero network calls (LLM is localhost-only), advisory routing suggestions, 250+ passing tests]
-->

# ogentic-shield

**Regulatory sensitivity detection for AI applications. Open-source.**

[![CI](https://github.com/OgenticAI/ogentic-shield/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/OgenticAI/ogentic-shield/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/OgenticAI/ogentic-shield/blob/main/LICENSE)
[![PyPI version](https://img.shields.io/pypi/v/ogentic-shield.svg)](https://pypi.org/project/ogentic-shield/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://github.com/OgenticAI/ogentic-shield#install)
[![Tests](https://img.shields.io/badge/tests-198%20passed-brightgreen.svg)](https://github.com/OgenticAI/ogentic-shield#development)

Detect attorney-client privilege, HIPAA PHI, financial MNPI, and 50+ PII types **before content reaches an AI model**. Extends [Microsoft Presidio](https://github.com/microsoft/presidio) with 30 domain-specific recognizers, a context-aware rules engine, and profile-driven scoring.

> **Try it without installing →** drop a document into the [live Streamlit demo](https://ogenticai-shield-demo.hf.space) and see redacted output + the entity table side-by-side. ([source](https://github.com/OgenticAI/shield-streamlit-demo))

- **Does it detect legal privilege?** &mdash; Yes. 10 recognizers for attorney-client privilege markers, counsel communications, work product doctrine, settlement terms, case numbers, law firm names, litigation holds, court filings, Bates numbers, and executive titles ([shield-legal](#shield-legal--attorney-client-privilege))
- **Does it detect clinical PHI?** &mdash; Yes. 10 recognizers for patient names, DOB, ICD-10 codes, clinical risk flags (suicidal ideation, self-harm), session markers, insurance IDs, 50+ psychiatric medications, provider names, SSNs, and psychotherapy note indicators ([shield-therapy](#shield-therapy--hipaa-phi--clinical-risk))
- **Does it detect financial MNPI?** &mdash; Yes. 10 recognizers for MNPI markers, M&A activity, deal values, leverage ratios, fund information, institution names, covenants, distribution restrictions, insider markers, and carry terms ([shield-finance](#shield-finance--mnpi--deal-terms))
- **Does it work offline?** &mdash; Yes. Layers 1 and 2 make zero network calls. No telemetry, no cloud APIs. Works in air-gapped environments ([offline by default](#offline-by-default))
- **How do I use it?** &mdash; `pip install ogentic-shield`, analyze in 3 lines. Python library, CLI tool, composable profiles ([quick start](#get-started-in-30-seconds))

---

## Table of Contents

- [Why This Exists](#why-this-exists)
- [About OgenticAI](#about-ogenticai)
- [What Problems Does This Solve?](#what-problems-does-this-solve)
- [Capability Matrix](#capability-matrix)
- [Get Started in 30 Seconds](#get-started-in-30-seconds)
- [Shield Profiles](#shield-profiles)
- [Detection Pipeline](#detection-pipeline)
- [CLI](#cli)
- [Python API](#python-api)
- [Redaction (Detection &ne; Redaction)](#redaction-detection--redaction)
- [MCP Server](#mcp-server)
- [Configuration](#configuration)
- [Offline by Default](#offline-by-default)
- [Frequently Asked Questions](#frequently-asked-questions)
- [Roadmap](#roadmap)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## Why This Exists

On February 10, 2026, *US v. Heppner* (S.D.N.Y.) established that sending content to public AI tools waives attorney-client privilege. The same reasoning extends to therapist-patient confidentiality under HIPAA, material non-public information under SEC/FINRA rules, and every regulated profession with a duty of confidentiality.

**30+ million US professionals** use AI daily. 71% of law firms have no AI policy. 43% of therapists have entered patient data into public AI. There is no open-source tool that answers a simple question before text reaches a model: *does this content contain something that should never leave this device?*

[Microsoft Presidio](https://github.com/microsoft/presidio) handles general PII well (names, SSNs, credit cards). It knows nothing about attorney-client privilege markers, psychotherapy note indicators, MNPI signals, or work product doctrine. `ogentic-shield` fills that gap.

---

## About OgenticAI

[OgenticAI](https://ogenticai.com) is building **trust infrastructure for regulated industries** &mdash; the tools that make AI safe for professionals who can't afford to get it wrong: lawyers, therapists, financial teams, and healthcare providers.

`ogentic-shield` is the first release in a series of open-source projects that together form the foundation for privacy-first AI:

| Project | Purpose | Status |
|---------|---------|--------|
| **[`ogentic-shield`](https://github.com/OgenticAI/ogentic-shield)** | Detect privileged, clinical, and financial sensitivity in text | **v0.3.0 &mdash; On PyPI** |
| `ogentic-audit` | Cryptographic, tamper-evident audit trails for AI usage | Coming soon |
| `ogentic-router` | Privacy-aware LLM routing (sensitive &rarr; local, safe &rarr; cloud) | Coming soon |
| `ogentic-redact` | Structure-aware document redaction for legal proceedings | Planned |
| `ogentic-vault` | Local-first, encrypted knowledge management per matter/patient | Planned |
| `ogentic-legal-mcp` | MCP servers for legal document intelligence and research | Planned |
| `ogentic-legal-bench` | Open benchmarks for legal AI trustworthiness | Planned |

These projects are designed to compose:

```
ogentic-shield ──> ogentic-router ──> ogentic-audit
  (classify)         (route)            (log)
      |                  |                  |
      v                  v                  v
ogentic-redact     ogentic-vault     ogentic-legal-bench
  (redact docs)    (knowledge DB)      (benchmarks)
      |                  |
      v                  v
  ogentic-legal-mcp
  (MCP servers for legal workflows)
```

Together they form a complete open-source stack for privilege-protected AI &mdash; and the foundation for [Sotto](https://sottotrust.ai/), OgenticAI's commercial product for regulated professionals.

All `ogentic-*` projects are Apache 2.0 licensed.

---

## What Problems Does This Solve?

| Problem | Solution | Profile |
|---------|----------|---------|
| **Attorney-client privilege waived** when legal content reaches public AI (*Heppner*) | Detect privilege markers, counsel communications, and work product before routing | `shield-legal` |
| **HIPAA violations** when therapists enter session notes into AI tools | Detect PHI, psychotherapy note indicators, diagnosis codes, and clinical risk flags | `shield-therapy` |
| **SEC/FINRA violations** when financial teams process MNPI through cloud AI | Detect insider markers, deal terms, fund information, and confidential designations | `shield-finance` |
| **No routing signal** &mdash; apps don't know whether to use local or cloud AI | Score-based routing suggestions: `LOCAL_ONLY`, `REDACT_CLOUD`, or `CLOUD_OK` | All |
| **[Presidio](https://github.com/microsoft/presidio) doesn't understand privilege** &mdash; only general PII | 30 domain-specific recognizers that extend Presidio as first-class citizens | All |

---

## Capability Matrix

| Capability | Supported | Notes |
|------------|-----------|-------|
| **Detection** | | |
| General PII (names, SSN, email, phone, credit card) | Yes | Via [Presidio](https://github.com/microsoft/presidio) built-in recognizers (50+ types) |
| Attorney-client privilege markers | Yes | `shield-legal` &mdash; 10 recognizers |
| Work product doctrine detection | Yes | `shield-legal` |
| Law firm name recognition (AmLaw 200) | Yes | `shield-legal` |
| Case numbers and Bates stamps | Yes | `shield-legal` |
| HIPAA Protected Health Information | Yes | `shield-therapy` &mdash; 10 recognizers |
| Psychotherapy note indicators | Yes | `shield-therapy` |
| Clinical risk flags (SI, self-harm) | Yes | `shield-therapy` |
| Psychiatric medication detection (50+ drugs) | Yes | `shield-therapy` |
| ICD-10 mental health diagnosis codes | Yes | `shield-therapy` |
| Material non-public information (MNPI) | Yes | `shield-finance` &mdash; 10 recognizers |
| M&A activity and deal values | Yes | `shield-finance` |
| Insider trading markers and blackout periods | Yes | `shield-finance` |
| Institution names (50+ banks/PE firms) | Yes | `shield-finance` |
| **Pipeline** | | |
| Layer 1: Regex + NER (&lt;50ms) | Yes | [Presidio](https://github.com/microsoft/presidio) engine with custom recognizers |
| Layer 2: Context-aware rules engine (&lt;10ms) | Yes | Confidence boosting via co-occurrence |
| Layer 3: Local LLM classification | Yes | Localhost Ollama, profile-tuned prompts, structured JSON output, retry + graceful fallback |
| Quality tiers + `Shield.required_models()` | Yes | `fast` / `quality` / `comprehensive`, with per-role overrides |
| Overlap resolution (longest span, highest confidence) | Yes | With category-group priority tiebreaker |
| **Scoring & Routing** | | |
| Weighted sensitivity scoring (0&ndash;100) | Yes | Profile-driven, composable weights |
| Sensitivity levels (NONE/LOW/MEDIUM/HIGH/CRITICAL) | Yes | Score-based thresholds |
| Routing suggestions (LOCAL_ONLY/REDACT_CLOUD/CLOUD_OK) | Yes | Advisory, not enforcement |
| **Interfaces** | | |
| Python library | Yes | `from ogentic_shield import Shield` |
| Async API + streaming | Yes | `AsyncShield.analyze()` / `analyze_stream()` for non-blocking UI integration |
| Batch API | Yes | `Shield.analyze_batch()` with parallel processing and per-item error containment |
| CLI tool | Yes | `ogentic-shield analyze`, `ogentic-shield profiles` |
| JSON / table / summary output | Yes | Pipe-friendly JSON, Rich tables, one-line summary |
| MCP server | Yes | `shield.{analyze, analyze_batch, redact, unredact, profiles}` async tools |
| HTTP API (FastAPI) | Planned | v0.3 |
| **Privacy** | | |
| Fully offline (zero network calls) | Yes | Layers 1 and 2 |
| No telemetry or analytics | Yes | By design |
| Air-gapped environment support | Yes | No internet required |
| **Limitations** | | |
| Document processing (PDF/DOCX) | No | Use with [OpenDataLoader PDF](https://github.com/opendataloader-project/opendataloader-pdf) for extraction, then pass text to shield |
| Redaction | No | Classification only &mdash; redaction is `ogentic-redact` |
| Routing enforcement | No | Advisory suggestions &mdash; enforcement is `ogentic-router` |
| GPU required | No | CPU only |

---

## Get Started in 30 Seconds

**Requires**: Python 3.10+ and a [spaCy](https://spacy.io/) language model (used by [Presidio](https://github.com/microsoft/presidio) for NER)

```bash
pip install ogentic-shield
python -m spacy download en_core_web_lg
```

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

### Analyze a document

Pass a path to `analyze_document` and get the same scoring shape with per-chunk breakdowns. **Phase 1 supports `.txt`, `.md`, and `.log`**; PDF / DOCX / XLSX / EML / MSG / HTML are recognized and emit a clear `UnsupportedDocumentFormatError` pointing at the `[documents]` extra (Phase 2 work — tracked on [OGE-398](https://linear.app/ogenticai/issue/OGE-398)).

```python
from ogentic_shield import Shield

shield = Shield(profiles=["shield-legal"])
result = shield.analyze_document("memo.txt")

print(result.format)                       # "text"
print(result.aggregate.score)              # max across chunks
print(result.aggregate.routing_suggestion) # LOCAL_ONLY if any chunk is CRITICAL
print(len(result.chunks))                  # per-chunk drill-down available
```

Extraction runs **in-process** on your machine. None of the document-parsing libraries phone home — the privacy contract is identical to the string-input path.

---

## Shield Profiles

Each profile adds a set of recognizers, rules, and scoring weights for a specific domain. Profiles are **composable** &mdash; load multiple for cross-domain work (e.g., a law firm handling healthcare litigation).

### `shield-legal` &mdash; Attorney-Client Privilege

| Recognizer | Entity Type | Example Match |
|------------|-------------|---------------|
| Counsel Communication | `COUNSEL_COMMUNICATION` | "outside counsel", "legal counsel", "in-house counsel" |
| Privilege Marker | `PRIVILEGE_MARKER` | "privileged and confidential", "attorney-client privilege" |
| Work Product | `WORK_PRODUCT` | "attorney work product", "prepared in anticipation of litigation" |
| Settlement Terms | `SETTLEMENT_TERMS` | "settle for $4.2M", "settlement agreement" |
| Case Number | `CASE_NUMBER` | "25-cr-00503", "24-cv-1234" |
| Law Firm Name | `LAW_FIRM_NAME` | Davis Polk, Kirkland & Ellis, Skadden (40+ AmLaw firms) |
| Litigation Marker | `LITIGATION_MARKER` | "litigation hold", "legal hold", "preservation notice" |
| Court Filing | `COURT_FILING` | "motion to dismiss", "summary judgment", "deposition" |
| Bates Number | `BATES_NUMBER` | "BATES 000123", "DOC-2026-0042" |
| Executive Name | `EXECUTIVE_NAME` | "CEO Williams", "General Counsel Martinez" |

**Scoring weights**: PRIVILEGE: 30, PII: 15, CONFIDENTIAL: 10

### `shield-therapy` &mdash; HIPAA PHI & Clinical Risk

| Recognizer | Entity Type | Example Match |
|------------|-------------|---------------|
| Patient Name | `PATIENT_NAME` | "Patient: Jane D.", "Client: Mary J." |
| Date of Birth | `DATE_OF_BIRTH` | "DOB: 03/15/1988", "Date of Birth: 1988-03-15" |
| Diagnosis Code | `DIAGNOSIS_CODE` | "F33.1", "F41.0", "DSM-5 criteria" |
| Clinical Risk Flag | `CLINICAL_RISK_FLAG` | "suicidal ideation", "self-harm", "homicidal ideation" |
| Session Marker | `SESSION_MARKER` | "Session 12", "intake assessment", "treatment plan" |
| Insurance ID | `INSURANCE_ID` | "Insurance ID: UHC-8847291", "Member ID" |
| Medication | `MEDICATION` | Sertraline, Lexapro, Zoloft, Abilify (50+ drugs, brand and generic) |
| Provider Name | `PROVIDER_NAME` | "Therapist Sarah", "Johnson, LCSW" |
| SSN | `SSN` | "123-45-6789", "SSN: 987-65-4321" |
| Psychotherapy Note Marker | `PSYCHOTHERAPY_NOTE_MARKER` | "process notes", "countertransference", "therapeutic alliance" |

**Scoring weights**: PHI: 28, PII: 15, CONFIDENTIAL: 10

### `shield-finance` &mdash; MNPI & Deal Terms

| Recognizer | Entity Type | Example Match |
|------------|-------------|---------------|
| MNPI Marker | `MNPI_MARKER` | "MNPI", "MATERIAL NON-PUBLIC", "CONFIDENTIAL" |
| M&A Activity | `MA_ACTIVITY` | "acquiring", "merger agreement", "takeover bid" |
| Deal Value | `DEAL_VALUE` | "$47/share", "$2.1 billion", "$200M commitment" |
| Leverage Ratio | `LEVERAGE_RATIO` | "5.2x EBITDA", "3.5x revenue" |
| Fund Information | `FUND_INFORMATION` | "Fund III", "LP allocation", "co-investment" |
| Institution Name | `INSTITUTION_NAME` | Goldman Sachs, Blackstone, KKR (50+ banks/PE firms) |
| Financial Terms | `FINANCIAL_TERMS` | "covenant", "DSCR", "term sheet", "waterfall" |
| Distribution Restriction | `DISTRIBUTION_RESTRICTION` | "do not distribute", "internal use only" |
| Insider Marker | `INSIDER_MARKER` | "insider trading", "blackout period", "restricted list" |
| Carry Terms | `CARRY_TERMS` | "20% carry", "hurdle rate", "preferred return" |

**Scoring weights**: MNPI: 30, PII: 12, CONFIDENTIAL: 10

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

## Detection Pipeline

```
Input Text
    |
    v
+-------------------------------------+
| Layer 1: REGEX + NER  (< 50ms)      |
|                                      |
| Presidio built-in PII recognizers    |
| + 30 custom domain recognizers       |
| Deduplicates overlapping spans       |
+------------------+-------------------+
                   |
                   v
+-------------------------------------+
| Layer 2: RULES ENGINE  (< 10ms)     |
|                                      |
| Context-aware confidence boosting    |
| Co-occurrence detection within       |
| configurable character windows       |
+------------------+-------------------+
                   |
                   v
+-------------------------------------+
| Layer 3: LLM (opt-in)                |
|                                      |
| Localhost Ollama only — never cloud  |
| Profile-tuned prompts, structured    |
| JSON output, runs only on            |
| ambiguous L1+L2 scores               |
+------------------+-------------------+
                   |
                   v
  Score (0-100) + Level + Routing
```

**Overlap resolution** (when multiple recognizers match the same span):
1. Longer span wins over shorter span
2. If same length, higher confidence wins
3. If same confidence: PRIVILEGE > PHI > MNPI > PII > CONFIDENTIAL

---

## CLI

```bash
# Analyze text directly
ogentic-shield analyze "privileged and confidential" \
  --profiles shield-legal --output json

# Analyze from file
ogentic-shield analyze --file memo.txt \
  --profiles shield-legal shield-finance

# Pipe from stdin
cat brief.txt | ogentic-shield analyze --profiles shield-legal

# Output formats
ogentic-shield analyze "..." --output json      # structured JSON
ogentic-shield analyze "..." --output table     # Rich colored table
ogentic-shield analyze "..." --output summary   # one-line summary

# List available profiles
ogentic-shield profiles list

# Show profile details
ogentic-shield profiles show shield-legal

# Version
ogentic-shield --version
```

### Output Examples

**Summary** (`--output summary`):

```
CRITICAL (94) | LOCAL_ONLY | 6 entities | COUNSEL_COMMUNICATION (0.93) | 12.4ms
```

**JSON** (`--output json`):

```json
{
  "text_hash": "sha256:a1b2c3d4e5f6...",
  "score": 94,
  "sensitivity_level": "CRITICAL",
  "routing_suggestion": "LOCAL_ONLY",
  "entity_count": 6,
  "processing_time_ms": 12.4,
  "layers_invoked": ["REGEX", "NER"],
  "profiles_active": ["shield-legal"],
  "entities": [
    {
      "text": "outside counsel",
      "category": "COUNSEL_COMMUNICATION",
      "category_group": "PRIVILEGE",
      "confidence": 0.93,
      "detection_layer": "REGEX",
      "start": 33,
      "end": 48
    }
  ]
}
```

---

## Python API

```python
from ogentic_shield import Shield, DetectionLayer

# Initialize with one or more profiles
shield = Shield(profiles=["shield-legal", "shield-therapy"])

# Analyze text
result = shield.analyze("Per our conversation with outside counsel...")

# Analyze with options
result = shield.analyze(
    text,
    profiles=["shield-legal"],           # override profiles for this call
    layers=[DetectionLayer.REGEX, DetectionLayer.NER],  # skip rules layer
    min_confidence=0.7,                  # filter low-confidence entities
)

# Inspect results
print(result.score)                # 0-100
print(result.sensitivity_level)    # NONE/LOW/MEDIUM/HIGH/CRITICAL
print(result.routing_suggestion)   # LOCAL_ONLY/REDACT_CLOUD/CLOUD_OK
print(result.entity_count)         # number of detected entities
print(result.processing_time_ms)   # analysis time

for entity in result.entities:
    print(f"{entity.text} -> {entity.category} ({entity.confidence:.2f})")

# List and inspect profiles
profiles = Shield.list_profiles()
profile = Shield.get_profile("shield-legal")
print(profile.supported_entities)
```

---

## Redaction (Detection &ne; Redaction)

`Shield.analyze()` **classifies** &mdash; it tells you what's in the text and how sensitive it is. It does not modify the content.

`Shield.redact()` **rewrites** &mdash; it substitutes identifying entities with deterministic tokens before you send the text to an external LLM, then `Shield.unredact()` restores them on the response.

### The principle: anonymity = masking *who*, not *how big*

When you wrap an LLM call with redaction, the goal is to mask **identifying information** without destroying **the shape of the data the model needs to reason about**:

| Category | Default behavior | Why |
|----------|------------------|-----|
| Person, sponsor, address, email, phone, SSN | **Redacted** | Identifies individuals or counterparties |
| Case number, Bates number (legal) | **Redacted** | Identifies the matter |
| DOB, insurance ID, medical license (therapy) | **Redacted** | HIPAA Safe Harbor identifiers |
| Loan amount, NOI, cap rate, EBITDA multiple, percentages | **Preserved** | The model needs the numbers to do math |
| Property type, business plan, year built, occupancy | **Preserved** | Generic; required for sizing/reasoning logic |
| Diagnosis code, medication, clinical risk flags | **Preserved** | Clinical content the model needs to respond appropriately |

The detection layer still flags the preserved categories (so audit and routing decisions see them); the redaction layer just doesn't mask them by default. Override per-call with `redact_categories=[...]` if your use case differs.

### Round-trip example

```python
from ogentic_shield import Shield

shield = Shield(profiles=["shield-finance"])

text = (
    "Goldman Sachs is advising John Smith on the acquisition at $47/share, "
    "representing a 5.2x EBITDA multiple. Contact: john@example.com."
)

redacted, mapping = shield.redact(text)
# redacted ≈ "[Sponsor_a3f9b1] is advising [Person_b7e0c4] on the acquisition
#            at $47/share, representing a 5.2x EBITDA multiple.
#            Contact: [Email_4d2af1]."
# Numbers stay; identifiers leave.

response = call_external_llm(redacted)

original = Shield.unredact(response, mapping)
# Tokens in the response are restored to "Goldman Sachs", "John Smith", etc.
```

### Token format

Tokens look like `[Person_a3f9b1]` &mdash; a friendly category prefix plus a 6-character hex hash. Properties:

- **Within one call**: same value gets the same token (so the LLM sees coherent references &mdash; "John Smith" mentioned three times is still one person).
- **Across calls**: tokens differ (per-call salt). The same value is not linkable across documents via rainbow-table lookup.
- **Reversible**: only via the returned `RedactionMapping` &mdash; nothing in the token itself reveals the original.

### Per-profile category defaults

| Profile | Default `redact_categories` |
|---------|------------------------------|
| `shield-finance` | `Person, Address, Sponsor, Email, Phone, Ssn` |
| `shield-legal` | defaults &nbsp;+&nbsp; `CaseNumber, BatesNumber` |
| `shield-therapy` | defaults &nbsp;+&nbsp; `DateOfBirth, InsuranceId, MedicalLicense` |

Override per call:

```python
# Mask only emails
redacted, mapping = shield.redact(text, redact_categories=["Email"])

# Power-user: pass underlying entity types directly
redacted, mapping = shield.redact(text, redact_categories=["INSTITUTION_NAME", "PERSON"])
```

Available labels: `Person`, `Address`, `Sponsor`, `Email`, `Phone`, `Ssn`, `DateOfBirth`, `InsuranceId`, `MedicalLicense`, `CaseNumber`, `BatesNumber`, `Diagnosis`, `Medication`, `CreditCard`, `BankNumber`, `Url`, `IpAddress`, `Passport`, `Itin`, `DriverLicense`, `DateTime`, `Iban`, `Nationality`.

---

## MCP Server

`ogentic-shield` ships an [MCP](https://modelcontextprotocol.io) server so LLM clients (Claude Desktop, Goose, Cursor, custom agents) can call into the same pipeline as the CLI &mdash; classify or redact text inline before forwarding it to a foundation model.

### Easiest install — MCP Bundle (`.mcpb`)

For non-developers and one-click distribution: download the latest `.mcpb` from [the releases page](https://github.com/OgenticAI/ogentic-shield/releases/latest), then in Claude Desktop go to **Settings → Connectors → `+` → Install from file** and pick the file you downloaded. Five `shield.*` tools appear; nothing else to configure. First launch downloads spaCy's `en_core_web_lg` model (~600MB, one time).

The bundle source lives at [`mcpb/`](mcpb/); rebuild via `./scripts/pack-mcpb.sh` (requires `npm install -g @anthropic-ai/mcpb`).

### Developer install — pip + manual config

```bash
# Optional dep — installs the model-context-protocol Python SDK
pip install 'ogentic-shield[mcp]'

# Run over stdio (Claude Desktop, Goose, Cursor)
ogentic-shield serve --profile shield-legal

# Run over SSE (network clients; loopback by default)
ogentic-shield serve --transport sse --port 8765 --profile shield-finance

# Multiple profiles loaded; pick one per call
ogentic-shield serve --profile shield-legal --profile shield-therapy
```

Equivalent module form: `python -m ogentic_shield.mcp --profile shield-legal`.

### Tools registered

| Tool | Purpose |
|------|---------|
| `shield.analyze` | Classify text. Returns score, level, routing suggestion, and shape-only entities (no raw matched text by default). |
| `shield.redact` | Substitute identifying entities with deterministic tokens. Returns `redacted_text` and a reversible `mapping`. |
| `shield.unredact` | Restore tokens in (model-rewritten) text using the mapping returned by `shield.redact`. |
| `shield.profiles` | List loaded profiles, supported entity categories, and the server's startup default. |

### Privacy invariants

- **`analyze` responses omit entity text by default.** The shape-only payload (category / confidence / span) is sufficient for routing decisions and avoids leaking the very content we're trying to protect. Opt in per call with `include_entities=true` for local debugging.
- **Profile names are an allow-list.** Only `shield-legal`, `shield-therapy`, and `shield-finance` are accepted; an unknown profile name raises rather than silently loading attacker-supplied YAML.
- **No raw text is logged.** Same `safe_emit` discipline as the rest of the codebase &mdash; tool exceptions surface as MCP errors; the server stays up.

### Claude Desktop config

```json
{
  "mcpServers": {
    "ogentic-shield": {
      "command": "ogentic-shield",
      "args": ["serve", "--profile", "shield-legal"]
    }
  }
}
```

---

## Configuration

Create an `ogentic-shield.yaml` in your project root to customize defaults:

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
    enabled: false              # opt-in only; requires ollama
    provider: ollama
    model: ""                    # empty = use ModelRegistry default for `quality`
    quality: fast                # fast | quality | comprehensive
    endpoint: http://localhost:11434  # MUST be localhost — enforced at startup
    timeout_ms: 5000
    max_retries: 2
    ambiguous_score_range: [20, 60]

scoring:
  min_confidence: 0.5
  dedup_strategy: longest_highest

output:
  include_text_hash: true
  include_processing_time: true
  max_entities: 50
```

---

## Offline by Default

Layers 1 and 2 make **zero network calls**. No telemetry, no analytics, no cloud APIs. Everything runs on your machine. Layer 3 (LLM, opt-in) calls **localhost Ollama only** &mdash; never an external endpoint. The endpoint is validated at config-load time and at client construction; any non-localhost host raises `LocalhostOnlyError` so a typo can't quietly send traffic offsite.

### Quality tiers and the model registry

Shield ships a `ModelRegistry` so downstream consumers (Sotto Desktop, Zing Browser, Zashboard, Gyri, any MCP client) don't each re-derive which Ollama models to pre-pull:

```python
from ogentic_shield import Shield, ModelTier

shield = Shield(profiles=["shield-legal"], quality="fast")
shield.required_models()              # ['granite3.1-moe:1b']
shield.required_models("quality")     # ['mixtral:8x7b']
shield.required_models("comprehensive")  # ['mixtral:8x7b', 'qwen3:4b']

# Per-role override — substitutes Shield's pick for the model you've standardized on:
shield = Shield(
    profiles=["shield-legal"],
    quality="fast",
    model_override={"classification": "phi4:14b"},
)
shield.required_models()              # ['phi4:14b']
```

Confidence scores are calibrated **per layer** at the pipeline level (OGE-321). The default calibration ships at `src/ogentic_shield/data/calibration.json`: REGEX / NER / RULES pass through unchanged (factor 1.0 — Presidio confidences and hand-tuned rule constants are already corpus-calibrated), and LLM is discounted (factor 0.7) to compensate for systematic over-confidence in self-reported model probabilities. Raw confidence is preserved in `entity.metadata["raw_confidence"]` for debugging:

```python
from ogentic_shield import Calibrator, set_calibrator
# Override the packaged default with your own corpus-fit factors:
set_calibrator(Calibrator.from_file("my_calibration.json"))
```

The packaged factors can be refit against the OGE-51 datasets via `python benchmarks/fit_calibration.py --json calibration.json --md benchmarks/CALIBRATION_REPORT.md`. Methods supported: `linear` (the v0.2.1 default), `platt` (sigmoid fit), `isotonic` (piecewise-linear breakpoints).

### Async + batch APIs

Shield ships in three flavors:

- **`Shield`** — sync, the default. Best for scripts and the CLI.
- **`AsyncShield`** — coroutine-friendly wrapper. Dispatches each call through `asyncio.to_thread` so a busy event loop (MCP server, web app) stays responsive.
- **`Shield.analyze_batch`** — parallel multi-text analysis with per-item error containment.

```python
import asyncio
from ogentic_shield import AsyncShield, BatchItemError, Shield

# Async — non-blocking, returns the same AnalysisResult shape
async def main():
    shield = AsyncShield(profiles=["shield-finance"])
    result = await shield.analyze("MNPI: pending acquisition of TargetCo at $4.2B.")
    print(result.score, result.routing_suggestion)

    # Streaming — yields a StreamEvent after each layer completes
    async for event in shield.analyze_stream(text):
        if event.is_final:
            print("done:", event.result.score)
        else:
            print(f"after {event.layer.value}: {len(event.entities)} entities so far")

asyncio.run(main())

# Batch — list-in, list-out, results align positionally with input
shield = Shield(profiles=["shield-finance"])
results = shield.analyze_batch(
    ["text 1", "text 2", "text 3"],
    max_workers=4,
)
for i, item in enumerate(results):
    if isinstance(item, BatchItemError):
        print(f"input {i} failed: {item.error_type}: {item.error}")
    else:
        print(f"input {i}: score={item.score}")
```

The MCP server uses `AsyncShield` natively — tools like `shield.analyze` and the new `shield.analyze_batch` are async, so MCP clients (Claude Desktop, Goose, Cursor) get non-blocking calls without `asyncio.to_thread` wrapping.

### Verifying Layer 3 against the benchmark targets

The labelled JSONL datasets under `benchmarks/` are the precision oracle. To verify Layer 3 against PRD §8 targets locally:

```bash
ollama serve &
ollama pull granite3.1-moe:1b
.venv/bin/python benchmarks/run_layer3_benchmark.py
```

Exit code 0 means every profile met its target (legal ≥90%, PHI ≥92%, MNPI ≥88%). The integration test suite (`tests/integration/`) is gated by `OGENTIC_SHIELD_OLLAMA_INTEGRATION=1` so CI runners without Ollama still get a green build.

> **Status (v0.2):** No model meets every PRD target on the current OGE-51 dataset, including the L1+L2-only baseline. Enabling Layer 3 trades precision for recall. Production callers should leave `enabled: false` for now. The full per-model comparison is in [`benchmarks/MOE_COMPARISON.md`](benchmarks/MOE_COMPARISON.md); calibration (OGE-321) and prompt-narrowing are the planned follow-ups to close the gap.

To run the multi-model MoE-vs-dense comparison (used in OGE-320):

```bash
ollama pull granite3.1-moe:1b granite3-moe:3b llama3.2:3b qwen3:4b
.venv/bin/python benchmarks/run_moe_comparison.py \
    --json benchmarks/MOE_COMPARISON.results.json \
    --md   benchmarks/MOE_COMPARISON.md
```

This means `ogentic-shield` works in air-gapped environments out of the box. No internet connection required for installation beyond the initial `pip install` and spaCy model download.

---

## Frequently Asked Questions

### What is ogentic-shield?

`ogentic-shield` is an open-source Python library that classifies text content for regulatory sensitivity across legal, clinical, and financial domains. It extends [Microsoft Presidio](https://github.com/microsoft/presidio) with 30 domain-specific recognizers that detect attorney-client privilege, HIPAA PHI, and financial MNPI &mdash; categories that Presidio doesn't cover.

### Why not just use Presidio directly?

[Presidio](https://github.com/microsoft/presidio) is excellent for general PII (names, SSNs, credit cards, phone numbers). But it has no concept of legal privilege, psychotherapy note indicators, or MNPI markers. `ogentic-shield` extends Presidio &mdash; all 50+ built-in Presidio recognizers are still available, plus 30 domain-specific ones.

### Does it work without an internet connection?

Yes. Layers 1 and 2 are fully offline. No API calls, no data transmission. Documents never leave your machine. This is critical for regulated environments where data residency matters.

### How fast is it?

Layer 1 (regex + NER) completes in under 50ms for text under 5,000 characters. Layer 2 (rules) adds under 10ms. The full pipeline without LLM runs in under 100ms. No GPU required.

### Does it enforce routing decisions?

No. `ogentic-shield` provides an **advisory** routing suggestion (`LOCAL_ONLY`, `REDACT_CLOUD`, or `CLOUD_OK`). Your application decides what to do with it. Enforcement is the job of `ogentic-router`, a separate project in the ecosystem.

### Can I create custom profiles?

Yes. Profiles can be defined as Python modules (for complex recognizer logic) or YAML files (for simple pattern definitions). See `CLAUDE.md` for the profile pattern and `PRD.md` Section 7.2 for the YAML format.

### How do I use this with PDFs?

`ogentic-shield` analyzes text, not files. For PDF processing, use [OpenDataLoader PDF](https://github.com/opendataloader-project/opendataloader-pdf) to extract text, then pass it to `ogentic-shield`:

```python
import opendataloader_pdf
from ogentic_shield import Shield

# Extract text from PDF
opendataloader_pdf.convert(input_path=["contract.pdf"], output_dir="output/", format="text")

# Analyze extracted text
shield = Shield(profiles=["shield-legal"])
with open("output/contract.txt") as f:
    result = shield.analyze(f.read())
```

### Can I combine multiple profiles?

Yes. Profiles are composable. Load `shield-legal` and `shield-finance` together for a law firm advising on M&A, or `shield-legal` and `shield-therapy` for healthcare litigation:

```python
shield = Shield(profiles=["shield-legal", "shield-finance"])
```

When profiles have conflicting weights for the same category group, the higher weight wins.

### What Python versions are supported?

Python 3.10 and above. Tested on 3.10, 3.11, 3.12, and 3.13.

### Is there a Docker image?

Not yet in v0.1. A Docker image is planned for v0.2 alongside the HTTP API server.

---

## Roadmap

| Feature | Version | Status |
|---------|---------|--------|
| 30 recognizers (legal, therapy, finance) | v0.1.0 | Shipped |
| 3-layer detection pipeline (regex/NER + rules + LLM stub) | v0.1.0 | Shipped |
| Configurable scoring with profile-driven weights | v0.1.0 | Shipped |
| CLI with JSON, table, and summary output | v0.1.0 | Shipped |
| 198 passing tests | v0.1.0 | Shipped |
| Category-aware `redact()` / `unredact()` API | v0.2.0 | Shipped |
| Per-profile redact-category defaults | v0.2.0 | Shipped |
| Layer 3: Local LLM classification via Ollama | v0.2.0 | Shipped |
| `ModelRegistry` + `Shield.required_models()` (fast / quality / comprehensive) | v0.2.0 | Shipped |
| Profile-tuned LLM prompts (legal, therapy, finance) | v0.2.0 | Shipped |
| `AsyncShield` + `analyze_stream()` for non-blocking UI integration | v0.2.0 | Shipped |
| `Shield.analyze_batch()` with parallel processing and per-item error containment | v0.2.0 | Shipped |
| MCP server tools fully async (`shield.analyze_batch` added) | v0.2.0 | Shipped |
| MCP server (`shield.analyze`, `shield.redact`, `shield.profiles`) | v0.2.0 | Planned |
| Audit event emission for ogentic-audit | v0.2.0 | Planned |
| Custom profile loading from YAML | v0.2.0 | Planned |
| Docker image | v0.2.0 | Planned |
| Additional shield profiles (healthcare, accounting) | v0.3.0+ | Planned |

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

# Run tests with coverage
pytest tests/ --cov=ogentic_shield --cov-report=term-missing

# Lint
ruff check src/ tests/

# Type check
mypy src/ogentic_shield/

# Run all quality checks (CI equivalent)
ruff check src/ tests/ && mypy src/ogentic_shield/ && pytest tests/ -v --cov=ogentic_shield
```

### Examples

Three runnable examples under [`examples/`](examples/) demonstrate the
Python API:

- [`examples/basic_usage.py`](examples/basic_usage.py) — Simplest end-to-end:
  initialise `Shield`, analyse text, print the result.
- [`examples/custom_profile.py`](examples/custom_profile.py) — Define rules
  in YAML, load with `load_profile_from_yaml`, register, analyse.
- [`examples/multi_profile.py`](examples/multi_profile.py) — Compose
  `shield-legal` + `shield-finance` so a single message gets evaluated
  against both regulatory frames simultaneously.

```bash
python examples/basic_usage.py
python examples/custom_profile.py
python examples/multi_profile.py
```

### Benchmarks

Labelled JSONL datasets + a runner that reports per-recognizer
precision/recall/F1, per-profile aggregates, and timing. See
[`benchmarks/README.md`](benchmarks/README.md) for the schema and current
state vs PRD targets.

```bash
# Run every dataset
python benchmarks/run_benchmarks.py

# Run a single dataset, write JSON report
python benchmarks/run_benchmarks.py --dataset legal_privilege --json out.json

# Strict mode — exit non-zero if any precision / performance target is missed
python benchmarks/run_benchmarks.py --strict
```

### Project Structure

```
ogentic-shield/
├── src/ogentic_shield/
│   ├── shield.py              # Main entry point (Shield class)
│   ├── models.py              # Dataclasses, enums, exceptions
│   ├── pipeline.py            # Orchestrates layers 1 → 2 → 3
│   ├── scoring.py             # Score calculation + routing suggestion
│   ├── config.py              # YAML config loading
│   ├── recognizers/           # 30 Presidio-compatible recognizers (extend EntityRecognizer)
│   │   ├── legal.py           # 10 legal recognizers
│   │   ├── therapy.py         # 10 therapy recognizers
│   │   └── finance.py         # 10 finance recognizers
│   ├── profiles/              # Shield profiles (recognizers + rules + weights)
│   │   ├── legal.py           # shield-legal
│   │   ├── therapy.py         # shield-therapy
│   │   └── finance.py         # shield-finance
│   ├── layers/                # Detection layers
│   │   ├── regex_ner.py       # Layer 1: Presidio + custom recognizers
│   │   ├── rules.py           # Layer 2: Context-aware rules engine
│   │   ├── llm.py             # Layer 3: orchestration (run_layer3)
│   │   ├── llm_client.py      # OllamaClient — localhost-only, retries, fallback
│   │   ├── llm_prompts.py     # Profile-tuned prompts + few-shot examples
│   │   └── llm_schema.py      # Pydantic schema for structured output
│   └── cli/                   # Click CLI
├── tests/                     # 198 tests
├── examples/                  # Runnable Python API examples (basic, custom, multi-profile)
├── benchmarks/                # Labelled JSONL datasets + precision/recall/F1 runner
├── .github/workflows/ci.yml   # Lint + typecheck + tests on every push & PR
├── CLAUDE.md                  # Architecture decisions & code conventions
└── PRD.md                     # Full product specification
```

---

## Trust & Compliance

OgenticAI publishes the following policy documents as part of our commitment to regulated-industry transparency:

- **[Data Provenance](docs/PROVENANCE.md)** &mdash; Every training corpus with source, license, intake date, and content hash. Covers legal, clinical/therapy, and finance tiers.
- **[Vertical-Expert Feedback Policy](docs/VERTICAL-EXPERT-FEEDBACK.md)** &mdash; How expert annotators are isolated from customer data, including the access boundary, annotation protocol, and audit trail.
- **[No-Telemetry Policy](docs/TELEMETRY-POLICY.md)** &mdash; Our architectural commitment to zero outbound data, the explicit network allow-list, and a user-runnable verification recipe (tcpdump / Little Snitch / Wireshark).
- **[Corpus Remediation Playbook](docs/CORPUS-REMEDIATION.md)** &mdash; Our CVE-style process for contaminated or mis-licensed training data, including a synthetic sample incident.

These documents are the on-record receipts for the claim:

> *Models trained on Sotto-tier corpora improve over time without any customer data entering the training loop.*

All four documents are `Draft` status pending review by Craig + external counsel.
Enterprise customers may request attestation letters or corpus archives via [security@ogenticai.com](mailto:security@ogenticai.com).

---

## Documentation

- [README](./README.md) &mdash; This file. Install, usage, profiles, FAQ
- [PRD.md](./PRD.md) &mdash; Full product requirements document (data models, API contract, detection pipeline, configuration, testing requirements)
- [CLAUDE.md](./CLAUDE.md) &mdash; Architecture decisions, code patterns, naming conventions, build order
- [CONTRIBUTING.md](./CONTRIBUTING.md) &mdash; How to contribute recognizers, tests, and domain expertise
- [LICENSE](./LICENSE) &mdash; Apache License 2.0

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

The most impactful contributions:

- **New recognizer patterns** for legal, clinical, or financial sensitivity
- **Test cases** for edge cases and false positives/negatives
- **Domain expertise** from lawyers, therapists, financial professionals, or compliance officers
- **Bug reports** with example text and expected vs. actual output
- **New shield profiles** for healthcare, accounting, government, or other regulated domains

### Quick Contribution Guide

1. **Fork** the repository
2. **Create a branch** (`feat/`, `fix/`, `test/`, `docs/`)
3. **Follow the patterns** in [CLAUDE.md](./CLAUDE.md) (recognizer structure, test structure, naming conventions)
4. **Run checks**: `ruff check src/ tests/ && pytest tests/ -v`
5. **Open a PR** against `main`

---

## License

[Apache License 2.0](https://github.com/OgenticAI/ogentic-shield/blob/main/LICENSE)

---

Built by [OgenticAI](https://ogenticai.com). Trust is not a policy &mdash; it's infrastructure.

**Found this useful?** Give us a star to help others discover ogentic-shield.
