"""Cleanup: caches, temp files and the Recycle Bin, each saying where it
lives, what removing it means and how risky that is. Nothing is ticked at
first, and removal always goes through the confirmation dialog (CLAUDE.md)."""

from .. import cleanup
from ..models import Risk, format_size
from ..widgets import RISK_TAG, Page, Table, confirm, filter_pill, info, later

_ALL, _NO_PROMPT = "All locations", "No permission needed"
_FILTERS = {
    _ALL: lambda _loc: True,
    Risk.SAFE.value: lambda loc: loc.risk == Risk.SAFE,
    Risk.CAUTION.value: lambda loc: loc.risk == Risk.CAUTION,
    _NO_PROMPT: lambda loc: not loc.admin,
}
_EXPLAIN = "Removes only what gets rebuilt or downloaded again. Your files and installed apps stay; " \
           "the Recycle Bin is the one exception."


class CleanupPage(Page):
    title = "Cleanup"
    icon = "cleanup"

    def __init__(self, parent):
        super().__init__(parent)
        self.keep = _FILTERS[_ALL]
        self.header_button("refresh", "Measure again", self.reload)
        filter_pill(self.header, list(_FILTERS), self._on_filter)
        self.table = Table(self.body, [("LOCATION", 190, "w"), ("WHERE", 200, "w"), ("WHAT IT MEANS", 0, "w"),
                                       ("SIZE", 80, "e")],
                           self._cells, self._show_selection, tooltip=lambda loc: loc.reason,
                           locked=lambda: self.busy)
        self.table.pack(fill="both", expand=True)
        self.bar.add_button("Clean selected", self._on_clean, "destructive")

    @staticmethod
    def _cells(loc):
        return [loc.name, [("dim", loc.where)], [loc.reason, ("tag", loc.risk.value, RISK_TAG[loc.risk])],
                format_size(loc.size_bytes)]

    def _on_filter(self, choice):
        self.keep = _FILTERS[choice]
        self.table.filter(self.keep)

    def _show_selection(self):
        chosen = self.table.chosen()
        if chosen:
            self.bar.say(f"{len(chosen)} selected · {format_size(sum(loc.size_bytes for loc in chosen))}")
        elif not self.busy:
            self.bar.say(_EXPLAIN)

    def reload(self):
        if self.busy:
            return
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say("Measuring caches and temp files…")
        self.run_async(cleanup.scan, self._on_scanned)

    def _on_scanned(self, locations):
        self.bar.done()
        self.set_busy(False)
        self.table.show(locations, "Nothing to clean" if not locations else "Nothing matches", self.keep)
        total = sum(loc.size_bytes for loc in locations)
        self.subtitle.configure(text=f"{format_size(total)} in {len(locations)} places" if locations else
                                "Nothing to clean")

    def _on_clean(self):
        chosen = self.table.chosen()
        if not chosen:
            info(self.winfo_toplevel(), "Nothing selected", "Tick one or more locations first.")
            return
        if not confirm(self.winfo_toplevel(), f"Clean {len(chosen)} location(s)?",
                       [f"• {loc.name} — {format_size(loc.size_bytes)} — {loc.risk.value}"
                        + (" — asks for permission" if loc.admin else "") for loc in chosen], "Clean"):
            return
        self.set_busy(True)
        total = len(chosen)

        def work():
            freed, errors = 0, []

            def log(what, size, error):
                if error:
                    errors.append(f"{what}: {error}")
                later(self.bar.say, f"Couldn't remove {what}" if error else f"Removed {format_size(size)} from {what}")

            for i, loc in enumerate(chosen):
                later(self._on_location_start, f"Cleaning {loc.name} · {i + 1} of {total}", i, total)
                freed += cleanup.clean(loc, log)
                later(self.bar.settle, (i + 1) / total, not errors)
            return freed, errors

        self.run_async(work, self._on_done)

    def _on_location_start(self, text, index, total):
        self.bar.say(text)
        self.bar.slice(index / total, (index + 1) / total)

    def _on_done(self, result):
        freed, errors = result
        self.set_busy(False)
        if errors:
            info(self.winfo_toplevel(), "Some things couldn't be removed",
                 f"Freed {format_size(freed)}.\n\n" + "\n".join(errors[:12])
                 + (f"\n…and {len(errors) - 12} more" if len(errors) > 12 else ""))
        else:
            info(self.winfo_toplevel(), "Cleanup complete", f"Freed {format_size(freed)} of disk space.")
        self.reload()
