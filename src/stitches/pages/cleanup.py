"""Cleanup: caches, temp files, old logs and old package versions, each
shown with where it lives and what removing it means (its risk at the end),
a filter by risk or password, and a live log of exactly what was removed
from where."""

from pathlib import Path

from gi.repository import GLib, Gtk, Pango

from .. import cleanup
from ..models import format_size
from ..models import Risk
from ..widgets import (RISK_TAG, Page, card, confirm, esc, info, label, make_table, scrolled, show_select_all,
                       strong, tag)

COL_SELECTED, COL_NAME, COL_SIZE, COL_REASON, COL_IDX = range(5)
_HOME = str(Path.home())
_FILTERS = {  # what the header's filter shows
    "All locations": lambda loc: True,
    "Safe": lambda loc: loc.risk == Risk.SAFE,
    "Caution": lambda loc: loc.risk == Risk.CAUTION,
    "No password needed": lambda loc: not loc.admin,
}
_ABOUT = ("Removes only what gets rebuilt or downloaded again. Your files and installed apps stay; "
          "Trash is the one exception.")


def _pretty(path: str) -> str:
    return "~" + path[len(_HOME):] if path.startswith(_HOME) else path


class CleanupPage(Page):
    title = "Cleanup"
    icon = "tool-brush-symbolic"

    def __init__(self):
        super().__init__()
        self.locations: list = []
        self.store = Gtk.ListStore(bool, str, str, str, int)
        self.keep = _FILTERS["All locations"]
        self.filter_model = self.store.filter_new()
        self.filter_model.set_visible_func(lambda model, it, _d: self.keep(self.locations[model[it][COL_IDX]]))
        self.header_button("view-refresh-symbolic", "Scan again", self.reload)
        shown = Gtk.ComboBoxText(valign=Gtk.Align.CENTER)
        for text in _FILTERS:
            shown.append_text(text)
        shown.set_active(0)
        shown.connect("changed", self._on_filter_changed)
        self.header.pack_end(shown, False, False, 0)

        table, _tree, self.select_all = make_table(
            self.filter_model, [("LOCATION", COL_NAME, True), ("WHAT REMOVING IT MEANS", COL_REASON, "wrap"),
                                ("SIZE", COL_SIZE, False)],
            on_toggle=self._on_toggled, toggle_col=COL_SELECTED, on_toggle_all=self._select,
        )
        self.body.pack_start(table, True, True, 0)

        aside = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=8, width_request=300)
        top = Gtk.Box()
        top.pack_start(label("Removed from", "card-title"), True, True, 0)
        self.freed = label("", "dim")
        top.pack_end(self.freed, False, False, 0)
        aside.pack_start(top, False, False, 0)
        self.log = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        empty = label("Nothing removed yet.\nEach path is listed here as it goes.",
                      "dim", xalign=0.5, justify=Gtk.Justification.CENTER)
        empty.show()
        self.log.set_placeholder(empty)
        self.log_scroll = scrolled(self.log)
        aside.pack_start(self.log_scroll, True, True, 0)
        self.body.pack_start(card(aside), False, False, 0)

        self.remove_button = self.bar.add_button("Remove selected", self._on_remove_clicked, "destructive-action")

    def _on_filter_changed(self, combo):
        self.keep = _FILTERS[combo.get_active_text()]
        self.filter_model.refilter()
        self._show_selection()

    def _on_toggled(self, path):
        child = self.filter_model.convert_iter_to_child_iter(self.filter_model.get_iter(path))
        self.store[child][COL_SELECTED] = not self.store[child][COL_SELECTED]
        self._show_selection()

    def _shown(self):
        """The rows the filter leaves on screen."""
        return [self.store[self.filter_model.convert_iter_to_child_iter(row.iter)] for row in self.filter_model]

    def _select(self, value):
        for row in self._shown():
            row[COL_SELECTED] = value
        self._show_selection()

    def _selected(self):
        return [self.locations[row[COL_IDX]] for row in self.store if row[COL_SELECTED]]

    def _show_selection(self):
        size = sum(loc.size_bytes for loc in self._selected())
        self.remove_button.set_label(f"Remove selected · {format_size(size)}" if size else "Remove selected")
        shown = self._shown()
        show_select_all(self.select_all, sum(row[COL_SELECTED] for row in shown), len(shown))

    # ---- scanning ----

    def reload(self):
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say("Measuring caches, logs and temp files…")
        self.run_async(cleanup.scan, self._on_scan_done)

    def _on_scan_done(self, locations):
        self.bar.done()
        self.locations = locations
        self.store.clear()
        for idx, loc in enumerate(locations):
            name = esc(loc.name) + ("  " + tag("password", ("#5a5c66", "#ececef")) if loc.admin else "")
            self.store.append([
                False, f'{name}\n<span size="small" alpha="60%">{esc(loc.where)}</span>',
                format_size(loc.size_bytes) if loc.size_bytes else "—",
                f'<span size="small">{esc(loc.reason)}</span>  {tag(loc.risk.value, RISK_TAG[loc.risk])}', idx,
            ])
        total = sum(loc.size_bytes for loc in locations)
        self.subtitle.set_text(f"{format_size(total)} reclaimable across {len(locations)} locations"
                               if locations else "Nothing to clean")
        self.bar.say(_ABOUT)
        self._show_selection()
        self.set_busy(False)

    # ---- cleaning ----

    def _on_remove_clicked(self):
        chosen = self._selected()
        if not chosen:
            info(self.window(), "Nothing selected", "Check one or more locations first.")
            return
        if not confirm(self.window(), f"Remove {format_size(sum(c.size_bytes for c in chosen))} "
                       f"from {len(chosen)} location(s)?",
                       [f"• {c.name} — {c.where} — {c.risk.value}" for c in chosen], "Remove"):
            return
        self.set_busy(True)
        for row in self.log.get_children():
            self.log.remove(row)
        self._freed_so_far = 0
        total = len(chosen)

        def work():
            freed, errors = 0, 0
            for i, loc in enumerate(chosen):
                GLib.idle_add(self._on_location_start, loc, i, total)
                failed = []

                def log(what, size, error):
                    failed.extend([error] if error else [])
                    GLib.idle_add(self._add_log_line, what, size, error)

                freed += cleanup.clean(loc, log)
                errors += len(failed)
                GLib.idle_add(self.bar.settle, (i + 1) / total, not failed)
            return freed, errors

        self.run_async(work, self._on_clean_done)

    def _on_location_start(self, loc, index, total):
        self.bar.say(f"Cleaning {strong(loc.name)} · {index + 1} of {total}"
                     + (" · asks for your password" if loc.admin else ""))
        self.bar.slice(index / total, (index + 1) / total)

    def _add_log_line(self, what, size, error):
        row = Gtk.Box(spacing=8, margin_top=4, margin_bottom=4)
        dot = "#c62f28" if error else "#1e8a4c"
        row.pack_start(label(f'<span foreground="{dot}">●</span>', use_markup=True), False, False, 0)
        row.pack_start(label(_pretty(what), "mono", ellipsize=Pango.EllipsizeMode.MIDDLE,
                             tooltip_text=error or _pretty(what)), True, True, 0)
        row.pack_end(label("failed" if error else format_size(size), "dim"), False, False, 0)
        self.log.add(row)
        row.show_all()
        self._freed_so_far += size
        self.freed.set_text(f"{format_size(self._freed_so_far)} freed")
        adj = self.log_scroll.get_vadjustment()
        GLib.idle_add(lambda: adj.set_value(adj.get_upper()))

    def _on_clean_done(self, result):
        freed, errors = result
        self.set_busy(False)
        self.bar.say(f"Freed {strong(format_size(freed))}" + (f" · {errors} item(s) couldn't be removed" if errors else ""))
        self.run_async(cleanup.scan, self._on_rescan_done)

    def _on_rescan_done(self, locations):
        # Rescan without pulsing the bar, so the final "Freed …" line stays up.
        status = self.bar.status.get_label()
        self._on_scan_done(locations)
        self.bar.say(status)
