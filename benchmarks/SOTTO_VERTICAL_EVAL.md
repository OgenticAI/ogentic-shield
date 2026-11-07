# Sotto Vertical Tier vs. Open-Weights Baselines

Evaluation methodology and reproducibility kit for OGE-447.

## Methodology

- **Task**: Domain-specific sensitive content detection
- **Corpus**: 200 labeled examples per domain (synthetic via generate_eval_corpus.py)
- **Cross-validation**: 10-fold stratified
- **Confidence intervals**: Bootstrap 95% CI (1000 iterations)
- **Baselines**: Llama 3.1, Mistral, Qwen 2.5, Granite 3.1
- **Prompts**: Zero-shot with structured output format

## Legal Privilege

| Model | Precision | Recall | F1 (95% CI) | TP/FP/FN/TN |
|---|---:|---:|---|---|
| _Results will be populated by run_sotto_vertical_eval.py_ | - | - | - | - |

## Therapy PHI

| Model | Precision | Recall | F1 (95% CI) | TP/FP/FN/TN |
|---|---:|---:|---|---|
| _Results will be populated by run_sotto_vertical_eval.py_ | - | - | - | - |

## Finance MNPI

| Model | Precision | Recall | F1 (95% CI) | TP/FP/FN/TN |
|---|---:|---:|---|---|
| _Results will be populated by run_sotto_vertical_eval.py_ | - | - | - | - |

## Aggregate Performance

Weighted average across legal (30%), therapy (35%), finance (35%):

| Model | Avg Precision | Avg Recall | Avg F1 | Domains Won |
|---|---:|---:|---:|---:|
| _Results will be populated by run_sotto_vertical_eval.py_ | - | - | - | - |

## Sotto vs. Best Baseline

| Domain | Sotto F1 | Best Baseline | Model | Delta |
|---|---:|---:|---|---:|
| _Results will be populated by run_sotto_vertical_eval.py_ | - | - | - | - |

## Task Definition

Per profile (legal/clinical/finance), "detected the privileged pattern" means:
- **True Positive (TP)**: At least one expected entity type is among detected types on a positive sample
- **False Positive (FP)**: Any domain-specific entity fires on an explicitly-negative sample
- **False Negative (FN)**: No expected entities detected on a positive sample
- **True Negative (TN)**: No detections on a negative sample

## Evaluation Set

The expanded corpus provides:
- ≥200 examples per profile
- Balanced TPs/TNs/adversarial-negatives
- Full recognizer coverage
- Versioned and committed to the repo

**Note**: Current corpus is synthetically generated via `generate_eval_corpus.py`. Will be replaced with human-curated examples from OGE-397 once available.

## Cross-Validation

Ten-fold stratified cross-validation ensures:
- Robust performance estimates
- Error bars on every reported metric
- Protection against overfitting to specific examples

## Baselines

Minimum comparison set:
- **Llama 3.1 8B** (Meta) — Default open-weights generalist
- **Mistral 7B / 7B-Instruct** (Mistral) — Popular alternative
- **Qwen 2.5 7B / 7B-Instruct** (Alibaba) — Strong on extraction tasks
- **Granite 3.1 8B** (IBM) — Strongest dense alternative to MoE
- **Sotto vertical tier** — granite3.1-moe:1b via Layer 3 (or custom model)

## Prompts

Same zero-shot prompt template across all baselines for apples-to-apples comparison:

### Legal
```
You are a legal privilege detector. Identify attorney-client privileged,
work product, or litigation-sensitive text. Output ONLY valid JSON:
{"detections": [{"category": "<CATEGORY>", "span_text": "<exact text>",
"confidence": <0-1>, "reasoning": "<one sentence>"}]}.
Output {"detections": []} for non-sensitive text.
```

### Clinical
```
You are a clinical PHI detector. Identify protected health information under HIPAA.
Output ONLY valid JSON:
{"detections": [{"category": "<CATEGORY>", "span_text": "<exact text>",
"confidence": <0-1>, "reasoning": "<one sentence>"}]}.
Output {"detections": []} for non-sensitive text.
```

### Finance
```
You are a financial MNPI detector. Identify material non-public information.
Output ONLY valid JSON:
{"detections": [{"category": "<CATEGORY>", "span_text": "<exact text>",
"confidence": <0-1>, "reasoning": "<one sentence>"}]}.
Output {"detections": []} for non-sensitive text.
```

## Scoring

- Uses same precision/recall/F1 logic as `benchmarks/run_benchmarks.py`
- Layer 1+2 numbers from existing benchmark runner
- Per-baseline runner swaps LLM via direct Ollama calls
- Bootstrap confidence intervals via stdlib (no external deps)

## Reproducibility

### Requirements
1. Install ogentic-shield: `pip install -e .`
2. Install and start Ollama: `ollama serve`
3. Pull models:
   ```bash
   ollama pull llama3.1:8b
   ollama pull mistral:7b
   ollama pull mistral:7b-instruct
   ollama pull qwen2.5:7b
   ollama pull qwen2.5:7b-instruct
   ollama pull granite3.1:8b
   ollama pull granite3.1-moe:1b
   ```

### Running the Evaluation
```bash
# Generate corpus (if not present)
python benchmarks/generate_eval_corpus.py

# Run evaluation
python benchmarks/run_sotto_vertical_eval.py

# With output files
python benchmarks/run_sotto_vertical_eval.py \
  --json results.json \
  --md benchmarks/SOTTO_VERTICAL_EVAL.md

# Custom Sotto model
python benchmarks/run_sotto_vertical_eval.py \
  --sotto-model custom-shield:latest
```

### Output Format
- **Markdown**: Human-readable tables with precision/recall/F1 + confidence intervals
- **JSON**: Machine-readable with tp/fp/fn/tn counts + CI bounds

### Verification
The harness commit hash and dataset hash are included in output for exact reproduction:
- Harness: `benchmarks/run_sotto_vertical_eval.py`
- Dataset: `benchmarks/eval_corpus/*.jsonl`

Single command, no hidden state, fully deterministic (fixed random seed).

---
Generated: _Timestamp will be added by run_sotto_vertical_eval.py_