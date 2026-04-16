# ogentic-shield — Product Requirements Document

**Version**: 0.1.0
**Status**: Foundation
**Owner**: David Oladeji, CTO — OgenticAI
**License**: Apache 2.0
**Date**: April 16, 2026

---

## 1. Problem Statement

On February 10, 2026, *US v. Heppner* (S.D.N.Y.) established that public AI tools waive attorney-client privilege. The same reasoning applies to therapist-patient privilege (HIPAA), financial MNPI (SEC/FINRA), and every regulated profession with confidentiality obligations.

30+ million US professionals use AI tools daily. 71% of law firms have no AI policy. 43% of therapists have entered patient data into public AI. There is no open-source tool that detects whether content is privileged, clinically sensitive, or contains material non-public information before it reaches an AI model.

Microsoft Presidio handles general PII (names, SSNs, credit cards). It knows nothing about:
- Attorney-client privilege markers
- Psychotherapy note indicators
- MNPI / insider information signals
- Work product doctrine markers
- HIPAA psychotherapy note protections

`ogentic-shield` fills this gap.

---

## 2. Product Definition

`ogentic-shield` is a Python library and CLI tool that classifies text content for regulatory sensitivity across regulated professions. It extends Microsoft Presidio with domain-specific recognizers for legal privilege, clinical/PHI content, and financial MNPI, then layers a configurable rules engine and optional local LLM classification on top.

It is the extraction of the sensitivity detection engine from the Sotto commercial product into a standalone open-source library.

### 2.1 What It Is
- A Python package (`pip install ogentic-shield`)
- A CLI tool (`ogentic-shield analyze "text..."`)
- An MCP server (`ogentic-shield serve --mcp`)
- A FastAPI server (`ogentic-shield serve --http`)
- A library importable in any Python project

### 2.2 What It Is Not
- Not an LLM. It classifies content; it does not generate responses.
- Not a router. Routing decisions are the consumer's responsibility (see `ogentic-router`).
- Not an audit trail. Logging is the consumer's responsibility (see `ogentic-audit`).
- Not a redaction engine. It identifies what to redact; redaction is `ogentic-redact`'s job.

### 2.3 Design Principles
1. **Fast by default**: Regex + NER layers respond in <50ms. LLM fallback is opt-in.
2. **Offline-first**: Works with zero network access. No cloud APIs required.
3. **Pluggable profiles**: Shield profiles (legal, therapy, finance) are additive and composable.
4. **Deterministic where possible**: Regex and pattern layers produce identical results for identical input.
5. **Presidio-compatible**: Custom recognizers follow Presidio's EntityRecognizer interface.
6. **Zero opinion on routing**: Classify and score. Let the consumer decide what to do.

---

## 3. Data Models

### 3.1 Core Types

```python
from enum import Enum
from dataclasses import dataclass, field

class SensitivityLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class CategoryGroup(str, Enum):
    PRIVILEGE = "PRIVILEGE"      # Attorney-client, work product
    PHI = "PHI"                  # HIPAA protected health information
    MNPI = "MNPI"                # Material non-public information
    PII = "PII"                  # General personally identifiable info
    CONFIDENTIAL = "CONFIDENTIAL"  # General confidentiality markers
    SAFE = "SAFE"                # Explicitly safe / no sensitivity

class DetectionLayer(str, Enum):
    REGEX = "REGEX"              # Layer 1: Pattern matching
    NER = "NER"                  # Layer 1: Presidio NER
    RULES = "RULES"             # Layer 2: Domain rules engine
    LLM = "LLM"                 # Layer 3: Local LLM classification
```

### 3.2 Entity Model

```python
@dataclass
class DetectedEntity:
    text: str                          # The matched text span
    category: str                      # Specific category (e.g., "ATTORNEY_CLIENT_PRIVILEGE")
    category_group: CategoryGroup      # Group for scoring/routing
    confidence: float                  # 0.0 - 1.0
    detection_layer: DetectionLayer    # Which layer detected it
    start: int                         # Character offset start
    end: int                           # Character offset end
    metadata: dict = field(default_factory=dict)  # Layer-specific metadata
```

### 3.3 Analysis Result

```python
@dataclass
class AnalysisResult:
    text_hash: str                     # SHA-256 of input text
    entities: list[DetectedEntity]     # All detected entities, sorted by start position
    score: int                         # 0-100 overall sensitivity score
    sensitivity_level: SensitivityLevel
    category_groups_found: set[CategoryGroup]
    top_category: str | None           # Highest-confidence entity category
    top_confidence: float              # Highest confidence value
    entity_count: int
    processing_time_ms: float          # Total analysis time
    layers_invoked: list[DetectionLayer]  # Which layers actually ran
    profile_ids: list[str]             # Which shield profiles were active
    routing_suggestion: str            # "LOCAL_ONLY" | "REDACT_CLOUD" | "CLOUD_OK" (advisory)
```

### 3.4 Shield Profile

```python
@dataclass
class ShieldProfile:
    id: str                            # e.g., "shield-legal"
    name: str                          # e.g., "Legal Privilege Protection"
    version: str                       # Semver
    description: str
    recognizers: list[EntityRecognizer]  # Presidio-compatible recognizers
    rules: list[Rule]                  # Domain rules
    scoring_weights: dict[CategoryGroup, float]  # How this profile weights categories
    supported_entities: list[str]      # Entity types this profile detects
```

### 3.5 Rule Model

```python
@dataclass
class Rule:
    id: str                            # e.g., "legal-privilege-counsel-communication"
    name: str
    description: str
    pattern: str                       # Regex pattern
    flags: int                         # Regex flags (re.IGNORECASE, etc.)
    category: str                      # Entity category to assign
    category_group: CategoryGroup
    confidence: float                  # Base confidence for this rule
    context_patterns: list[str] = field(default_factory=list)  # Boost confidence if these appear nearby
    context_window: int = 200          # Characters to search for context
    context_confidence_boost: float = 0.05  # How much to boost when context matches
    enabled: bool = True
```

---

## 4. API Contract

### 4.1 Python API

```python
from ogentic_shield import Shield

# Initialize with profiles
shield = Shield(profiles=["shield-legal", "shield-therapy"])

# Analyze text
result: AnalysisResult = shield.analyze(
    "Per our conversation with outside counsel at Davis Polk..."
)

# Access results
print(result.score)                    # 94
print(result.sensitivity_level)        # CRITICAL
print(result.routing_suggestion)       # LOCAL_ONLY
print(result.entities[0].category)     # ATTORNEY_CLIENT_PRIVILEGE
print(result.entities[0].confidence)   # 0.95
print(result.entities[0].text)         # "outside counsel"

# Analyze with options
result = shield.analyze(
    text,
    profiles=["shield-legal"],         # Override profiles for this call
    layers=[DetectionLayer.REGEX, DetectionLayer.NER],  # Skip LLM layer
    min_confidence=0.7,                # Filter low-confidence entities
    include_context=True,              # Include surrounding text in entity metadata
)

# List available profiles
profiles = Shield.list_profiles()

# Get profile details
profile = Shield.get_profile("shield-legal")
print(profile.supported_entities)
```

### 4.2 CLI

```bash
# Analyze text directly
ogentic-shield analyze "Per our conversation with outside counsel..." \
  --profiles shield-legal \
  --output json

# Analyze from file
ogentic-shield analyze --file memo.txt --profiles shield-legal shield-finance

# Analyze from stdin (pipe-friendly)
cat memo.txt | ogentic-shield analyze --profiles shield-legal

# Output formats
ogentic-shield analyze "..." --output json      # Full structured JSON
ogentic-shield analyze "..." --output table     # Human-readable table
ogentic-shield analyze "..." --output summary   # One-line summary

# List profiles
ogentic-shield profiles list

# Profile details
ogentic-shield profiles show shield-legal

# Validate a custom profile
ogentic-shield profiles validate ./my-profile.yaml

# Start MCP server
ogentic-shield serve --mcp --port 3001

# Start HTTP server
ogentic-shield serve --http --port 8080

# Version
ogentic-shield --version
```

### 4.3 CLI Output Examples

**JSON output** (`--output json`):
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
    },
    {
      "text": "Davis Polk",
      "category": "LAW_FIRM_NAME",
      "category_group": "PII",
      "confidence": 0.97,
      "detection_layer": "REGEX",
      "start": 52,
      "end": 62
    }
  ]
}
```

**Table output** (`--output table`):
```
╭──────────────────────────────────────────────────────────╮
│  ogentic-shield v0.1.0 — shield-legal                    │
├──────────────────────────────────────────────────────────┤
│  Score: 94/100  Level: CRITICAL  Route: LOCAL_ONLY       │
│  Entities: 6    Time: 12.4ms    Layers: REGEX, NER       │
├──────────┬──────────────────────────┬────────┬───────────┤
│ Entity   │ Category                 │ Conf.  │ Layer     │
├──────────┼──────────────────────────┼────────┼───────────┤
│ outside… │ COUNSEL_COMMUNICATION    │ 0.93   │ REGEX     │
│ Davis P… │ LAW_FIRM_NAME            │ 0.97   │ REGEX     │
│ SEC inv… │ REGULATORY_INVESTIGATION │ 0.91   │ REGEX     │
│ $4.2M    │ SETTLEMENT_TERMS         │ 0.88   │ REGEX     │
│ 25-cr-0… │ CASE_NUMBER              │ 0.99   │ REGEX     │
│ Williams │ PERSON_NAME              │ 0.82   │ NER       │
╰──────────┴──────────────────────────┴────────┴───────────╯
```

**Summary output** (`--output summary`):
```
CRITICAL (94) | LOCAL_ONLY | 6 entities | PRIVILEGE: COUNSEL_COMMUNICATION (0.93) | 12.4ms
```

### 4.4 MCP Server Tools

When running as an MCP server, expose these tools:

```
analyze_text
  - text: string (required)
  - profiles: string[] (optional, default: all loaded)
  - min_confidence: float (optional, default: 0.5)
  → Returns: AnalysisResult as JSON

list_profiles
  → Returns: array of { id, name, version, description, entity_count }

get_profile
  - profile_id: string (required)
  → Returns: full ShieldProfile as JSON

check_sensitivity
  - text: string (required)
  → Returns: { score: int, level: string, routing_suggestion: string }
  (lightweight version — entities not returned, faster)
```

### 4.5 HTTP API

FastAPI server with OpenAPI docs at `/docs`.

```
POST /v1/analyze
  Body: { "text": "...", "profiles": ["shield-legal"], "min_confidence": 0.5 }
  → 200: AnalysisResult

GET /v1/profiles
  → 200: [{ id, name, version, description }]

GET /v1/profiles/{profile_id}
  → 200: ShieldProfile

POST /v1/check
  Body: { "text": "..." }
  → 200: { score, level, routing_suggestion }

GET /health
  → 200: { status: "ok", version: "0.1.0", profiles_loaded: [...] }
```

---

## 5. Shield Profiles — v0.1.0

### 5.1 shield-legal

**Purpose**: Detect attorney-client privilege, work product, and litigation-sensitive content.

**Recognizers** (Presidio-compatible):

| ID | Entity Type | Method | Example Match |
|---|---|---|---|
| `legal-privilege-communication` | COUNSEL_COMMUNICATION | Regex | "outside counsel", "legal counsel", "in-house counsel" |
| `legal-privilege-marker` | PRIVILEGE_MARKER | Regex | "privileged and confidential", "attorney-client" |
| `legal-work-product` | WORK_PRODUCT | Regex | "attorney work product", "at the direction of counsel", "prepared in anticipation of litigation" |
| `legal-settlement` | SETTLEMENT_TERMS | Regex | "settle for $4.2M", "settlement amount" |
| `legal-case-number` | CASE_NUMBER | Regex | "25-cr-00503", "24-cv-1234" |
| `legal-firm-name` | LAW_FIRM_NAME | Regex | AmLaw 200 firm names (Davis Polk, Kirkland, Skadden, etc.) |
| `legal-litigation-hold` | LITIGATION_MARKER | Regex | "litigation hold", "legal hold", "preservation notice" |
| `legal-court-filing` | COURT_FILING | Regex | "motion to dismiss", "summary judgment", "complaint" |
| `legal-bates-number` | BATES_NUMBER | Regex | "BATES 000123", "DOC-2026-0042" |
| `legal-executive-title` | EXECUTIVE_NAME | Regex + NER | "CEO Williams", "General Counsel Martinez" |

**Scoring weights**:
```yaml
scoring_weights:
  PRIVILEGE: 30
  PII: 15
  CONFIDENTIAL: 10
```

### 5.2 shield-therapy

**Purpose**: Detect HIPAA PHI, psychotherapy note content, and clinical risk indicators.

**Recognizers**:

| ID | Entity Type | Method | Example Match |
|---|---|---|---|
| `therapy-patient-name` | PATIENT_NAME | Regex + NER | "Patient: Jane Doe", "patient Jane D." |
| `therapy-dob` | DATE_OF_BIRTH | Regex | "DOB: 03/15/1988", "DOB 1988-03-15" |
| `therapy-diagnosis-code` | DIAGNOSIS_CODE | Regex | "F33.1", "F41.0", ICD-10 mental health codes |
| `therapy-clinical-risk` | CLINICAL_RISK_FLAG | Regex | "suicidal ideation", "self-harm", "homicidal" |
| `therapy-session-marker` | SESSION_MARKER | Regex | "Session 12", "session notes", "intake assessment" |
| `therapy-insurance-id` | INSURANCE_ID | Regex | "Insurance ID: UHC-8847291", "Member ID" |
| `therapy-medication` | MEDICATION | Regex | Top 50 psychiatric medications + dosages |
| `therapy-provider-name` | PROVIDER_NAME | Regex + NER | "Dr. Martinez", "therapist Sarah" |
| `therapy-ssn` | SSN | Regex | "123-45-6789" |
| `therapy-psychotherapy-note` | PSYCHOTHERAPY_NOTE_MARKER | Regex | "process notes", "countertransference", "therapeutic alliance" |

**Scoring weights**:
```yaml
scoring_weights:
  PHI: 28
  PII: 15
  CONFIDENTIAL: 10
```

### 5.3 shield-finance

**Purpose**: Detect MNPI, deal terms, and fund-sensitive information.

**Recognizers**:

| ID | Entity Type | Method | Example Match |
|---|---|---|---|
| `finance-mnpi-marker` | MNPI_MARKER | Regex | "CONFIDENTIAL", "MATERIAL NON-PUBLIC", "MNPI" |
| `finance-ma-activity` | MA_ACTIVITY | Regex | "acquiring", "merger", "acquisition", "takeover" |
| `finance-deal-value` | DEAL_VALUE | Regex | "$47/share", "$2.1 billion", "$12M commitment" |
| `finance-leverage` | LEVERAGE_RATIO | Regex | "5.2x EBITDA", "3.5x revenue" |
| `finance-fund-info` | FUND_INFORMATION | Regex | "Fund III", "LP allocation", "co-invest" |
| `finance-institution` | INSTITUTION_NAME | Regex | Top 50 banks/PE firms |
| `finance-covenant` | FINANCIAL_TERMS | Regex | "covenant", "DSCR", "term sheet", "waterfall" |
| `finance-restriction` | DISTRIBUTION_RESTRICTION | Regex | "do not distribute", "internal use only" |
| `finance-insider` | INSIDER_MARKER | Regex | "insider", "non-public information", "blackout period" |
| `finance-carry-terms` | CARRY_TERMS | Regex | "20% carry", "reduced carry", "hurdle rate" |

**Scoring weights**:
```yaml
scoring_weights:
  MNPI: 30
  PII: 12
  CONFIDENTIAL: 10
```

---

## 6. Detection Pipeline

Processing order is strict. Each layer runs only if configured and needed.

```
Input Text
    │
    ▼
┌─────────────────────────────────────┐
│ Layer 1: REGEX + NER  (< 50ms)      │
│                                     │
│ • Presidio AnalyzerEngine with      │
│   built-in recognizers (PII)        │
│ • Custom recognizers from active    │
│   shield profiles                   │
│ • All patterns run in parallel      │
│ • Deduplicates overlapping spans    │
│   (longest match wins, then highest │
│   confidence)                       │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Layer 2: RULES ENGINE  (< 10ms)     │
│                                     │
│ • Context-aware rules from profiles │
│ • Boosts confidence when context    │
│   patterns appear near an entity    │
│ • Can promote LOW → MEDIUM → HIGH   │
│   based on co-occurrence            │
│ • Example: "counsel" alone = 0.60   │
│   "counsel" + "privileged" nearby   │
│   = 0.93                            │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Layer 3: LLM CLASSIFICATION (opt-in)│
│ (200-500ms, only for ambiguous)     │
│                                     │
│ • Only runs if:                     │
│   - Explicitly enabled              │
│   - Score is 20-60 (ambiguous zone) │
│   - No PRIVILEGE/MNPI already found │
│ • Sends text to local LLM (Ollama)  │
│ • Structured JSON output            │
│ • Can add entities not caught by    │
│   regex (contextual sensitivity)    │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ SCORING + RESULT                    │
│                                     │
│ • Weighted score per profile        │
│ • Sensitivity level assignment      │
│ • Routing suggestion (advisory)     │
│ • Deduplication + sorting           │
│ • Return AnalysisResult             │
└─────────────────────────────────────┘
```

### 6.1 Overlap Resolution

When multiple recognizers match overlapping spans:
1. Longer span wins over shorter span
2. If same length, higher confidence wins
3. If same confidence, PRIVILEGE > PHI > MNPI > PII > CONFIDENTIAL

### 6.2 Scoring Algorithm

```python
def calculate_score(entities: list[DetectedEntity], profiles: list[ShieldProfile]) -> int:
    if not entities:
        return 0

    # Merge scoring weights from all active profiles
    weights = {}
    for profile in profiles:
        for group, weight in profile.scoring_weights.items():
            weights[group] = max(weights.get(group, 0), weight)

    raw_score = sum(
        weights.get(entity.category_group, 10) * entity.confidence
        for entity in entities
    )

    return min(100, round(raw_score))
```

### 6.3 Routing Suggestion Logic

```python
def suggest_routing(entities, score) -> str:
    has_privilege = any(e.category_group == CategoryGroup.PRIVILEGE for e in entities)
    has_mnpi = any(e.category_group == CategoryGroup.MNPI for e in entities)

    if has_privilege or has_mnpi:
        return "LOCAL_ONLY"

    has_phi = any(e.category_group == CategoryGroup.PHI for e in entities)
    if has_phi or score > 30:
        return "REDACT_CLOUD"

    return "CLOUD_OK"
```

---

## 7. Configuration

### 7.1 Config File (ogentic-shield.yaml)

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
    enabled: false              # Opt-in
    provider: ollama            # Only ollama supported in v0.1
    model: llama3.1:8b          # Small model for classification
    endpoint: http://localhost:11434
    timeout_ms: 5000
    ambiguous_score_range: [20, 60]  # Only invoke LLM in this score range

scoring:
  min_confidence: 0.5           # Drop entities below this
  dedup_strategy: longest_highest  # How to handle overlapping entities

output:
  include_text_hash: true
  include_processing_time: true
  max_entities: 50              # Cap for very large documents

custom_profiles_dir: ./profiles  # Load additional profiles from here
```

### 7.2 Custom Profile Format (YAML)

```yaml
id: shield-my-firm
name: "My Firm Custom Profile"
version: "1.0.0"
description: "Custom recognizers for Smith & Jones LLP"
extends: shield-legal           # Inherit from base profile

recognizers:
  - id: custom-client-names
    entity_type: CLIENT_NAME
    category_group: PII
    method: regex
    patterns:
      - "Acme Corp(oration)?"
      - "Johnson Family Trust"
      - "Meridian Holdings"
    confidence: 0.95
    context_patterns:
      - "client"
      - "matter"
      - "engagement"

rules:
  - id: custom-matter-numbers
    pattern: "SM&J-\\d{4}-\\d{3}"
    category: MATTER_NUMBER
    category_group: PII
    confidence: 0.99

scoring_weights:
  PII: 20   # Override: we weight PII higher for our firm
```

---

## 8. Testing Requirements

### 8.1 Unit Tests

Every recognizer must have:
- At least 3 true positive test cases
- At least 2 true negative test cases (things it should NOT match)
- Edge cases (partial matches, case variations, Unicode)

Every profile must have:
- An integration test analyzing a realistic multi-paragraph text
- Verified entity count, categories, and confidence ranges
- Verified scoring output
- Verified routing suggestion

### 8.2 Benchmark Tests

A `benchmarks/` directory with:
- `legal_privilege.jsonl`: 50+ labeled examples of privileged vs. non-privileged text
- `therapy_phi.jsonl`: 50+ labeled examples of PHI vs. non-PHI text
- `finance_mnpi.jsonl`: 50+ labeled examples of MNPI vs. non-MNPI text

Each line: `{"text": "...", "expected_entities": [...], "expected_level": "HIGH"}`

Benchmark runner reports: precision, recall, F1 per category, per profile.

### 8.3 Performance Tests

- Layer 1 (regex + NER) must complete in <50ms for text under 5,000 characters
- Layer 2 (rules) must complete in <10ms
- Full pipeline (without LLM) must complete in <100ms
- Memory usage must stay under 200MB with all profiles loaded

---

## 9. Packaging & Distribution

### 9.1 Python Package

```
Package name:     ogentic-shield
PyPI:             pip install ogentic-shield
Min Python:       3.10
Dependencies:     presidio-analyzer, presidio-anonymizer, pyyaml, click, rich, pydantic
Optional deps:    fastapi, uvicorn (for HTTP server), mcp (for MCP server), ollama (for LLM layer)
Entry point:      ogentic-shield (CLI)
```

### 9.2 Docker

```dockerfile
FROM python:3.12-slim
RUN pip install ogentic-shield[server]
EXPOSE 8080
CMD ["ogentic-shield", "serve", "--http", "--port", "8080"]
```

### 9.3 Installation Groups

```
pip install ogentic-shield              # Core library + CLI
pip install ogentic-shield[server]      # + FastAPI HTTP server
pip install ogentic-shield[mcp]         # + MCP server
pip install ogentic-shield[llm]         # + Ollama LLM layer
pip install ogentic-shield[all]         # Everything
```

---

## 10. v0.1.0 Scope (What Ships First)

### In Scope
- Core Shield class with analyze() method
- Layer 1: Presidio + custom recognizers (regex-based)
- Layer 2: Rules engine with context boosting
- shield-legal profile (10 recognizers)
- shield-therapy profile (10 recognizers)
- shield-finance profile (10 recognizers)
- Scoring algorithm with configurable weights
- Routing suggestion (advisory, not enforcement)
- CLI with analyze, profiles, and --output json/table/summary
- YAML config file support
- Custom profile loading from YAML
- Unit tests for all recognizers (3+ positive, 2+ negative each)
- Integration tests per profile
- Benchmark test harness + initial datasets (10 examples each)
- README with usage examples
- Apache 2.0 license

### Out of Scope (v0.2+)
- LLM classification layer (Layer 3) — requires Ollama integration
- MCP server mode — requires mcp package
- HTTP API server — requires FastAPI
- Rust crate / Node.js package
- Document processing (PDF/DOCX) — that's ogentic-redact's job
- Redaction — that's ogentic-redact
- Audit logging — that's ogentic-audit
- Performance benchmarking suite
- CI/CD pipeline
- Docker image
- PyPI publishing

---

## 11. Success Metrics (v0.1.0)

| Metric | Target |
|---|---|
| Precision on legal privilege detection | ≥ 90% |
| Precision on PHI detection | ≥ 92% |
| Precision on MNPI detection | ≥ 88% |
| False positive rate (safe text flagged) | ≤ 5% |
| Analysis time (text < 5K chars, no LLM) | < 100ms |
| Test coverage | ≥ 85% |
| All recognizers have ≥ 5 test cases | 100% |
