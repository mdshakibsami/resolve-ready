"""Verification of encoded files before originals are touched."""

from __future__ import annotations

from pathlib import Path

from .presets import Preset
from .probe import MediaInfo, ProbeError, probe


def verify_output(src: MediaInfo, dst: Path, preset: Preset) -> tuple[bool, str]:
    """Compare an encoded file against its source. Returns (ok, message)."""
    if not dst.exists():
        return False, "output file is missing"
    if dst.stat().st_size < 1024:
        return False, "output file is empty"

    try:
        out = probe(dst)
    except ProbeError as exc:
        return False, f"cannot read output: {exc}"

    expected_codec = "dnxhd" if preset.video_codec == "dnxhd" else "prores"
    if out.vcodec != expected_codec:
        return False, f"video codec is {out.vcodec}, expected {expected_codec}"
    if (out.width, out.height) != (src.width, src.height):
        return False, f"resolution is {out.width}x{out.height}, expected {src.width}x{src.height}"
    if abs(float(out.fps) - float(src.fps)) > 0.01:
        return False, f"frame rate is {out.fps}, expected {src.fps}"
    if out.pix_fmt != preset.pix_fmt:
        return False, f"pixel format is {out.pix_fmt}, expected {preset.pix_fmt}"

    tolerance = max(0.5, 2.0 / float(src.fps or 25))
    if abs(out.duration - src.duration) > tolerance:
        return False, f"duration is {out.duration:.2f}s, expected {src.duration:.2f}s"

    if src.has_audio:
        if not out.has_audio:
            return False, "audio track is missing"
        if out.acodec != preset.audio_codec:
            return False, f"audio codec is {out.acodec}, expected {preset.audio_codec}"
        if out.sample_rate != preset.audio_rate:
            return False, f"audio rate is {out.sample_rate}, expected {preset.audio_rate}"
        if src.channels and out.channels != src.channels:
            return False, f"audio has {out.channels} channels, expected {src.channels}"
    elif out.has_audio:
        return False, "unexpected audio track in output"

    return True, "verified"
