"""Main application window."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

from ..core.backup import create_backup  # noqa: E402
from ..core.encoder import encode  # noqa: E402
from ..core.presets import (  # noqa: E402
    DEFAULT_PRESET_ID,
    PRESETS,
    estimate_size_mb,
)
from ..core.probe import (  # noqa: E402
    MediaInfo,
    check_compatibility,
    find_media,
    probe,
)
from .. import SUPPORT_LABEL, SUPPORT_URL  # noqa: E402
from ..core.settings import Settings  # noqa: E402
from ..core.verify import verify_output  # noqa: E402
from . import compat  # noqa: E402
from .job import JobItem  # noqa: E402

log = logging.getLogger("resolve_ready")

OUTPUT_MODES = ("same", "subfolder", "custom")

PHASE_IDLE = "idle"
PHASE_RUNNING = "running"
PHASE_FINISHED = "finished"

PAGE_MARGIN = 20
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24

CODEC_LABELS = {
    "h264": "H.264",
    "hevc": "HEVC",
    "dnxhd": "DNxHR",
    "prores": "ProRes",
    "av1": "AV1",
    "vp9": "VP9",
    "mpeg4": "MPEG-4",
}


def _codec_label(codec: str) -> str:
    return CODEC_LABELS.get(codec, codec.upper() if codec else "?")


def _human_duration(seconds: float) -> str:
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _film_image(size: int) -> Gtk.Image:
    """Return the bundled film-strip icon at a predictable size."""
    path = Path(__file__).with_name("film-symbolic.svg")
    if path.exists():
        try:
            image = Gtk.Image.new_from_pixbuf(
                GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, True)
            )
            image.set_pixel_size(size)
            image.set_size_request(size, size)
            return image
        except GLib.Error:
            pass
    image = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
    image.set_pixel_size(size)
    return image


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, settings: Settings, **kwargs) -> None:
        super().__init__(**kwargs)
        self.settings = settings
        self.store = Gio.ListStore(item_type=JobItem)
        self.selection = Gtk.SingleSelection(model=self.store)
        self.cancel_event = threading.Event()
        self.running = False
        self.phase = PHASE_IDLE
        self.completed_outputs: list[Path] = []
        self._batch_total = 0
        self._batch_done = 0
        self._batch_index = 0
        self._batch_failures = 0
        self._batch_cancelled = 0
        self._scan_threads: list[threading.Thread] = []

        self.set_default_size(settings.get("window_width"), settings.get("window_height"))
        self.set_size_request(760, 620)
        self.set_title("Resolve Ready")

        self._build_actions()
        self._build_ui()
        self._apply_settings()
        self._update_summary()
        self.connect("close-request", self._on_close_request)

    # ------------------------------------------------------------------ UI
    def _build_actions(self) -> None:
        actions = [
            ("add-files", self._choose_files),
            ("add-folder", self._choose_folder),
            ("remove", self._remove_selected),
            ("clear", self._clear_queue),
            ("convert", self._start_conversion),
            ("cancel", self._cancel_conversion),
        ]
        if SUPPORT_URL:
            actions.append(("support", self._open_support))
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, cb=callback: cb())
            self.add_action(action)

    def _build_ui(self) -> None:
        header = self._build_header()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE_LG)
        root.set_margin_top(PAGE_MARGIN)
        root.set_margin_bottom(PAGE_MARGIN)
        root.set_margin_start(PAGE_MARGIN)
        root.set_margin_end(PAGE_MARGIN)

        root.append(self._build_source_card())
        root.append(self._build_settings_card())
        root.append(self._build_queue_section())
        root.append(self._build_footer())

        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(root)
        self.set_content(compat.build_toolbar(header, self.toast_overlay))

        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("enter", self._on_drag_enter)
        drop_target.connect("leave", self._on_drag_leave)
        drop_target.connect("drop", self._on_drop)
        self.add_controller(drop_target)

    def _build_header(self) -> Adw.HeaderBar:
        header = Adw.HeaderBar()
        title = Adw.WindowTitle(title="Resolve Ready", subtitle="Prepare video for DaVinci Resolve")
        header.set_title_widget(title)

        self.theme_button = Gtk.Button()
        self.theme_button.add_css_class("flat")
        self.theme_button.add_css_class("circular")
        self.theme_button.connect("clicked", lambda _b: self._toggle_theme())
        header.pack_end(self.theme_button)

        menu = Gio.Menu()
        if SUPPORT_URL:
            menu.append(SUPPORT_LABEL, "win.support")
        menu.append("About Resolve Ready", "app.about")
        self.menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        self.menu_button.set_menu_model(menu)
        self.menu_button.add_css_class("flat")
        self.menu_button.add_css_class("circular")
        self.menu_button.set_tooltip_text("Main menu")
        header.pack_end(self.menu_button)
        return header

    def _build_source_card(self) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE_MD)
        card.add_css_class("rr-card")
        card.add_css_class("rr-source-card")
        self.drop_card = card

        tile = Gtk.CenterBox()
        tile.add_css_class("rr-icon-tile")
        tile.set_halign(Gtk.Align.CENTER)
        tile.set_valign(Gtk.Align.CENTER)
        icon = _film_image(28)
        tile.set_center_widget(icon)
        card.append(tile)

        self.drop_title = Gtk.Label(label="Import any videos here", xalign=0.5)
        self.drop_title.add_css_class("rr-card-title")
        self.drop_title.set_halign(Gtk.Align.CENTER)
        self.drop_title.set_justify(Gtk.Justification.CENTER)
        card.append(self.drop_title)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE_SM)
        actions.set_halign(Gtk.Align.CENTER)
        actions.set_valign(Gtk.Align.CENTER)
        self.add_files_button = self._labeled_button("Add Files", "document-open-symbolic")
        self.add_files_button.add_css_class("rr-upload-button")
        self.add_files_button.connect("clicked", lambda _b: self._choose_files())
        self.add_folder_button = self._labeled_button("Add Folder", "folder-open-symbolic")
        self.add_folder_button.add_css_class("rr-folder-button")
        self.add_folder_button._rr_icon.add_css_class("rr-folder-icon")
        self.add_folder_button.connect("clicked", lambda _b: self._choose_folder())
        actions.append(self.add_files_button)
        actions.append(self.add_folder_button)
        card.append(actions)
        return card

    def _build_settings_card(self) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE_XL)
        card.add_css_class("rr-card")
        card.add_css_class("rr-settings-card")
        self.settings_card = card

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE_MD)
        left.set_hexpand(True)
        left.append(self._section_title("Conversion"))
        left.append(self._format_row())
        left.append(self._output_row())
        self.custom_dir_label = Gtk.Label(xalign=0)
        self.custom_dir_label.add_css_class("rr-custom-path")
        self.custom_dir_label.set_wrap(True)
        self.custom_dir_label.set_margin_start(82)
        self.custom_dir_label.set_visible(False)
        left.append(self.custom_dir_label)
        card.append(left)

        card.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE_SM)
        right.set_size_request(300, -1)
        right.append(self._section_title("Safety"))

        self.backup_switch = Gtk.Switch()
        right.append(self._switch_row(self.backup_switch, "Archive originals (.tar)"))
        self.skip_switch = Gtk.Switch()
        right.append(self._switch_row(self.skip_switch, "Skip compatible files"))
        card.append(right)
        return card

    def _format_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE_MD)
        label = Gtk.Label(label="Format", xalign=0)
        label.add_css_class("rr-field-label")
        label.set_size_request(70, -1)
        self.preset_dropdown = Gtk.DropDown.new_from_strings([p.label for p in PRESETS])
        self.preset_dropdown.set_hexpand(True)
        self.preset_dropdown.set_tooltip_text("Intermediate codec written by ffmpeg")
        self.preset_dropdown.connect("notify::selected", self._on_preset_changed)
        row.append(label)
        row.append(self.preset_dropdown)
        return row

    def _output_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE_MD)
        label = Gtk.Label(label="Save to", xalign=0)
        label.add_css_class("rr-field-label")
        label.set_size_request(70, -1)
        self.output_dropdown = Gtk.DropDown.new_from_strings(
            ["Same folder", "“Resolve Ready” subfolder", "Custom folder…"]
        )
        self.output_dropdown.set_hexpand(True)
        self.output_dropdown.connect("notify::selected", self._on_output_changed)
        row.append(label)
        row.append(self.output_dropdown)
        return row

    def _switch_row(self, switch: Gtk.Switch, title: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.add_css_class("rr-switch-row")
        switch.set_valign(Gtk.Align.CENTER)
        row.append(switch)
        title_label = Gtk.Label(label=title, xalign=0)
        title_label.add_css_class("rr-switch-title")
        row.append(title_label)
        return row

    @staticmethod
    def _section_title(text: str) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("rr-section-title")
        return label

    @staticmethod
    def _labeled_button(label: str, icon_name: str) -> Gtk.Button:
        """Build an icon + text button whose label can be updated later."""
        button = Gtk.Button()
        button.add_css_class("image-text-button")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        image = Gtk.Image.new_from_icon_name(icon_name)
        image.set_pixel_size(16)
        text = Gtk.Label(label=label)
        box.append(image)
        box.append(text)
        button.set_child(box)
        button._rr_icon = image
        button._rr_label = text
        return button

    def _build_queue_section(self) -> Gtk.Box:
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE_SM)
        section.set_vexpand(True)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE_SM)
        title = Gtk.Label(label="Queue", xalign=0)
        title.add_css_class("heading")
        self.queue_count_label = Gtk.Label(label="0 files")
        self.queue_count_label.add_css_class("rr-count-pill")
        self.queue_count_label.set_valign(Gtk.Align.CENTER)
        header.append(title)
        header.append(self.queue_count_label)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)

        self.clear_button = Gtk.Button()
        self.clear_button.set_icon_name("edit-clear-all-symbolic")
        self.clear_button.add_css_class("flat")
        self.clear_button.add_css_class("circular")
        self.clear_button.set_tooltip_text("Clear queue")
        self.clear_button.connect("clicked", lambda _b: self._clear_queue())
        header.append(self.clear_button)
        section.append(header)

        self.queue_stack = Gtk.Stack()
        self.queue_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.queue_stack.set_transition_duration(150)
        self.queue_stack.set_vexpand(True)

        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE_SM)
        empty.add_css_class("rr-card")
        empty.add_css_class("rr-empty-state")
        empty.set_halign(Gtk.Align.FILL)
        empty.set_valign(Gtk.Align.FILL)
        empty.set_vexpand(True)
        empty_tile = Gtk.CenterBox()
        empty_tile.add_css_class("rr-empty-icon-tile")
        empty_tile.set_halign(Gtk.Align.CENTER)
        empty_tile.set_valign(Gtk.Align.CENTER)
        empty_tile.set_center_widget(_film_image(22))
        empty_title = Gtk.Label(label="No footage queued")
        empty_title.add_css_class("rr-empty-title")
        empty_subtitle = Gtk.Label(label="Drop files above or add a folder to begin.")
        empty_subtitle.add_css_class("rr-empty-subtitle")
        empty.append(empty_tile)
        empty.append(empty_title)
        empty.append(empty_subtitle)
        self.queue_stack.add_named(empty, "empty")

        self.column_view = Gtk.ColumnView(model=self.selection)
        self.column_view.add_css_class("rr-queue-view")
        if hasattr(self.column_view, "set_show_row_separators"):
            self.column_view.set_show_row_separators(True)
        self._add_column("Name", self._bind_name, expand=True)
        self._add_column("Duration", self._bind_duration, width=80)
        self._add_column("Source", self._bind_source, width=190)
        self._add_column("Status", self._bind_status, width=180, setup=self._setup_status)
        self._add_column("Progress", self._bind_progress, width=120, setup=self._setup_progress)

        scroller = Gtk.ScrolledWindow()
        scroller.add_css_class("rr-queue")
        scroller.set_child(self.column_view)
        scroller.set_vexpand(True)
        scroller.set_min_content_height(180)
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.queue_stack.add_named(scroller, "queue")
        section.append(self.queue_stack)
        return section

    def _build_footer(self) -> Gtk.Box:
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SPACE_SM)
        footer.add_css_class("rr-card")
        footer.add_css_class("rr-footer")

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACE_MD)
        self.summary_label = Gtk.Label(label="", xalign=0)
        self.summary_label.add_css_class("rr-summary")
        self.summary_label.set_hexpand(True)
        self.summary_label.set_wrap(True)

        self.convert_button = self._labeled_button("Convert", "media-playback-start-symbolic")
        self.convert_button.add_css_class("suggested-action")
        self.convert_button.set_size_request(150, -1)
        self.convert_button.connect("clicked", lambda _b: self._start_conversion())

        self.secondary_button = self._labeled_button("Cancel", "process-stop-symbolic")
        self.secondary_button.set_size_request(130, -1)
        self.secondary_button.set_sensitive(False)
        self.secondary_button.connect("clicked", lambda _b: self._cancel_conversion())

        row.append(self.summary_label)
        row.append(self.convert_button)
        row.append(self.secondary_button)
        footer.append(row)

        self.batch_bar = Gtk.ProgressBar()
        self.batch_bar.add_css_class("rr-batch-progress")
        self.batch_bar.set_show_text(False)
        self.batch_bar.set_visible(False)
        footer.append(self.batch_bar)
        return footer

    def _add_column(self, title, bind_func, width=None, expand=False, setup=None) -> None:
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", setup or self._setup_label)
        factory.connect("bind", bind_func)
        factory.connect("unbind", self._unbind_cell)
        column = Gtk.ColumnViewColumn(title=title, factory=factory)
        column.set_resizable(True)
        if width:
            column.set_fixed_width(width)
        if expand:
            column.set_expand(True)
        self.column_view.append_column(column)

    @staticmethod
    def _setup_label(_factory, list_item) -> None:
        label = Gtk.Label(xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_margin_start(6)
        label.set_margin_end(6)
        list_item.set_child(label)

    @staticmethod
    def _setup_status(_factory, list_item) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.add_css_class("rr-status-pill")
        box.set_halign(Gtk.Align.START)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_start(6)
        box.set_margin_end(6)
        dot = Gtk.Box()
        dot.add_css_class("rr-status-dot")
        dot.set_valign(Gtk.Align.CENTER)
        label = Gtk.Label(xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(dot)
        box.append(label)
        list_item.set_child(box)
        list_item._status_box = box
        list_item._status_label = label

    @staticmethod
    def _setup_progress(_factory, list_item) -> None:
        bar = Gtk.ProgressBar()
        bar.add_css_class("rr-queue-progress")
        bar.set_valign(Gtk.Align.CENTER)
        bar.set_margin_start(6)
        bar.set_margin_end(10)
        bar.set_show_text(False)
        list_item.set_child(bar)

    @staticmethod
    def _unbind_cell(_factory, list_item) -> None:
        for attr in ("_notify_handler", "_notify_handler2"):
            handler = getattr(list_item, attr, None)
            if handler:
                obj, hid = handler
                try:
                    obj.disconnect(hid)
                except (TypeError, ValueError):
                    pass
                setattr(list_item, attr, None)

    @staticmethod
    def _bind_name(_factory, list_item) -> None:
        job = list_item.get_item()
        label = list_item.get_child()
        label.set_text(job.name)
        label.set_tooltip_text(str(job.path))

    @staticmethod
    def _bind_duration(_factory, list_item) -> None:
        job = list_item.get_item()
        label = list_item.get_child()
        label.set_text(job.duration)

        def refresh(obj, _param) -> None:
            label.set_text(obj.duration)

        list_item._notify_handler = (job, job.connect("notify::duration", refresh))

    @staticmethod
    def _bind_source(_factory, list_item) -> None:
        job = list_item.get_item()
        label = list_item.get_child()
        label.set_text(job.source)

        def refresh(obj, _param) -> None:
            label.set_text(obj.source)

        list_item._notify_handler = (job, job.connect("notify::source", refresh))

    def _bind_status(self, _factory, list_item) -> None:
        job = list_item.get_item()
        box = list_item._status_box
        label = list_item._status_label

        def refresh(*_args) -> None:
            label.set_text(job.status or "—")
            label.set_tooltip_text(job.reasons_text or None)
            for variant in ("ok", "warn", "run", "error", "muted"):
                box.remove_css_class(variant)
            box.add_css_class(self._status_variant(job))

        refresh()
        hid = job.connect("notify::status", refresh)
        hid2 = job.connect("notify::state", refresh)
        list_item._notify_handler = (job, hid)
        list_item._notify_handler2 = (job, hid2)

    @staticmethod
    def _status_variant(job: JobItem) -> str:
        if job.state == "done":
            return "ok"
        if job.state == "error":
            return "error"
        if job.state == "running":
            return "run"
        if job.state == "ready":
            return "ok"
        if job.state == "pending" and job.status == "Needs conversion":
            return "warn"
        return "muted"

    def _bind_progress(self, _factory, list_item) -> None:
        bar = list_item.get_child()
        job = list_item.get_item()

        def refresh(*_args) -> None:
            bar.set_fraction(job.progress)

        refresh()
        hid = job.connect("notify::progress", refresh)
        list_item._notify_handler = (job, hid)

    # ------------------------------------------------------------- settings
    def _apply_settings(self) -> None:
        self._loading_settings = True
        preset_ids = [p.id for p in PRESETS]
        preset_id = self.settings.get("preset") or DEFAULT_PRESET_ID
        index = preset_ids.index(preset_id) if preset_id in preset_ids else 0
        self.preset_dropdown.set_selected(index)
        preset = PRESETS[index]
        self.preset_dropdown.set_tooltip_text(preset.description)

        mode = self.settings.get("output_mode")
        self.output_dropdown.set_selected(OUTPUT_MODES.index(mode) if mode in OUTPUT_MODES else 0)
        self._update_custom_dir_label()

        self.backup_switch.set_active(bool(self.settings.get("make_backup")))
        self.skip_switch.set_active(bool(self.settings.get("skip_compatible")))
        self._loading_settings = False

        self.backup_switch.connect(
            "notify::active",
            lambda s, _p: self.settings.set("make_backup", s.get_active()),
        )
        self.skip_switch.connect("notify::active", self._on_skip_changed)
        self._update_theme_button()

    def _on_preset_changed(self, dropdown, _param) -> None:
        preset = PRESETS[dropdown.get_selected()]
        self.settings.set("preset", preset.id)
        self.preset_dropdown.set_tooltip_text(preset.description)
        if not getattr(self, "_loading_settings", False):
            self._update_summary()

    def _on_skip_changed(self, switch, _param) -> None:
        self.settings.set("skip_compatible", switch.get_active())
        for index in range(self.store.get_n_items()):
            job = self.store.get_item(index)
            if job.info:
                self._refresh_job_availability(job)
        self._update_summary()

    def _on_output_changed(self, dropdown, _param) -> None:
        self._update_custom_dir_label()
        if getattr(self, "_loading_settings", False):
            return
        index = dropdown.get_selected()
        if index == 2:
            custom = self.settings.get("custom_dir")
            if custom and Path(custom).is_dir():
                self.settings.set("output_mode", "custom")
                return
            self._choose_custom_folder(previous=self.settings.get("output_mode"))
            return
        self.settings.set("output_mode", OUTPUT_MODES[index])

    def _update_custom_dir_label(self) -> None:
        if not hasattr(self, "custom_dir_label"):
            return
        index = self.output_dropdown.get_selected()
        mode = OUTPUT_MODES[index] if index in range(len(OUTPUT_MODES)) else "same"
        if mode == "custom":
            path = self.settings.get("custom_dir") or ""
            self.custom_dir_label.set_text(path or "No folder selected")
            self.custom_dir_label.set_tooltip_text(path or None)
            self.custom_dir_label.set_visible(True)
        else:
            self.custom_dir_label.set_visible(False)

    def _choose_custom_folder(self, previous: str | None = None) -> None:
        custom = self.settings.get("custom_dir")
        preferred = Path(custom) if custom else None

        def on_selected(path: str) -> None:
            self.settings.set("custom_dir", path)
            self.settings.set("output_mode", "custom")
            self.output_dropdown.set_selected(2)
            self._update_custom_dir_label()

        def on_cancelled() -> None:
            self.output_dropdown.set_selected(OUTPUT_MODES.index(previous or "same"))
            self._update_custom_dir_label()

        compat.choose_folder(
            self,
            title="Choose output folder",
            initial_folder=self._file_dialog_start(preferred, use_queue=False),
            on_selected=on_selected,
            on_cancelled=on_cancelled,
        )

    # ---------------------------------------------------------------- theme
    def _toggle_theme(self) -> None:
        current = "light" if self.settings.get("theme") == "light" else "dark"
        new_theme = "light" if current == "dark" else "dark"
        app = self.get_application()
        if app is not None and hasattr(app, "apply_theme"):
            app.apply_theme(new_theme, save=True)
        else:
            self.settings.set("theme", new_theme)
            self.settings.save()
            scheme = (
                Adw.ColorScheme.FORCE_LIGHT
                if new_theme == "light"
                else Adw.ColorScheme.FORCE_DARK
            )
            Adw.StyleManager.get_default().set_color_scheme(scheme)
        self._update_theme_button()

    def _update_theme_button(self) -> None:
        if not hasattr(self, "theme_button"):
            return
        theme = "light" if self.settings.get("theme") == "light" else "dark"
        if theme == "dark":
            self.remove_css_class("rr-light")
            self.theme_button.set_icon_name("weather-clear-symbolic")
            self.theme_button.set_tooltip_text("Switch to light mode")
        else:
            self.add_css_class("rr-light")
            self.theme_button.set_icon_name("weather-clear-night-symbolic")
            self.theme_button.set_tooltip_text("Switch to dark mode")

    # ---------------------------------------------------------------- input
    def _file_dialog_start(
        self, preferred: Path | None = None, *, use_queue: bool = True
    ) -> Gio.File:
        """Pick an existing folder so a stale last-folder cannot break the chooser."""
        candidates: list[Path] = []
        if preferred is not None:
            candidates.append(preferred)
        if use_queue and self.store.get_n_items():
            candidates.append(self.store.get_item(0).path.parent)
        candidates.extend((Path.home() / "Videos", Path.home()))
        for candidate in candidates:
            try:
                if candidate.is_dir():
                    return Gio.File.new_for_path(str(candidate))
            except OSError:
                continue
        return Gio.File.new_for_path(str(Path.home()))

    def _choose_files(self) -> None:
        if self.running:
            return
        video_filter = Gtk.FileFilter()
        video_filter.set_name("Video files")
        for pattern in ("*.mp4", "*.mov", "*.m4v", "*.mkv", "*.avi", "*.webm",
                        "*.mts", "*.m2ts", "*.mxf", "*.wmv", "*.flv", "*.ts"):
            video_filter.add_pattern(pattern)
        all_filter = Gtk.FileFilter()
        all_filter.set_name("All files")
        all_filter.add_pattern("*")

        compat.choose_files(
            self,
            title="Add video files",
            filters=[video_filter, all_filter],
            initial_folder=self._file_dialog_start(),
            on_selected=self.add_paths,
        )

    def _choose_folder(self) -> None:
        if self.running:
            return
        compat.choose_folder(
            self,
            title="Add a folder of videos",
            initial_folder=self._file_dialog_start(),
            on_selected=lambda path: self.add_paths([path]),
        )

    def _on_drag_enter(self, _target, _x, _y):
        if not self.running:
            self.drop_card.add_css_class("rr-drag-active")
            self.drop_title.set_text("Release to import videos")
        return Gdk.DragAction.COPY

    def _on_drag_leave(self, _target) -> None:
        self.drop_card.remove_css_class("rr-drag-active")
        self._restore_drop_title()

    def _on_drop(self, _target, value, _x, _y) -> bool:
        self.drop_card.remove_css_class("rr-drag-active")
        self._restore_drop_title()
        if self.running:
            return False
        paths: list[str] = []
        try:
            for gfile in value.get_files():
                path = gfile.get_path()
                if path:
                    paths.append(path)
        except AttributeError:
            return False
        if not paths:
            return False
        self.add_paths(paths)
        return True

    def add_paths(self, paths: list[str]) -> None:
        if self.running:
            return
        try:
            media = find_media(paths)
        except Exception as exc:  # noqa: BLE001
            self._toast(f"Could not read that location: {exc}")
            self._log(f"Could not scan added paths: {exc}")
            return
        if not media:
            self._toast("No video files found")
            return

        new_jobs: list[JobItem] = []
        for path in media:
            base = self._base_for(path, paths)
            try:
                rel = path.parent.relative_to(base)
            except ValueError:
                rel = Path(".")
            job = JobItem(path, base, rel)
            self.store.append(job)
            new_jobs.append(job)

        self.completed_outputs.clear()
        self._set_phase(PHASE_IDLE)
        self._log(f"Added {len(new_jobs)} file(s) to the queue")
        self._update_summary()
        thread = threading.Thread(target=self._scan_jobs, args=(new_jobs,), daemon=True)
        self._scan_threads.append(thread)
        thread.start()

    @staticmethod
    def _base_for(path: Path, added: list[str]) -> Path:
        for raw in added:
            candidate = Path(raw).expanduser()
            if candidate.is_dir():
                try:
                    path.relative_to(candidate)
                    return candidate
                except ValueError:
                    pass
        return path.parent

    def _scan_jobs(self, jobs: list[JobItem]) -> None:
        for job in jobs:
            if job.removed:
                continue
            try:
                info = probe(job.path)
                compat = check_compatibility(info)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self._probe_failed, job, str(exc) or exc.__class__.__name__)
                continue
            GLib.idle_add(self._probe_done, job, info, compat)

    def _probe_done(self, job: JobItem, info: MediaInfo, compat) -> bool:
        if job.removed or getattr(self, "_closing", False):
            return GLib.SOURCE_REMOVE
        job.info = info
        job.compat = compat
        job.duration = info.duration_text
        job.source = f"{_codec_label(info.vcodec)} · {info.width}×{info.height}"
        self._refresh_job_availability(job)
        self._log(
            f"Scanned {job.path.name}: {info.vcodec} {info.width}x{info.height} "
            f"{info.fps_text}, audio={info.acodec or 'none'}"
        )
        self._update_summary()
        return GLib.SOURCE_REMOVE

    def _refresh_job_availability(self, job: JobItem) -> None:
        if job.state in ("running", "done", "error"):
            return
        skip = bool(self.skip_switch.get_active()) if hasattr(self, "skip_switch") else True
        if job.compat and job.compat.ready:
            if skip:
                job.state = "ready"
                job.status = "Skipped"
            else:
                job.state = "ready"
                job.status = "Compatible"
        else:
            job.state = "pending"
            job.status = "Needs conversion"

    def _probe_failed(self, job: JobItem, message: str) -> bool:
        if job.removed or getattr(self, "_closing", False):
            return GLib.SOURCE_REMOVE
        job.state = "error"
        job.status = "Unreadable"
        job.progress = 0.0
        self._log(f"Could not read {job.path.name}: {message}")
        self._update_summary()
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------- queue mgmt
    def _remove_selected(self) -> None:
        if self.running:
            self._toast("Stop the current batch first")
            return
        job = self.selection.get_selected_item()
        if job is None:
            return
        job.removed = True
        for index in range(self.store.get_n_items()):
            if self.store.get_item(index) is job:
                self.store.remove(index)
                break
        self._reset_finished_if_empty()
        self._update_summary()

    def _clear_queue(self) -> None:
        if self.running:
            self._toast("Stop the current batch first")
            return
        for index in range(self.store.get_n_items()):
            self.store.get_item(index).removed = True
        self.store.remove_all()
        self._reset_finished_if_empty()
        self._update_summary()

    def _reset_finished_if_empty(self) -> None:
        if self.phase == PHASE_FINISHED and not self.store.get_n_items():
            self.phase = PHASE_IDLE
            self.completed_outputs.clear()
            self.batch_bar.set_visible(False)

    # ------------------------------------------------------------- conversion
    def _candidates(self) -> list[JobItem]:
        jobs = [self.store.get_item(i) for i in range(self.store.get_n_items())]
        skip = bool(self.skip_switch.get_active()) if hasattr(self, "skip_switch") else True
        return [
            job for job in jobs
            if job.state != "done" and job.info is not None
            and not (skip and job.compat and job.compat.ready)
        ]

    def _start_conversion(self) -> None:
        if self.running or self.phase == PHASE_FINISHED:
            return
        jobs = [
            job for job in self._candidates()
            if not job.removed
        ]
        if not jobs:
            self._toast("Nothing to convert — files are already compatible")
            return

        preset = PRESETS[self.preset_dropdown.get_selected()]
        mode = OUTPUT_MODES[self.output_dropdown.get_selected()]
        if mode == "custom" and not (
            self.settings.get("custom_dir") and Path(self.settings.get("custom_dir")).is_dir()
        ):
            self._toast("Choose a custom output folder first")
            return

        options = SimpleNamespace(
            preset=preset,
            output_mode=mode,
            custom_dir=Path(self.settings.get("custom_dir") or Path.home()),
            make_backup=bool(self.backup_switch.get_active()),
        )
        self._begin_batch(jobs, options)

    def _begin_batch(self, jobs: list[JobItem], options) -> None:
        self.completed_outputs.clear()
        self._batch_index = 0
        self.running = True
        self.cancel_event = threading.Event()
        self._set_phase(PHASE_RUNNING)
        self.batch_bar.set_visible(True)
        self.batch_bar.set_fraction(0.0)
        self._batch_total = len(jobs)
        self._batch_done = 0
        self._batch_failures = 0
        self._batch_cancelled = 0

        for job in jobs:
            job.state = "pending"
            job.status = "Queued"
            job.progress = 0.0

        self._log(
            f"Starting batch: {len(jobs)} file(s), {options.preset.label}, "
            f"output={options.output_mode}, backup={options.make_backup}"
        )
        thread = threading.Thread(target=self._worker, args=(jobs, options), daemon=True)
        thread.start()

    def _worker(self, jobs: list[JobItem], options) -> None:
        if options.make_backup:
            GLib.idle_add(self._set_transient_status, "Creating backup archive…")
            try:
                root = self._backup_root(jobs)
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                dest = root / f"Original Videos Backup {timestamp}.tar"
                count = create_backup(root, [job.path for job in jobs], dest)
                self._log(f"Backup created: {dest} ({count} files)")
            except Exception as exc:  # noqa: BLE001
                self._log(f"Backup failed: {exc}")
                GLib.idle_add(self._batch_aborted, f"Backup failed: {exc}")
                return

        for job in jobs:
            if self.cancel_event.is_set():
                GLib.idle_add(self._mark_cancelled, job)
                continue
            GLib.idle_add(self._job_started, job)

            temp: Path | None = None
            try:
                dst = self._destination(job, options)
                temp = dst.parent / f".{dst.stem}.resolve-ready-tmp{dst.suffix}"
                temp.unlink(missing_ok=True)
                job.dst = dst

                def progress(fraction: float, current=job) -> None:
                    GLib.idle_add(self._job_progress, current, fraction)

                result = encode(
                    job.info, options.preset, temp,
                    on_progress=progress,
                    cancel_event=self.cancel_event,
                )

                if result.cancelled:
                    temp.unlink(missing_ok=True)
                    GLib.idle_add(self._job_cancelled, job)
                    continue
                if not result.ok:
                    temp.unlink(missing_ok=True)
                    GLib.idle_add(self._job_failed, job, result.error, result.log_tail)
                    continue

                ok, message = verify_output(job.info, temp, options.preset)
                if not ok:
                    temp.unlink(missing_ok=True)
                    GLib.idle_add(self._job_failed, job, f"Verification failed: {message}", result.log_tail)
                    continue

                dst = _unique_path(dst) if dst.exists() else dst
                temp.replace(dst)
                job.dst = dst
            except Exception as exc:  # noqa: BLE001
                if temp is not None:
                    try:
                        temp.unlink(missing_ok=True)
                    except OSError:
                        pass
                self._log(f"Unexpected error for {job.path.name}: {exc}")
                GLib.idle_add(self._job_failed, job, f"Unexpected error: {exc}")
                continue

            self._log(f"Saved {dst}")
            GLib.idle_add(self._job_done, job, "Done")

        GLib.idle_add(self._batch_finished)

    @staticmethod
    def _backup_root(jobs: list[JobItem]) -> Path:
        try:
            root = Path(os.path.commonpath([str(job.path.parent) for job in jobs]))
        except ValueError:
            root = Path.home()
        return root if root != Path("/") else Path.home()

    def _destination(self, job: JobItem, options) -> Path:
        if options.output_mode == "same":
            folder = job.path.parent
        elif options.output_mode == "subfolder":
            folder = job.base_root / "Resolve Ready" / job.rel_dir
        else:
            folder = options.custom_dir / job.rel_dir
        folder.mkdir(parents=True, exist_ok=True)

        dst = folder / f"{job.path.stem}.mov"
        if dst.resolve() == job.path.resolve():
            dst = folder / f"{job.path.stem} (converted).mov"
        return _unique_path(dst)

    def _see_files(self) -> None:
        if not self.completed_outputs:
            return
        folder = self.completed_outputs[-1].parent.resolve()
        if not folder.is_dir():
            self._toast(f"Output folder no longer exists: {folder}")
            return
        try:
            Gio.AppInfo.launch_default_for_uri(folder.as_uri(), None)
        except GLib.Error as exc:
            self._toast(f"Could not open {folder.name}: {exc.message}")
            return
        self._log(f"Opened output folder: {folder}")

    def _cancel_conversion(self) -> None:
        if not self.running:
            return
        self.cancel_event.set()
        self.secondary_button.set_sensitive(False)
        self.secondary_button.remove_css_class("destructive-action")
        self._log("Cancellation requested…")

    # --------------------------------------------------------- idle callbacks
    def _set_phase(self, phase: str) -> None:
        self.phase = phase
        busy = phase == PHASE_RUNNING
        if hasattr(self, "settings_card"):
            self.settings_card.set_sensitive(not busy)
            self.add_files_button.set_sensitive(not busy)
            self.add_folder_button.set_sensitive(not busy)
            self.clear_button.set_sensitive(not busy)
        self._update_actions()

    def _update_actions(self) -> None:
        if not hasattr(self, "convert_button"):
            return
        candidates = self._candidates() if self.phase != PHASE_FINISHED else []
        can_convert = self.phase == PHASE_IDLE and bool(candidates)
        self.convert_button.set_sensitive(can_convert)
        self.secondary_button.set_sensitive(
            self.phase == PHASE_RUNNING and not self.cancel_event.is_set()
        )
        if self.phase == PHASE_RUNNING:
            self.convert_button._rr_label.set_text("Converting…")
            self._set_suggested(self.convert_button, False)
            self.secondary_button.add_css_class("destructive-action")
            self.secondary_button.set_tooltip_text("Stop the current batch")
        else:
            self.convert_button._rr_label.set_text(self._convert_label(len(candidates)))
            self._set_suggested(self.convert_button, can_convert)
            self.secondary_button.remove_css_class("destructive-action")
            self.secondary_button.set_tooltip_text(None)

    @staticmethod
    def _set_suggested(button: Gtk.Button, enabled: bool) -> None:
        if enabled:
            button.add_css_class("suggested-action")
        else:
            button.remove_css_class("suggested-action")

    @staticmethod
    def _convert_label(count: int) -> str:
        if count <= 0:
            return "Convert"
        return f"Convert {count} file" if count == 1 else f"Convert {count} files"

    def _update_queue_state(self) -> None:
        if not hasattr(self, "queue_count_label"):
            return
        count = self.store.get_n_items()
        self.queue_count_label.set_text("1 file" if count == 1 else f"{count} files")
        self.queue_stack.set_visible_child_name("queue" if count else "empty")
        if hasattr(self, "clear_button"):
            self.clear_button.set_sensitive(count > 0 and not self.running)
        if not self.drop_card.has_css_class("rr-drag-active"):
            self._restore_drop_title()

    def _restore_drop_title(self) -> None:
        if not hasattr(self, "drop_title"):
            return
        self.drop_title.set_text(
            "Import more videos here" if self.store.get_n_items() else "Import any videos here"
        )

    def _update_summary(self) -> None:
        self._update_queue_state()
        self._update_actions()
        if self.running or self.phase == PHASE_FINISHED or getattr(self, "_closing", False):
            return
        jobs = [self.store.get_item(i) for i in range(self.store.get_n_items())]
        if not jobs:
            self.summary_label.set_text("Add footage to begin")
            return
        if any(job.state == "scanning" for job in jobs):
            count = sum(1 for job in jobs if job.state == "scanning")
            noun = "file" if count == 1 else "files"
            self.summary_label.set_text(f"Scanning {count} {noun}…")
            return
        candidates = self._candidates()
        if not candidates:
            if all(job.state == "done" for job in jobs):
                noun = "file" if len(jobs) == 1 else "files"
                self.summary_label.set_text(f"{len(jobs)} {noun} · queue complete")
            else:
                noun = "file" if len(jobs) == 1 else "files"
                self.summary_label.set_text(f"{len(jobs)} {noun} · nothing to convert")
            return

        preset = PRESETS[self.preset_dropdown.get_selected()]
        duration = sum(job.info.duration for job in candidates)
        size_mb = sum(
            estimate_size_mb(job.info.duration, preset, job.info.has_audio)
            for job in candidates
        )
        size_text = (
            f"~{size_mb / 1024:.1f} GB" if size_mb >= 1024 else f"~{size_mb:.0f} MB"
        )
        count = len(candidates)
        noun = "file" if count == 1 else "files"
        self.summary_label.set_text(
            f"{count} {noun} · {_human_duration(duration)} · {size_text} at {preset.label}"
        )

    def _job_started(self, job: JobItem) -> bool:
        self._batch_index += 1
        job.state = "running"
        job.status = "Converting…"
        job.progress = 0.0
        self.batch_bar.set_fraction(self._batch_done / max(1, self._batch_total))
        self.summary_label.set_text(
            f"Converting {self._batch_index} of {self._batch_total} · {job.name}"
        )
        return GLib.SOURCE_REMOVE

    def _job_progress(self, job: JobItem, fraction: float) -> bool:
        job.progress = max(0.0, min(1.0, fraction))
        overall = (self._batch_done + job.progress) / max(1, self._batch_total)
        self.batch_bar.set_fraction(overall)
        self.summary_label.set_text(
            f"Converting {max(1, self._batch_index)} of {self._batch_total} · "
            f"{round(job.progress * 100)}%"
        )
        return GLib.SOURCE_REMOVE

    def _job_done(self, job: JobItem, status: str) -> bool:
        job.progress = 1.0
        job.state = "done"
        job.status = status
        if job.dst is not None:
            self.completed_outputs.append(job.dst)
        self._batch_done += 1
        self.batch_bar.set_fraction(self._batch_done / max(1, self._batch_total))
        return GLib.SOURCE_REMOVE

    def _job_failed(self, job: JobItem, error: str, tail: str = "") -> bool:
        job.state = "error"
        job.status = "Failed"
        job.progress = 0.0
        self._batch_failures += 1
        self._batch_done += 1
        self._log(f"FAILED {job.path.name}: {error}")
        if tail:
            self._log(tail)
        self.batch_bar.set_fraction(self._batch_done / max(1, self._batch_total))
        self._toast(f"{job.path.name}: {error}")
        return GLib.SOURCE_REMOVE

    def _job_cancelled(self, job: JobItem) -> bool:
        job.state = "pending"
        job.status = "Cancelled"
        job.progress = 0.0
        self._batch_cancelled += 1
        self._batch_done += 1
        self.batch_bar.set_fraction(self._batch_done / max(1, self._batch_total))
        return GLib.SOURCE_REMOVE

    def _mark_cancelled(self, job: JobItem) -> bool:
        if job.state != "done":
            job.state = "pending"
            job.status = "Cancelled"
            self._batch_cancelled += 1
        return GLib.SOURCE_REMOVE

    def _batch_aborted(self, message: str) -> bool:
        self.running = False
        self._set_phase(PHASE_IDLE)
        self.batch_bar.set_visible(False)
        self.summary_label.set_text(message)
        self._toast(message)
        return GLib.SOURCE_REMOVE

    def _batch_finished(self) -> bool:
        self.running = False
        self._set_phase(PHASE_FINISHED)
        self.batch_bar.set_fraction(1.0)
        self.batch_bar.set_visible(False)
        count = len(self.completed_outputs)
        noun = "file" if count == 1 else "files"
        succeeded = (
            count > 0
            and count == self._batch_total
            and self._batch_failures == 0
            and self._batch_cancelled == 0
        )
        if count:
            state = "Batch complete" if succeeded else "Batch finished"
            self.summary_label.set_text(f"{state} · {count} {noun} converted")
        else:
            self.summary_label.set_text("Batch finished · no files converted")
        if succeeded:
            self._show_success_dialog(self.summary_label.get_text())
        else:
            self._toast("Batch finished")
        self._update_queue_state()
        self._log("Batch finished")
        return GLib.SOURCE_REMOVE

    def _show_success_dialog(self, message: str) -> None:
        responses = [("close", "Close", False)]
        if self.completed_outputs:
            responses.append(("files", "See Files", True))

        def on_response(response: str) -> None:
            if response == "files":
                self._see_files()

        compat.show_alert(
            self,
            heading="Conversion complete",
            body=message,
            responses=responses,
            default_response="close",
            close_response="close",
            on_response=on_response,
        )

    def _set_transient_status(self, text: str) -> bool:
        self.summary_label.set_text(text)
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------ misc
    def _open_support(self) -> None:
        if not SUPPORT_URL:
            return
        try:
            Gio.AppInfo.launch_default_for_uri(SUPPORT_URL, None)
        except GLib.Error as exc:
            self._toast(f"Could not open the support link: {exc.message}")

    def _toast(self, message: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast.new(message))

    def _log(self, message: str) -> None:
        log.info(message)

    def _on_close_request(self, *_args) -> bool:
        if self.running:
            self._toast("Cancel the batch before closing")
            return True
        self.settings.set("window_width", self.get_width())
        self.settings.set("window_height", self.get_height())
        self.settings.save()
        self._closing = True
        return False
