# Ogentic Shield — MCP Bundle

This directory builds `ogentic-shield.mcpb` — a single-file MCP Bundle (MCPB)
that any non-technical user can drop into Claude Desktop, Goose, Cursor, or
any other MCPB-compatible client to get the five `shield.*` tools running
locally.

## End-user install (the whole point)

1. Download `ogentic-shield-0.2.0.mcpb` from the [latest GitHub release](https://github.com/OgenticAI/ogentic-shield/releases/latest).
2. Open Claude Desktop. Settings → Connectors → click the `+` button → "Install from file" → pick the `.mcpb` you just downloaded.
3. First launch downloads the spaCy `en_core_web_lg` model (~600MB) — one-time, ~2 minutes on a normal connection.
4. Restart Claude Desktop. Five `shield.*` tools appear under the new connector.

No git, no Python, no terminal. Claude Desktop's bundled UV runtime handles dependency installation in the background.

## Building the bundle (developers only)

```bash
# One-time: install Anthropic's MCPB CLI
npm install -g @anthropic-ai/mcpb

# From repo root:
./scripts/pack-mcpb.sh
```

The packed file lands at `dist/ogentic-shield-0.2.0.mcpb`. Attach it to a
GitHub release for distribution.

## What the bundle contains

```
ogentic-shield.mcpb (zip)
├── manifest.json       # MCPB v0.4 spec, declares 5 tools + UV runtime
├── pyproject.toml      # Pulls ogentic-shield[mcp,llm] from GitHub main
├── src/
│   └── server.py       # Entry point: spaCy model download + run() shim
└── icon.png            # Bundle icon (optional)
```

The bundle does **not** include:

- The Python interpreter (Claude Desktop's UV runtime provides one).
- The spaCy model (downloaded on first launch — too big to bundle and
  changes shape across spaCy versions anyway).
- An Ollama install (Layer 3 is opt-in; users who want it install Ollama
  separately and pull `granite3.1-moe:1b`).

## What runs where

The user's machine. **Nothing leaves the device.** Same privacy contract as
running `python -m ogentic_shield.mcp` from a clone — the MCPB is a
delivery format, not a different runtime.

## Updating the bundle

When a new ogentic-shield version ships:

1. Bump `version` in both `manifest.json` and `pyproject.toml`.
2. If pinning `ogentic-shield@…` to a tag rather than `main`, update the git
   ref in `pyproject.toml`.
3. Rebuild via `./scripts/pack-mcpb.sh` and attach to the release.

Once `ogentic-shield` lands on PyPI, swap the `git+https://…` reference in
`pyproject.toml` for `ogentic-shield[mcp,llm]>=…` and pin a version range.
