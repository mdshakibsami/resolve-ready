#!/usr/bin/env bash
# Build a fully self-contained AppImage (Python, GTK4, libadwaita, ffmpeg).
#
# The build runs in an Ubuntu 22.04 container so the result runs on Ubuntu
# 22.04+, Debian 12+, Fedora 36+ and Arch (glibc 2.35 floor).
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

DOCKER="${DOCKER:-docker}"
IMAGE="resolve-ready-appimage:${VERSION}"

if ! command -v "$DOCKER" >/dev/null 2>&1; then
    echo "error: Docker is required to build the self-contained AppImage." >&2
    echo "Install Docker or build the .deb with ./packaging/build_deb.sh." >&2
    exit 1
fi

mkdir -p "$ROOT/dist"

echo "Building container image (Ubuntu 22.04)…"
"$DOCKER" build --network host \
    -f "$ROOT/packaging/appimage/Dockerfile" \
    -t "$IMAGE" "$ROOT"

echo "Building AppImage…"
"$DOCKER" run --rm --network host \
    -e VERSION="$VERSION" \
    -v "$ROOT/dist:/out" \
    "$IMAGE"

# The file is created by the container (usually owned by root) but is already
# executable.  Make it executable when the host user owns it, and ignore EPERM.
chmod +x "$ROOT/dist/ResolveReady-${VERSION}-x86_64.AppImage" 2>/dev/null || true

echo
echo "Run with:"
echo "  ./dist/ResolveReady-${VERSION}-x86_64.AppImage"
