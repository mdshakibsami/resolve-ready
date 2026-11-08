"""Project metadata, CLI and compatibility tests."""

from __future__ import annotations

import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import resolve_ready  # noqa: E402
from resolve_ready.__main__ import build_parser  # noqa: E402
from resolve_ready.core.probe import MediaInfo  # noqa: E402
from resolve_ready.ui import compat  # noqa: E402


class MetadataTests(unittest.TestCase):
    def test_version_is_semver(self) -> None:
        parts = resolve_ready.__version__.split(".")
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(part.isdigit() for part in parts))

    def test_project_identity(self) -> None:
        self.assertEqual(
            resolve_ready.__app_id__,
            "io.github.mdshakibsami.ResolveReady",
        )
        self.assertTrue(resolve_ready.PROJECT_URL.startswith("https://"))

    def test_support_link_is_optional(self) -> None:
        self.assertNotIn("example", resolve_ready.SUPPORT_URL)
        if resolve_ready.SUPPORT_URL:
            self.assertTrue(resolve_ready.SUPPORT_URL.startswith("https://"))
        self.assertTrue(resolve_ready.SUPPORT_LABEL)

    def test_cli_version_flag(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit) as caught:
            parser.parse_args(["--version"])
        self.assertEqual(caught.exception.code, 0)

    def test_cli_accepts_files(self) -> None:
        args = build_parser().parse_args(["one.mp4", "a folder"])
        self.assertEqual(args.files, ["one.mp4", "a folder"])


class FpsTextTests(unittest.TestCase):
    @staticmethod
    def _info(rate: str) -> MediaInfo:
        return MediaInfo(
            path=Path("clip.mp4"),
            duration=4.0,
            width=1920,
            height=1080,
            fps=Fraction(rate),
            vcodec="h264",
            vprofile="High",
            pix_fmt="yuv420p",
            acodec=None,
            sample_rate=None,
            channels=None,
            container="mov,mp4",
            size=1024,
            bit_rate=1000,
        )

    def test_fractional_rate_has_one_suffix(self) -> None:
        self.assertEqual(self._info("30000/1001").fps_text, "29.97 fps")

    def test_integer_rate_has_one_suffix(self) -> None:
        self.assertEqual(self._info("60/1").fps_text, "60 fps")


class CompatTests(unittest.TestCase):
    def test_detection_flags_are_bool(self) -> None:
        for name in (
            "GTK_HAS_FILE_DIALOG",
            "ADW_HAS_TOOLBAR_VIEW",
            "ADW_HAS_ALERT_DIALOG",
            "ADW_HAS_MESSAGE_DIALOG",
            "ADW_HAS_ABOUT_DIALOG",
            "ADW_HAS_ABOUT_WINDOW",
        ):
            self.assertIsInstance(getattr(compat, name), bool, name)

    def test_helpers_exist(self) -> None:
        for name in (
            "build_toolbar",
            "choose_files",
            "choose_folder",
            "show_alert",
            "show_about",
        ):
            self.assertTrue(callable(getattr(compat, name)), name)


if __name__ == "__main__":
    unittest.main()
