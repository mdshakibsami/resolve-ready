#!/usr/bin/env bash
# Runs inside the packaging/appimage Docker image.
set -euo pipefail

: "${VERSION:?VERSION must be set}"

cd /work
rm -rf AppDir ./*.AppImage
cp /src/packaging/appimage/recipe.yml /work/recipe.yml

echo "Building self-contained AppImage for Resolve Ready ${VERSION}…"
/opt/appimage-builder.AppImage --recipe /work/recipe.yml

mkdir -p /out
shopt -s nullglob
artifacts=(./*.AppImage)
if [ ${#artifacts[@]} -eq 0 ]; then
    echo "error: appimage-builder did not produce an AppImage" >&2
    exit 1
fi
cp -f "${artifacts[@]}" /out/
chmod 755 /out/*.AppImage
echo
echo "Built:"
ls -lh /out/*.AppImage
