"""Uninstall: every installed app from APT, Snap, Flatpak and Wine in one
list, with where it came from and how risky it is to remove."""

from gi.repository import GLib, Gtk

from ..models import Risk, Source, format_size
from ..scanner import scan_all
from ..uninstaller import clean_leftovers, uninstall
from ..widgets import RISK_TAG, Page, confirm, esc, info, make_table, show_select_all, strong, tag

COL_SELECTED, COL_NAME, COL_SOURCE, COL_VERSION, COL_SIZE, COL_RISK, COL_REASON, COL_IDX = range(8)
_SOURCE_TAG = {
    Source.APT: ("#8a4200", "#fff1e6"),
    Source.SNAP: ("#3441b0", "#eef1ff"),
    Source.FLATPAK: ("#16664b", "#e7f6f0"),
    Source.WINE: ("#9b1f5b", "#fdeef5"),
    Source.LOCAL: ("#5b2fb3", "#efe8ff"),
}
_ALL = "All sources"


class UninstallPage(Page):
    title = "Uninstall"
    icon = "stitches-uninstall-symbolic"  # icons/: apps, one taken out

    def __init__(self):
        super().__init__()
        self.apps: list = []
        self.search_text = ""
        self.source_filter = _ALL
        self.store = Gtk.ListStore(bool, str, str, str, str, str, str, int)
        self.filter_model = self.store.filter_new()
        self.filter_model.set_visible_func(self._row_visible)

        self.header_button("view-refresh-symbolic", "Scan again", self.reload)
        sources = Gtk.ComboBoxText(valign=Gtk.Align.CENTER)
        for text in (_ALL, *(s.value for s in Source)):
            sources.append_text(text)
        sources.set_active(0)
        sources.connect("changed", self._on_source_changed)
        self.header.pack_end(sources, False, False, 0)
        search = Gtk.SearchEntry(placeholder_text="Search installed software", width_chars=26, valign=Gtk.Align.CENTER)
        search.connect("search-changed", self._on_search_changed)
        self.header.pack_end(search, False, False, 0)

        table, tree, self.select_all = make_table(
            self.filter_model,
            [("APP", COL_NAME, True), ("INSTALLED VIA", COL_SOURCE, False), ("VERSION", COL_VERSION, False),
             ("SIZE", COL_SIZE, False), ("RISK TO REMOVE", COL_RISK, False)],
            on_toggle=self._on_toggled, toggle_col=COL_SELECTED, on_toggle_all=self._select,
        )
        self.select_all.set_tooltip_text("Select all, except system-critical")
        tree.set_tooltip_column(COL_REASON)
        self.body.pack_start(table, True, True, 0)

        self.bar.add_button("Uninstall selected", self._on_uninstall_clicked, "destructive-action")

    # ---- filtering and selection ----

    def _row_visible(self, model, it, _data):
        app = self.apps[model[it][COL_IDX]]
        if self.source_filter != _ALL and app.source.value != self.source_filter:
            return False
        return self.search_text.lower() in app.name.lower()

    def _on_search_changed(self, entry):
        self.search_text = entry.get_text()
        self.filter_model.refilter()
        self._show_selection()

    def _on_source_changed(self, combo):
        self.source_filter = combo.get_active_text()
        self.filter_model.refilter()
        self._show_selection()

    def _on_toggled(self, path):
        child = self.filter_model.convert_iter_to_child_iter(self.filter_model.get_iter(path))
        self.store[child][COL_SELECTED] = not self.store[child][COL_SELECTED]
        self._show_selection()

    def _shown(self):
        """The rows the search and source filter leave on screen."""
        return [self.store[self.filter_model.convert_iter_to_child_iter(row.iter)] for row in self.filter_model]

    def _can_select_all(self, row) -> bool:
        return self.apps[row[COL_IDX]].risk != Risk.CRITICAL  # those stay one at a time, on purpose

    def _select(self, value):
        """The header checkbox: every app on screen that isn't system-critical, or none."""
        for row in self._shown():
            row[COL_SELECTED] = value and self._can_select_all(row)
        self._show_selection()

    def _selected(self):
        return [self.apps[row[COL_IDX]] for row in self.store if row[COL_SELECTED]]

    def _show_selection(self):
        chosen = self._selected()
        self.bar.say(f"{strong(f'{len(chosen)} selected')} · {format_size(sum(a.size_bytes for a in chosen))}"
                     if chosen else f"{len(self.apps)} apps")
        shown = self._shown()
        show_select_all(self.select_all, sum(row[COL_SELECTED] and self._can_select_all(row) for row in shown),
                        sum(map(self._can_select_all, shown)))

    # ---- scanning ----

    def reload(self):
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say("Scanning for installed software…")
        self.run_async(scan_all, self._on_scan_done)

    def _on_scan_done(self, apps):
        self.bar.done()
        self.apps = apps
        self.store.clear()
        for idx, app in enumerate(apps):
            self.store.append([
                False, esc(app.name), tag(app.source.value, _SOURCE_TAG[app.source]), esc(app.version),
                app.size_human if app.size_bytes else "—", tag(app.risk.value, RISK_TAG[app.risk]),
                esc(app.risk_reason), idx,
            ])
        found = sorted({a.source.value for a in apps}, key=[s.value for s in Source].index)
        self.subtitle.set_text(f"{len(apps)} apps from {', '.join(found)}" if apps else "Nothing found")
        self._show_selection()
        self.set_busy(False)

    # ---- uninstall flow ----

    def _on_uninstall_clicked(self):
        selected = self._selected()
        if not selected:
            info(self.window(), "Nothing selected", "Check one or more items first.")
            return
        critical = any(a.risk == Risk.CRITICAL for a in selected)
        if confirm(self.window(), f"Uninstall {len(selected)} item(s)?",
                   [f"• {a.name} — {a.source.value} — {a.risk.value}" for a in selected], "Uninstall",
                   "I understand this includes system-critical software" if critical else ""):
            self._run_uninstall_async(selected)

    def _run_uninstall_async(self, apps):
        self.set_busy(True)
        total = len(apps)

        def work():
            results = []
            for i, app in enumerate(apps):
                GLib.idle_add(self._on_item_start, f"Uninstalling {strong(app.name)} · {i + 1} of {total}", i, total)
                ok, message, leftovers = uninstall(app)
                results.append((app, ok, message, leftovers))
                GLib.idle_add(self._on_item_done, ok, i + 1, total,
                              f"{strong(app.name)} removed" if ok else f"{strong(app.name)} failed: {esc(message)}")
            return results

        self.run_async(work, self._on_uninstall_done)

    def _on_item_start(self, markup, index, total):
        self.bar.say(markup)
        self.bar.slice(index / total, (index + 1) / total)

    def _on_item_done(self, ok, done_count, total, markup):
        self.bar.settle(done_count / total, ok)
        self.bar.say(markup)

    def _on_uninstall_done(self, results):
        self.set_busy(False)
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
            info(self.window(), "Some items failed to uninstall", "\n".join(f"{a.name}: {m}" for a, m in failures))
        if warnings:
            info(self.window(), "Removed, with a warning", "\n".join(f"{a.name}: {m}" for a, m in warnings))
        if all_leftovers:
            # The uninstall's own final line stays up until the leftover
            # question is answered, instead of flashing away under the dialog.
            self._offer_leftover_cleanup(all_leftovers, app_freed)
        else:
            if app_freed:
                info(self.window(), "Uninstall complete", f"Freed {format_size(app_freed)} of disk space.")
            GLib.timeout_add(800, lambda: (self.reload(), False)[1])

    def _offer_leftover_cleanup(self, paths, app_freed):
        dialog = Gtk.Dialog(title="Leftover files found", transient_for=self.window(), modal=True)
        dialog.add_buttons("Skip", Gtk.ResponseType.CANCEL, "Delete Selected", Gtk.ResponseType.OK)
        content = dialog.get_content_area()
        content.pack_start(Gtk.Label(label="These weren't removed by the uninstaller. Delete them too?"),
                           False, False, 6)
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(200)
        listbox = Gtk.ListBox()
        checks = []
        for path in paths:
            check = Gtk.CheckButton(label=str(path), active=True)
            checks.append((check, path))
            listbox.add(check)
        scroll.add(listbox)
        content.pack_start(scroll, True, True, 6)
        dialog.show_all()
        response = dialog.run()
        to_delete = [p for c, p in checks if c.get_active()] if response == Gtk.ResponseType.OK else []
        dialog.destroy()
        if to_delete:
            self._run_leftover_cleanup_async(to_delete, app_freed)
        else:
            if app_freed:
                info(self.window(), "Uninstall complete", f"Freed {format_size(app_freed)} of disk space.")
            self.reload()

    def _run_leftover_cleanup_async(self, paths, app_freed):
        self.set_busy(True)
        total = len(paths)

        def work():
            freed_total, all_errors = app_freed, []
            for i, path in enumerate(paths):
                GLib.idle_add(self._on_item_start, f"Removing {strong(path.name)} · {i + 1} of {total}", i, total)
                freed, errors = clean_leftovers([path])
                freed_total += freed
                all_errors.extend(errors)
                GLib.idle_add(self._on_item_done, not errors, i + 1, total, f"Removed {strong(path.name)}")
            return freed_total, all_errors

        self.run_async(work, self._on_leftover_cleanup_done)

    def _on_leftover_cleanup_done(self, result):
        freed_bytes, errors = result
        self.set_busy(False)
        GLib.timeout_add(800, lambda: (self.reload(), False)[1])
        if errors:
            info(self.window(), "Some leftovers couldn't be deleted",
                 f"Freed {format_size(freed_bytes)}.\n\n" + "\n".join(f"{p}: {err}" for p, err in errors))
        else:
            info(self.window(), "Uninstall complete", f"Freed {format_size(freed_bytes)} of disk space.")
