"""Encoding presets and ffmpeg command construction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .probe import MediaInfo


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    description: str
    video_codec: str          # ffmpeg encoder name
    profile: str              # encoder profile argument
    pix_fmt: str
    video_mbps: float         # rough bitrate for size estimates
    audio_codec: str = "pcm_s24le"
    audio_rate: int = 48000

    @property
    def extension(self) -> str:
        return ".mov"


PRESETS: tuple[Preset, ...] = (
    Preset("dnxhr_sq", "DNxHR SQ", "Balanced editing quality (recommended)",
           "dnxhd", "dnxhr_sq", "yuv422p", 56.0),
    Preset("dnxhr_lb", "DNxHR LB", "Lightweight offline / proxy quality",
           "dnxhd", "dnxhr_lb", "yuv422p", 19.0),
    Preset("dnxhr_hq", "DNxHR HQ", "High quality, larger files",
           "dnxhd", "dnxhr_hq", "yuv422p", 84.0),
    Preset("dnxhr_hqx", "DNxHR HQX", "10-bit 4:2:2, maximum quality",
           "dnxhd", "dnxhr_hqx", "yuv422p10le", 110.0),
    Preset("prores_proxy", "ProRes 422 Proxy", "Very small ProRes files",
           "prores_ks", "0", "yuv422p10le", 11.0),
    Preset("prores_lt", "ProRes 422 LT", "Light ProRes editing files",
           "prores_ks", "1", "yuv422p10le", 23.0),
    Preset("prores_422", "ProRes 422", "Standard ProRes quality",
           "prores_ks", "2", "yuv422p10le", 34.0),
    Preset("prores_hq", "ProRes 422 HQ", "High quality ProRes",
           "prores_ks", "3", "yuv422p10le", 50.0),
)

DEFAULT_PRESET_ID = "dnxhr_hq"
AUDIO_MBPS = 2.304  # 24-bit stereo @ 48 kHz


def get_preset(preset_id: str) -> Preset:
    for preset in PRESETS:
        if preset.id == preset_id:
            return preset
    return next(p for p in PRESETS if p.id == DEFAULT_PRESET_ID)


def estimate_size_mb(duration: float, preset: Preset, has_audio: bool) -> float:
    mbps = preset.video_mbps + (AUDIO_MBPS if has_audio else 0)
    return mbps * duration / 8.0


def build_command(
    src: Path,
    dst: Path,
    info: MediaInfo,
    preset: Preset,
) -> list[str]:
    """Build the ffmpeg invocation for one conversion.

    The caller writes to a temporary file and renames it after verification.
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-y",
        "-loglevel", "warning",
        "-i", str(src),
        "-map", "0:v:0",
    ]

    if info.has_audio:
        cmd += [
            "-map", "0:a:0",
            "-c:a", preset.audio_codec,
            "-ar", str(preset.audio_rate),
            "-ac", str(info.channels or 2),
        ]

    cmd += [
        "-c:v", preset.video_codec,
        "-profile:v", preset.profile,
        "-pix_fmt", preset.pix_fmt,
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-color_range", "tv",
        "-map_metadata", "0",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        "-nostats",
        str(dst),
    ]
    return cmd
