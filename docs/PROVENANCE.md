# OgenticAI — Model Training Data Provenance

**Version:** 0.1.0
**Status:** Draft — pending review by Craig + external counsel before going live
**Ticket:** [OGE-446](https://linear.app/ogenticai/issue/OGE-446)
**Last updated:** 2026-06-27

---

## Overview

This document lists every corpus used to train Sotto-tier models, with source,
license, intake date, and content hash of the version trained on. It is the
on-record receipt for the claim:

> *"Models trained on Sotto-tier corpora improve over time without any customer
> data entering the training loop."*

Buyers' counsel in legal, healthcare, and finance can read this document line by
line to verify that claim independently.

**How to read this document:**

- Each row in the corpus registry covers one discrete dataset used in fine-tuning.
- `sha256` is the hash of the exact archive file ingested into the training
  pipeline. Buyers can request the archive to reproduce the hash.
- `Model versions` lists every Sotto model version whose fine-tuned weights were
  trained on this corpus entry. A new row is added when a corpus is updated or
  replaced.
- This document is updated by the model team when a new fine-tune is kicked off.
  Interim placeholder hashes (`sha256:TBD-<slug>`) are replaced once the corpus
  archive is finalized.

---

## Corpus Registry

### Legal tier (`shield-legal`)

| Corpus | License | Source | Intake date | sha256 | Model versions |
|---|---|---|---|---|---|
| US public court opinions via CourtListener bulk export | CC0 / Public Domain | [courtlistener.com](https://www.courtlistener.com/api/bulk-info/) bulk export 2026-04-15 | 2026-04-15 | `sha256:TBD-courtlistener-2026-04-15` | legal-tier v0.1 |
| Federal Rules of Civil Procedure and Evidence (official text) | Public Domain (US Gov) | [uscourts.gov](https://www.uscourts.gov/rules-policies) | 2026-04-15 | `sha256:TBD-frcp-2026-04-15` | legal-tier v0.1 |
| ABA Model Rules of Professional Conduct | Licensed via ABA institutional agreement | American Bar Association | 2026-04-20 | `sha256:TBD-aba-model-rules-2026-04-20` | legal-tier v0.1 |
| OgenticAI internal legal eval corpus (synthetic + public) | Proprietary — OgenticAI-generated | Internal eval harness | 2026-05-01 | `sha256:TBD-oge-legal-eval-v1` | legal-tier v0.1 |

### Clinical / Therapy tier (`shield-therapy`)

| Corpus | License | Source | Intake date | sha256 | Model versions |
|---|---|---|---|---|---|
| JAMA case reports (de-identified) | Licensed via JAMA institutional license | [jamanetwork.com](https://jamanetwork.com) | 2026-05-01 | `sha256:TBD-jama-cases-2026-05-01` | clinical-tier v0.1 |
| DSM-5-TR clinical vignettes (licensed excerpt) | Licensed via APA institutional agreement | American Psychiatric Association | 2026-05-01 | `sha256:TBD-dsm5tr-vignettes-2026-05-01` | clinical-tier v0.1 |
| MIMIC-III discharge summaries (de-identified, PhysioNet) | PhysioNet Credentialed Health Data License 1.5.0 | [physionet.org/content/mimiciii](https://physionet.org/content/mimiciii/) | 2026-05-10 | `sha256:TBD-mimic-iii-2026-05-10` | clinical-tier v0.1 |
| OgenticAI internal therapy eval corpus (synthetic) | Proprietary — OgenticAI-generated | Internal eval harness | 2026-05-15 | `sha256:TBD-oge-therapy-eval-v1` | clinical-tier v0.1 |

### Finance tier (`shield-finance`)

| Corpus | License | Source | Intake date | sha256 | Model versions |
|---|---|---|---|---|---|
| SEC EDGAR 10-Q / 10-K filings (2015–2025) | Public Domain (US Gov) | [sec.gov/edgar](https://www.sec.gov/cgi-bin/browse-edgar) bulk data | 2026-04-30 | `sha256:TBD-edgar-10q-10k-2026-04-30` | finance-tier v0.1 |
| SEC enforcement actions and administrative proceedings | Public Domain (US Gov) | [sec.gov/litigation](https://www.sec.gov/litigation) | 2026-04-30 | `sha256:TBD-sec-enforcement-2026-04-30` | finance-tier v0.1 |
| FINRA regulatory notices (public) | Public Domain | [finra.org/rules-guidance](https://www.finra.org/rules-guidance/notices) | 2026-05-05 | `sha256:TBD-finra-notices-2026-05-05` | finance-tier v0.1 |
| OgenticAI internal finance eval corpus (synthetic + public) | Proprietary — OgenticAI-generated | Internal eval harness | 2026-05-15 | `sha256:TBD-oge-finance-eval-v1` | finance-tier v0.1 |

---

## Hash verification

To verify a content hash against a corpus archive:

```bash
# Download the archive from the source listed above (or request it from security@ogenticai.com)
sha256sum <archive-file>
# Compare against the sha256 value in the table above
```

Placeholder hashes (`sha256:TBD-*`) are replaced by the model team when the
corresponding corpus archive is finalized and stored in OgenticAI's corpus
registry. The finalized archive is available on request to enterprise customers
under NDA.

---

## Corpus update process

When a corpus is updated or replaced:

1. A new row is added to this document (the old row is **never deleted**).
2. The new row's `sha256` is populated once the archive is finalized.
3. The `Model versions` column of the new row is filled when the fine-tune using
   the new corpus ships.
4. This document is committed in the same PR as the model version bump in
   `CHANGELOG.md`.

---

## What is NOT in these corpora

The following categories of data are explicitly excluded from all Sotto-tier
training corpora, by technical access control and contractual obligation:

- Any data originating from a customer's Sotto Desktop installation
- Any data transmitted by a user's Sotto session (chat, document, clipboard)
- Any customer telemetry (see [`docs/TELEMETRY-POLICY.md`](TELEMETRY-POLICY.md))
- Any data provided by expert annotators that was sourced from customer contexts
  (see [`docs/VERTICAL-EXPERT-FEEDBACK.md`](VERTICAL-EXPERT-FEEDBACK.md))

---

## Contact

Questions about this document: [security@ogenticai.com](mailto:security@ogenticai.com)

Enterprise customers may request corpus archives for independent hash verification
under the terms of their enterprise agreement.
