"""App Manager, as on Linux: the catalog as tiles side by side — each app's
icon, what's installed, at what version and through what — with search and
filters, and bulk install through winget, one app at a time, behind the line
loader. Clicking a tile opens its details: what it is, how to install it by
hand, and the steps some apps need afterwards. The Terminal under it all
shows each install as it runs; every result comes from looking again."""

import os
import subprocess
import tkinter as tk

from .. import appmanager
from ..catalog import CATALOG, CATEGORIES
from ..elevate import tail
from ..models import Risk
from ..widgets import (FONTS, RISK_TAG, STATUS_TAG, Button, IconButton, Page, Rounded, Terminal, Tiles, filter_pill,
                       info, later, os_switch, px, role, search_pill)
from .databases import DatabasePanel

_ALL, _ANY = "All categories", "Any status"
_WORD_TAG = {"Installed": RISK_TAG[Risk.SAFE], "Installing…": STATUS_TAG["Info"], "Failed": RISK_TAG[Risk.CRITICAL]}
_INK = {"Installed": "#6fcf97", "Failed": "#ff6b5e"}
_WRAP = 360  # how wide the details cards' text wraps, at 96 DPI


def _card(parent, title: str):
    """A titled card in the details, and the frame its content goes in."""
    card = Rounded(parent, radius=14, pad=12, bg="card", border="border")
    role(tk.Label(card.inner, text=title.upper(), font=FONTS["caps"], anchor="w"), fg="dim").pack(fill="x")
    return card


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
                           on_open=self._open, group=lambda app: app.category,
                           tickable=self._tickable, locked=lambda: self.busy)
        self.table.grid(row=0, column=0, sticky="nsew", pady=(0, px(12)))
        # The details sit in the tiles' own cell, so the Terminal and the action
        # bar stay put while they swap — as on Linux, where they're two children
        # of one Gtk.Stack inside the body. Both stay gridded and the one to show
        # is raised: a Tk cell that has held two widgets stops re-mapping either
        # after a grid_remove(), and stacking order has no such trouble.
        self.shown = None  # the app whose details are open
        self.details = self._build_details()
        self.details.grid(row=0, column=0, sticky="nsew", pady=(0, px(12)))
        tk.Misc.lift(self.table)  # Canvas.tkraise raises items drawn on it, not the widget
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

    # ---- an app's details ----

    def _build_details(self):
        """Built once and filled when an app is opened, so opening one is a
        swap, not a rebuild. The cards: who it is, what it does, how to
        install it by hand, and what some apps need afterwards."""
        view = tk.Frame(self.body)
        view.columnconfigure((0, 1), weight=1, uniform="details")

        top = Rounded(view, radius=14, pad=10, bg="card", border="border")
        IconButton(top.inner, "back", "All apps", self._close, size=30, icon=15, hover="border").pack(side="left")
        self.detail_icon = tk.Label(top.inner)
        self.detail_icon.pack(side="left", padx=px(12))
        words = tk.Frame(top.inner)
        words.pack(side="left", fill="x", expand=True)
        self.detail_name = tk.Label(words, font=FONTS["heading"], anchor="w")
        self.detail_name.pack(fill="x")
        self.detail_line = role(tk.Label(words, anchor="w"), fg="dim")
        self.detail_line.pack(fill="x")
        self.detail_install = Button(top.inner, "Install", self._install_shown, "suggested")
        top.configure(height=px(62))  # gridded "ew", so it needs its own height
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, px(12)))
        view.rowconfigure(1, weight=1)  # the two cards under it take the rest

        about = _card(view, "What it does")
        self.detail_about = tk.Label(about.inner, anchor="w", justify="left", wraplength=px(_WRAP))
        self.detail_about.pack(fill="x", pady=(px(6), 0))
        self.detail_site = role(tk.Label(about.inner, anchor="w", cursor="hand2"), fg="dim")
        self.detail_site.pack(fill="x", pady=(px(6), 0))
        self.detail_site.bind("<Button-1>", lambda _e: self.shown and os.startfile(self.shown.site))
        about.grid(row=1, column=0, sticky="nsew", padx=(0, px(8)))

        manual = _card(view, "Install it yourself")
        IconButton(manual.inner, "copy", "Copy the command", self._copy_steps, size=28, icon=14,
                   hover="border").place(relx=1.0, y=0, anchor="ne")
        role(tk.Label(manual.inner, anchor="w", justify="left", wraplength=px(_WRAP),
                      text="In a terminal, the same install Stitches runs:"), fg="dim").pack(fill="x", pady=(px(6), 0))
        self.detail_steps = tk.Label(manual.inner, anchor="w", justify="left", font=("Consolas", 9),
                                     wraplength=px(_WRAP))
        self.detail_steps.pack(fill="x", pady=(px(6), 0))
        manual.grid(row=1, column=1, sticky="nsew", padx=(px(8), 0))

        self.setup_card = _card(view, "After installing")
        self.detail_setup = tk.Label(self.setup_card.inner, anchor="w", justify="left", wraplength=px(2 * _WRAP))
        self.detail_setup.pack(fill="x", pady=(px(6), 0))
        self.setup_card.configure(height=px(118))
        self.setup_row = 2  # only apps with steps of their own: WARP, Avro, Docker…

        # The apps with more to them than installing get their own panel under
        # the details, as on Linux. Built once, shown only while its app is open.
        by_name = {a.name: a for a in CATALOG}
        self.panels = {by_name["MySQL"]: DatabasePanel(view, self, "MySQL"),
                       by_name["PostgreSQL"]: DatabasePanel(view, self, "PostgreSQL")}
        return view

    def _show_panel(self, app):
        """The open app's own panel, if it has one; the others are put away
        (a typed superuser password lasts one visit)."""
        for owner, panel in self.panels.items():
            if owner is not app:
                panel.grid_remove()
                panel.forget()
        panel = self.panels.get(app)
        if panel is None:
            return
        panel.grid(row=self.setup_row + 1, column=0, columnspan=2, sticky="nsew", pady=(px(12), 0))
        panel.reload()

    def _open(self, app):
        self.shown = app
        self.detail_icon.configure(image=self._picture(app))
        self.detail_name.configure(text=app.name)
        self.detail_about.configure(text=app.about)
        self.detail_site.configure(text=f"Other ways to install it: {app.site.split('://', 1)[-1].split('/', 1)[0]}")
        self.detail_steps.configure(text="\n".join(appmanager.manual_steps(app)))
        self.detail_setup.configure(text="\n".join(f"{n}. {step}" for n, step in enumerate(app.setup, 1)))
        if app.setup:
            self.setup_card.grid(row=self.setup_row, column=0, columnspan=2, sticky="ew", pady=(px(12), 0))
        else:
            self.setup_card.grid_remove()
        self._show_details()
        self._show_panel(app)
        tk.Misc.lift(self.details)

    def _show_details(self):
        """The open app's status line and whether it can be installed now."""
        if self.shown is None:
            return
        status, word = self.statuses[self.shown], self.words.get(self.shown)
        word = word or ("Installed" if status.installed else "Not installed")
        line = f"{self.shown.description} · {self.shown.category} · {word}"
        if status.installed:
            line += f" · {status.version or 'version unknown'}"
            if status.via != "winget":
                line += f" (via {status.via})"
        self.detail_line.configure(text=line)
        if self._tickable(self.shown):
            self.detail_install.pack(side="right")
        else:
            self.detail_install.pack_forget()

    def _close(self):
        self.shown = None
        self._show_panel(None)
        tk.Misc.lift(self.table)  # Canvas.tkraise raises items drawn on it, not the widget
        self._show_selection()

    def _copy_steps(self):
        self.clipboard_clear()
        self.clipboard_append(self.detail_steps.cget("text"))
        self.bar.say("The command is on the clipboard.")

    def _install_shown(self):
        if self.shown is not None and not self.busy:
            self._install([self.shown])

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
        if self.shown is not None:
            self._close()  # a filter or a search is for the tiles

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
            self.bar.say(f"{have} of {len(CATALOG)} installed · click an app for what it does and how to install "
                         "it by hand; each installer asks for permission itself")

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
        self._show_details()
        if self.shown in self.panels:  # Check again reads the open server's service and lists again
            self.panels[self.shown].reload()
        have = sum(s.installed for s in statuses)
        self.subtitle.configure(text=f"{have} of {len(CATALOG)} installed")

    # ---- installing ----

    def _on_install(self):
        chosen = self.table.chosen()
        if not chosen:
            info(self.winfo_toplevel(), "Nothing selected", "Tick one or more apps that aren't installed yet.")
            return
        self._install(chosen)

    def _install(self, chosen):
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
        self._show_details()
        self.bar.say(f"Installing {app.name} · {index + 1} of {total}")
        self.bar.slice(index / total, (index + 1) / total)

    def _on_app_done(self, statuses, app, ok, done, total):
        self.statuses = dict(zip(CATALOG, statuses))
        self.words[app] = None if ok else "Failed"
        self.table.redraw()
        self._show_details()
        self.bar.settle(done / total, ok)

    def _on_done(self, result):
        total, failures = result
        self.set_busy(False)
        self.words = {app: word for app, word in self.words.items() if word == "Failed"}
        self.table.filter(self._keep)
        self._show_details()
        self.bar.say(f"{total - len(failures)} of {total} installed")
        if failures:
            info(self.winfo_toplevel(), "Some apps weren't installed",
                 "\n\n".join(f"{app.name}:\n{tail(text)}" for app, text in failures))
