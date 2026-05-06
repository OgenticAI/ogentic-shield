"""MCP (Model Context Protocol) server for ogentic-shield.

Exposes the Shield pipeline as MCP tools so any MCP client — Claude Desktop,
Goose, Cursor, Gyri, Continue, etc. — can mount Shield with a single config
line and get sensitivity detection on tap.

Tools (v0.2):
    shield.analyze    → run a profile-aware analysis pass
    shield.redact     → run analysis + redact identifying entities
    shield.profiles   → list available shield profiles

Run:
    python -m ogentic_shield.mcp                     # stdio (default)
    python -m ogentic_shield.mcp --transport sse     # SSE on port 8765
    ogentic-shield serve                             # equivalent CLI form
"""

from ogentic_shield.mcp.server import build_server, run

__all__ = ["build_server", "run"]
