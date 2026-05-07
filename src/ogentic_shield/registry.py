"""Model registry: which Ollama models Shield needs at each quality tier.

Shield is consumed by Sotto Desktop, Zing Browser, Zashboard, Gyri, and any MCP
client. Without a single source of truth, every consumer re-derives "what model
should I pre-pull for Layer 3 classification?" — and they drift. This registry
centralizes the recommendation; consumers call :py:meth:`Shield.required_models`
to know what to pull, and may pass ``model_override={"classification": "..."}``
to substitute a model they've already standardized on.
"""

from __future__ import annotations

from enum import Enum

# ── Roles ────────────────────────────────────────────────────────────────────
# Stable string keys so consumers can compose overrides as plain dicts without
# importing the enum. Roles are deliberately narrow — add a new key only when a
# layer genuinely needs a *different* model class, not a different size of the
# same class (size differences belong to quality tiers).

ROLE_CLASSIFICATION = "classification"
ROLE_NER_AUGMENT = "ner_augment"


class ModelTier(str, Enum):
    """Quality vs. footprint trade-off for the LLM-backed layers.

    - ``FAST`` — small MoE; fits comfortably alongside an editor on a laptop.
    - ``QUALITY`` — dense larger model; better recall on adversarial text,
      heavier RAM/VRAM cost.
    - ``COMPREHENSIVE`` — quality classifier *plus* an NER-augment model for
      consumers that want belt-and-braces extraction (e.g. Sotto Desktop's
      "thorough" mode).
    """

    FAST = "fast"
    QUALITY = "quality"
    COMPREHENSIVE = "comprehensive"


def _coerce_tier(tier: ModelTier | str) -> ModelTier:
    if isinstance(tier, ModelTier):
        return tier
    try:
        return ModelTier(tier)
    except ValueError as exc:
        valid = ", ".join(t.value for t in ModelTier)
        raise ValueError(f"Unknown quality tier '{tier}'. Valid: {valid}") from exc


class ModelRegistry:
    """Recommended Ollama models per role and quality tier.

    >>> ModelRegistry().required_models("fast")
    ['granite3.1-moe:1b']
    >>> ModelRegistry({"classification": "phi4:14b"}).get("classification", "fast")
    'phi4:14b'
    """

    # Granite 3.1 MoE 1B is the v0.2 default for "fast" — small enough to fit
    # alongside an editor on a 16GB laptop and still produce parseable JSON for
    # the structured-output prompt in :mod:`ogentic_shield.layers.llm_prompts`.
    # Mixtral 8x7B is the "quality" pick because it consistently outperforms
    # dense 7B models on the legal/MNPI benchmarks (see OGE-320).
    #
    # OGE-320 also tested ``granite3-moe:3b``, ``llama3.2:3b``, and ``qwen3:4b``
    # against the OGE-51 datasets (see benchmarks/MOE_COMPARISON.md). Findings:
    #   - granite3-moe:3b is *worse* than 1B on finance precision (47.6% vs 55.6%)
    #     so it is intentionally NOT recommended at any tier.
    #   - llama3.2:3b is the best active Layer 3 model today (~67% precision)
    #     but still under the L1+L2-only baseline, so promoting it would be a
    #     regression. Available via ``model_override`` for callers who want to
    #     trade slightly more precision than 1B for marginal recall.
    #   - qwen3:4b times out frequently on therapy-length inputs at the default
    #     5s timeout; intentionally kept only for COMPREHENSIVE/NER augment use.
    DEFAULTS: dict[ModelTier, dict[str, str]] = {
        ModelTier.FAST: {
            ROLE_CLASSIFICATION: "granite3.1-moe:1b",
        },
        ModelTier.QUALITY: {
            ROLE_CLASSIFICATION: "mixtral:8x7b",
        },
        ModelTier.COMPREHENSIVE: {
            ROLE_CLASSIFICATION: "mixtral:8x7b",
            ROLE_NER_AUGMENT: "qwen3:4b",
        },
    }

    def __init__(self, overrides: dict[str, str] | None = None):
        self._overrides: dict[str, str] = dict(overrides or {})

    def get(self, role: str, tier: ModelTier | str = ModelTier.FAST) -> str:
        """Resolve the model name for ``role`` at ``tier``.

        Per-role override wins over the tier default. Raises ``KeyError`` if
        the role isn't defined for the requested tier and no override exists —
        callers should treat this as a misconfiguration, not a runtime fallback.
        """
        if role in self._overrides:
            return self._overrides[role]
        tier_enum = _coerce_tier(tier)
        defaults = self.DEFAULTS[tier_enum]
        if role not in defaults:
            raise KeyError(
                f"No default model for role '{role}' at tier '{tier_enum.value}'. "
                f"Pass overrides={{'{role}': '<model>'}} on Shield init."
            )
        return defaults[role]

    def required_models(self, tier: ModelTier | str = ModelTier.FAST) -> list[str]:
        """Models a consumer should ``ollama pull`` before using ``tier``.

        Override values are substituted in; tier roles without overrides keep
        their default. The list is deduplicated and order-stable so pre-pull
        scripts are reproducible.
        """
        tier_enum = _coerce_tier(tier)
        seen: set[str] = set()
        models: list[str] = []
        for role in self.DEFAULTS[tier_enum]:
            model = self._overrides.get(role, self.DEFAULTS[tier_enum][role])
            if model not in seen:
                seen.add(model)
                models.append(model)
        return models


__all__ = [
    "ModelRegistry",
    "ModelTier",
    "ROLE_CLASSIFICATION",
    "ROLE_NER_AUGMENT",
]
