"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .core.settings import state_dir


def setup_logging() -> Path:
    directory = state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    log_file = directory / "resolve-ready.log"
    logging.basicConfig(
        filename=str(log_file),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    def handle_uncaught(exc_type, exc_value, exc_tb) -> None:
        logging.exception("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = handle_uncaught
    return log_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resolve-ready",
        description="Convert video into formats DaVinci Resolve can edit on Linux.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"Resolve Ready {__version__}",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="video files or folders to add to the queue",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging()

    # Import GTK only after argument parsing so --version works headlessly.
    from .app import ResolveReadyApp

    app = ResolveReadyApp()
    program = sys.argv[0] if argv is None else "resolve-ready"
    return app.run([program, *args.files])


if __name__ == "__main__":
    raise SystemExit(main())
