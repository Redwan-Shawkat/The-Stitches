"""Updates: what Windows Update, winget, Chocolatey and Scoop would install,
in one list. Windows Update and Chocolatey update as one batch each, so a
bulk update asks for permission once per source, not once per package."""

from .. import updates
from ..elevate import tail
from ..models import format_size
from ..widgets import Page, Table, filter_pill, info, later, search_pill

_SOURCE_TAG = {
    updates.WINDOWS_UPDATE: ("#3441b0", "#eef1ff"),
    updates.WINGET: ("#8a4200", "#fff1e6"),
    updates.CHOCOLATEY: ("#16664b", "#e7f6f0"),
    updates.SCOOP: ("#9b1f5b", "#fdeef5"),
}
_ALL = "All sources"


class UpdatesPage(Page):
    title = "Updates"
    icon = "updates"

    def __init__(self, parent):
        super().__init__(parent)
        self.source, self.search = _ALL, ""
        self.header_button("refresh", "Check again", self.reload)
        filter_pill(self.header, [_ALL, *updates.SOURCES], self._on_filter)
        search_pill(self.header, "Search updates", self._on_search)
        self.table = Table(self.body, [("UPDATE", 0, "w"), ("SOURCE", 120, "w"), ("INSTALLED", 110, "w"),
                                       ("NEW", 110, "w"), ("SIZE", 70, "e")],
                           self._cells, self._show_selection, locked=lambda: self.busy)
        self.table.pack(fill="both", expand=True)
        self.bar.add_button("Update selected", self._on_update, "suggested")

    @staticmethod
    def _cells(u):
        return [[u.name, ("dim", u.detail)] if u.detail and u.detail not in u.name else u.name,
                [("tag", u.source, _SOURCE_TAG[u.source])], u.current or "—", u.new,
                format_size(u.size_bytes) if u.size_bytes else "—"]

    def _on_filter(self, choice):
        self.source = choice
        self.table.filter(self._keep)

    def _on_search(self, text):
        self.search = text.lower()
        self.table.filter(self._keep)

    def _keep(self, u) -> bool:
        return self.source in (_ALL, u.source) and self.search in u.name.lower()

    def _show_selection(self):
        chosen = self.table.chosen()
        if chosen:
            self.bar.say(f"{len(chosen)} selected · {format_size(sum(u.size_bytes for u in chosen))} to download")
        elif not self.busy:
            self.bar.say(f"{len(self.table.items)} updates")

    # ---- checking ----

    def reload(self):
        if self.busy:
            return
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say("Asking Windows Update, winget, Chocolatey and Scoop…")
        self.run_async(updates.find_updates, self._on_found)

    def _on_found(self, found):
        self.bar.done()
        self.set_busy(False)
        self.table.show(found, "Everything is up to date" if not found else "Nothing matches", self._keep)
        sources = sorted({u.source for u in found}, key=updates.SOURCES.index)
        self.subtitle.configure(text=f"{len(found)} waiting, from {', '.join(sources)}" if found else
                                "Everything is up to date")

    # ---- updating ----

    def _on_update(self):
        chosen = self.table.chosen()
        if not chosen:
            info(self.winfo_toplevel(), "Nothing selected", "Tick one or more updates first.")
            return
        jobs = updates.plan_jobs(chosen)
        self.set_busy(True)
        total = len(jobs)

        def work():
            failures = []
            for i, job in enumerate(jobs):
                names = job[0].source if len(job) > 1 else job[0].name
                later(self._on_job_start, f"Updating {names} · {i + 1} of {total}", i, total)
                ok, text = updates.apply(job)
                if not ok:
                    failures.append((job, text))
                later(self.bar.settle, (i + 1) / total, not failures)
            return total, failures

        self.run_async(work, self._on_done)

    def _on_job_start(self, text, index, total):
        self.bar.say(text)
        self.bar.slice(index / total, (index + 1) / total)

    def _on_done(self, result):
        total, failures = result
        self.set_busy(False)
        self.bar.say(f"{total - len(failures)} of {total} updated")
        if failures:
            info(self.winfo_toplevel(), "Some updates didn't go through",
                 "\n\n".join(f"{', '.join(u.name for u in job)}:\n{tail(text)}" for job, text in failures))
        self.after(800, self.reload)
