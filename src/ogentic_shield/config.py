"""Configuration loading from YAML files."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml  # type: ignore[import-untyped]  # PyYAML stubs not pinned.

from ogentic_shield.models import ConfigError

logger = logging.getLogger("ogentic_shield.config")

DEFAULT_CONFIG_FILENAME = "ogentic-shield.yaml"


@dataclass
class LlmConfig:
    enabled: bool = False
    provider: str = "ollama"
    model: str = "llama3.1:8b"
    endpoint: str = "http://localhost:11434"
    timeout_ms: int = 5000
    ambiguous_score_range: list[int] = field(default_factory=lambda: [20, 60])


@dataclass
class ScoringConfig:
    min_confidence: float = 0.5
    dedup_strategy: str = "longest_highest"


@dataclass
class OutputConfig:
    include_text_hash: bool = True
    include_processing_time: bool = True
    max_entities: int = 50


@dataclass
class ShieldConfig:
    version: str = "0.1"
    profiles: list[str] = field(default_factory=lambda: ["shield-legal", "shield-therapy"])
    layers_regex: bool = True
    layers_ner: bool = True
    layers_rules: bool = True
    llm: LlmConfig = field(default_factory=LlmConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    custom_profiles_dir: str | None = None


def load_config(path: str | Path | None = None) -> ShieldConfig:
    """Load config from YAML file. Returns defaults if no file found."""
    if path is None:
        candidates = [
            Path(DEFAULT_CONFIG_FILENAME),
            Path.home() / ".config" / "ogentic-shield" / DEFAULT_CONFIG_FILENAME,
        ]
        for candidate in candidates:
            if candidate.exists():
                path = candidate
                break

    if path is None:
        logger.debug("No config file found, using defaults")
        return ShieldConfig()

    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ConfigError(f"Invalid config format in {path}")

    llm_data = data.get("layers", {}).get("llm", {})
    llm_config = LlmConfig(
        enabled=llm_data.get("enabled", False),
        provider=llm_data.get("provider", "ollama"),
        model=llm_data.get("model", "llama3.1:8b"),
        endpoint=llm_data.get("endpoint", "http://localhost:11434"),
        timeout_ms=llm_data.get("timeout_ms", 5000),
        ambiguous_score_range=llm_data.get("ambiguous_score_range", [20, 60]),
    )

    scoring_data = data.get("scoring", {})
    scoring_config = ScoringConfig(
        min_confidence=scoring_data.get("min_confidence", 0.5),
        dedup_strategy=scoring_data.get("dedup_strategy", "longest_highest"),
    )

    output_data = data.get("output", {})
    output_config = OutputConfig(
        include_text_hash=output_data.get("include_text_hash", True),
        include_processing_time=output_data.get("include_processing_time", True),
        max_entities=output_data.get("max_entities", 50),
    )

    layers_data = data.get("layers", {})

    return ShieldConfig(
        version=data.get("version", "0.1"),
        profiles=data.get("profiles", ["shield-legal", "shield-therapy"]),
        layers_regex=layers_data.get("regex", True),
        layers_ner=layers_data.get("ner", True),
        layers_rules=layers_data.get("rules", True),
        llm=llm_config,
        scoring=scoring_config,
        output=output_config,
        custom_profiles_dir=data.get("custom_profiles_dir"),
    )
