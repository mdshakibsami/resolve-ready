"""Run ffmpeg conversions with progress reporting and cancellation."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .presets import Preset, build_command
from .probe import MediaInfo

ProgressCallback = Callable[[float], None]


@dataclass
class EncodeResult:
    ok: bool
    cancelled: bool = False
    error: str = ""
    log_tail: str = ""


def _signal_group(proc: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except (ProcessLookupError, PermissionError):
        try:
            proc.send_signal(sig)
        except ProcessLookupError:
            pass


def encode(
    info: MediaInfo,
    preset: Preset,
    dst: Path,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> EncodeResult:
    """Encode one file to a temporary destination."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()

    cmd = build_command(info.path, dst, info, preset)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError:
        return EncodeResult(False, error="ffmpeg was not found. Install ffmpeg first.")

    stderr_lines: list[str] = []

    def drain_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_lines.append(line.rstrip())
            if len(stderr_lines) > 400:
                del stderr_lines[:200]

    reader = threading.Thread(target=drain_stderr, daemon=True)
    reader.start()

    cancelled = False
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                _signal_group(proc, signal.SIGINT)
                break
            line = raw.strip()
            if line.startswith("out_time_us="):
                try:
                    micros = int(line.split("=", 1)[1])
                except (ValueError, IndexError):
                    continue
                if micros >= 0 and info.duration > 0 and on_progress:
                    on_progress(min(0.99, micros / 1_000_000.0 / info.duration))
            elif line == "progress=end" and on_progress:
                on_progress(1.0)
    finally:
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            _signal_group(proc, signal.SIGKILL)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        reader.join(timeout=3)
        for stream in (proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass

    tail = "\n".join(stderr_lines[-20:])

    if cancelled:
        dst.unlink(missing_ok=True)
        return EncodeResult(False, cancelled=True, error="Cancelled", log_tail=tail)

    if proc.returncode != 0:
        dst.unlink(missing_ok=True)
        return EncodeResult(
            False,
            error=f"ffmpeg exited with code {proc.returncode}",
            log_tail=tail,
        )

    if not dst.exists() or dst.stat().st_size < 1024:
        dst.unlink(missing_ok=True)
        return EncodeResult(False, error="ffmpeg produced no usable output", log_tail=tail)

    return EncodeResult(True, log_tail=tail)
