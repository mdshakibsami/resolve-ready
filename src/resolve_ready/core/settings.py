"""Persistent application settings."""

from __future__ import annotations

import json
import os
from pathlib import Path

SETTINGS_VERSION = 3

DEFAULTS: dict = {
    "settings_version": SETTINGS_VERSION,
    "preset": "dnxhr_hq",
    "output_mode": "subfolder",      # same | subfolder | custom
    "custom_dir": "",
    "make_backup": False,
    "skip_compatible": True,
    "theme": "dark",                # dark | light
    "window_width": 980,
    "window_height": 720,
}

# Conversion defaults are reset once when an older settings file is upgraded.
# Theme and window size stay untouched.
UPGRADE_DEFAULT_KEYS = (
    "preset",
    "output_mode",
    "custom_dir",
    "make_backup",
    "skip_compatible",
)


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "resolve-ready"


class Settings:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "settings.json"
        self.values = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return

        stored_version = data.get("settings_version", 1)
        if not isinstance(stored_version, int):
            stored_version = 1

        for key in DEFAULTS:
            if key in data and isinstance(data[key], type(DEFAULTS[key])):
                self.values[key] = data[key]
            elif key in data:
                # Allow int/float interchange for window sizes.
                if isinstance(DEFAULTS[key], int) and isinstance(data[key], (int, float)):
                    self.values[key] = int(data[key])

        if stored_version < SETTINGS_VERSION:
            for key in UPGRADE_DEFAULT_KEYS:
                self.values[key] = DEFAULTS[key]
            self.values["settings_version"] = SETTINGS_VERSION
            try:
                self.save()
            except OSError:
                # A read-only config directory should not stop the app.
                pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        part = self.path.with_name(self.path.name + ".part")
        part.write_text(json.dumps(self.values, indent=2), encoding="utf-8")
        part.replace(self.path)

    def get(self, key: str):
        return self.values.get(key, DEFAULTS.get(key))

    def set(self, key: str, value) -> None:
        self.values[key] = value


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "resolve-ready"
