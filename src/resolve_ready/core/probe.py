"""ffprobe helpers and media compatibility checks."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

VIDEO_EXTENSIONS = {
    ".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm", ".mts", ".m2ts",
    ".mxf", ".wmv", ".flv", ".3gp", ".ogv", ".mpg", ".mpeg", ".ts",
}

# Codecs DaVinci Resolve (Linux, free edition) can decode for editing.
RESOLVE_VIDEO_CODECS = {"dnxhd", "prores"}
RESOLVE_CONTAINERS = {"mov", "mp4", "mxf"}


class ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    duration: float
    width: int
    height: int
    fps: Fraction
    vcodec: str
    vprofile: str
    pix_fmt: str
    acodec: str | None
    sample_rate: int | None
    channels: int | None
    container: str
    size: int
    bit_rate: int

    @property
    def has_audio(self) -> bool:
        return self.acodec is not None

    @property
    def duration_text(self) -> str:
        total = int(round(self.duration))
        m, s = divmod(total, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @property
    def fps_text(self) -> str:
        if self.fps.denominator == 1:
            return f"{int(self.fps)} fps"
        return f"{float(self.fps):.3f}".rstrip("0").rstrip(".") + " fps"

    @property
    def source_text(self) -> str:
        codec = self.vcodec.upper() if self.vcodec else "?"
        if self.acodec:
            return f"{codec} + {self.acodec.upper()}"
        return f"{codec} (no audio)"


@dataclass(frozen=True)
class Compatibility:
    ready: bool
    reasons: tuple[str, ...]


def _parse_rate(value: str | None) -> Fraction:
    if not value or value in ("0/0", "N/A"):
        return Fraction(0, 1)
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError):
        return Fraction(0, 1)


def probe(path: str | Path) -> MediaInfo:
    """Read media information with ffprobe."""
    path = Path(path)
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as exc:
        raise ProbeError("ffprobe was not found. Install ffmpeg first.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"Timed out while reading {path.name}") from exc

    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()
        raise ProbeError(detail[-1] if detail else f"Could not read {path.name}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"Invalid ffprobe output for {path.name}") from exc

    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and s.get("disposition", {}).get("attached_pic", 0) == 0), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise ProbeError(f"{path.name} has no video stream")

    fmt = data.get("format", {})
    duration = float(video.get("duration") or fmt.get("duration") or 0)
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"

    return MediaInfo(
        path=path,
        duration=duration,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=_parse_rate(rate),
        vcodec=str(video.get("codec_name") or ""),
        vprofile=str(video.get("profile") or ""),
        pix_fmt=str(video.get("pix_fmt") or ""),
        acodec=str(audio.get("codec_name")) if audio else None,
        sample_rate=int(audio.get("sample_rate")) if audio and audio.get("sample_rate") else None,
        channels=int(audio.get("channels")) if audio and audio.get("channels") else None,
        container=str(fmt.get("format_name") or ""),
        size=int(fmt.get("size") or 0),
        bit_rate=int(fmt.get("bit_rate") or 0),
    )


def check_compatibility(info: MediaInfo) -> Compatibility:
    """Explain whether Resolve can edit this file as-is on Linux."""
    reasons: list[str] = []

    if info.vcodec in ("h264", "hevc"):
        reasons.append(f"{info.vcodec.upper()} video is decode-restricted to Resolve Studio on Linux")
    elif info.vcodec == "av1":
        reasons.append("AV1 support in Resolve on Linux is unreliable")
    elif info.vcodec not in RESOLVE_VIDEO_CODECS:
        reasons.append(f"{info.vcodec.upper() or 'Unknown'} video is not a Resolve editing codec")

    if info.has_audio:
        if not info.acodec.startswith("pcm_"):
            reasons.append(f"{info.acodec.upper()} audio is not supported by Resolve Free on Linux")
        elif info.sample_rate != 48000:
            reasons.append(f"Audio is {info.sample_rate} Hz; Resolve expects 48 kHz")

    if info.vcodec in RESOLVE_VIDEO_CODECS and info.container:
        if not any(name in info.container for name in RESOLVE_CONTAINERS):
            reasons.append(f"{info.container} container is not ideal for Resolve")

    return Compatibility(ready=not reasons, reasons=tuple(reasons))


def find_media(paths: list[str | Path]) -> list[Path]:
    """Expand files and directories into a sorted list of video files."""
    found: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            found.extend(
                p for p in sorted(path.rglob("*"))
                if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
            )
        elif path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            found.append(path)

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in found:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique
