"""Updates: every pending update from APT, Snap, Flatpak and GitHub-released
AppImages in one list, updated in bulk behind the line loader. The circle
over the ticks selects them all, so there's no separate Update all."""

import time

from gi.repository import GLib, Gtk

from .. import updates
from ..models import format_size
from ..shell import tail
from ..widgets import Page, arrow, info, make_table, show_select_all, strong, tag, two_lines

COL_SELECTED, COL_NAME, COL_SOURCE, COL_VERSION, COL_SIZE, COL_STATUS, COL_IDX = range(7)
_SOURCE_TAG = {
    updates.APT: ("#8a4200", "#fff1e6"),
    updates.SNAP: ("#3441b0", "#eef1ff"),
    updates.FLATPAK: ("#16664b", "#e7f6f0"),
    updates.GITHUB: ("#22242b", "#ececef"),
}
_STATUS = {  # status -> Pango attributes
    "Available": 'alpha="60%"',
    "Queued": 'alpha="60%"',
    "Updating…": 'foreground="#4c5ce6" weight="600"',
    "Updated": 'foreground="#1e8a4c" weight="600"',
    "Failed": 'foreground="#c62f28" weight="600"',
}
_ALL = "All sources"


class UpdatesPage(Page):
    title = "Updates"
    icon = "software-update-available-symbolic"

    def __init__(self):
        super().__init__()
        self.updates: list = []
        self.search_text = ""
        self.source_filter = _ALL
        self.store = Gtk.ListStore(bool, str, str, str, str, str, int)
        self.filter_model = self.store.filter_new()
        self.filter_model.set_visible_func(self._row_visible)

        self.header_button("view-refresh-symbolic", "Check again", self.reload)
        sources = Gtk.ComboBoxText(valign=Gtk.Align.CENTER)
        for text in (_ALL, *updates.SOURCES):
            sources.append_text(text)
        sources.set_active(0)
        sources.connect("changed", self._on_source_changed)
        self.header.pack_end(sources, False, False, 0)
        search = Gtk.SearchEntry(placeholder_text="Search updates", width_chars=22, valign=Gtk.Align.CENTER)
        search.connect("search-changed", self._on_search_changed)
        self.header.pack_end(search, False, False, 0)

        table, _tree, self.select_all = make_table(
            self.filter_model,
            [("APP", COL_NAME, True), ("SOURCE", COL_SOURCE, False), ("VERSION", COL_VERSION, False),
             ("SIZE", COL_SIZE, False), ("STATUS", COL_STATUS, False)],
            on_toggle=self._on_toggled, toggle_col=COL_SELECTED, on_toggle_all=self._select,
        )
        self.body.pack_start(table, True, True, 0)

        self.update_button = self.bar.add_button("Update selected", self._on_update_clicked, "suggested-action")

    # ---- filtering and selection ----

    def _row_visible(self, model, it, _data):
        u = self.updates[model[it][COL_IDX]]
        if self.source_filter != _ALL and u.source != self.source_filter:
            return False
        return self.search_text.lower() in u.name.lower()

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

    def _select(self, value):
        """The header checkbox: every update on screen that's still to do, or none."""
        for row in self._shown():
            row[COL_SELECTED] = value and "Updated" not in row[COL_STATUS]
        self._show_selection()

    def _pending(self):
        return [self.updates[row[COL_IDX]] for row in self.store if "Updated" not in row[COL_STATUS]]

    def _show_selection(self):
        n = sum(1 for row in self.store if row[COL_SELECTED])
        self.update_button.set_label(f"Update selected · {n}" if n else "Update selected")
        shown = self._shown()
        show_select_all(self.select_all, sum(row[COL_SELECTED] for row in shown),
                        sum("Updated" not in row[COL_STATUS] for row in shown))

    def _set_status(self, update, status):
        idx = self.updates.index(update)
        for row in self.store:
            if row[COL_IDX] == idx:
                row[COL_STATUS] = f"<span {_STATUS[status]}>{status}</span>"
                if status == "Updated":
                    row[COL_SELECTED] = False

    # ---- checking ----

    def reload(self):
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say("Checking APT, Snap, Flatpak and GitHub for updates…")
        self.run_async(updates.find_updates, self._on_check_done)

    def _on_check_done(self, found):
        self.bar.done()
        self.updates = found
        self.store.clear()
        for idx, u in enumerate(found):
            self.store.append([
                False, two_lines(u.name, u.detail), tag(u.source, _SOURCE_TAG[u.source]), arrow(u.current, u.new),
                format_size(u.size_bytes) if u.size_bytes else "—",
                f"<span {_STATUS['Available']}>Available</span>", idx,
            ])
        self._show_summary(time.strftime("%H:%M"))
        self._show_selection()
        self.bar.say(f"{len(found)} updates" if found else "Everything is up to date")
        self.set_busy(False)

    def _show_summary(self, checked_at):
        sources = [s for s in updates.SOURCES if any(u.source == s for u in self.updates)]
        n = len(self.updates)
        self.subtitle.set_text(
            f"{n} update{'s' * (n != 1)} from {', '.join(sources)} · checked {checked_at}" if n
            else f"Everything is up to date · checked {checked_at}"
        )
        self.set_count(n)

    # ---- updating ----

    def _on_update_clicked(self):
        chosen = [self.updates[row[COL_IDX]] for row in self.store if row[COL_SELECTED]]
        if not chosen:
            info(self.window(), "Nothing selected", "Check one or more updates first.")
            return
        for u in chosen:
            self._set_status(u, "Queued")
        self.set_busy(True)
        jobs, total = updates.plan_jobs(chosen), len(chosen)

        def work():
            done, failures = 0, []
            for job in jobs:
                GLib.idle_add(self._on_job_start, job, done, total)
                ok, message = updates.apply(job)
                if not ok:
                    failures.append((job, message))
                done += len(job)
                GLib.idle_add(self._on_job_done, job, ok, done, total)
            return total, failures

        self.run_async(work, self._on_all_done)

    def _on_job_start(self, job, done, total):
        for u in job:
            self._set_status(u, "Updating…")
        if len(job) == 1:
            self.bar.say(f"Updating {strong(job[0].name)} · {done + 1} of {total}")
        else:
            self.bar.say(f"Updating {strong(f'{len(job)} {job[0].source} packages')} · "
                         f"{done + 1}–{done + len(job)} of {total} · asks for your password")
        self.bar.slice(done / total, (done + len(job)) / total)

    def _on_job_done(self, job, ok, done, total):
        for u in job:
            self._set_status(u, "Updated" if ok else "Failed")
        self.bar.settle(done / total, ok)

    def _on_all_done(self, result):
        total, failures = result
        failed = sum(len(job) for job, _ in failures)
        self.bar.say(f"Updated {strong(str(total - failed))} of {total}" + (f" · {failed} failed" if failed else ""))
        self.set_count(len(self._pending()))
        self._show_selection()
        self.set_busy(False)
        if failures:
            info(self.window(), "Some updates failed", "\n\n".join(
                f"{', '.join(u.name for u in job)}:\n{tail(message, 4)}" for job, message in failures))
