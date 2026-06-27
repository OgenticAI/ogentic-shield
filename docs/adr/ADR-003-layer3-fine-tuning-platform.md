# ADR-003: Layer 3 Fine-Tuning Platform Selection

**Status:** PENDING — decision gate after Phase 1 bake-off
**Ticket:** [OGE-794](https://linear.app/ogenticai/issue/OGE-794)
**Date:** TBD (after 2-week bake-off, ~2026-07)
**Author:** TBD (David, after reviewing bake-off results)

---

## Context

[OGE-313](https://linear.app/ogenticai/issue/OGE-313) shipped an Ollama-based zero-shot
Layer 3 classifier. [OGE-320](https://linear.app/ogenticai/issue/OGE-320) measured that
zero-shot Layer 3 degrades precision by 15–30pp vs the L1+L2 baseline across all three
shield profiles (legal privilege, therapy PHI, finance MNPI).

A LoRA fine-tuned small model (Qwen3 ~8B class) trained on the shield evaluation corpus
is the next precision lever. The fine-tuned model would be served remotely (not via
localhost Ollama), complementing rather than replacing the local path.

Two platforms were shortlisted after evaluating Together AI, Fireworks, Factory.ai,
and Atherial (see `docs/vendor-eval-together-atherial-factory.md`):

- **Together AI** — default candidate; LoRA + serverless inference, SOC2 Type II,
  HIPAA-aligned options, regional data residency, integrated train-and-serve API.
- **Fireworks AI** — closest peer; reportedly fastest iteration, same ~$0.48–0.50/M
  training cost for 8B models.

---

## Decision drivers

1. **Precision/recall on the shield eval corpus** — does fine-tuning close the
   15–30pp precision gap vs L1+L2 on legal privilege, therapy PHI, and finance MNPI?
2. **p95 inference latency** — target: under 500ms per call (remote endpoint is more
   lenient than the 100ms local target).
3. **Training cost** — Phase 1 budget guardrail: $500 total across both platforms.
4. **Training UX** — job submission, monitoring, iteration speed, error ergonomics.
5. **LoRA serving ergonomics** — can the platform serve multiple LoRA adapters
   (one per shield profile) without excessive overhead or separate deployments?
6. **Compliance alignment** — SOC2, HIPAA-aligned options, data residency for
   shield's enterprise customers.

---

## Options evaluated

### Option A: Together AI

| Criterion | Notes |
|---|---|
| Precision (eval corpus) | TBD — measure with `eval_finetuned.py --provider together` |
| p95 inference latency | TBD |
| Training cost | TBD — use Together's cost estimator pre-run |
| Training UX | REST API, web dashboard, checkpoint resume, upfront cost estimate |
| LoRA serving | Per-request LoRA adapter loading; dedicated endpoint option |
| Compliance | SOC2 Type II, HIPAA BAA available, NA/EU/Asia data residency |

### Option B: Fireworks AI

| Criterion | Notes |
|---|---|
| Precision (eval corpus) | TBD — measure with `eval_finetuned.py --provider fireworks` |
| p95 inference latency | TBD |
| Training cost | TBD |
| Training UX | REST API, reportedly fastest iteration in class |
| LoRA serving | Per-request LoRA adapter loading; shared inference pool |
| Compliance | SOC2 (check HIPAA BAA availability) |

---

## Decision criteria table (fill in after bake-off)

| Criterion | Weight | Together AI score | Fireworks score |
|---|:---:|:---:|:---:|
| Precision improvement (vs L1+L2 baseline) | 35% | — | — |
| p95 latency <= 500ms | 25% | — | — |
| Total training cost within $500 | 15% | — | — |
| LoRA serving ergonomics (multi-profile) | 15% | — | — |
| Compliance (SOC2 + HIPAA BAA) | 10% | — | — |
| **Weighted total** | 100% | — | — |

Score each criterion 1–5, multiply by weight, sum for weighted total.

---

## Outcome

**Decision:** [PENDING]

**Rationale:** [PENDING — fill in after bake-off results are available from
`eval_finetuned.py --json bakeoff_results.json`]

**Winner platform:** [PENDING]

---

## Consequences

**If Together AI wins:**
- Phase 2 issue: wire Together AI inference into Layer 3 behind a feature flag
- Add `together` provider to `layers/llm_client.py` (parallel to `OllamaClient`)
- Add `TOGETHER_API_KEY` to the deployment secrets
- Per-profile LoRA adapters: evaluate whether per-profile LoRA is worth the
  additional cost vs a single combined adapter

**If Fireworks wins:**
- Same as above but with Fireworks endpoint and `FIREWORKS_API_KEY`
- Verify HIPAA BAA availability before production use with PHI data

**Either way:**
- The localhost Ollama path (AD-07 contract) is preserved as the default
  (`llm.enabled: false`). Remote fine-tuned inference is opt-in via config.
- Phase 3 (distilling factory agent logs) evaluates the same platform for
  tool-calling fine-tuning — winning platform gets first consideration.

---

## References

- OGE-313: Ollama Layer 3 integration
- OGE-320: MoE model benchmarks (zero-shot baselines)
- OGE-396: Prompt narrowing mitigation
- OGE-794: This bake-off (Phase 0 + 1)
- `docs/vendor-eval-together-atherial-factory.md`: Full vendor evaluation
- `benchmarks/generate_eval_corpus.py`: Phase 0 eval set generator
- `benchmarks/bakeoff/`: Phase 1 bake-off scripts
