# Changelog

All notable changes to `ogentic-shield` are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.6.2] - Unreleased

### Fixed

- **SSNs are now detected under `shield-legal` and `shield-finance`.** Only `shield-therapy` (and `shield-therapy-pro`) registered `SsnRecognizer`, so an SSN in legal or financial text passed through with no entity. All built-in profiles now share the same `SsnRecognizer`, and Presidio's validated `US_SSN` recognizer is now requested for every profile (it catches unlabeled space-separated forms such as `412 71 3359`). Labeled and dashed SSNs surface as `SSN`; redaction already maps both types. Detection on the bundled benchmark corpora is unchanged.
- **US phone numbers no longer need a context word.** Presidio's `PhoneRecognizer` scores 0.4 and relies on a context word to clear the 0.5 threshold, but its `call` context word is a spaCy stopword that Presidio filters out, so `call 415-555-0182 today` and `... or (415) 555-0182` were missed entirely. A new `UsPhoneRecognizer` scores 0.6 for numbers in a US phone layout (`415-555-0182`, `(415) 555-0182`, `415.555.0182`, optional `+1`) that `phonenumbers` validates. Bare 10-digit runs, SSNs, dates, ZIP+4 and prefixed IDs such as `INV-415-555-0182` are not matched; bare digit runs still need a context word as before.
- **The CLI no longer corrupts its own output on first run.** With the spaCy model missing, Presidio installed `en_core_web_lg` (~400 MB) at analysis time and pip's progress went to stdout, so `--output json` was unparseable. Shield now never downloads models at runtime: a missing model raises `ModelNotInstalledError` (exported from `ogentic_shield`), and every CLI command exits with code `3` and an actionable message on stderr, leaving stdout empty. The guard covers `analyze`, `test-recognizer`, the MCP server and the HTTP service, which all build their analyzer through one function.
- **Email detection no longer makes a network call.** Presidio's `EmailRecognizer` validated domains with tldextract's default extractor, which fetches the public suffix list over HTTPS on first use. Shield now swaps in `OfflineEmailRecognizer`, which uses tldextract's bundled snapshot with no remote URLs and no disk cache. Analysis is fully offline.

### Added

- **`ogentic-shield models download [--model NAME]`**, the explicit one-time setup step for the spaCy model (default `en_core_web_lg`). spaCy/pip progress goes to stderr. README and PyPI quickstarts use it.

---

## [0.6.1] - 2026-07-23

### Fixed

- **Context-boost rules no longer mint a false entity from their trigger word.** `Rule` gains a `boost_only` flag; the `shield-therapy` rules `therapy-phi-patient-context` and `therapy-medication-diagnosis-boost` now set it. The bare word "patient" is no longer labelled `PATIENT_NAME`, and "medication"/"prescribed" no longer labelled `MEDICATION`. Real patient names and drug names (from `PatientNameRecognizer` / `MedicationRecognizer`) are unaffected and are still confidence-boosted when clinical context is nearby.
- **Name recognizers no longer over-match under case-insensitive matching.** Presidio applies `IGNORECASE` globally, which defeated the `[A-Z]` proper-name capitalisation in `PatientNameRecognizer`, `ProviderNameRecognizer`, and `ExecutiveNameRecognizer` — so `"the patient rested well"`, `"the therapist noted…"`, and `"the CFO reported…"` were mislabelled as names. The name tokens are now wrapped in `(?-i:…)` so they require real capitalisation, while keywords (and ALL-CAPS headers such as `PATIENT:`) stay case-insensitive.

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
