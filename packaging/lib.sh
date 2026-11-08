#!/usr/bin/env bash
# Shared metadata for the packaging scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -z "${VERSION:-}" ]; then
    VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/src/resolve_ready/__init__.py" | head -n 1)"
fi
if [ -z "${VERSION:-}" ]; then
    echo "error: could not determine the project version" >&2
    exit 1
fi

APP_ID="io.github.mdshakibsami.ResolveReady"
APP_NAME="ResolveReady"
PKG_NAME="resolve-ready"

export ROOT VERSION APP_ID APP_NAME PKG_NAME
