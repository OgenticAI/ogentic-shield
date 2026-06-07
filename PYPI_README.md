# ogentic-shield

**Regulatory sensitivity detection for legal privilege, clinical PHI, and financial MNPI.**

[![PyPI](https://img.shields.io/pypi/v/ogentic-shield)](https://pypi.org/project/ogentic-shield/)
[![Python](https://img.shields.io/pypi/pyversions/ogentic-shield)](https://pypi.org/project/ogentic-shield/)
[![License](https://img.shields.io/badge/license-Apache_2.0-blue)](https://github.com/OgenticAI/ogentic-shield/blob/main/LICENSE)

`ogentic-shield` classifies whether a piece of text — or a whole document —
contains content that shouldn't leave a regulated boundary. Attorney-client
privilege. HIPAA-protected clinical content. Material non-public financial
information. The long tail of PII. It returns a structured `AnalysisResult`
(score, category groups, detected entities, suggested routing) and can
redact masked tokens back into plaintext after a round-trip through an
external LLM.

Built for the legal, clinical, and financial AI workflows where the wrong
default is "ship the prompt to OpenAI and hope."

## Why this exists

On February 10, 2026, *US v. Heppner* (S.D.N.Y.) established that sending
privileged content through a third-party AI tool can constitute waiver.
The guardrail every regulated org now needs — **classify before you call** —
didn't exist as an OSS primitive. Shield is that primitive.

## Install

```bash
pip install ogentic-shield                # core (Layer 1 + 2)
pip install 'ogentic-shield[llm]'         # + Layer 3 (Ollama-backed disambiguation)
pip install 'ogentic-shield[mcp]'         # + MCP server (Claude Desktop / Goose / Cursor)
pip install 'ogentic-shield[server]'      # + FastAPI HTTP surface
pip install 'ogentic-shield[all]'         # everything
```

> Layer 1 + 2 require the spaCy `en_core_web_lg` model:
> `python -m spacy download en_core_web_lg`

## 30-second example

```python
from ogentic_shield import Shield

shield = Shield(profiles=["shield-legal"])

# Text-level analysis
result = shield.analyze(
    "Privileged attorney-client memo: do not disclose to opposing counsel."
)
print(result.score)                  # 0..100 sensitivity score
print(result.category_groups_found)  # {CategoryGroup.PRIVILEGE}
print(result.routing_suggestion)     # "local_only"

# Document-level redaction (v0.4.0+)
redacted = shield.redact_document("memo.txt")
print(redacted.redacted_text)        # entities replaced with deterministic tokens
print(redacted.mapping.tokens)       # token -> original, for round-trip after LLM
```

The full API — profiles, layers, calibration, redaction, async, MCP,
HTTP server, document analysis — is documented on GitHub. **See the
[README on GitHub](https://github.com/OgenticAI/ogentic-shield#readme)
for the complete reference.**

## What's in the box

- **Three-layer detection** — fast regex (Layer 1) → spaCy NER (Layer 2)
  → optional local-LLM disambiguation (Layer 3). Each layer adds precision
  without surrendering recall.
- **Profile-driven** — `shield-legal`, `shield-finance`, `shield-healthcare`,
  custom. Profiles define which categories to flag and at what threshold.
- **Documents API** — `Shield.analyze_document()` and `Shield.redact_document()`
  handle `.txt` / `.md` / `.log` today; PDF / DOCX / XLSX / EML / MSG /
  HTML on the roadmap.
- **Token-preserving redaction** — `Shield.redact()` and the new
  `Shield.redact_document()` substitute entities with deterministic
  `[Label_abc123]` tokens. Pair with `unredact_text()` to restore
  originals after a round-trip through OpenAI / Anthropic / Ollama.
- **MCP server** — `ogentic-shield --mcp` exposes Shield as an MCP tool
  surface (`shield.analyze`, `shield.profiles`, `shield.calibration`).
  Claude Desktop, Goose, and Cursor all work out of the box.
- **Privacy-first** — runs entirely in-process. No telemetry, no
  Ogentic-hosted infra. The audit row Shield emits is shape-only
  (hashes, scores, category names) — never the prompt text itself.

## Part of a stack

`ogentic-shield` is the classification leg of the OgenticAI privacy-routing
stack:

```
ogentic-shield  →  ogentic-router  →  ogentic-audit
   (classify)        (route)            (forensic log)
```

Together they form the open-source foundation for
[Sotto](https://sottotrust.ai/), OgenticAI's commercial product for
regulated professionals.

## Links

- **Full README + API reference:** https://github.com/OgenticAI/ogentic-shield#readme
- **Issues / discussion:** https://github.com/OgenticAI/ogentic-shield/issues
- **Release notes:** https://github.com/OgenticAI/ogentic-shield/releases
- **Apache 2.0 license:** https://github.com/OgenticAI/ogentic-shield/blob/main/LICENSE
