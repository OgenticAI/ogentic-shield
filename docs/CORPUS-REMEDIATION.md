# Corpus Remediation Playbook

**Version:** 0.1.0
**Status:** Draft — pending review by Craig + external counsel before going live
**Ticket:** [OGE-446](https://linear.app/ogenticai/issue/OGE-446)
**Last updated:** 2026-06-27

---

## Overview

This playbook defines OgenticAI's response process when a training corpus used
in Sotto-tier model fine-tuning is found to have been scraped without
authorization, contaminated, or improperly licensed. It follows the same
severity-graded, time-bounded pattern as a CVE response.

The playbook exists because "we promise we'll deal with problems" loses
regulated-industry deals. "Here is the documented procedure that runs when
problems happen" wins them.

---

## Trigger conditions

This playbook is activated when any of the following is confirmed:

1. **Unauthorized scraping**: A corpus previously believed to be licensed or
   public domain is found to contain content scraped without authorization.
2. **License violation**: A corpus license is found to be incompatible with
   commercial use, or the license terms were misrepresented by the supplier.
3. **Data contamination**: A corpus is found to contain customer-origin data,
   personally identifiable information beyond what was disclosed, or content
   whose inclusion violates a third party's rights.
4. **Improper chain-of-custody**: A corpus's provenance metadata is found to be
   inaccurate or unverifiable.
5. **External notification**: OgenticAI receives a credible notice (DMCA,
   legal demand, security researcher report) alleging that a corpus in use
   violates a third party's rights.

---

## Severity classification

| Severity | Definition | Target response time |
|---|---|---|
| **Critical** | Customer-origin data confirmed in training corpus | 24 hours to public notice, 30 days to clean weights |
| **High** | Unauthorized scraping or license violation confirmed | 72 hours to public notice, 30 days to clean weights |
| **Medium** | Probable violation under investigation | 7 days to preliminary notice, 60 days to resolution |
| **Low** | Minor provenance metadata inaccuracy, no rights violation | 30 days to corrected provenance document |

---

## Playbook steps

### Step 1 — Identification

**Owner**: Model team + CTO

**Actions**:

1. Identify the affected corpus entry in `docs/PROVENANCE.md` (by `sha256` hash
   and corpus name).
2. List every model version trained on that corpus (from the `Model versions`
   column in `docs/PROVENANCE.md`).
3. Characterize the nature of the violation:
   - What content categories are potentially affected?
   - What is the scope (entire corpus vs. subset)?
   - Is there evidence that the affected content influenced model behavior in
     a measurable way?
4. Assign a severity level (Critical / High / Medium / Low) per the table above.
5. Open an internal incident ticket in Linear (prefix: `INCIDENT-`), linked to
   this playbook.
6. Notify legal@ogenticai.com and security@ogenticai.com.

**Output**: Incident ticket with affected corpus, affected model versions,
severity, and initial scope assessment.

---

### Step 2 — Public notice

**Owner**: CTO

**Actions**:

1. Publish a notice at `ogenticai.com/policies/incidents/<incident-id>` with
   the following information:
   - Date notice was published
   - Affected corpus name (from `docs/PROVENANCE.md`)
   - Affected model versions
   - Nature of the issue (what was wrong, how it was discovered)
   - What OgenticAI is doing about it (remediation plan, timeline)
   - How affected users will be notified (see Step 4)
2. Post the notice with the same prominence as a security advisory (pinned to
   the OgenticAI status page and linked from the Sotto Desktop release notes).
3. Update `docs/PROVENANCE.md` to add a `Remediation` column entry for the
   affected row, linking to the incident notice.

**Timeline**: Per severity table above (24–72 hours for Critical/High).

---

### Step 3 — Remediation

**Owner**: Model team

**Actions**:

1. Remove the affected corpus from the training pipeline immediately.
2. Identify a replacement corpus (licensed, public domain, or synthetic) that
   covers the same domain without the violation.
3. Retrain or fine-tune on the clean corpus. Timeline target:
   - **Critical/High**: clean weights shipped within 30 days of Step 1
   - **Medium**: clean weights shipped within 60 days
4. The replacement corpus is added as a new row in `docs/PROVENANCE.md`. The
   affected row is annotated with `Status: Remediated — see incident-<id>`.
5. The clean model version is assigned a new version number. The version bump
   is documented in `CHANGELOG.md` with a reference to the incident.
6. The clean weights are published to the Sotto Desktop update channel (see
   Step 4).

---

### Step 4 — Disclosure to affected users

**Owner**: Engineering + CTO

**Actions**:

1. The Sotto Desktop update channel can carry a **notice payload** in addition
   to model weights. The notice payload surfaces in the Sotto Desktop UI the
   next time a user launches the app after downloading the update.
2. For Critical and High severity incidents, the notice payload is required and
   must include:
   - A plain-language description of the issue
   - A link to the public notice at `ogenticai.com/policies/incidents/<id>`
   - A statement that the clean model has been deployed and is now running
3. For enterprise customers, OgenticAI will additionally:
   - Send a direct email notification to the enterprise contact on file within
     48 hours of the public notice (Critical/High)
   - Offer a signed attestation letter on request

---

## Synthetic sample incident (illustrative)

**Incident ID**: INCIDENT-0001 (synthetic — for illustration only)

**Date opened**: 2026-08-15 (hypothetical)

**Affected corpus**: "Legal commentary — miscellaneous" (hypothetical — not a
real corpus in `docs/PROVENANCE.md`)

**Affected model versions**: legal-tier v0.3 (hypothetical)

**Nature of issue**: A corpus supplier represented a dataset as containing only
public domain legal commentary. A security researcher notified OgenticAI that
a subset (~3% of the dataset by token count) appeared to be scraped from a
subscription-only legal database without authorization.

**Severity**: High

**Step 1 — Identification** (2026-08-15):
- Corpus identified, model version legal-tier v0.3 confirmed as affected
- Severity assessed as High (unauthorized scraping, no customer-origin data)
- Internal incident ticket INCIDENT-0001 opened
- legal@ogenticai.com and security@ogenticai.com notified

**Step 2 — Public notice** (2026-08-17, within 72 hours):
- Notice published at `ogenticai.com/policies/incidents/incident-0001`
- Notice pinned to status page
- `docs/PROVENANCE.md` updated with `Status: Remediated — see incident-0001`

**Step 3 — Remediation** (completed 2026-09-10, within 30 days):
- Affected corpus removed from training pipeline
- Replacement: equivalent coverage from CourtListener (CC0) + OgenticAI
  synthetic examples
- Retrained: legal-tier v0.4 shipped with clean corpus
- `CHANGELOG.md` updated with reference to incident-0001

**Step 4 — Disclosure to affected users** (2026-09-10):
- Sotto Desktop update channel carried notice payload with legal-tier v0.4
- Notice displayed to all users on next launch
- Enterprise customers notified by email on 2026-08-18

**Outcome**: Resolved. legal-tier v0.3 weights removed from update channel.
Users still running v0.3 receive a forced-upgrade notice on next launch.

---

## Contact

To report a potential corpus issue:
[security@ogenticai.com](mailto:security@ogenticai.com)

For legal questions about this policy:
[legal@ogenticai.com](mailto:legal@ogenticai.com)
