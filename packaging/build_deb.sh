#!/usr/bin/env bash
# Build an installable, dependency-based Debian package.
#
# The package is Architecture: all (pure Python). It is tested on Ubuntu
# 22.04/24.04/26.04 and Debian 12/13 on amd64. Newer releases and derivatives
# are expected to work when they provide the declared dependencies, but are not
# guaranteed until tested.
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

STAGE="$ROOT/build/deb/${PKG_NAME}_${VERSION}_all"
OUT="$ROOT/dist/${PKG_NAME}_${VERSION}_all.deb"

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/lib/resolve-ready" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/scalable/apps" \
         "$STAGE/usr/share/icons/hicolor/256x256/apps" \
         "$STAGE/usr/share/metainfo" \
         "$STAGE/usr/share/man/man1"

# Application code
cp -a "$ROOT/src/resolve_ready" "$STAGE/usr/lib/resolve-ready/"
find "$STAGE/usr/lib/resolve-ready" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$STAGE/usr/lib/resolve-ready" -name '*.pyc' -delete

# Launcher and desktop integration
install -Dm755 "$ROOT/packaging/resolve-ready" "$STAGE/usr/bin/resolve-ready"
install -Dm644 "$ROOT/assets/io.github.mdshakibsami.ResolveReady.desktop" \
    "$STAGE/usr/share/applications/io.github.mdshakibsami.ResolveReady.desktop"
install -Dm644 "$ROOT/assets/resolve-ready.svg" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps/resolve-ready.svg"
install -Dm644 "$ROOT/assets/resolve-ready.png" \
    "$STAGE/usr/share/icons/hicolor/256x256/apps/resolve-ready.png"
install -Dm644 "$ROOT/assets/io.github.mdshakibsami.ResolveReady.metainfo.xml" \
    "$STAGE/usr/share/metainfo/io.github.mdshakibsami.ResolveReady.metainfo.xml"
install -Dm644 "$ROOT/LICENSE" "$STAGE/usr/share/doc/$PKG_NAME/copyright"
mkdir -p "$STAGE/usr/share/man/man1" "$STAGE/usr/share/doc/$PKG_NAME"
gzip -9 -n -c "$ROOT/packaging/resolve-ready.1" > "$STAGE/usr/share/man/man1/resolve-ready.1.gz"
gzip -9 -n -c "$ROOT/packaging/changelog" > "$STAGE/usr/share/doc/$PKG_NAME/changelog.gz"

# Normalize permissions regardless of the developer's umask.
find "$STAGE" -type d -exec chmod 0755 {} +
find "$STAGE" -type f -exec chmod 0644 {} +
chmod 0755 "$STAGE/usr/bin/resolve-ready"

INSTALLED_SIZE="$(du -sk "$STAGE" | cut -f1)"

cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $VERSION
Section: video
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, libgtk-4-1 (>= 4.6), libadwaita-1-0 (>= 1.1), ffmpeg
Installed-Size: $INSTALLED_SIZE
Maintainer: MD Shakib <126575973+mdshakibsami@users.noreply.github.com>
Homepage: https://github.com/mdshakibsami/resolve-ready
Description: Convert video for DaVinci Resolve on Linux
 Resolve Ready transcodes H.264, H.265 and AAC footage into DNxHR or
 ProRes video with 24-bit PCM audio, which DaVinci Resolve can read on
 Linux. It verifies every output and keeps the originals.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
exit 0
EOF

cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

# dpkg-deb does not generate checksums on its own.
(cd "$STAGE" && find usr -type f -print0 | sort -z | xargs -0 md5sum > DEBIAN/md5sums)
chmod 644 "$STAGE/DEBIAN/md5sums"

mkdir -p "$ROOT/dist"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT"

echo
echo "Built: $OUT"
dpkg-deb --info "$OUT"
echo
echo "Install with:"
echo "  sudo apt install \"$OUT\""
