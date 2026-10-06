"""App Manager, as on Linux: the catalog as tiles side by side — each app's
icon, what's installed, at what version and through what — with search and
filters, and bulk install through winget, one app at a time, behind the line
loader. The Terminal under the tiles shows each install as it runs; every
result comes from looking again."""

import subprocess
import tkinter as tk

from .. import appmanager
from ..catalog import CATALOG, CATEGORIES
from ..elevate import tail
from ..models import Risk
from ..widgets import RISK_TAG, STATUS_TAG, Page, Terminal, Tiles, filter_pill, info, later, os_switch, px, search_pill

_ALL, _ANY = "All categories", "Any status"
_WORD_TAG = {"Installed": RISK_TAG[Risk.SAFE], "Installing…": STATUS_TAG["Info"], "Failed": RISK_TAG[Risk.CRITICAL]}
_INK = {"Installed": "#6fcf97", "Failed": "#ff6b5e"}


class AppsPage(Page):
    title = "App Manager"
    icon = "apps"

    def __init__(self, parent):
        super().__init__(parent)
        self.statuses = {app: appmanager.NOT_INSTALLED for app in CATALOG}
        self.words = {}  # app -> a word of its own while it's queued, installing or failed
        self.pictures = {}  # app -> its icon, kept: Tk drops an image nothing holds on to
        self.category, self.state, self.search = _ALL, _ANY, ""
        self.header_button("refresh", "Check again", self.reload)
        filter_pill(self.header, [_ANY, "Installed", "Not installed"], lambda c: self._set(state=c))
        filter_pill(self.header, [_ALL, *CATEGORIES], lambda c: self._set(category=c))
        search_pill(self.header, "Search apps", lambda t: self._set(search=t.lower()))
        os_switch(self.header, "Windows", "Linux")
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(0, weight=1)
        self.table = Tiles(self.body, "APPS", self._cells, self._picture, self._show_selection,
                           tickable=self._tickable, locked=lambda: self.busy)
        self.table.grid(row=0, column=0, sticky="nsew", pady=(0, px(12)))
        self.terminal = Terminal(self.body, "Each install's command and what it prints show up here.", _INK)
        self.terminal.configure(height=px(160))
        self.terminal.grid(row=1, column=0, sticky="ew")
        self.bar.add_button("Install selected", self._on_install, "suggested")

    def _tickable(self, app) -> bool:
        return not self.statuses[app].installed and self.words.get(app) not in ("Queued", "Installing…")

    def _picture(self, app):
        if app not in self.pictures:
            picture = tk.PhotoImage(master=self, file=str(app.icon))  # 64 pixels
            self.pictures[app] = picture.subsample(max(1, round(64 / px(32))))
        return self.pictures[app]

    def _cells(self, app):
        status, word = self.statuses[app], self.words.get(app)
        word = word or ("Installed" if status.installed else "Not installed")
        line = [("tag", word, _WORD_TAG[word])] if word in _WORD_TAG else [("dim", word)]
        if status.installed:
            line += [status.version or "version unknown", ("dim", f"via {status.via}") if status.via != "winget" else ""]
        return [[("bold", app.name)], [("dim", f"{app.description} · {app.category}")], line]

    def _set(self, **choice):
        self.__dict__.update(choice)
        self.table.filter(self._keep)

    def _keep(self, app) -> bool:
        return (self.category in (_ALL, app.category)
                and (self.state == _ANY or self.statuses[app].installed == (self.state == "Installed"))
                and self.search in f"{app.name} {app.description}".lower())

    def _show_selection(self):
        chosen = self.table.chosen()
        if chosen:
            self.bar.say(f"{len(chosen)} selected")
        elif not self.busy:
            have = sum(s.installed for s in self.statuses.values())
            self.bar.say(f"{have} of {len(CATALOG)} installed · installs through winget; each installer asks "
                         "for permission itself")

    # ---- checking ----

    def reload(self):
        if self.busy:
            return
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say("Asking winget what's installed, and looking on PATH…")
        self.run_async(appmanager.check, self._on_checked)

    def _on_checked(self, statuses):
        self.bar.done()
        self.set_busy(False)
        self.statuses = dict(zip(CATALOG, statuses))
        self.table.show(list(CATALOG), "Nothing matches", self._keep)
        have = sum(s.installed for s in statuses)
        self.subtitle.configure(text=f"{have} of {len(CATALOG)} installed")

    # ---- installing ----

    def _on_install(self):
        chosen = self.table.chosen()
        if not chosen:
            info(self.winfo_toplevel(), "Nothing selected", "Tick one or more apps that aren't installed yet.")
            return
        self.words = {app: "Queued" for app in chosen}
        self.table.selected.clear()
        self.table.redraw()
        self.set_busy(True)
        self.terminal.clear()
        total = len(chosen)

        def log(line):
            if (line := appmanager.readable(line)) is not None:
                self.terminal.log(line)

        def work():
            failures = []
            for i, app in enumerate(chosen):
                later(self._on_app_start, app, i, total)
                self.terminal.log(f"▶ {app.name} · winget")
                self.terminal.log(f"$ {subprocess.list2cmdline(appmanager.install_command(app))}")
                _code, text = appmanager.install(app, on_line=log)
                statuses = appmanager.check()  # did it work? Ask winget, not the exit code
                ok = statuses[CATALOG.index(app)].installed
                self.terminal.log(f"{'Installed' if ok else 'Failed'}: {app.name}")
                if not ok:
                    failures.append((app, text))
                later(self._on_app_done, statuses, app, ok, i + 1, total)
            return total, failures

        self.run_async(work, self._on_done)

    def _on_app_start(self, app, index, total):
        self.words[app] = "Installing…"
        self.table.redraw()
        self.bar.say(f"Installing {app.name} · {index + 1} of {total}")
        self.bar.slice(index / total, (index + 1) / total)

    def _on_app_done(self, statuses, app, ok, done, total):
        self.statuses = dict(zip(CATALOG, statuses))
        self.words[app] = None if ok else "Failed"
        self.table.redraw()
        self.bar.settle(done / total, ok)

    def _on_done(self, result):
        total, failures = result
        self.set_busy(False)
        self.words = {app: word for app, word in self.words.items() if word == "Failed"}
        self.table.filter(self._keep)
        self.bar.say(f"{total - len(failures)} of {total} installed")
        if failures:
            info(self.winfo_toplevel(), "Some apps weren't installed",
                 "\n\n".join(f"{app.name}:\n{tail(text)}" for app, text in failures))
