"""Pydantic schema for Layer 3 structured output.

Ollama 0.4+ accepts a JSON schema via ``format=`` and constrains the model's
generation to match it. Defining the schema as a Pydantic model gives us:

- a single source of truth for the wire format,
- automatic schema generation (``LlmResponse.model_json_schema()``),
- post-parse validation that the model populated all required fields.

Hallucinated spans (``span_text`` not findable in the original input) are
filtered out by the orchestration layer in :mod:`ogentic_shield.layers.llm`,
not here — keep the schema permissive about *content*, strict about *shape*.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LlmDetection(BaseModel):
    """One classification result emitted by the model."""

    category: str = Field(
        ...,
        description="Category label from the profile's allow-list (e.g. PRIVILEGE_MARKER).",
    )
    span_text: str = Field(
        ...,
        min_length=1,
        description="Exact substring from the input that triggered the detection.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model's confidence, 0.0–1.0. Calibrated downstream.",
    )
    reasoning: str = Field(
        default="",
        description="Brief justification — kept internal for debugging, never surfaced to audit.",
    )


class LlmResponse(BaseModel):
    """Top-level wrapper. ``detections`` may be empty if the model finds nothing."""

    detections: list[LlmDetection] = Field(default_factory=list)


__all__ = ["LlmDetection", "LlmResponse"]
