# Changelog

All notable changes to `ogentic-shield` are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Fixed

- **Context-boost rules no longer mint a false entity from their trigger word.** `Rule` gains a `boost_only` flag; the `shield-therapy` rules `therapy-phi-patient-context` and `therapy-medication-diagnosis-boost` now set it. The bare word "patient" is no longer labelled `PATIENT_NAME`, and "medication"/"prescribed" no longer labelled `MEDICATION`. Real patient names and drug names (from `PatientNameRecognizer` / `MedicationRecognizer`) are unaffected and are still confidence-boosted when clinical context is nearby.

---

## [0.6.0] - 2026-07-22

### Added

- **Configurable NER spaCy model** via `ShieldConfig.ner_model` (default `en_core_web_lg`; loaded from `layers.ner_model` in YAML). `en_core_web_sm` runs the pipeline at **~165 MB vs ~780 MB** (~4.8×) with identical detection on the regulated profiles — the lever for serverless / small-container / free-tier deployments. (#54, OGE-1743)
- **Shield `/analyze` HTTP service** under `deploy/` — a thin FastAPI wrapper over the pipeline, Dockerfile + `railway.json` for any container host. Reads `SHIELD_NER_MODEL` / `SHIELD_PROFILES` from env. (#48/#49, OGE-1433)

### Fixed

- **NER analyzer is now cached** per `(model, profiles)` instead of rebuilt on every `analyze()` call. Previously the spaCy model reloaded per request, which added seconds of latency and, under concurrency, multiplied the model in RAM until the process OOM-crashed. First call pays the load; subsequent calls are ~ms. (#54, OGE-1743)

---

## [0.5.0] - 2026-06-24

### Added

- `Shield.classify_batch(texts: list[str], *, profile: str | None = None) -> list[AnalysisResult | BatchItemError]` — convenience API for analysing multiple texts in a single call. Per-item errors are captured as `BatchItemError` objects so a single bad input does not abort the whole batch. Empty-list input returns `[]` immediately. (#42, OGE-1057)

### Fixed

- Bumped `mypy>=1.13` minimum to accept numpy 2.x PEP 695 `type X = ...` stub syntax during type-checking. Runtime behaviour is unchanged; `requires-python` stays at `>=3.10`. (#37, OGE-1029)

---

## [0.4.0] - 2026-05-01

_Initial public release on PyPI. Layers 1 and 2 (regex + NER, context-aware rules) fully operational across `shield-legal`, `shield-therapy`, and `shield-finance` profiles. Layer 3 (LLM) shipped as an opt-in stub requiring a local Ollama instance._

---
