# Changelog

All notable changes to `ogentic-shield` are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
