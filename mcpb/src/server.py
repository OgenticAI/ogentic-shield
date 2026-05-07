"""MCPB entry point for ogentic-shield.

Claude Desktop launches this via UV (`uv run --directory <bundle> src/server.py`).
The script:

1. Ensures spaCy's `en_core_web_lg` model is downloaded — Presidio needs it for
   NER, and pip can't reliably bundle it because it's distributed as a
   separate ~600MB asset.
2. Reads ``OGENTIC_SHIELD_PROFILES`` (comma-separated) from the env that the
   manifest's ``user_config`` plumbs in. Falls back to all four profiles.
3. Hands off to ``ogentic_shield.mcp.run`` over stdio — the same entry point
   the local CLI uses, so MCPB and stdio installs are byte-equivalent.

Logs go to stderr so Claude Desktop's per-server log file captures them
(``~/Library/Logs/Claude/mcp-server-ogentic-shield.log`` on macOS).
"""

from __future__ import annotations

import os
import subprocess
import sys


def _ensure_spacy_model() -> None:
    """Download ``en_core_web_lg`` on first launch if not already present.

    Quietly returns if the model is already on the user's system. Streams
    pip's output to stderr so Claude Desktop's log file shows progress
    during the one-time download.
    """
    try:
        import spacy  # noqa: F401
    except ImportError:
        # Should never happen — ogentic-shield depends on spacy via Presidio.
        # If we hit this, the bundle's pyproject.toml or UV resolution failed.
        print(
            "ogentic-shield-mcpb: spaCy is not installed. Did UV finish "
            "resolving dependencies? Check Claude Desktop's MCP server logs.",
            file=sys.stderr,
        )
        raise

    try:
        import en_core_web_lg  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        print(
            "ogentic-shield-mcpb: downloading spaCy en_core_web_lg model "
            "(~600MB, one time)...",
            file=sys.stderr,
            flush=True,
        )
        subprocess.run(
            [sys.executable, "-m", "spacy", "download", "en_core_web_lg"],
            check=True,
            stderr=sys.stderr,
            stdout=sys.stderr,
        )


def _resolve_profiles() -> list[str]:
    """Parse the comma-separated profile list from the env."""
    raw = os.environ.get("OGENTIC_SHIELD_PROFILES", "").strip()
    if not raw:
        return [
            "shield-legal",
            "shield-therapy",
            "shield-therapy-pro",
            "shield-finance",
        ]
    return [p.strip() for p in raw.split(",") if p.strip()]


def main() -> None:
    _ensure_spacy_model()
    from ogentic_shield.mcp import run

    profiles = _resolve_profiles()
    print(
        f"ogentic-shield-mcpb: launching with profiles={profiles}",
        file=sys.stderr,
        flush=True,
    )
    run(transport="stdio", profiles=profiles)


if __name__ == "__main__":
    main()
