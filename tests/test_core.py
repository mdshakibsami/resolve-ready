"""Core tests: probing, presets, encoding and verification."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resolve_ready.core.encoder import encode
from resolve_ready.core.presets import (  # noqa: E402
    DEFAULT_PRESET_ID,
    PRESETS,
    build_command,
    estimate_size_mb,
    get_preset,
)
from resolve_ready.core.probe import (  # noqa: E402
    MediaInfo,
    check_compatibility,
    find_media,
    probe,
)
from resolve_ready.core.settings import (  # noqa: E402
    DEFAULTS,
    SETTINGS_VERSION,
    Settings,
)
from resolve_ready.core.verify import verify_output  # noqa: E402


def make_sample(path: Path, *, audio: bool = True, seconds: int = 1) -> None:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=duration={seconds}:size=320x240:rate=25",
    ]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "96k", "-shortest"]
    cmd.append(str(path))
    subprocess.run(cmd, check=True, capture_output=True)


class SettingsTests(unittest.TestCase):
    def test_conversion_defaults(self) -> None:
        self.assertEqual(DEFAULTS["preset"], "dnxhr_hq")
        self.assertEqual(DEFAULTS["output_mode"], "subfolder")
        self.assertFalse(DEFAULTS["make_backup"])
        self.assertTrue(DEFAULTS["skip_compatible"])

    def test_legacy_settings_reset_conversion_defaults_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "preset": "prores_proxy",
                        "output_mode": "same",
                        "custom_dir": "/tmp/out",
                        "make_backup": True,
                        "skip_compatible": False,
                        "theme": "light",
                        "window_width": 1200,
                        "window_height": 800,
                    }
                ),
                encoding="utf-8",
            )

            settings = Settings(path)

            self.assertEqual(settings.get("preset"), "dnxhr_hq")
            self.assertEqual(settings.get("output_mode"), "subfolder")
            self.assertEqual(settings.get("custom_dir"), "")
            self.assertFalse(settings.get("make_backup"))
            self.assertTrue(settings.get("skip_compatible"))
            self.assertEqual(settings.get("theme"), "light")
            self.assertEqual(settings.get("window_width"), 1200)
            self.assertEqual(settings.get("window_height"), 800)

            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["settings_version"], SETTINGS_VERSION)
            self.assertEqual(saved["preset"], "dnxhr_hq")

    def test_current_settings_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "settings_version": SETTINGS_VERSION,
                        "preset": "prores_proxy",
                        "output_mode": "same",
                        "make_backup": True,
                        "skip_compatible": False,
                    }
                ),
                encoding="utf-8",
            )

            settings = Settings(path)

            self.assertEqual(settings.get("preset"), "prores_proxy")
            self.assertEqual(settings.get("output_mode"), "same")
            self.assertTrue(settings.get("make_backup"))
            self.assertFalse(settings.get("skip_compatible"))


class ProbeTests(unittest.TestCase):
    def test_probe_and_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "sample.mp4"
            make_sample(sample)
            info = probe(sample)

            self.assertEqual((info.width, info.height), (320, 240))
            self.assertEqual(float(info.fps), 25.0)
            self.assertEqual(info.vcodec, "h264")
            self.assertEqual(info.acodec, "aac")
            self.assertTrue(info.has_audio)

            compat = check_compatibility(info)
            self.assertFalse(compat.ready)
            self.assertTrue(any("H264" in r or "H.264" in r for r in compat.reasons))
            self.assertTrue(any("AAC" in r for r in compat.reasons))

    def test_resolve_ready_media_is_compatible(self) -> None:
        info = MediaInfo(
            path=Path("ready.mov"), duration=10.0, width=1920, height=1080,
            fps=Fraction(25, 1), vcodec="dnxhd", vprofile="DNXHR SQ", pix_fmt="yuv422p",
            acodec="pcm_s24le", sample_rate=48000, channels=2,
            container="mov", size=1000, bit_rate=50_000_000,
        )
        self.assertTrue(check_compatibility(info).ready)

    def test_pcm_at_44100_needs_attention(self) -> None:
        info = MediaInfo(
            path=Path("odd.mov"), duration=10.0, width=1280, height=720,
            fps=Fraction(25, 1), vcodec="prores", vprofile="HQ", pix_fmt="yuv422p10le",
            acodec="pcm_s24le", sample_rate=44100, channels=2,
            container="mov", size=1000, bit_rate=50_000_000,
        )
        self.assertFalse(check_compatibility(info).ready)

    def test_find_media_is_recursive_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            sample = root / "sub" / "clip.mp4"
            make_sample(sample, audio=False)
            found = find_media([str(root), str(sample), str(root / "missing.mp4")])
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].resolve(), sample.resolve())


class PresetTests(unittest.TestCase):
    def test_default_preset(self) -> None:
        self.assertEqual(get_preset("dnxhr_sq").profile, "dnxhr_sq")
        self.assertEqual(get_preset("nope").id, DEFAULT_PRESET_ID)

    def test_estimate_size(self) -> None:
        preset = get_preset("dnxhr_sq")
        size = estimate_size_mb(60.0, preset, True)
        self.assertGreater(size, 400)
        self.assertLess(size, 500)

    def test_command_structure(self) -> None:
        info = MediaInfo(
            path=Path("in.mp4"), duration=5.0, width=1280, height=720,
            fps=Fraction(25, 1), vcodec="h264", vprofile="High", pix_fmt="yuv420p",
            acodec="aac", sample_rate=44100, channels=2,
            container="mp4", size=1, bit_rate=1,
        )
        cmd = build_command(Path("in.mp4"), Path("out.mov"), info, get_preset("dnxhr_sq"))
        self.assertIn("-progress", cmd)
        self.assertIn("dnxhr_sq", cmd)
        self.assertIn("pcm_s24le", cmd)
        self.assertIn("48000", cmd)
        self.assertEqual(cmd[-1], "out.mov")


class EncodeTests(unittest.TestCase):
    def test_encode_verify_dnxhr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.mp4"
            make_sample(src)
            info = probe(src)
            out = Path(tmp) / "out.mov"
            seen: list[float] = []

            result = encode(info, get_preset("dnxhr_sq"), out, on_progress=seen.append)
            self.assertTrue(result.ok, result.error)
            self.assertTrue(out.exists())
            if seen:
                self.assertLessEqual(max(seen), 1.0)

            ok, message = verify_output(info, out, get_preset("dnxhr_sq"))
            self.assertTrue(ok, message)

            # A ProRes preset must not validate a DNxHR file.
            ok, _ = verify_output(info, out, get_preset("prores_422"))
            self.assertFalse(ok)

    def test_encode_silent_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "silent.mp4"
            make_sample(src, audio=False)
            info = probe(src)
            self.assertFalse(info.has_audio)
            out = Path(tmp) / "silent.mov"
            result = encode(info, get_preset("dnxhr_lb"), out)
            self.assertTrue(result.ok, result.error)
            ok, message = verify_output(info, out, get_preset("dnxhr_lb"))
            self.assertTrue(ok, message)

    def test_encode_prores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.mp4"
            make_sample(src)
            info = probe(src)
            out = Path(tmp) / "out.mov"
            result = encode(info, get_preset("prores_422"), out)
            self.assertTrue(result.ok, result.error)
            ok, message = verify_output(info, out, get_preset("prores_422"))
            self.assertTrue(ok, message)

    def test_all_presets_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.mp4"
            make_sample(src)
            info = probe(src)
            for preset in PRESETS:
                with self.subTest(preset=preset.id):
                    out = Path(tmp) / f"{preset.id}.mov"
                    result = encode(info, preset, out)
                    self.assertTrue(result.ok, result.error)
                    ok, message = verify_output(info, out, preset)
                    self.assertTrue(ok, message)


if __name__ == "__main__":
    unittest.main()
