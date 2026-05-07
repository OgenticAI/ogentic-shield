"""Thin Ollama wrapper used by Layer 3.

Why a wrapper rather than calling ``ollama`` directly from the layer:

1. **Localhost-only invariant** is enforced in one place (the constructor).
   AD-07 — "Layer 3 calls localhost only, never an external endpoint" — is a
   contractual promise in the README. Centralizing the check here means a
   future regression has exactly one place to slip past.
2. **Retry/fallback logic** doesn't pollute the orchestration code in
   ``layers/llm.py``. Each retry covers JSON / schema validation failures
   the same way; connection errors short-circuit (no point retrying when
   Ollama is down).
3. **The Pydantic schema is passed through** as the structured-output format,
   so the wire layer always receives parsed objects — never raw JSON strings.

The wrapper returns ``None`` after exhausting retries; callers treat that as
"the LLM didn't help us today" and fall back silently to the L1+L2 score.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("ogentic_shield.layers.llm_client")

_TModel = TypeVar("_TModel", bound=BaseModel)

# LLMs are systematically over-confident relative to regex/NER calibration in
# the rest of the pipeline (which uses corpus-tuned thresholds). The 0.85
# multiplier is the v0.2 baseline — broader confidence calibration framework
# is OGE-321. Bumping or lowering this constant should be paired with a fresh
# benchmarks/run_layer3_benchmark.py run.
CONFIDENCE_CALIBRATION_FACTOR = 0.85

_LOCALHOST_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


class LocalhostOnlyError(ValueError):
    """Raised when an Ollama endpoint resolves to anything other than localhost."""


def _validate_localhost(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"}:
        raise LocalhostOnlyError(
            f"Ollama endpoint must use http(s); got '{parsed.scheme or '(missing)'}' in '{endpoint}'."
        )
    host = (parsed.hostname or "").lower()
    if host not in _LOCALHOST_HOSTS:
        raise LocalhostOnlyError(
            f"Ollama endpoint must be localhost (got host='{host}'). "
            "Layer 3 is contractually localhost-only — see README §Privacy."
        )


class OllamaClient:
    """Constrained-output Ollama caller.

    >>> from ogentic_shield.layers.llm_schema import LlmResponse
    >>> client = OllamaClient(endpoint="http://localhost:11434", model="granite3.1-moe:1b")
    >>> result = client.classify("Some prompt", LlmResponse)  # doctest: +SKIP
    """

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        timeout_ms: int = 5000,
        max_retries: int = 2,
    ):
        _validate_localhost(endpoint)
        self._endpoint = endpoint
        self._model = model
        self._timeout_s = max(0.1, timeout_ms / 1000.0)
        self._max_retries = max(0, max_retries)
        self._client = self._build_client()

    def _build_client(self) -> object | None:
        """Lazy-import ollama. Returns ``None`` if the optional extra is missing."""
        try:
            import ollama  # type: ignore[import-not-found]
        except ImportError:
            logger.warning(
                "Layer 3 requested but the 'ollama' package is not installed — "
                "install with `pip install ogentic-shield[llm]`. "
                "Falling back to L1+L2 score."
            )
            return None
        return ollama.Client(host=self._endpoint, timeout=self._timeout_s)  # type: ignore[no-any-return]

    @property
    def model(self) -> str:
        return self._model

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def classify(self, prompt: str, schema: type[_TModel]) -> _TModel | None:
        """Run ``prompt`` through the model, parsing the response into ``schema``.

        Retries on ``ValidationError`` / ``json.JSONDecodeError`` with
        exponential backoff (100ms → 200ms → 400ms…). Connection errors
        short-circuit — Ollama being down today won't be different in 200ms.
        Returns ``None`` after exhausting retries; the caller falls back to
        the L1+L2 score (see :func:`ogentic_shield.layers.llm.run_layer3`).
        """
        if self._client is None:
            return None

        attempt = 0
        last_error: Exception | None = None
        while attempt <= self._max_retries:
            try:
                raw = self._chat(prompt, schema)
            except _ConnectionLikeError as exc:
                logger.warning("Ollama call failed (no retry): %s", exc)
                return None
            except Exception as exc:  # noqa: BLE001 — defensive: ollama raises bare Exception in some paths
                logger.warning("Ollama call raised %s; treating as fallback.", exc.__class__.__name__)
                return None

            try:
                return schema.model_validate_json(raw)
            except (ValidationError, json.JSONDecodeError) as exc:
                last_error = exc
                attempt += 1
                if attempt > self._max_retries:
                    break
                backoff_s = 0.1 * (2 ** (attempt - 1))
                logger.info(
                    "Ollama produced unparseable output (attempt %d/%d); retrying in %.2fs.",
                    attempt,
                    self._max_retries + 1,
                    backoff_s,
                )
                time.sleep(backoff_s)

        logger.warning(
            "Ollama returned malformed structured output after %d attempts: %s",
            self._max_retries + 1,
            last_error,
        )
        return None

    def _chat(self, prompt: str, schema: type[_TModel]) -> str:
        """One round-trip to Ollama. Raises ``_ConnectionLikeError`` for transport issues."""
        assert self._client is not None  # narrowed by classify()
        try:
            response = self._client.chat(  # type: ignore[attr-defined]
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                format=schema.model_json_schema(),
                options={"temperature": 0.0},
            )
        except Exception as exc:
            # Ollama's Python SDK wraps httpx errors inconsistently across
            # versions; treat anything connection-shaped as fatal-for-this-call
            # so we don't burn retry budget on a service that isn't running.
            name = exc.__class__.__name__.lower()
            if any(token in name for token in ("connect", "timeout", "httperror", "responseerror")):
                raise _ConnectionLikeError(str(exc)) from exc
            raise

        # Newer Ollama SDKs expose `.message.content`; older ones return dicts.
        message = getattr(response, "message", None)
        if message is None and isinstance(response, dict):
            message = response.get("message")
        if message is None:
            raise RuntimeError("Ollama response missing 'message' field.")
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("Ollama response 'message.content' was not a string.")
        return content


class _ConnectionLikeError(RuntimeError):
    """Internal marker for transport-layer failures we don't want to retry."""


__all__ = [
    "OllamaClient",
    "LocalhostOnlyError",
    "CONFIDENCE_CALIBRATION_FACTOR",
]
