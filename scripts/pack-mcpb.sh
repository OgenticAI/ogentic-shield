#!/usr/bin/env bash
# Build ogentic-shield-<version>.mcpb from the mcpb/ scaffold.
#
# Requires: @anthropic-ai/mcpb (`npm install -g @anthropic-ai/mcpb`).
# Output:   dist/ogentic-shield-<version>.mcpb
#
# Run from the repo root: `./scripts/pack-mcpb.sh`.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUNDLE_SRC="${REPO_ROOT}/mcpb"
DIST_DIR="${REPO_ROOT}/dist"

if ! command -v mcpb >/dev/null 2>&1; then
    echo "ERROR: mcpb CLI not found." >&2
    echo "Install it once with: npm install -g @anthropic-ai/mcpb" >&2
    exit 1
fi

VERSION="$(python3 -c "
import json, sys
with open('${BUNDLE_SRC}/manifest.json') as f:
    print(json.load(f)['version'])
")"

mkdir -p "${DIST_DIR}"
OUT="${DIST_DIR}/ogentic-shield-${VERSION}.mcpb"

echo "Packing ${BUNDLE_SRC} → ${OUT}"
# `mcpb pack <source-dir> [output-file]` zips the directory and validates
# the manifest. We pass an explicit output path so it lands in dist/.
mcpb pack "${BUNDLE_SRC}" "${OUT}"

echo
echo "Bundle ready:"
ls -lh "${OUT}"
echo
echo "Distribute by attaching this file to a GitHub release."
echo "Users install via Claude Desktop → Connectors → + → Install from file."
