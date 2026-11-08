"""GTK / libadwaita compatibility helpers.

Resolve Ready supports GTK 4.6 and libadwaita 1.1 (Ubuntu 22.04) up to the
current releases.  Newer widgets are used when available; otherwise the
helpers fall back to APIs that have existed since GTK 4.0 / libadwaita 1.0.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

GTK_HAS_FILE_DIALOG = hasattr(Gtk, "FileDialog")
ADW_HAS_TOOLBAR_VIEW = hasattr(Adw, "ToolbarView")
ADW_HAS_ALERT_DIALOG = hasattr(Adw, "AlertDialog")
ADW_HAS_MESSAGE_DIALOG = hasattr(Adw, "MessageDialog")
ADW_HAS_ABOUT_DIALOG = hasattr(Adw, "AboutDialog")
ADW_HAS_ABOUT_WINDOW = hasattr(Adw, "AboutWindow")


# --------------------------------------------------------------------- layout
def build_toolbar(header: Gtk.Widget, content: Gtk.Widget) -> Gtk.Widget:
    """Return a header + content container using the best available widget."""
    if ADW_HAS_TOOLBAR_VIEW:
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(content)
        return toolbar

    # libadwaita < 1.4 has no Adw.ToolbarView.
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.append(header)
    content.set_vexpand(True)
    box.append(content)
    return box


# ------------------------------------------------------------------- dialogs
def _keep_alive(window: Gtk.Window, dialog: Gtk.NativeDialog) -> None:
    """Prevent a native dialog from being garbage-collected while open."""
    dialogs = getattr(window, "_rr_native_dialogs", None)
    if dialogs is None:
        dialogs = []
        window._rr_native_dialogs = dialogs
    dialogs.append(dialog)


def _forget(window: Gtk.Window, dialog: Gtk.NativeDialog) -> None:
    dialogs = getattr(window, "_rr_native_dialogs", None)
    if dialogs and dialog in dialogs:
        dialogs.remove(dialog)


def _set_native_folder(dialog: Gtk.FileChooser, folder: Gio.File | None) -> None:
    if folder is None:
        return
    try:
        dialog.set_current_folder(folder, None)
    except (GLib.Error, TypeError, AttributeError):
        pass


def _native_paths(dialog: Gtk.FileChooser) -> list[str]:
    paths: list[str] = []
    try:
        model = dialog.get_files()
    except AttributeError:
        model = None
    if model is not None:
        for index in range(model.get_n_items()):
            path = model.get_item(index).get_path()
            if path:
                paths.append(path)
        return paths
    gfile = dialog.get_file()
    if gfile is not None and gfile.get_path():
        paths.append(gfile.get_path())
    return paths


def choose_files(
    window: Gtk.Window,
    *,
    title: str,
    filters: list[Gtk.FileFilter],
    initial_folder: Gio.File | None,
    on_selected,
) -> None:
    """Pick one or more files; ``on_selected`` receives a list of paths."""
    if GTK_HAS_FILE_DIALOG:
        dialog = Gtk.FileDialog(title=title, modal=True)
        if initial_folder is not None:
            dialog.set_initial_folder(initial_folder)
        store = Gio.ListStore(item_type=Gtk.FileFilter)
        for file_filter in filters:
            store.append(file_filter)
        dialog.set_filters(store)

        def done(file_dialog, result) -> None:
            try:
                files = file_dialog.open_multiple_finish(result)
            except GLib.Error:
                return
            paths: list[str] = []
            for index in range(files.get_n_items()):
                path = files.get_item(index).get_path()
                if path:
                    paths.append(path)
            if paths:
                on_selected(paths)

        dialog.open_multiple(window, None, done)
        return

    dialog = Gtk.FileChooserNative.new(
        title, window, Gtk.FileChooserAction.OPEN, "_Open", "_Cancel"
    )
    dialog.set_select_multiple(True)
    _set_native_folder(dialog, initial_folder)
    for file_filter in filters:
        dialog.add_filter(file_filter)

    def on_response(native, response) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            paths = _native_paths(native)
            if paths:
                on_selected(paths)
        _forget(window, native)
        native.destroy()

    dialog.connect("response", on_response)
    _keep_alive(window, dialog)
    dialog.show()


def choose_folder(
    window: Gtk.Window,
    *,
    title: str,
    initial_folder: Gio.File | None,
    on_selected,
    on_cancelled=None,
) -> None:
    """Pick a folder; ``on_selected`` receives the path."""
    if GTK_HAS_FILE_DIALOG:
        dialog = Gtk.FileDialog(title=title, modal=True)
        if initial_folder is not None:
            dialog.set_initial_folder(initial_folder)

        def done(file_dialog, result) -> None:
            try:
                folder = file_dialog.select_folder_finish(result)
            except GLib.Error:
                if on_cancelled is not None:
                    on_cancelled()
                return
            path = folder.get_path()
            if path:
                on_selected(path)

        dialog.select_folder(window, None, done)
        return

    dialog = Gtk.FileChooserNative.new(
        title, window, Gtk.FileChooserAction.SELECT_FOLDER, "_Select", "_Cancel"
    )
    _set_native_folder(dialog, initial_folder)

    def on_response(native, response) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            paths = _native_paths(native)
            if paths:
                on_selected(paths[0])
        elif on_cancelled is not None:
            on_cancelled()
        _forget(window, native)
        native.destroy()

    dialog.connect("response", on_response)
    _keep_alive(window, dialog)
    dialog.show()


# --------------------------------------------------------------------- alert
def show_alert(
    parent: Gtk.Window,
    *,
    heading: str,
    body: str,
    responses: list[tuple[str, str, bool]],
    default_response: str,
    close_response: str,
    on_response,
) -> None:
    """Show a message dialog.

    ``responses`` is a list of ``(id, label, suggested)`` tuples.  The newer
    libadwaita dialog is used when available; GTK's dialog is the fallback.
    """
    if ADW_HAS_ALERT_DIALOG:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        for response_id, label, suggested in responses:
            dialog.add_response(response_id, label)
            if suggested:
                dialog.set_response_appearance(
                    response_id, Adw.ResponseAppearance.SUGGESTED
                )
        dialog.set_default_response(default_response)
        dialog.set_close_response(close_response)
        dialog.connect("response", lambda _dialog, response: on_response(response))
        dialog.present(parent)
        return

    if ADW_HAS_MESSAGE_DIALOG:
        dialog = Adw.MessageDialog(
            transient_for=parent, modal=True, heading=heading, body=body
        )
        for response_id, label, suggested in responses:
            dialog.add_response(response_id, label)
            if suggested:
                dialog.set_response_appearance(
                    response_id, Adw.ResponseAppearance.SUGGESTED
                )
        dialog.set_default_response(default_response)
        dialog.set_close_response(close_response)
        dialog.connect("response", lambda _dialog, response: on_response(response))
        dialog.present()
        return

    # libadwaita 1.1: use the GTK dialog, mapping string ids to integers.
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.NONE,
        text=heading,
        secondary_text=body,
    )
    mapping: dict[int, str] = {}
    default_id = 1
    for index, (response_id, label, _suggested) in enumerate(responses, start=1):
        dialog.add_button(label, index)
        mapping[index] = response_id
        if response_id == default_response:
            default_id = index
    dialog.set_default_response(default_id)

    def on_gtk_response(gtk_dialog, response_id) -> None:
        gtk_dialog.destroy()
        on_response(mapping.get(response_id, close_response))

    dialog.connect("response", on_gtk_response)
    dialog.present()


# --------------------------------------------------------------------- about
def show_about(
    parent: Gtk.Window,
    *,
    application_name: str,
    application_icon: str,
    version: str,
    developer_name: str,
    comments: str,
    developers: list[str],
    license_type,
    website: str | None = None,
    support_url: str | None = None,
    support_label: str = "Support the project",
) -> None:
    """Show the About dialog using the best API available."""
    if ADW_HAS_ABOUT_DIALOG:
        dialog = Adw.AboutDialog(
            application_name=application_name,
            application_icon=application_icon,
            version=version,
            developer_name=developer_name,
            comments=comments,
            developers=developers,
            license_type=license_type,
            website=website,
        )
        if support_url:
            dialog.add_link(support_label, support_url)
        dialog.present(parent)
        return

    if ADW_HAS_ABOUT_WINDOW:
        window = Adw.AboutWindow(
            transient_for=parent,
            application_name=application_name,
            application_icon=application_icon,
            version=version,
            developer_name=developer_name,
            comments=comments,
            developers=developers,
            license_type=license_type,
            website=website,
        )
        if support_url:
            window.add_link(support_label, support_url)
        window.present()
        return

    # libadwaita 1.1: GTK's own about dialog.
    dialog = Gtk.AboutDialog(
        transient_for=parent,
        modal=True,
        program_name=application_name,
        logo_icon_name=application_icon,
        version=version,
        comments=comments,
        authors=developers,
        license_type=license_type,
        website=website or "",
        website_label="Project homepage" if website else "",
    )
    dialog.present()
