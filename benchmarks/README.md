# ogentic-shield benchmarks

Labelled JSONL datasets + a runner that reports per-recognizer
precision/recall/F1, per-profile aggregates, and timing distributions.

## Layout

```
benchmarks/
├── legal_privilege.jsonl    # 233 examples (147 TP + 41 TN + 45 adversarial)
├── therapy_phi.jsonl        # 215 examples (129 TP + 41 TN + 45 adversarial)
├── finance_mnpi.jsonl       # 212 examples (126 TP + 41 TN + 45 adversarial)
├── therapy_phi_pro.jsonl    # 215 examples (130 TP + 40 TN + 45 adversarial)
├── run_benchmarks.py        # The runner
├── fit_calibration.py       # Calibration fitting script
├── validate_corpus.py       # Corpus validation script
└── README.md                # This file
```

## JSONL schema

Each line is a JSON object:

```json
{
  "id": "legal-tp-01",
  "text": "Privileged & confidential — outside counsel reviewed ...",
  "expected_entities": [{"type": "PRIVILEGE_MARKER"}, {"type": "COUNSEL_COMMUNICATION"}],
  "expected_level": "CRITICAL",
  "category": "true_positive",
  "notes": "Canonical privileged email"
}
```

| Field | Meaning |
|---|---|
| `id` | Stable identifier (used in reports) |
| `text` | Input string passed to `Shield.analyze` |
| `expected_entities` | List of `{type}` dicts. For TPs, at least one of these MUST be detected. Optional `start` / `end` for span-level grading (currently unused). |
| `expected_level` | `NONE` / `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` |
| `category` | `true_positive` (must trigger) / `true_negative` (must not trigger) / `adversarial_negative` (tricky case that must not trigger) |
| `notes` | Free-text rationale |

## Running

```bash
# Run every dataset
python benchmarks/run_benchmarks.py

# Run a single dataset
python benchmarks/run_benchmarks.py --dataset legal_privilege

# Save a machine-readable JSON report
python benchmarks/run_benchmarks.py --json /tmp/bench.json

# Strict mode — exit 1 if precision / performance targets are missed
python benchmarks/run_benchmarks.py --strict
```

## Scoring rules

- **True positive**: `category=true_positive` AND ≥1 expected entity type was
  detected → counts toward TP.
- **False negative**: `category=true_positive` AND no expected entity type was
  detected → counts toward FN.
- **False positive**: `category=true_negative` or `adversarial_negative` AND
  any **domain-specific** entity was detected → counts toward FP. Generic
  Presidio types (PERSON, EMAIL_ADDRESS, PHONE_NUMBER, US_SSN, etc.) are
  filtered out — they fire on every text and aren't what the shield
  profiles are testing.
- **True negative**: `category=true_negative` or `adversarial_negative` AND
  no domain-specific entity was detected → counts toward TN.
- **Latency**: each `Shield.analyze` call is wrapped with
  `time.perf_counter()`. A warmup call runs first so spaCy's lazy-load
  cost doesn't inflate the median.

Per-recognizer counts include hits regardless of `category` so reviewers
can see whether each individual recognizer is precise / recall-y on its
own slice of the dataset.

## Targets (PRD §8)

| Profile | Precision target | Performance target |
|---|---|---|
| `shield-legal` | ≥90% | median <100ms |
| `shield-therapy` | ≥92% | median <100ms |
| `shield-finance` | ≥88% | median <100ms |

These are **aspirational** for v0.1.0. The runner emits a green/red flag per
target; the runner is informational by default (exit 0) so CI doesn't gate
v0.1.0 on aspirational metrics. Use `--strict` in CI once the targets are
consistently met.

## Current state (v0.1.0)

Targets not yet met across all three profiles. Specific gaps captured by
the runner:

- **shield-legal**: ~85% precision. Remaining FPs are `PRIVILEGE_MARKER`
  on adversarial use of "privilege" as a verb, and `SETTLEMENT_TERMS`
  on accounting "settlement of accounts." Tightening the regexes / context
  windows will close the gap.
- **shield-therapy**: ~85% precision. `DIAGNOSIS_CODE` fires on contexts
  that don't carry PHI (research/educational text). `SESSION_MARKER` and
  `PSYCHOTHERAPY_NOTE_INDICATOR` recall is below target — patterns need
  to be more permissive.
- **shield-finance**: ~75% precision. `MNPI_MARKER` and `INSIDER_MARKER`
  catch the word "Confidential" / "Insider information" in non-MNPI
  contexts. Tightening to require co-occurrence with deal/security
  language will help.
- **Performance**: median ~700ms vs 100ms target. Cost is spaCy
  `en_core_web_lg` NER on every text. Future optimisations: skip NER
  when no regex layer matches, or run NER only on long texts.

These are tracked as v0.1.x improvement work — the runner exists to
measure progress.

## Adding a new example

1. Pick the right dataset file based on which profile should detect it.
2. Append a JSON line with the schema above.
3. Set `category` honestly:
   - `true_positive` if the engine SHOULD detect at least one of the listed
     entity types.
   - `true_negative` if the input is benign and no domain-specific
     detection should fire.
   - `adversarial_negative` if the input is intentionally tricky (false-
     positive trap).
4. Re-run the benchmark to confirm the example behaves as expected.

## Adding a new dataset

1. Create `benchmarks/<name>.jsonl` with 20+ examples.
2. Add an entry to the `DATASETS` list in `run_benchmarks.py`:
   ```python
   {
     "name": "<name>",
     "jsonl": BENCHMARKS_DIR / "<name>.jsonl",
     "profile_id": "<profile-id>",
     "precision_target": 0.XX,
   }
   ```
3. Document targets in this README.

## Sotto Vertical Evaluation

The `run_sotto_vertical_eval.py` script compares ogentic-shield with Sotto vertical
tier models against open-weights baselines on an expanded evaluation corpus:

```bash
# Generate expanded corpus (200+ examples per domain)
python benchmarks/generate_eval_corpus.py

# Run evaluation (requires Ollama with models pulled)
python benchmarks/run_sotto_vertical_eval.py

# Write results to files
python benchmarks/run_sotto_vertical_eval.py \
  --json results.json \
  --md benchmarks/SOTTO_VERTICAL_EVAL.md

# Use custom Sotto model
python benchmarks/run_sotto_vertical_eval.py \
  --sotto-model granite3.1-moe:3b
```

### Features
- **10-fold stratified cross-validation** for robust metrics
- **Bootstrap 95% confidence intervals** on all F1 scores
- **Zero-shot prompting** with consistent format across models
- **Automatic corpus generation** if not present
- **Skip-on-missing** for models not pulled locally

### Baselines
- Llama 3.1 8B
- Mistral 7B / 7B-Instruct
- Qwen 2.5 7B / 7B-Instruct
- Granite 3.1 8B
- Sotto vertical tier (granite3.1-moe:1b or custom)

See `benchmarks/SOTTO_VERTICAL_EVAL.md` for full methodology and reproducibility instructions.
