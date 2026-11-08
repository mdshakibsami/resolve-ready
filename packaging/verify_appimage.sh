#!/usr/bin/env bash
# Verify that an AppImage's bundled ffmpeg produces correct colours.
#
# FFmpeg 6.1.2's C-only 8-bit DNxHR encoder corrupts chroma and creates
# magenta/green bars.  This check runs the AppImage's own Python and ffmpeg
# against a synthetic H.264/AAC clip, then compares the result with the source.
#
# The host needs ffmpeg, ffprobe and python3; the AppImage is not installed and
# is extracted into a temporary directory.
set -euo pipefail

APPIMAGE="${1:-}"
if [ -z "$APPIMAGE" ] || [ ! -f "$APPIMAGE" ]; then
    echo "usage: $0 path/to/ResolveReady-*.AppImage" >&2
    exit 2
fi
APPIMAGE="$(readlink -f "$APPIMAGE")"
if [ ! -x "$APPIMAGE" ]; then
    echo "error: AppImage is not executable: $APPIMAGE" >&2
    exit 2
fi
for tool in ffmpeg ffprobe python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "error: $tool is required to verify the AppImage" >&2
        exit 2
    fi
done

WORK="$(mktemp -d "${TMPDIR:-/tmp}/resolve-ready-verify.XXXXXX")"
cleanup() {
    rm -rf "$WORK"
}
trap cleanup EXIT

echo "Extracting $(basename "$APPIMAGE")…"
(
    cd "$WORK"
    "$APPIMAGE" --appimage-extract >/dev/null
)
APPDIR="$WORK/squashfs-root"
if [ ! -x "$APPDIR/AppRun" ]; then
    echo "error: AppImage extraction did not produce AppRun" >&2
    exit 1
fi

# AppRun normally starts the GUI.  Switch it to a shell for this isolated
# extracted copy so the bundled Python/ffmpeg can be invoked directly.
sed -i \
    -e 's|^APPDIR_EXEC_PATH=.*|APPDIR_EXEC_PATH=/bin/sh|' \
    -e 's|^APPDIR_EXEC_ARGS=.*|APPDIR_EXEC_ARGS=$@|' \
    "$APPDIR/AppRun.env"

ffmpeg -hide_banner -nostdin -y -loglevel error \
    -f lavfi -i "testsrc2=size=640x360:rate=25:duration=2" \
    -f lavfi -i "sine=frequency=440:sample_rate=44100:duration=2" \
    -c:v mpeg4 -q:v 2 -c:a aac -shortest \
    "$WORK/source.mp4"

cat > "$WORK/encode.py" <<'PY'
import os
from pathlib import Path

from resolve_ready.core.encoder import encode
from resolve_ready.core.presets import get_preset
from resolve_ready.core.probe import probe

source = Path(os.environ["VERIFY_SOURCE"])
output = Path(os.environ["VERIFY_OUTPUT"])
preset = get_preset(os.environ["VERIFY_PRESET"])
info = probe(source)
print(
    "source:",
    info.vcodec,
    info.acodec,
    f"{info.width}x{info.height}",
    f"{float(info.fps):.3f} fps",
)
result = encode(info, preset, output)
if not result.ok:
    raise SystemExit(f"{preset.id} encoding failed: {result.error}\n{result.log_tail}")
print("encoded:", preset.id, output, output.stat().st_size, "bytes")
PY

cat > "$WORK/inner.sh" <<'SH'
#!/bin/sh
set -eu
VERIFY_SOURCE="$1" VERIFY_OUTPUT="$2" VERIFY_PRESET="$3" python3 "$4"
SH
chmod +x "$WORK/inner.sh"

for PRESET in dnxhr_lb dnxhr_sq dnxhr_hq dnxhr_hqx prores_422; do
    OUTPUT="$WORK/output-$PRESET.mov"
    echo "Encoding $PRESET with the bundled Python and ffmpeg…"
    (
        cd "$APPDIR"
        ./AppRun "$WORK/inner.sh" "$WORK/source.mp4" "$OUTPUT" "$PRESET" "$WORK/encode.py"
    )

    VIDEO_CODEC="$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=codec_name -of csv=p=0 "$OUTPUT")"
    AUDIO_CODEC="$(ffprobe -v error -select_streams a:0 \
        -show_entries stream=codec_name -of csv=p=0 "$OUTPUT")"
    case "$PRESET" in
        dnxhr_*) EXPECTED_VIDEO="dnxhd" ;;
        prores_*) EXPECTED_VIDEO="prores" ;;
    esac
    if [ "$VIDEO_CODEC" != "$EXPECTED_VIDEO" ] || [ "$AUDIO_CODEC" != "pcm_s24le" ]; then
        echo "error: $PRESET produced unexpected streams: video=$VIDEO_CODEC audio=$AUDIO_CODEC" >&2
        exit 1
    fi

    SSIM_LOG="$WORK/ssim-$PRESET.log"
    ffmpeg -hide_banner -nostdin -i "$WORK/source.mp4" -i "$OUTPUT" \
        -lavfi "[0:v][1:v]ssim" -f null - >"$SSIM_LOG" 2>&1 || {
            tail -40 "$SSIM_LOG" >&2
            echo "error: $PRESET frame comparison failed" >&2
            exit 1
        }
    SSIM="$(sed -n 's/.* All:\([0-9.]*\).*/\1/p' "$SSIM_LOG" | tail -n 1)"
    if [ -z "$SSIM" ]; then
        tail -40 "$SSIM_LOG" >&2
        echo "error: could not read SSIM score for $PRESET" >&2
        exit 1
    fi
    python3 - "$PRESET" "$SSIM" <<'PY'
import sys

preset, ssim = sys.argv[1], float(sys.argv[2])
# Correct DNxHR/ProRes round trips are near 0.99.  The FFmpeg C-only 8-bit
# DNxHR bug produced a score around 0.61.
if ssim < 0.90:
    raise SystemExit(
        f"error: {preset} frame quality is too low (SSIM {ssim:.4f} < 0.90)"
    )
print(f"{preset}: SSIM {ssim:.4f}")
PY
done

echo "AppImage frame-quality check passed for all presets."
