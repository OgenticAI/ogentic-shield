"""Layer 1: Presidio regex + NER entity detection."""

from __future__ import annotations

import logging
import time

from presidio_analyzer import AnalyzerEngine

from ogentic_shield.models import (
    CATEGORY_GROUP_PRIORITY,
    CategoryGroup,
    DetectedEntity,
    DetectionLayer,
    ShieldProfile,
)

logger = logging.getLogger("ogentic_shield.layers.regex_ner")

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
) -> list[DetectedEntity]:
    """Run Layer 1: Presidio regex + NER detection with custom recognizers."""
    start_time = time.perf_counter()

    analyzer = AnalyzerEngine()

    for profile in profiles:
        for recognizer in profile.recognizers:
            analyzer.registry.add_recognizer(recognizer)

    all_entity_types = set()
    for profile in profiles:
        all_entity_types.update(profile.supported_entities)
    all_entity_types.update(["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS"])

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
