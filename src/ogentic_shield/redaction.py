"""Category-aware redaction: substitute identifying entities with deterministic tokens.

The principle: **detection is not redaction**. ``Shield.analyze()`` flags sensitive
entities and emits a score; ``Shield.redact()`` rewrites identifying entities into
opaque tokens before the text is handed to an external LLM. Numbers, ratios,
diagnoses-as-clinical-content and other "shape" information are preserved by
default — the model still needs them to reason. Only "who" is masked.

Round-trip:

    redacted, mapping = shield.redact(text, profile="finance")
    response = call_llm(redacted)
    final = shield.unredact(response, mapping)
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone

from ogentic_shield.models import DetectedEntity, RedactionMapping

logger = logging.getLogger("ogentic_shield.redaction")


# High-level category labels the caller passes (e.g. ``"Person"``) → underlying
# entity types emitted by recognizers (e.g. ``PERSON``, ``EXECUTIVE_NAME``).
# Labels are the stable, user-facing vocabulary; entity types are an
# implementation detail of the recognizers.
CATEGORY_LABEL_TO_ENTITY_TYPES: dict[str, list[str]] = {
    # Identifying ("who")
    "Person":         ["PERSON", "EXECUTIVE_NAME", "PATIENT_NAME", "PROVIDER_NAME"],
    "Address":        ["LOCATION"],
    "Sponsor":        ["INSTITUTION_NAME", "LAW_FIRM_NAME", "FUND_INFORMATION"],
    "Email":          ["EMAIL_ADDRESS"],
    "Phone":          ["PHONE_NUMBER"],
    "Ssn":            ["SSN", "US_SSN"],
    "DateOfBirth":    ["DATE_OF_BIRTH"],
    "InsuranceId":    ["INSURANCE_ID"],
    "MedicalLicense": ["MEDICAL_LICENSE"],
    "CaseNumber":     ["CASE_NUMBER"],
    "BatesNumber":    ["BATES_NUMBER"],
    "Diagnosis":      ["DIAGNOSIS_CODE"],
    "Medication":     ["MEDICATION"],
    "CreditCard":     ["CREDIT_CARD"],
    "BankNumber":     ["US_BANK_NUMBER"],
    "Url":            ["URL"],
    "IpAddress":      ["IP_ADDRESS"],
    "Passport":       ["US_PASSPORT"],
    "Itin":           ["US_ITIN"],
    "DriverLicense":  ["US_DRIVER_LICENSE"],
    "DateTime":       ["DATE_TIME"],
    "Iban":           ["IBAN_CODE"],
    "Nationality":    ["NRP"],
}

# Identifying-only set — masks "who" without clobbering numeric content the
# model needs to reason about (loan amounts, ratios, percentages, etc.).
DEFAULT_REDACT_CATEGORIES: list[str] = [
    "Person", "Address", "Sponsor", "Email", "Phone", "Ssn",
]

# Each profile knows its own identifying-only categories. Callers can still
# override via the ``redact_categories`` parameter on ``redact()``.
PROFILE_REDACT_CATEGORIES: dict[str, list[str]] = {
    "shield-finance": list(DEFAULT_REDACT_CATEGORIES),
    "shield-legal":   list(DEFAULT_REDACT_CATEGORIES) + ["CaseNumber", "BatesNumber"],
    "shield-therapy": list(DEFAULT_REDACT_CATEGORIES) + [
        "DateOfBirth", "InsuranceId", "MedicalLicense",
    ],
}


def _resolve_categories(
    profile_id: str | None,
    redact_categories: list[str] | None,
) -> list[str]:
    """Per-call override beats profile default beats global default."""
    if redact_categories is not None:
        return list(redact_categories)
    if profile_id and profile_id in PROFILE_REDACT_CATEGORIES:
        return list(PROFILE_REDACT_CATEGORIES[profile_id])
    return list(DEFAULT_REDACT_CATEGORIES)


def _expand_entity_types(categories: list[str]) -> set[str]:
    expanded: set[str] = set()
    unknown: list[str] = []
    for cat in categories:
        if cat in CATEGORY_LABEL_TO_ENTITY_TYPES:
            expanded.update(CATEGORY_LABEL_TO_ENTITY_TYPES[cat])
        elif cat.isupper() or "_" in cat:
            # Power-user escape hatch: raw entity types pass through verbatim.
            expanded.add(cat)
        else:
            unknown.append(cat)
    if unknown:
        logger.warning("Unknown redaction categories ignored: %s", unknown)
    return expanded


def _label_for(entity_type: str) -> str:
    """Reverse-lookup the friendly label for an entity type — used in token prefixes."""
    for label, types in CATEGORY_LABEL_TO_ENTITY_TYPES.items():
        if entity_type in types:
            return label
    return entity_type.title().replace("_", "")


def _short_hash(salt: str, value: str) -> str:
    return hashlib.sha256((salt + value).encode("utf-8")).hexdigest()[:6]


def redact_text(
    text: str,
    entities: list[DetectedEntity],
    profile_id: str | None = None,
    redact_categories: list[str] | None = None,
) -> tuple[str, RedactionMapping]:
    """Substitute identifying entities with deterministic tokens.

    Args:
        text: Original input.
        entities: Detected entities from a ``Shield.analyze()`` pass over ``text``.
        profile_id: Profile in use — selects per-profile defaults when
            ``redact_categories`` is None.
        redact_categories: Explicit category labels (or raw entity types) to mask.
            ``None`` → per-profile defaults, falling back to
            ``DEFAULT_REDACT_CATEGORIES``.

    Returns:
        ``(redacted_text, mapping)`` — pass ``mapping`` to ``unredact_text()``
        to restore the original values.
    """
    categories = _resolve_categories(profile_id, redact_categories)
    target_entity_types = _expand_entity_types(categories)

    # Per-call salt: same value gets the same token within this call (so the
    # LLM sees coherent references), but different tokens across calls (so
    # the same value isn't linkable across documents).
    salt = secrets.token_hex(8)
    text_hash = f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"

    mapping = RedactionMapping(
        categories_redacted=categories,
        profile_id=profile_id,
        text_hash=text_hash,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    targets = [e for e in entities if e.category in target_entity_types]
    if not targets:
        return text, mapping

    # Drop overlaps — keep the longer span; mirrors the dedup rule in regex_ner.
    targets.sort(key=lambda e: (e.start, -(e.end - e.start)))
    non_overlapping: list[DetectedEntity] = []
    for ent in targets:
        if non_overlapping and ent.start < non_overlapping[-1].end:
            continue
        non_overlapping.append(ent)

    value_to_token: dict[tuple[str, str], str] = {}
    parts: list[str] = []
    cursor = 0
    for ent in non_overlapping:
        parts.append(text[cursor:ent.start])
        original = text[ent.start:ent.end]
        label = _label_for(ent.category)
        key = (label, original)
        token = value_to_token.get(key)
        if token is None:
            token = f"[{label}_{_short_hash(salt, original)}]"
            value_to_token[key] = token
            mapping.tokens[token] = original
        parts.append(token)
        cursor = ent.end
    parts.append(text[cursor:])

    return "".join(parts), mapping


def unredact_text(text: str, mapping: RedactionMapping) -> str:
    """Restore tokens in ``text`` to their original values using ``mapping``.

    Tokens not present in ``text`` are silently skipped — round-tripping
    through an LLM that drops or rephrases content remains safe.
    """
    if not mapping.tokens:
        return text
    # Replace longer tokens first; token format is fixed-width per-call so
    # this matters only across heterogeneous mappings, but it's cheap insurance.
    ordered = sorted(mapping.tokens.items(), key=lambda kv: -len(kv[0]))
    out = text
    for token, original in ordered:
        out = out.replace(token, original)
    return out
