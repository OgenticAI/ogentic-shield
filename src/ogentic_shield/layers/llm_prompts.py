"""Profile-specific prompt templates for Layer 3.

Every prompt has the same shape:

1. **System frame** — domain framing, definition of what counts as positive
   for the profile, a hard rule that ``category`` must come from the supplied
   allow-list, and an explicit JSON schema reminder.
2. **Few-shot examples** — 3 hand-written examples per profile, freshly
   authored so they don't overlap the labelled benchmark dataset (which is
   what we measure precision against in OGE-314). Each example shows the
   model what *negative* output looks like too — empty ``detections`` list
   for non-sensitive text.
3. **Existing-entity hint** — what regex/NER/rules already found, so the
   model can corroborate or extend rather than re-emit duplicates.

The category allow-lists below mirror :mod:`ogentic_shield.profiles.legal`,
``…therapy``, and ``…finance`` exactly. Keep them in sync — drift would let
the LLM emit categories the scoring engine doesn't understand.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ogentic_shield.layers.llm_schema import LlmResponse
from ogentic_shield.models import CategoryGroup, DetectedEntity

# ── Category → CategoryGroup map ─────────────────────────────────────────────
# The orchestration layer needs this to populate DetectedEntity.category_group
# from the LLM's free-form ``category`` string. Categories not in this map are
# treated as hallucinations and dropped.

CATEGORY_TO_GROUP: dict[str, CategoryGroup] = {
    # shield-legal
    "COUNSEL_COMMUNICATION": CategoryGroup.PRIVILEGE,
    "PRIVILEGE_MARKER": CategoryGroup.PRIVILEGE,
    "WORK_PRODUCT": CategoryGroup.PRIVILEGE,
    "LITIGATION_MARKER": CategoryGroup.PRIVILEGE,
    "SETTLEMENT_TERMS": CategoryGroup.CONFIDENTIAL,
    "CASE_NUMBER": CategoryGroup.CONFIDENTIAL,
    "LAW_FIRM_NAME": CategoryGroup.CONFIDENTIAL,
    "COURT_FILING": CategoryGroup.CONFIDENTIAL,
    "BATES_NUMBER": CategoryGroup.CONFIDENTIAL,
    "EXECUTIVE_NAME": CategoryGroup.PII,
    # shield-therapy
    "PATIENT_NAME": CategoryGroup.PHI,
    "DATE_OF_BIRTH": CategoryGroup.PHI,
    "DIAGNOSIS_CODE": CategoryGroup.PHI,
    "CLINICAL_RISK_FLAG": CategoryGroup.PHI,
    "SESSION_MARKER": CategoryGroup.PHI,
    "INSURANCE_ID": CategoryGroup.PHI,
    "MEDICATION": CategoryGroup.PHI,
    "PROVIDER_NAME": CategoryGroup.PHI,
    "PSYCHOTHERAPY_NOTE_MARKER": CategoryGroup.PHI,
    "SSN": CategoryGroup.PII,
    # shield-finance
    "MNPI_MARKER": CategoryGroup.MNPI,
    "MA_ACTIVITY": CategoryGroup.MNPI,
    "DEAL_VALUE": CategoryGroup.MNPI,
    "INSIDER_MARKER": CategoryGroup.MNPI,
    "FUND_INFORMATION": CategoryGroup.MNPI,
    "LEVERAGE_RATIO": CategoryGroup.MNPI,
    "CARRY_TERMS": CategoryGroup.MNPI,
    "INSTITUTION_NAME": CategoryGroup.CONFIDENTIAL,
    "FINANCIAL_TERMS": CategoryGroup.CONFIDENTIAL,
    "DISTRIBUTION_RESTRICTION": CategoryGroup.CONFIDENTIAL,
}


@dataclass(frozen=True)
class PromptTemplate:
    profile_id: str
    system_frame: str
    few_shot: str
    allowed_categories: tuple[str, ...]


# ── Schema string used by every system frame ─────────────────────────────────
# The Pydantic schema is the contract; pretty-printing it here makes the
# prompt self-documenting for any future maintainer reading the raw text.

_SCHEMA_HINT = json.dumps(LlmResponse.model_json_schema(), indent=2)


_LEGAL_FRAME = """You are a legal-privilege classifier. Decide whether spans of text are
attorney-client privileged, attorney work product, or otherwise legally
sensitive. Be conservative: when a span could be either privileged or routine
business communication, prefer NOT to flag it — false positives are costly.

Allowed categories (use ONLY these strings in `category`):
COUNSEL_COMMUNICATION, PRIVILEGE_MARKER, WORK_PRODUCT, SETTLEMENT_TERMS,
CASE_NUMBER, LAW_FIRM_NAME, LITIGATION_MARKER, COURT_FILING, BATES_NUMBER,
EXECUTIVE_NAME.

Return strictly valid JSON matching this schema:
{schema}

`span_text` MUST be an exact substring of the input. If the text contains
nothing privileged, return {{"detections": []}}.
"""

_LEGAL_FEWSHOT = """Example 1 — privileged (true positive):
INPUT: "From: General Counsel. This memo, prepared at the direction of counsel
in anticipation of pending litigation, summarizes our analysis of the Acme
contract dispute."
OUTPUT:
{"detections": [
  {"category": "COUNSEL_COMMUNICATION", "span_text": "From: General Counsel",
   "confidence": 0.95,
   "reasoning": "Communication originating from in-house counsel."},
  {"category": "WORK_PRODUCT", "span_text": "prepared at the direction of counsel in anticipation of pending litigation",
   "confidence": 0.97,
   "reasoning": "Classic work-product doctrine language."}
]}

Example 2 — routine business with legal vocabulary (true negative):
INPUT: "We need legal sign-off on the new vendor agreement before quarter end —
please loop in procurement."
OUTPUT:
{"detections": []}

Example 3 — settlement detail with confidentiality marker:
INPUT: "Per the confidential settlement, the parties agreed to dismiss the
2024 NDC matter without admission of liability."
OUTPUT:
{"detections": [
  {"category": "SETTLEMENT_TERMS", "span_text": "the confidential settlement, the parties agreed to dismiss the 2024 NDC matter without admission of liability",
   "confidence": 0.9,
   "reasoning": "Confidential settlement terms with explicit non-admission clause."}
]}
"""


_THERAPY_FRAME = """You are a HIPAA PHI classifier for clinical and therapy notes. Identify
spans that are protected health information: patient identifiers, diagnostic
codes, treatment details, psychotherapy process notes, or clinical risk
indicators. Be conservative: ordinary medical vocabulary in non-clinical
contexts (e.g. a wellness blog post) should NOT be flagged.

Allowed categories (use ONLY these strings in `category`):
PATIENT_NAME, DATE_OF_BIRTH, DIAGNOSIS_CODE, CLINICAL_RISK_FLAG,
SESSION_MARKER, INSURANCE_ID, MEDICATION, PROVIDER_NAME,
PSYCHOTHERAPY_NOTE_MARKER, SSN.

Return strictly valid JSON matching this schema:
{schema}

`span_text` MUST be an exact substring of the input. If the text contains no
PHI, return {{"detections": []}}.
"""

_THERAPY_FEWSHOT = """Example 1 — clinical note (true positive):
INPUT: "Session 14 progress: Pt M.K., DOB 04/22/1979, dx F41.1 generalized
anxiety, currently titrating up on escitalopram 20mg."
OUTPUT:
{"detections": [
  {"category": "SESSION_MARKER", "span_text": "Session 14 progress",
   "confidence": 0.92,
   "reasoning": "Numbered session marker — clinical record context."},
  {"category": "DATE_OF_BIRTH", "span_text": "DOB 04/22/1979",
   "confidence": 0.97,
   "reasoning": "Explicit DOB token."},
  {"category": "DIAGNOSIS_CODE", "span_text": "F41.1",
   "confidence": 0.96,
   "reasoning": "ICD-10 anxiety code."},
  {"category": "MEDICATION", "span_text": "escitalopram 20mg",
   "confidence": 0.93,
   "reasoning": "Named medication with dosage in clinical context."}
]}

Example 2 — wellness content with medical words (true negative):
INPUT: "Five lifestyle changes that may help with mild anxiety: regular sleep,
limited caffeine, daily walks, journaling, and time outdoors."
OUTPUT:
{"detections": []}

Example 3 — psychotherapy process note:
INPUT: "Process notes — significant countertransference noticed during the
patient's discussion of paternal estrangement; bracketed for supervision."
OUTPUT:
{"detections": [
  {"category": "PSYCHOTHERAPY_NOTE_MARKER", "span_text": "Process notes",
   "confidence": 0.93,
   "reasoning": "Process-note header is protected under HIPAA's psychotherapy-notes carveout."},
  {"category": "PSYCHOTHERAPY_NOTE_MARKER", "span_text": "countertransference",
   "confidence": 0.9,
   "reasoning": "Therapeutic-process content typical of psychotherapy notes."}
]}
"""


_FINANCE_FRAME = """You are a Material Non-Public Information (MNPI) classifier for financial
communications. Identify spans that disclose non-public deal terms, insider
restrictions, or fund-sensitive information that would be material to an
investor's decision-making. Be conservative: publicly disclosed earnings,
historical market data, or general industry commentary should NOT be flagged.

Allowed categories (use ONLY these strings in `category`):
MNPI_MARKER, MA_ACTIVITY, DEAL_VALUE, LEVERAGE_RATIO, FUND_INFORMATION,
INSTITUTION_NAME, FINANCIAL_TERMS, DISTRIBUTION_RESTRICTION,
INSIDER_MARKER, CARRY_TERMS.

Return strictly valid JSON matching this schema:
{schema}

`span_text` MUST be an exact substring of the input. If the text contains no
MNPI, return {{"detections": []}}.
"""

_FINANCE_FEWSHOT = """Example 1 — pre-announcement deal terms (true positive):
INPUT: "Internal — pending take-private of Helio Industries at $62/share, a
38% premium to last close. Lazard advising; targeting signing next Tuesday."
OUTPUT:
{"detections": [
  {"category": "MA_ACTIVITY", "span_text": "pending take-private of Helio Industries",
   "confidence": 0.95,
   "reasoning": "Unannounced M&A transaction."},
  {"category": "DEAL_VALUE", "span_text": "$62/share, a 38% premium to last close",
   "confidence": 0.93,
   "reasoning": "Specific pre-announcement price and premium."},
  {"category": "INSTITUTION_NAME", "span_text": "Lazard advising",
   "confidence": 0.85,
   "reasoning": "Named advisor on a pre-announcement deal."}
]}

Example 2 — public earnings recap (true negative):
INPUT: "Apple reported Q1 revenue of $119.6B, up 2% YoY, beating consensus by
$1B. Services segment grew 11%."
OUTPUT:
{"detections": []}

Example 3 — fund commitment with restriction language:
INPUT: "Fund VII LP is calling $150M from anchor LPs against the Q3 close;
distribution sheet is internal-only until LPAC sign-off."
OUTPUT:
{"detections": [
  {"category": "FUND_INFORMATION", "span_text": "Fund VII LP is calling $150M from anchor LPs against the Q3 close",
   "confidence": 0.91,
   "reasoning": "Non-public capital-call detail tied to a named fund."},
  {"category": "DISTRIBUTION_RESTRICTION", "span_text": "internal-only until LPAC sign-off",
   "confidence": 0.94,
   "reasoning": "Explicit non-distribution clause pending committee approval."}
]}
"""


PROMPTS: dict[str, PromptTemplate] = {
    "shield-legal": PromptTemplate(
        profile_id="shield-legal",
        system_frame=_LEGAL_FRAME.format(schema=_SCHEMA_HINT),
        few_shot=_LEGAL_FEWSHOT,
        allowed_categories=(
            "COUNSEL_COMMUNICATION",
            "PRIVILEGE_MARKER",
            "WORK_PRODUCT",
            "SETTLEMENT_TERMS",
            "CASE_NUMBER",
            "LAW_FIRM_NAME",
            "LITIGATION_MARKER",
            "COURT_FILING",
            "BATES_NUMBER",
            "EXECUTIVE_NAME",
        ),
    ),
    "shield-therapy": PromptTemplate(
        profile_id="shield-therapy",
        system_frame=_THERAPY_FRAME.format(schema=_SCHEMA_HINT),
        few_shot=_THERAPY_FEWSHOT,
        allowed_categories=(
            "PATIENT_NAME",
            "DATE_OF_BIRTH",
            "DIAGNOSIS_CODE",
            "CLINICAL_RISK_FLAG",
            "SESSION_MARKER",
            "INSURANCE_ID",
            "MEDICATION",
            "PROVIDER_NAME",
            "PSYCHOTHERAPY_NOTE_MARKER",
            "SSN",
        ),
    ),
    "shield-finance": PromptTemplate(
        profile_id="shield-finance",
        system_frame=_FINANCE_FRAME.format(schema=_SCHEMA_HINT),
        few_shot=_FINANCE_FEWSHOT,
        allowed_categories=(
            "MNPI_MARKER",
            "MA_ACTIVITY",
            "DEAL_VALUE",
            "LEVERAGE_RATIO",
            "FUND_INFORMATION",
            "INSTITUTION_NAME",
            "FINANCIAL_TERMS",
            "DISTRIBUTION_RESTRICTION",
            "INSIDER_MARKER",
            "CARRY_TERMS",
        ),
    ),
}


def _summarize_existing(existing_entities: list[DetectedEntity], limit: int = 8) -> str:
    """Compact list of L1+L2 hits to give the model context without leaking the full doc."""
    if not existing_entities:
        return "(none)"
    rows = []
    for entity in existing_entities[:limit]:
        rows.append(
            f"- {entity.category} @ [{entity.start}:{entity.end}] (conf={entity.confidence:.2f})"
        )
    if len(existing_entities) > limit:
        rows.append(f"- … and {len(existing_entities) - limit} more")
    return "\n".join(rows)


def narrow_allowed_categories(
    profile_id: str,
    existing_entities: list[DetectedEntity],
) -> tuple[str, ...]:
    """Compute the per-call allowed-category set for Layer 3 (OGE-396).

    Layer 3 is positioned as a *complementary* classifier: it should propose
    entities for categories the regex / NER layers didn't already cover, not
    re-emit detections in categories L1+L2 handled correctly. Re-emission was
    the dominant precision-tax mode measured in OGE-320 (15–30pp drop across
    profiles, almost entirely from the LLM duplicating `COUNSEL_COMMUNICATION`,
    `WORK_PRODUCT`, `PATIENT_NAME`, etc. that the regex layer already caught).

    Returns the template's full ``allowed_categories`` minus any category that
    already appears in ``existing_entities``. Categories outside the template
    altogether (custom profiles, hallucinated labels) are ignored — the post-
    filter and ``CATEGORY_TO_GROUP`` check in ``layers/llm.py`` handle those.

    Returns an empty tuple if every allowed category is already covered. The
    caller should treat that as "skip the LLM call for this profile" because
    there's nothing left for Layer 3 to add.
    """
    template = PROMPTS.get(profile_id)
    if template is None:
        return ()
    covered = {e.category for e in existing_entities}
    return tuple(cat for cat in template.allowed_categories if cat not in covered)


def build_prompt(
    profile_id: str,
    text: str,
    existing_entities: list[DetectedEntity],
) -> str | None:
    """Assemble the final user-message prompt for ``profile_id``.

    Returns ``None`` if the profile has no prompt template — caller should
    skip the LLM call for that profile. (Custom profiles registered via
    :func:`ogentic_shield.profiles.register_profile` won't have built-in
    prompts; that's by design — Layer 3 stays opt-in for custom domains
    until a prompt is contributed via :pep:`OGE-322`.)

    Returns ``None`` *also* when every category in the profile's allow-list
    is already covered by L1+L2 (OGE-396) — there's no remaining work for
    Layer 3 to do, so we short-circuit before paying the model RTT.
    """
    template = PROMPTS.get(profile_id)
    if template is None:
        return None

    # OGE-396: narrow the allow-list to categories L1+L2 didn't catch.
    narrowed = narrow_allowed_categories(profile_id, existing_entities)
    if not narrowed:
        # L1+L2 already covered every allowed category — Layer 3 has nothing
        # additive to contribute. Caller should skip the LLM call.
        return None

    covered_categories = sorted(
        {e.category for e in existing_entities} & set(template.allowed_categories)
    )
    covered_block = (
        "\n".join(f"- {c}" for c in covered_categories) if covered_categories else "(none)"
    )

    return (
        f"{template.system_frame}\n\n"
        f"{template.few_shot}\n\n"
        f"## Existing Layer 1+2 entities (do not duplicate; corroborate or extend):\n"
        f"{_summarize_existing(existing_entities)}\n\n"
        f"## Categories ALREADY COVERED by Layer 1+2 — do NOT re-emit:\n"
        f"{covered_block}\n\n"
        f"## Allowed categories for THIS call (only emit detections from this set):\n"
        f"{', '.join(narrowed)}\n\n"
        f"If you're unsure whether a span fits a covered category vs an allowed one, "
        f"prefer to return an empty detection list. Layer 1+2 are the source of "
        f"truth for the covered categories above.\n\n"
        f"## INPUT:\n{text}\n\n## OUTPUT:\n"
    )


__all__ = [
    "CATEGORY_TO_GROUP",
    "PROMPTS",
    "PromptTemplate",
    "build_prompt",
    "narrow_allowed_categories",
]
