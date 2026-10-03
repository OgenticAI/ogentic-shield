"""Layer 1: Presidio regex + NER entity detection."""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path

import phonenumbers
import spacy.util
import tldextract
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import EmailRecognizer

from ogentic_shield.models import (
    CATEGORY_GROUP_PRIORITY,
    CategoryGroup,
    DetectedEntity,
    DetectionLayer,
    ModelNotInstalledError,
    ShieldProfile,
)
from ogentic_shield.profiles import get_profile

logger = logging.getLogger("ogentic_shield.layers.regex_ner")

# Presidio's EmailRecognizer validates domains with the module-level
# ``tldextract.extract``, which fetches the public suffix list over HTTPS on
# first use. Shield is on-device: use tldextract's bundled snapshot, with no
# remote URLs and no disk cache.
_OFFLINE_TLD_EXTRACT = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=())


class OfflineEmailRecognizer(EmailRecognizer):
    """Presidio's EmailRecognizer with network-free domain validation."""

    def __init__(self) -> None:
        # Keep Presidio's name so recognizer metadata is unchanged.
        super().__init__(name="EmailRecognizer")

    def validate_result(self, pattern_text: str) -> bool:
        return _OFFLINE_TLD_EXTRACT(pattern_text).fqdn != ""


class UsPhoneRecognizer(PatternRecognizer):
    """US numbers written in a phone layout, detected without context words.

    Presidio's PhoneRecognizer scores 0.4 and needs a context word to clear
    the 0.5 default threshold, but its "call" context word is a spaCy
    stopword that Presidio filters out, so "call 415-555-0182" and
    "... or (415) 555-0182" were dropped. Requiring the 3-3-4 separator
    layout (optional "(area)" and "+1") plus phonenumbers validation keeps
    SSNs (3-2-4), dates, invalid area codes and bare digit runs out.
    """

    PATTERNS = [
        Pattern(
            name="us_phone_formatted",
            regex=r"(?<![\w-])(?:\+1[ .-]?)?(?:\(\d{3}\) ?|\d{3}[.-])\d{3}[.-]\d{4}(?![\w-])",
            score=0.6,
        ),
    ]

    def __init__(self) -> None:
        super().__init__(supported_entity="PHONE_NUMBER", patterns=self.PATTERNS, supported_language="en")

    def invalidate_result(self, pattern_text: str) -> bool:
        try:
            return not phonenumbers.is_valid_number(phonenumbers.parse(pattern_text, "US"))
        except phonenumbers.NumberParseException:
            return True


def ensure_model_installed(ner_model: str) -> None:
    """Raise :class:`ModelNotInstalledError` if ``ner_model`` is missing.

    Presidio's spaCy engine would otherwise ``pip install`` the model at
    runtime (~400 MB for ``en_core_web_lg``) and print the download progress
    to stdout, corrupting machine-readable CLI output. Shield never downloads
    models during analysis; setup is the explicit ``models download`` command.
    """
    if spacy.util.is_package(ner_model) or Path(ner_model).exists():
        return
    raise ModelNotInstalledError(
        f"spaCy model '{ner_model}' is not installed. Shield does not download models "
        f"at analysis time. Install it once with:\n"
        f"  ogentic-shield models download --model {ner_model}\n"
        f"or: python -m spacy download {ner_model}"
    )


def build_analyzer(ner_model: str) -> AnalyzerEngine:
    """A Presidio analyzer that never touches the network.

    Fails fast if the spaCy model is missing (no runtime download), swaps in
    :class:`OfflineEmailRecognizer`, and adds :class:`UsPhoneRecognizer`.
    Every analyzer Shield builds goes through here.
    """
    ensure_model_installed(ner_model)
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": ner_model}],
        }
    )
    analyzer = AnalyzerEngine(nlp_engine=provider.create_engine())
    analyzer.registry.remove_recognizer("EmailRecognizer")
    analyzer.registry.add_recognizer(OfflineEmailRecognizer())
    analyzer.registry.add_recognizer(UsPhoneRecognizer())
    return analyzer


@lru_cache(maxsize=8)
def _get_analyzer(ner_model: str, profile_ids: tuple[str, ...]) -> AnalyzerEngine:
    """Build (once, then cache) a Presidio analyzer for a model + profile set.

    Presidio loads its spaCy model at construction — ~780 MB for
    ``en_core_web_lg``, ~165 MB for ``en_core_web_sm``. Building a fresh engine
    per :func:`run_layer1` call reloaded that model on **every request**, which
    both added seconds of latency and, under concurrency, multiplied the model
    in memory until the container OOM-killed. Caching by ``(ner_model,
    profile_ids)`` loads each model once and reuses it — the reuse pattern
    Presidio itself recommends. ``AnalyzerEngine.analyze`` is stateless, so the
    shared engine is safe across the server's request threads.
    """
    analyzer = build_analyzer(ner_model)
    for pid in profile_ids:
        for recognizer in get_profile(pid).recognizers:
            analyzer.registry.add_recognizer(recognizer)
    return analyzer

# Mapping from custom entity types to their category groups
_ENTITY_CATEGORY_GROUP: dict[str, CategoryGroup] = {
    # Legal
    "COUNSEL_COMMUNICATION": CategoryGroup.PRIVILEGE,
    "PRIVILEGE_MARKER": CategoryGroup.PRIVILEGE,
    "WORK_PRODUCT": CategoryGroup.PRIVILEGE,
    "SETTLEMENT_TERMS": CategoryGroup.CONFIDENTIAL,
    "CASE_NUMBER": CategoryGroup.PII,
    "LAW_FIRM_NAME": CategoryGroup.PII,
    "LITIGATION_MARKER": CategoryGroup.PRIVILEGE,
    "COURT_FILING": CategoryGroup.CONFIDENTIAL,
    "BATES_NUMBER": CategoryGroup.CONFIDENTIAL,
    # Government
    "COMMERCIAL_PRICING": CategoryGroup.CONFIDENTIAL,
    "EXECUTIVE_NAME": CategoryGroup.PII,
    # Therapy
    "PATIENT_NAME": CategoryGroup.PHI,
    "DATE_OF_BIRTH": CategoryGroup.PHI,
    "DIAGNOSIS_CODE": CategoryGroup.PHI,
    "CLINICAL_RISK_FLAG": CategoryGroup.PHI,
    "SESSION_MARKER": CategoryGroup.PHI,
    "INSURANCE_ID": CategoryGroup.PHI,
    "MEDICATION": CategoryGroup.PHI,
    "PROVIDER_NAME": CategoryGroup.PHI,
    "SSN": CategoryGroup.PII,
    "PSYCHOTHERAPY_NOTE_MARKER": CategoryGroup.PHI,
    # Therapy-pro (OGE-355)
    "DSM5_DIAGNOSIS": CategoryGroup.PHI,
    "CPT_CODE": CategoryGroup.PHI,
    "MINOR_CLIENT_MARKER": CategoryGroup.PHI,
    "TRAUMA_INDICATOR": CategoryGroup.PHI,
    # Finance
    "MNPI_MARKER": CategoryGroup.MNPI,
    "MA_ACTIVITY": CategoryGroup.MNPI,
    "DEAL_VALUE": CategoryGroup.MNPI,
    "LEVERAGE_RATIO": CategoryGroup.MNPI,
    "FUND_INFORMATION": CategoryGroup.MNPI,
    "INSTITUTION_NAME": CategoryGroup.PII,
    "FINANCIAL_TERMS": CategoryGroup.MNPI,
    "DISTRIBUTION_RESTRICTION": CategoryGroup.CONFIDENTIAL,
    "INSIDER_MARKER": CategoryGroup.MNPI,
    "CARRY_TERMS": CategoryGroup.MNPI,
    # Presidio built-ins
    "PERSON": CategoryGroup.PII,
    "PHONE_NUMBER": CategoryGroup.PII,
    "EMAIL_ADDRESS": CategoryGroup.PII,
    "CREDIT_CARD": CategoryGroup.PII,
    "IBAN_CODE": CategoryGroup.PII,
    "US_SSN": CategoryGroup.PII,
    "US_DRIVER_LICENSE": CategoryGroup.PII,
    "LOCATION": CategoryGroup.PII,
    "DATE_TIME": CategoryGroup.PII,
    "NRP": CategoryGroup.PII,
    "IP_ADDRESS": CategoryGroup.PII,
    "URL": CategoryGroup.PII,
    "US_BANK_NUMBER": CategoryGroup.PII,
    "US_PASSPORT": CategoryGroup.PII,
    "US_ITIN": CategoryGroup.PII,
    "MEDICAL_LICENSE": CategoryGroup.PHI,
}


def _get_category_group(entity_type: str) -> CategoryGroup:
    return _ENTITY_CATEGORY_GROUP.get(entity_type, CategoryGroup.PII)


def _deduplicate_entities(entities: list[DetectedEntity]) -> list[DetectedEntity]:
    """Resolve overlapping entities per PRD §6.1.

    1. Longer span wins over shorter span
    2. If same length, higher confidence wins
    3. If same confidence, higher priority category group wins
    """
    if not entities:
        return []

    sorted_entities = sorted(entities, key=lambda e: e.start)
    result: list[DetectedEntity] = []

    for entity in sorted_entities:
        if not result:
            result.append(entity)
            continue

        last = result[-1]
        if entity.start < last.end:
            last_len = last.end - last.start
            curr_len = entity.end - entity.start
            if curr_len > last_len:
                result[-1] = entity
            elif curr_len == last_len:
                if entity.confidence > last.confidence:
                    result[-1] = entity
                elif entity.confidence == last.confidence:
                    last_priority = CATEGORY_GROUP_PRIORITY.get(last.category_group, 0)
                    curr_priority = CATEGORY_GROUP_PRIORITY.get(entity.category_group, 0)
                    if curr_priority > last_priority:
                        result[-1] = entity
        else:
            result.append(entity)

    return result


def run_layer1(
    text: str,
    profiles: list[ShieldProfile],
    min_confidence: float = 0.5,
    ner_model: str = "en_core_web_lg",
) -> list[DetectedEntity]:
    """Run Layer 1: Presidio regex + NER detection with custom recognizers.

    ``ner_model`` selects the spaCy model behind Presidio's NER — default
    ``en_core_web_lg`` (accuracy), ``en_core_web_sm`` for a ~5x smaller memory
    footprint. The analyzer is cached per ``(ner_model, profiles)`` so the model
    loads once rather than per call.
    """
    start_time = time.perf_counter()

    analyzer = _get_analyzer(ner_model, tuple(p.id for p in profiles))

    all_entity_types = set()
    for profile in profiles:
        all_entity_types.update(profile.supported_entities)
    all_entity_types.update(["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN"])

    logger.debug("Running %d entity types against %d chars", len(all_entity_types), len(text))

    presidio_results = analyzer.analyze(
        text=text,
        entities=list(all_entity_types),
        language="en",
    )

    entities: list[DetectedEntity] = []
    for result in presidio_results:
        if result.score < min_confidence:
            continue

        detection_layer = DetectionLayer.REGEX
        if result.recognition_metadata and result.recognition_metadata.get(
            "recognizer_name", ""
        ).startswith("Spacy"):
            detection_layer = DetectionLayer.NER

        entity = DetectedEntity(
            text=text[result.start:result.end],
            category=result.entity_type,
            category_group=_get_category_group(result.entity_type),
            confidence=result.score,
            detection_layer=detection_layer,
            start=result.start,
            end=result.end,
            metadata={
                "recognizer": result.recognition_metadata.get("recognizer_name", "unknown")
                if result.recognition_metadata
                else "unknown",
            },
        )
        entities.append(entity)

    entities = _deduplicate_entities(entities)

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info("Layer 1 complete: %d entities in %.1fms", len(entities), elapsed_ms)

    return entities
