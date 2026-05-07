"""`ogentic-shield serve` — start the MCP server.

A thin Click wrapper around `ogentic_shield.mcp.run()`. The actual server
lives in `src/ogentic_shield/mcp/server.py` so it's importable + testable
without going through Click.
"""

from __future__ import annotations

import click


@click.command(name="serve")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"], case_sensitive=False),
    default="stdio",
    show_default=True,
    help="MCP transport. Use 'stdio' for Claude Desktop / Goose / Cursor; "
    "'sse' for network clients.",
)
@click.option(
    "--profile",
    "profiles",
    multiple=True,
    help="Shield profile id to load (repeatable). "
    "Choices: shield-legal, shield-therapy, shield-finance. "
    "Defaults to shield-legal.",
)
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Bind host (SSE only).",
)
@click.option(
    "--port",
    default=8765,
    type=int,
    show_default=True,
    help="Bind port (SSE only).",
)
def serve(transport: str, profiles: tuple[str, ...], host: str, port: int) -> None:
    """Start the ogentic-shield MCP server."""
    from ogentic_shield.mcp import run

    run(
        transport=transport.lower(),
        profiles=list(profiles) if profiles else None,
        host=host,
        port=port,
    )
