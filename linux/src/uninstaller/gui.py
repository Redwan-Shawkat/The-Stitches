"""GTK3 GUI. One window, kept as one module — splitting a single cohesive
window into more files would be indirection, not structure."""

import os
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from .models import Risk, Source, format_size
from .scanner import scan_all
from .uninstaller import clean_leftovers, uninstall

_ICON_PATH = os.path.join(os.path.dirname(__file__), "icon.svg")
_THEME_DIRS = ("/usr/share/themes", os.path.expanduser("~/.themes"), os.path.expanduser("~/.local/share/themes"))
_VARIANT_SUFFIXES = ("-dark", "-light", "_dark", "_light", "dark", "light")


def _strip_theme_variant(name: str) -> str:
    """"ZorinPurple-Dark" -> "ZorinPurple", "Adwaita" -> "Adwaita"."""
    low = name.lower()
    for suffix in _VARIANT_SUFFIXES:
        if low.endswith(suffix):
            return name[: len(name) - len(suffix)].rstrip("-_")
    return name


def _list_installed_themes() -> set:
    names = set()
    for d in _THEME_DIRS:
        try:
            names.update(os.listdir(d))
        except OSError:
            pass
    return names


def _find_theme_variant(installed: set, family: str, want_dark: bool):
    """Find the installed theme name that is `family`'s dark/light sibling.

    GTK themes name variants two different ways: a shared base name plus
    "-dark" (Adwaita/Yaru), or two fully separate names (ZorinPurple-Dark /
    ZorinPurple-Light). Matching by stripped family name covers both without
    hardcoding either scheme.
    """
    target = "dark" if want_dark else "light"
    for name in installed:
        if target in name.lower() and _strip_theme_variant(name).lower() == family.lower():
            return name
    return None

# GTK themes paint a gradient on progressbar fill; background-color alone
# doesn't override it, so background-image has to be cleared too.
_PROGRESS_CSS = b"""
progressbar.op-success trough progress { background-image: none; background-color: #2e7d32; }
progressbar.op-error trough progress { background-image: none; background-color: #c62828; }
"""

(
    COL_SELECTED,
    COL_NAME,
    COL_SOURCE,
    COL_VERSION,
    COL_SIZE,
    COL_RISK,
    COL_REASON,
    COL_IDX,
) = range(8)

_RISK_COLOR = {
    Risk.SAFE.value: "#2e7d32",
    Risk.CAUTION.value: "#b8860b",
    Risk.CRITICAL.value: "#c62828",
}
_SOURCES = (Source.APT.value, Source.SNAP.value, Source.FLATPAK.value, Source.WINE.value)


class UninstallerWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="The Uninstaller")
        self.set_default_size(900, 560)
        self.apps: list = []
        self.search_text = ""
        self.source_filter = "All sources"

        self.store = Gtk.ListStore(bool, str, str, str, str, str, str, int)
        self.filter_model = self.store.filter_new()
        self.filter_model.set_visible_func(self._row_visible)

        if os.path.exists(_ICON_PATH):
            self.set_icon_from_file(_ICON_PATH)

        settings = Gtk.Settings.get_default()
        current_theme = settings.get_property("gtk-theme-name") or "Adwaita"
        self._installed_themes = _list_installed_themes()
        self._theme_family = _strip_theme_variant(current_theme)
        self._theme_is_dark = "dark" in current_theme.lower() or bool(
            settings.get_property("gtk-application-prefer-dark-theme")
        )

        self.add(self._build_ui())
        self.show_all()
        self.progress_bar.hide()  # no_show_all keeps it hidden through future show_all() too
        self.reload()

    # ---- layout ----

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        root.set_border_width(8)
        root.pack_start(self._build_toolbar(), False, False, 0)
        root.pack_start(self._build_list(), True, True, 0)
        root.pack_start(self._build_progress(), False, False, 0)
        root.pack_start(self._build_actionbar(), False, False, 0)
        return root

    def _build_toolbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search installed software…")
        search.connect("search-changed", self._on_search_changed)
        bar.pack_start(search, True, True, 0)

        self.source_combo = Gtk.ComboBoxText()
        for label in ("All sources", *_SOURCES):
            self.source_combo.append_text(label)
        self.source_combo.set_active(0)
        self.source_combo.connect("changed", self._on_source_changed)
        bar.pack_start(self.source_combo, False, False, 0)

        refresh = Gtk.Button(label="Refresh")
        refresh.connect("clicked", lambda _b: self.reload())
        bar.pack_start(refresh, False, False, 0)

        self.theme_toggle = Gtk.ToggleButton(
            label="☀" if self._theme_is_dark else "🌙", active=self._theme_is_dark
        )
        self.theme_toggle.set_tooltip_text("Switch between light and dark mode")
        self.theme_toggle.connect("toggled", self._on_theme_toggled)
        bar.pack_end(self.theme_toggle, False, False, 0)
        return bar

    def _on_theme_toggled(self, button):
        dark = button.get_active()
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme", dark)
        variant = _find_theme_variant(self._installed_themes, self._theme_family, dark)
        if variant:
            settings.set_property("gtk-theme-name", variant)
        elif not dark and self._theme_family in self._installed_themes:
            settings.set_property("gtk-theme-name", self._theme_family)
        button.set_label("☀" if dark else "🌙")

    def _build_progress(self):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.spinner = Gtk.Spinner()
        self.spinner.set_no_show_all(True)
        row.pack_start(self.spinner, False, False, 0)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_no_show_all(True)
        self.progress_bar.set_show_text(False)
        row.pack_start(self.progress_bar, True, True, 0)
        return row

    def _build_list(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.tree = Gtk.TreeView(model=self.filter_model)
        self.tree.set_tooltip_column(COL_REASON)

        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self._on_toggled)
        self.tree.append_column(Gtk.TreeViewColumn("", toggle, active=COL_SELECTED))
        self.tree.append_column(Gtk.TreeViewColumn("Name", Gtk.CellRendererText(), text=COL_NAME))
        self.tree.append_column(
            Gtk.TreeViewColumn("Installed via", Gtk.CellRendererText(), text=COL_SOURCE)
        )
        self.tree.append_column(
            Gtk.TreeViewColumn("Version", Gtk.CellRendererText(), text=COL_VERSION)
        )
        self.tree.append_column(Gtk.TreeViewColumn("Size", Gtk.CellRendererText(), text=COL_SIZE))

        risk_renderer = Gtk.CellRendererText()
        risk_col = Gtk.TreeViewColumn("Risk to remove", risk_renderer, text=COL_RISK)
        risk_col.set_cell_data_func(risk_renderer, self._risk_cell_data)
        self.tree.append_column(risk_col)

        for col in self.tree.get_columns():
            col.set_resizable(True)
        scrolled.add(self.tree)
        return scrolled

    def _build_actionbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.status_label = Gtk.Label(label="")
        bar.pack_start(self.status_label, True, True, 0)

        select_all = Gtk.Button(label="Select All (non-critical)")
        select_all.connect("clicked", self._on_select_all)
        bar.pack_start(select_all, False, False, 0)

        select_none = Gtk.Button(label="Select None")
        select_none.connect("clicked", self._on_select_none)
        bar.pack_start(select_none, False, False, 0)

        uninstall_btn = Gtk.Button(label="Uninstall Selected")
        uninstall_btn.get_style_context().add_class("destructive-action")
        uninstall_btn.connect("clicked", self._on_uninstall_clicked)
        bar.pack_start(uninstall_btn, False, False, 0)
        return bar

    def _risk_cell_data(self, _column, cell, model, it, _data):
        risk = model[it][COL_RISK]
        cell.set_property("foreground", _RISK_COLOR.get(risk))
        cell.set_property("weight", Pango.Weight.BOLD if risk == Risk.CRITICAL.value else Pango.Weight.NORMAL)

    # ---- filtering ----

    def _row_visible(self, model, it, _data):
        if self.source_filter != "All sources" and model[it][COL_SOURCE] != self.source_filter:
            return False
        return self.search_text.lower() in (model[it][COL_NAME] or "").lower()

    def _on_search_changed(self, entry):
        self.search_text = entry.get_text()
        self.filter_model.refilter()

    def _on_source_changed(self, combo):
        self.source_filter = combo.get_active_text()
        self.filter_model.refilter()

    def _on_toggled(self, _renderer, path):
        it = self.filter_model.get_iter(path)
        child_it = self.filter_model.convert_iter_to_child_iter(it)
        self.store[child_it][COL_SELECTED] = not self.store[child_it][COL_SELECTED]

    def _on_select_all(self, _button):
        for row in self.store:
            if row[COL_RISK] != Risk.CRITICAL.value:
                row[COL_SELECTED] = True

    def _on_select_none(self, _button):
        for row in self.store:
            row[COL_SELECTED] = False

    # ---- scanning ----

    def reload(self):
        self.status_label.set_text("Scanning for installed software…")
        self.progress_bar.hide()
        self.spinner.show()
        self.spinner.start()
        self.set_sensitive(False)

        def worker():
            apps = scan_all()
            GLib.idle_add(self._on_scan_done, apps)

        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_done(self, apps):
        self.spinner.stop()
        self.spinner.hide()
        self.apps = apps
        self.store.clear()
        for idx, app in enumerate(apps):
            self.store.append(
                [False, app.name, app.source.value, app.version, app.size_human, app.risk.value, app.risk_reason, idx]
            )
        self.status_label.set_text(f"{len(apps)} item(s) found")
        self.set_sensitive(True)
        return False

    # ---- uninstall flow ----

    def _on_uninstall_clicked(self, _button):
        selected = [self.apps[row[COL_IDX]] for row in self.store if row[COL_SELECTED]]
        if not selected:
            self._info_dialog("Nothing selected", "Check one or more items first.")
            return
        if self._confirm(selected):
            self._run_uninstall_async(selected)

    def _confirm(self, apps) -> bool:
        critical = [a for a in apps if a.risk == Risk.CRITICAL]
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING if critical else Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Uninstall {len(apps)} item(s)?",
        )
        dialog.format_secondary_text(
            "\n".join(f"• {a.name} — {a.source.value} — {a.risk.value}" for a in apps)
        )
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Uninstall", Gtk.ResponseType.OK)
        ok_button = dialog.get_widget_for_response(Gtk.ResponseType.OK)
        if critical:
            check = Gtk.CheckButton(label="I understand this includes system-critical software")
            dialog.get_content_area().pack_start(check, False, False, 6)
            check.show()
            ok_button.set_sensitive(False)
            check.connect("toggled", lambda c: ok_button.set_sensitive(c.get_active()))
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def _run_uninstall_async(self, apps):
        self.set_sensitive(False)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.show()
        total = len(apps)

        def worker():
            results = []
            for i, app in enumerate(apps):
                GLib.idle_add(self._on_uninstall_item_start, app, i, total)
                ok, message, leftovers = uninstall(app)
                results.append((app, ok, message, leftovers))
                GLib.idle_add(self._on_uninstall_item_done, app, ok, message, i + 1, total)
            GLib.idle_add(self._on_uninstall_done, results)

        threading.Thread(target=worker, daemon=True).start()

    def _start_progress_slice(self, start_frac, end_frac):
        """Animate the bar filling toward `end_frac` while the real operation
        (a blocking subprocess/file call with no progress of its own) runs in
        the background, so it reads as continuously advancing instead of
        jumping only when each item finishes."""
        style = self.progress_bar.get_style_context()
        style.remove_class("op-error")
        style.add_class("op-success")  # green while running; flips to red only on failure
        self.progress_bar.set_fraction(start_frac)
        self._progress_animating = True

        def tick():
            if not self._progress_animating:
                return False
            # Crawl to 92% of the slice; the real completion callback snaps
            # the last stretch so it never looks stuck short of the line.
            ceiling = start_frac + (end_frac - start_frac) * 0.92
            frac = min(ceiling, self.progress_bar.get_fraction() + (end_frac - start_frac) * 0.06)
            self.progress_bar.set_fraction(frac)
            return self._progress_animating

        GLib.timeout_add(60, tick)

    def _on_uninstall_item_start(self, app, index, total):
        self.status_label.set_text(f"Uninstalling {app.name}… ({index + 1}/{total})")
        self._start_progress_slice(index / total, (index + 1) / total)
        return False

    def _on_uninstall_item_done(self, app, ok, message, done_count, total):
        self._progress_animating = False
        style = self.progress_bar.get_style_context()
        style.remove_class("op-success")
        style.remove_class("op-error")
        style.add_class("op-success" if ok else "op-error")
        self.progress_bar.set_fraction(done_count / total)
        self.status_label.set_text(
            f"{app.name}: done ({done_count}/{total})" if ok else f"{app.name} failed: {message}"
        )
        return False

    def _on_uninstall_done(self, results):
        self.set_sensitive(True)
        all_leftovers, failures, warnings = [], [], []
        app_freed = 0
        for app, ok, message, leftovers in results:
            if ok:
                app_freed += app.size_bytes
                all_leftovers.extend(leftovers)
                if message:
                    warnings.append((app, message))
            else:
                failures.append((app, message))
        if failures:
            self._info_dialog(
                "Some items failed to uninstall",
                "\n".join(f"{a.name}: {msg}" for a, msg in failures),
            )
        if warnings:
            self._info_dialog(
                "Removed, with a warning",
                "\n".join(f"{a.name}: {msg}" for a, msg in warnings),
            )
        if all_leftovers:
            # Leave the uninstall's own final green/red line up until the
            # leftover question is answered, instead of it flashing away
            # under the dialog.
            self._offer_leftover_cleanup(all_leftovers, app_freed)
        else:
            if app_freed:
                self._info_dialog("Uninstall complete", f"Freed {format_size(app_freed)} of disk space.")
            GLib.timeout_add(800, lambda: (self.reload(), False)[1])
        return False

    def _offer_leftover_cleanup(self, paths, app_freed):
        dialog = Gtk.Dialog(title="Leftover files found", transient_for=self, modal=True)
        dialog.add_buttons("Skip", Gtk.ResponseType.CANCEL, "Delete Selected", Gtk.ResponseType.OK)
        content = dialog.get_content_area()
        content.pack_start(
            Gtk.Label(label="These weren't removed by the uninstaller. Delete them too?"),
            False, False, 6,
        )
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(200)
        listbox = Gtk.ListBox()
        checks = []
        for path in paths:
            check = Gtk.CheckButton(label=str(path))
            check.set_active(True)
            checks.append((check, path))
            listbox.add(check)
        scrolled.add(listbox)
        content.pack_start(scrolled, True, True, 6)
        dialog.show_all()
        response = dialog.run()
        to_delete = [p for c, p in checks if c.get_active()] if response == Gtk.ResponseType.OK else []
        dialog.destroy()
        if to_delete:
            self._run_leftover_cleanup_async(to_delete, app_freed)
        else:
            if app_freed:
                self._info_dialog("Uninstall complete", f"Freed {format_size(app_freed)} of disk space.")
            self.reload()

    def _run_leftover_cleanup_async(self, paths, app_freed):
        self.set_sensitive(False)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.show()
        total = len(paths)

        def worker():
            freed_total = app_freed
            all_errors = []
            for i, path in enumerate(paths):
                GLib.idle_add(self._on_leftover_item_start, path, i, total)
                freed, errors = clean_leftovers([path])
                freed_total += freed
                all_errors.extend(errors)
                GLib.idle_add(self._on_leftover_item_done, path, not errors, i + 1, total)
            GLib.idle_add(self._on_leftover_cleanup_done, freed_total, all_errors)

        threading.Thread(target=worker, daemon=True).start()

    def _on_leftover_item_start(self, path, index, total):
        self.status_label.set_text(f"Removing {path.name}… ({index + 1}/{total})")
        self._start_progress_slice(index / total, (index + 1) / total)
        return False

    def _on_leftover_item_done(self, path, ok, done_count, total):
        self._progress_animating = False
        style = self.progress_bar.get_style_context()
        style.remove_class("op-success")
        style.remove_class("op-error")
        style.add_class("op-success" if ok else "op-error")
        self.progress_bar.set_fraction(done_count / total)
        return False

    def _on_leftover_cleanup_done(self, freed_bytes, errors):
        self.set_sensitive(True)
        GLib.timeout_add(800, lambda: (self.reload(), False)[1])
        if errors:
            self._info_dialog(
                "Some leftovers couldn't be deleted",
                f"Freed {format_size(freed_bytes)}.\n\n"
                + "\n".join(f"{p}: {err}" for p, err in errors),
            )
        else:
            self._info_dialog("Uninstall complete", f"Freed {format_size(freed_bytes)} of disk space.")
        return False

    def _info_dialog(self, title, text):
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK, text=title,
        )
        dialog.format_secondary_text(text)
        dialog.run()
        dialog.destroy()


class UninstallerApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.linux-the-uninstaller")

    def do_activate(self):
        (self.props.active_window or UninstallerWindow(self)).present()


def main() -> int:
    # Without this, WM_CLASS defaults to the interpreter name ("python3"),
    # so the desktop shell can't match the running window to our .desktop
    # entry / icon — it shows a generic icon in the dock and alt-tab instead.
    GLib.set_prgname("linux-the-uninstaller")
    GLib.set_application_name("The Uninstaller")
    provider = Gtk.CssProvider()
    provider.load_from_data(_PROGRESS_CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    return UninstallerApp().run(sys.argv)
