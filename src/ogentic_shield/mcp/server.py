"""MCP server surface for ogentic-shield (OGE-310/311/312).

The model-context-protocol Python SDK (`mcp>=1.0`) handles all the wire-level
concerns — JSON-RPC framing, stdio/SSE/HTTP transports, capability negotiation.
We just register tools that wrap the existing `Shield` pipeline.

Tool design discipline:
    - **Names mirror the public Python API** so docs and tests carry over:
      `shield.analyze`, `shield.redact`, `shield.profiles`.
    - **Inputs are JSON-friendly primitives** — strings, ints, bools, lists.
      No dataclasses, no enums (we serialize their `.value`).
    - **Outputs are structured dicts** that match the on-the-wire shape of
      `AnalysisResult` / `RedactionMapping` minus internal Python idioms.
    - **Failure-safe**: tool exceptions become MCP error responses; the server
      stays up. Same `safe_*` discipline as the rest of the codebase.

Profile selection:
    - Each tool accepts an optional ``profile`` argument (``"shield-legal"``,
      ``"shield-therapy"``, ``"shield-finance"``).
    - Default is the first profile the server was started with (configurable
      via ``--profile`` on the CLI / ``OGENTIC_SHIELD_PROFILE`` env var).
    - Multiple profiles can be loaded; tool calls just pick which one to use
      per call.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Any

from ogentic_shield import __version__
from ogentic_shield.models import (
    AnalysisResult,
    DetectedEntity,
    RedactionMapping,
)
from ogentic_shield.profiles import list_profiles
from ogentic_shield.shield import Shield

logger = logging.getLogger("ogentic_shield.mcp")

# The set of profiles the server is willing to load on demand. Locked down to
# the three v0.2 profiles so a hostile client can't ask the server to load an
# attacker-controlled YAML by name.
_KNOWN_PROFILES: set[str] = {"shield-legal", "shield-therapy", "shield-finance"}

# Default tool-input shape for the model: only the text we're classifying needs
# to be required. Profile + flags are optional with sensible defaults.

DEFAULT_PROFILE = "shield-legal"


def _resolve_profile(requested: str | None, server_default: str) -> str:
    """Pick the effective profile for a tool call.

    Caller's ``profile`` arg wins if provided and known. Otherwise fall back
    to the server's startup default. Unknown values raise so the model can't
    silently mis-classify content under the wrong profile.
    """
    if requested:
        if requested not in _KNOWN_PROFILES:
            raise ValueError(
                f"Unknown profile {requested!r}. "
                f"Known profiles: {sorted(_KNOWN_PROFILES)}",
            )
        return requested
    return server_default


def _entity_to_dict(entity: DetectedEntity, *, include_text: bool) -> dict[str, Any]:
    """Serialize a DetectedEntity for the tool response.

    Defaults to **shape-only** (no entity text) — same privacy invariant as
    `audit.py`'s `_entity_shape`. Callers who need the literal matched text
    can opt in via `include_entities=true` on the tool call. That flag exists
    primarily for debugging local consumers (Claude Desktop on the developer's
    laptop); production consumers should leave it off.
    """
    out: dict[str, Any] = {
        "category": entity.category,
        "category_group": entity.category_group.value,
        "confidence": round(entity.confidence, 4),
        "layer": entity.detection_layer.value,
        "start": entity.start,
        "end": entity.end,
    }
    if include_text:
        out["text"] = entity.text
    return out


def _result_to_dict(
    result: AnalysisResult,
    *,
    include_entities: bool,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "score": result.score,
        "level": result.sensitivity_level.value,
        "routing": result.routing_suggestion,
        "entity_count": result.entity_count,
        "category_groups_found": [g.value for g in result.category_groups_found],
        "top_category": result.top_category,
        "top_confidence": round(result.top_confidence, 4),
        "layers_invoked": [layer.value for layer in result.layers_invoked],
        "processing_time_ms": result.processing_time_ms,
        "profile_ids": list(result.profile_ids),
        "text_hash": result.text_hash,
    }
    if include_entities:
        # When the caller opts in, ALSO include entity text. Documented above.
        out["entities"] = [
            _entity_to_dict(e, include_text=True) for e in result.entities
        ]
    else:
        # Shape-only view — safe to include in the default response.
        out["entities"] = [
            _entity_to_dict(e, include_text=False) for e in result.entities
        ]
    return out


def _mapping_to_dict(mapping: RedactionMapping) -> dict[str, Any]:
    """Serialize a RedactionMapping for the tool response.

    Returns the full mapping (including reversal tokens) — the caller needs
    these to call ``shield.unredact`` later. The MCP transport is in-process
    or to a trusted local client; we don't gate the mapping behind another
    flag the way we do entity text.
    """
    return asdict(mapping)


def build_server(
    profiles: list[str] | None = None,
    *,
    name: str = "ogentic-shield",
):
    """Construct (but don't run) the FastMCP server.

    Factored out from `run()` so tests can introspect the registered tools
    without needing a real transport. The MCP SDK is imported lazily so the
    rest of the package keeps working when `mcp` isn't installed
    (it's an optional dep — `pip install ogentic-shield[mcp]`).
    """
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "ogentic-shield MCP server requires the `mcp` package. "
            "Install with: pip install 'ogentic-shield[mcp]'",
        ) from e

    profile_ids = profiles or [DEFAULT_PROFILE]
    server_default_profile = profile_ids[0]

    # Build a Shield up front so first call doesn't pay the full Presidio
    # initialization cost (~300ms cold). Holds spaCy models in memory.
    shield = Shield(profiles=profile_ids)

    # NB: FastMCP's constructor doesn't take a `version` kwarg in mcp>=1.x;
    # we surface __version__ via the `shield.profiles` tool response instead.
    server = FastMCP(name=name)

    @server.tool(name="shield.analyze")
    def shield_analyze(
        text: str,
        profile: str | None = None,
        include_entities: bool = False,
    ) -> dict[str, Any]:
        """Classify text for regulatory sensitivity.

        Args:
            text: Input text to analyze.
            profile: Shield profile id, e.g. ``shield-legal``,
                ``shield-therapy``, ``shield-finance``. Defaults to the
                server's startup profile.
            include_entities: When true, the response includes the matched
                text for each detected entity. Off by default — the
                shape-only response (category / confidence / span) is
                sufficient for routing decisions and avoids leaking the
                very content we're protecting.

        Returns:
            Dict with ``score`` (0-100), ``level`` (NONE..CRITICAL),
            ``routing`` suggestion, ``entities`` (shape-only by default),
            and pipeline diagnostics.
        """
        if not text:
            raise ValueError("`text` must be a non-empty string")
        active_profile = _resolve_profile(profile, server_default_profile)
        result = shield.analyze(text, profiles=[active_profile])
        return _result_to_dict(result, include_entities=include_entities)

    @server.tool(name="shield.redact")
    def shield_redact(
        text: str,
        profile: str | None = None,
        redact_categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """Substitute identifying entities with deterministic tokens.

        Use this *before* sending text to an external LLM. Pair with
        ``shield.unredact`` (or restore manually using the returned mapping)
        on the model's response.

        Args:
            text: Input text.
            profile: Shield profile id; defaults to the server's startup
                profile.
            redact_categories: Override category labels to mask (e.g.
                ``["Person", "Email"]``). When omitted, the per-profile
                default identifying-only set is used.

        Returns:
            Dict with ``redacted_text`` and ``mapping`` (pass ``mapping`` to
            ``shield.unredact`` to restore originals).
        """
        if not text:
            raise ValueError("`text` must be a non-empty string")
        active_profile = _resolve_profile(profile, server_default_profile)
        redacted, mapping = shield.redact(
            text,
            profile=active_profile,
            redact_categories=redact_categories,
        )
        return {
            "redacted_text": redacted,
            "mapping": _mapping_to_dict(mapping),
        }

    @server.tool(name="shield.unredact")
    def shield_unredact(text: str, mapping: dict[str, Any]) -> dict[str, str]:
        """Restore tokens in ``text`` to their original values.

        ``mapping`` should be the dict returned by ``shield.redact``. Tokens
        not present in ``text`` are silently skipped — a model that drops or
        rewords part of the input still round-trips safely.
        """
        if not isinstance(mapping, dict):
            raise ValueError("`mapping` must be the dict returned by shield.redact")
        # Reconstruct the dataclass from the wire form.
        rebuilt = RedactionMapping(
            tokens=dict(mapping.get("tokens") or {}),
            categories_redacted=list(mapping.get("categories_redacted") or []),
            profile_id=mapping.get("profile_id"),
            text_hash=str(mapping.get("text_hash") or ""),
            created_at=str(mapping.get("created_at") or ""),
        )
        restored = Shield.unredact(text, rebuilt)
        return {"text": restored}

    @server.tool(name="shield.profiles")
    def shield_profiles() -> dict[str, Any]:
        """List available shield profiles loaded on this server.

        Returns the static profile catalog — what profiles exist on this
        server, what entity types each detects, and which one is the
        startup default. Callers use this to drive UI dropdowns or to
        decide which profile to pass on subsequent ``analyze`` / ``redact``
        calls.
        """
        loaded = [
            {
                "id": p.id,
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "supported_entities": list(p.supported_entities),
                "category_groups": sorted({g.value for g in p.scoring_weights}),
            }
            for p in list_profiles()
            if p.id in _KNOWN_PROFILES
        ]
        return {
            "profiles": loaded,
            "default_profile": server_default_profile,
            "active_profiles": list(profile_ids),
            "reviewer_version": __version__,
        }

    logger.info(
        "ogentic-shield MCP server built: profiles=%s default=%s tools=%s",
        profile_ids,
        server_default_profile,
        ["shield.analyze", "shield.redact", "shield.unredact", "shield.profiles"],
    )
    return server


def run(
    transport: str = "stdio",
    *,
    profiles: list[str] | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """Build and run the MCP server.

    Args:
        transport: ``"stdio"`` (default — for Claude Desktop, Goose, etc.)
            or ``"sse"`` (for network clients). Streamable HTTP support
            arrives in a follow-up ticket.
        profiles: List of profile ids to load. Defaults to
            ``[DEFAULT_PROFILE]`` which can be overridden via the
            ``OGENTIC_SHIELD_PROFILE`` env var.
        host / port: Bind address for SSE transport. Loopback by default;
            don't expose this server on a public interface without an
            auth proxy in front of it.
    """
    if profiles is None:
        env_profile = os.environ.get("OGENTIC_SHIELD_PROFILE")
        profiles = [env_profile] if env_profile else [DEFAULT_PROFILE]

    server = build_server(profiles=profiles)

    if transport == "stdio":
        # FastMCP's run() method dispatches to the right transport.
        server.run(transport="stdio")
    elif transport == "sse":
        # Bind explicit host/port via FastMCP settings before running. The
        # SDK reads from `server.settings` on SSE startup.
        server.settings.host = host
        server.settings.port = port
        server.run(transport="sse")
    else:
        raise ValueError(
            f"Unknown transport {transport!r}. Use 'stdio' or 'sse'.",
        )


def main() -> None:
    """CLI entry point — `python -m ogentic_shield.mcp`."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m ogentic_shield.mcp",
        description="ogentic-shield MCP server — exposes Shield as MCP tools.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse"),
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        help="Shield profile to load (repeatable). Default: shield-legal.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="SSE bind host")
    parser.add_argument("--port", type=int, default=8765, help="SSE bind port")
    args = parser.parse_args()

    run(
        transport=args.transport,
        profiles=args.profiles,
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
