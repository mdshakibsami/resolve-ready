"""Application object and lifecycle."""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from . import (  # noqa: E402
    PROJECT_URL,
    SUPPORT_LABEL,
    SUPPORT_URL,
    __app_id__,
    __version__,
)
from .core.settings import Settings  # noqa: E402
from .ui import compat  # noqa: E402
from .ui.window import MainWindow  # noqa: E402


class ResolveReadyApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self.settings = Settings()
        self.window: MainWindow | None = None

    # ------------------------------------------------------------- lifecycle
    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        Gtk.Window.set_default_icon_name("resolve-ready")
        self._install_css()
        self.apply_theme(self.settings.get("theme"))
        self._install_actions()
        self.set_accels_for_action("win.add-files", ["<Control>o"])
        self.set_accels_for_action("win.add-folder", ["<Control><Shift>o"])
        self.set_accels_for_action("win.convert", ["<Control>Return"])
        self.set_accels_for_action("win.remove", ["Delete"])
        self.set_accels_for_action("app.quit", ["<Control>q"])

    def do_activate(self) -> None:
        self._ensure_window()
        self.window.present()

    def do_open(self, files, _n_files: int, _hint: str) -> None:
        self._ensure_window()
        paths = [gfile.get_path() for gfile in files if gfile.get_path()]
        if paths:
            self.window.add_paths(paths)
        self.window.present()

    def _ensure_window(self) -> MainWindow:
        if self.window is None:
            self.window = MainWindow(application=self, settings=self.settings)
        return self.window

    # ----------------------------------------------------------------- theme
    def apply_theme(self, theme: str, *, save: bool = False) -> None:
        """Apply dark or light mode to the whole application."""
        theme = "light" if theme == "light" else "dark"
        scheme = (
            Adw.ColorScheme.FORCE_LIGHT
            if theme == "light"
            else Adw.ColorScheme.FORCE_DARK
        )
        Adw.StyleManager.get_default().set_color_scheme(scheme)
        self.settings.set("theme", theme)
        if save:
            self.settings.save()

    # ----------------------------------------------------------------- setup
    def _install_css(self) -> None:
        css_path = Path(__file__).with_name("style.css")
        if not css_path.exists():
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        self._install_accent_vars(display)

    @staticmethod
    def _install_accent_vars(display) -> None:
        """Keep native libadwaita widgets on the tungsten-orange accent.

        libadwaita 1.9 exposes semantic colors as CSS variables, while older
        versions read the @accent_bg_color named color directly. The named
        color override lives in style.css; this provider handles the newer
        versions without breaking GTK 4.10 setups.
        """
        if display is None or (Gtk.get_major_version(), Gtk.get_minor_version()) < (4, 16):
            return
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"""
            :root {
              --accent-bg-color: #e06f2f;
              --accent-fg-color: #1f1107;
              --accent-color: #c95a1d;
            }
            """,
            -1,
        )
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
        )

    def _install_actions(self) -> None:
        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", lambda *_args: self._show_about())
        self.add_action(about)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_args: self.quit())
        self.add_action(quit_action)

    def _show_about(self) -> None:
        parent = self.window
        if parent is None:
            return
        compat.show_about(
            parent,
            application_name="Resolve Ready",
            application_icon="resolve-ready",
            version=__version__,
            developer_name="MD Shakib",
            comments=(
                "Convert camera footage into formats DaVinci Resolve can edit on Linux. "
                "Video becomes DNxHR or ProRes; audio becomes 24-bit PCM at 48 kHz. "
                "Every output is verified against its source. Originals are kept."
            ),
            developers=["MD Shakib"],
            license_type=Gtk.License.MIT_X11,
            website=PROJECT_URL,
            support_url=SUPPORT_URL,
            support_label=SUPPORT_LABEL,
        )
