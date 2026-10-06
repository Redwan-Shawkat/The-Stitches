"""App Manager: the catalog as tiles, side by side and grouped by category —
each app's icon, what's installed, at what version and through what — with
search and filters, and bulk install behind the line loader, one password per
source. Clicking a tile opens its details: what it is, how to install it by
hand, and for PHP its extensions. The Terminal under it all shows each install
as it runs; every result comes from looking again afterwards."""

import shlex
import time

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

from .. import appmanager, catalog
from ..shell import tail
from ..widgets import (Page, Terminal, card, confirm, esc, icon_button, info, label, os_switch, scrolled,
                       show_select_all, strong, tag)
from .php import PhpPanel

_SOURCE_TAG = {
    catalog.APT: ("#8a4200", "#fff1e6"),
    catalog.SNAP: ("#3441b0", "#eef1ff"),
    catalog.FLATPAK: ("#16664b", "#e7f6f0"),
}
_STATUS = {  # status -> Pango attributes
    "Installed": 'foreground="#1e8a4c" weight="600"',
    "Not installed": 'alpha="60%"',
    "Queued": 'alpha="60%"',
    "Installing…": 'foreground="#4c5ce6" weight="600"',
    "Failed": 'foreground="#c62f28" weight="600"',
}
_ON_DARK = {"Installed": "#5fd38d", "Done": "#5fd38d", "Failed": "#ff6b5e"}
_ALL_CATEGORIES, _ALL_SOURCES, _ANY_STATUS = "All categories", "All sources", "Any status"
_STATUSES = (_ANY_STATUS, "Installed", "Not installed")
_ICON_SIZE = 36
_PHP = next(a for a in catalog.CATALOG if a.name == "PHP")  # its details hold the extensions


def _combo(options, on_change):
    combo = Gtk.ComboBoxText(valign=Gtk.Align.CENTER)
    for text in options:
        combo.append_text(text)
    combo.set_active(0)
    combo.connect("changed", lambda c: on_change(c.get_active_text()))
    return combo


class AppsPage(Page):
    title = "App Manager"
    icon = "system-software-install-symbolic"

    def __init__(self):
        super().__init__()
        self.apps = list(catalog.CATALOG)
        self.statuses = [appmanager.NOT_INSTALLED] * len(self.apps)
        self.words = {}  # app index -> a word of its own while it's queued, installing or failed
        self.filters = {"search": "", "category": _ALL_CATEGORIES, "source": _ALL_SOURCES, "status": _ANY_STATUS}

        self.header_button("view-refresh-symbolic", "Check again", self.reload)
        for key, options in (("status", _STATUSES), ("source", (_ALL_SOURCES, *catalog.SOURCES)),
                             ("category", (_ALL_CATEGORIES, *catalog.CATEGORIES))):
            self.header.pack_end(_combo(options, lambda text, k=key: self._set_filter(k, text)), False, False, 0)
        search = Gtk.SearchEntry(placeholder_text="Search apps", width_chars=18, valign=Gtk.Align.CENTER)
        search.connect("search-changed", lambda e: self._set_filter("search", e.get_text()))
        self.header.pack_end(search, False, False, 0)
        self.header.pack_end(os_switch("Linux", "Windows"), False, False, 6)

        self.checks, self.lines, self.index = [], [], {}  # index: tile -> app index
        self.groups = []  # (box, flow, check, handler, app indices)
        tiles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for name in catalog.CATEGORIES:
            tiles.pack_start(self._group(name, [i for i, a in enumerate(self.apps) if a.category == name]),
                             False, False, 0)
        self.views = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.views.add_named(scrolled(tiles), "tiles")
        self.views.add_named(self._build_details(), "details")
        self.body.pack_start(self.views, True, True, 0)
        self.shown = None  # the app index whose details are open

        # Outside the body, so it stays readable and scrollable while the body is locked for an install.
        self.terminal = Terminal("Each install's command and what it prints show up here.", _ON_DARK)
        self.terminal.set_size_request(-1, 140)
        for side in ("top", "start", "end"):
            getattr(self.terminal, f"set_margin_{side}")(12 if side == "top" else 28)
        self.pack_start(self.terminal, False, False, 0)
        self.reorder_child(self.terminal, 2)  # between the body and the action bar
        self.install_button = self.bar.add_button("Install selected", self._on_install_clicked, "suggested-action")

    # ---- tiles ----

    def _group(self, name, members):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=8)
        heading = Gtk.Box(spacing=8)
        check = Gtk.CheckButton(tooltip_text=f"Select all {name} that aren't installed")
        handler = check.connect("toggled", self._tick_group, members)
        heading.pack_start(check, False, False, 0)
        heading.pack_start(label(name, "card-title"), False, False, 0)
        box.pack_start(heading, False, False, 0)
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, min_children_per_line=2,
                           max_children_per_line=3, column_spacing=24, row_spacing=12)
        flow.set_filter_func(lambda child: self._visible(self.index[child.get_child()]))
        flow.connect("child-activated", lambda _f, child: self._open(self.index[child.get_child()]))
        for i in members:
            flow.add(self._tile(i, self.apps[i]))
        box.pack_start(flow, False, False, 0)
        group = card(box)
        self.groups.append((group, flow, check, handler, members))
        return group

    def _tile(self, i, app):
        grid = Gtk.Grid(column_spacing=10, row_spacing=2, margin=4)
        picture = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(app.icon), _ICON_SIZE, _ICON_SIZE, True)
        grid.attach(Gtk.Image.new_from_pixbuf(picture), 0, 0, 1, 3)
        grid.attach(label(f"<b>{esc(app.name)}</b>", use_markup=True, hexpand=True,
                          ellipsize=Pango.EllipsizeMode.END), 1, 0, 1, 1)
        grid.attach(label(app.description, "dim", ellipsize=Pango.EllipsizeMode.END, tooltip_text=app.description),
                    1, 1, 2, 1)
        self.lines.append(label("", use_markup=True, ellipsize=Pango.EllipsizeMode.END))
        grid.attach(self.lines[i], 1, 2, 2, 1)
        self.checks.append(Gtk.CheckButton(valign=Gtk.Align.START))
        self.checks[i].connect("toggled", lambda _c: self._show_selection())
        grid.attach(self.checks[i], 2, 0, 1, 1)
        self.index[grid] = i
        return grid

    def _status(self, i):
        """(the tile's status line, whether it can be installed now)."""
        app, status = self.apps[i], self.statuses[i]
        word = self.words.get(i) or ("Installed" if status.installed else "Not installed")
        parts = [f"<span {_STATUS[word]}>{word}</span>"]
        if status.installed:
            parts.append(esc(appmanager.short_version(status.version, status.via) or "version unknown"))
            if status.via != app.source:
                parts.append(f"via {esc(status.via)}")
        return (f"{tag(app.source, _SOURCE_TAG[app.source])}  {' · '.join(parts)}",
                not status.installed and word not in ("Queued", "Installing…"))

    def _show_tile(self, i):
        line, enabled = self._status(i)
        self.lines[i].set_markup(line)
        self.checks[i].set_sensitive(enabled)
        if not enabled:
            self.checks[i].set_active(False)
        if i == self.shown:
            self._show_details()

    # ---- an app's details ----

    def _build_details(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        top = Gtk.Box(spacing=12, margin=8)
        top.pack_start(icon_button("go-previous-symbolic", "All apps", self._close), False, False, 0)
        self.detail_icon = Gtk.Image()
        top.pack_start(self.detail_icon, False, False, 0)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER)
        self.detail_name = label("", "card-title")
        self.detail_line = label("", use_markup=True)
        titles.pack_start(self.detail_name, False, False, 0)
        titles.pack_start(self.detail_line, False, False, 0)
        top.pack_start(titles, True, True, 0)
        self.detail_install = Gtk.Button(label="Install", valign=Gtk.Align.CENTER, no_show_all=True)
        self.detail_install.get_style_context().add_class("suggested-action")
        self.detail_install.connect("clicked", lambda _b: self._install([self.apps[self.shown]]))
        top.pack_end(self.detail_install, False, False, 0)
        box.pack_start(card(top), False, False, 0)

        cards = Gtk.Box(spacing=16, homogeneous=True)
        about = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        about.pack_start(label("What it does", "card-title"), False, False, 0)
        self.detail_about = label("", wrap=True)
        about.pack_start(self.detail_about, False, False, 0)
        self.detail_site = label("", "dim", use_markup=True, ellipsize=Pango.EllipsizeMode.END)
        about.pack_start(self.detail_site, False, False, 0)
        cards.pack_start(card(about), True, True, 0)
        manual = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        heading = Gtk.Box(spacing=8)
        heading.pack_start(label("Install it yourself", "card-title"), True, True, 0)
        copy = icon_button("edit-copy-symbolic", "Copy the commands",
                           lambda: Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(self.detail_steps.get_text(), -1))
        heading.pack_start(copy, False, False, 0)
        manual.pack_start(heading, False, False, 0)
        manual.pack_start(label("In a terminal, the same install Stitches runs:", "dim"), False, False, 0)
        self.detail_steps = label("", "monospace", selectable=True, wrap=True)
        manual.pack_start(self.detail_steps, False, False, 0)
        cards.pack_start(card(manual), True, True, 0)
        box.pack_start(cards, False, False, 0)

        setup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        setup.pack_start(label("After installing", "card-title"), False, False, 0)
        self.detail_setup = label("", wrap=True, selectable=True)
        setup.pack_start(self.detail_setup, False, False, 0)
        self.setup_card = card(setup)
        self.setup_card.set_no_show_all(True)  # only apps with steps of their own: Avro, WARP
        box.pack_start(self.setup_card, False, False, 0)

        self.php = PhpPanel(self)
        self.php.set_no_show_all(True)
        self.php.set_size_request(-1, 420)  # the details scroll, so on a small screen the switches still get room
        box.pack_start(self.php, True, True, 0)
        details = scrolled(box)
        details.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        return details

    def _open(self, i):
        self.shown = i
        app = self.apps[i]
        self.detail_icon.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(app.icon), 48, 48, True))
        self.detail_name.set_text(app.name)
        self.detail_about.set_text(app.about)
        host = app.site.split("://", 1)[-1].split("/", 1)[0]
        self.detail_site.set_markup(f'Other ways to install it: <a href="{esc(app.site)}">{esc(host)}</a>')
        self.detail_steps.set_text("\n".join(appmanager.manual_steps(app)))
        self.detail_setup.set_text("\n".join(f"{n}. {step}" for n, step in enumerate(app.setup, 1)))
        self.setup_card.set_no_show_all(False)
        self.setup_card.show_all() if app.setup else self.setup_card.hide()
        self._show_details()
        if app is _PHP:
            self.php.set_no_show_all(False)  # hidden from the window's show_all until PHP is opened
            self.php.show_all()
            self.php.reload()
        else:
            self.php.hide()
            self._show_summary()  # not PHP's hint from the last app opened
        self.views.set_visible_child_name("details")

    def _show_details(self):
        line, enabled = self._status(self.shown)
        self.detail_line.set_markup(f"{esc(self.apps[self.shown].description)} · {line}")
        self.detail_install.set_visible(enabled)

    def _close(self):
        if self.shown is not None:
            self.shown = None
            self.views.set_visible_child_name("tiles")
            self._show_summary()

    # ---- filtering and selection ----

    def _visible(self, i):
        app, status, f = self.apps[i], self.statuses[i], self.filters
        return ((f["category"] == _ALL_CATEGORIES or app.category == f["category"])
                and (f["source"] == _ALL_SOURCES or app.source == f["source"])
                and (f["status"] == _ANY_STATUS or status.installed == (f["status"] == "Installed"))
                and f["search"].lower() in f"{app.name} {app.description}".lower())

    def _set_filter(self, key, value):
        self.filters[key] = value
        self._refilter()
        self._close()  # a search is for the tiles

    def _refilter(self):
        for group, flow, _check, _handler, members in self.groups:
            flow.invalidate_filter()
            group.set_visible(any(self._visible(i) for i in members))
        self._show_selection()

    def _tickable(self, members):
        return [i for i in members if self.checks[i].get_sensitive() and self._visible(i)]

    def _tick_group(self, check, members):
        """A category's checkbox: every app in it on screen that isn't installed yet, or none."""
        on = check.get_active()  # read once: each tick below redraws this checkbox
        for i in self._tickable(members):
            self.checks[i].set_active(on)

    def _show_selection(self):
        n = sum(c.get_active() for c in self.checks)
        self.install_button.set_label(f"Install selected · {n}" if n else "Install selected")
        for _group, _flow, check, handler, members in self.groups:
            tickable = self._tickable(members)
            with check.handler_block(handler):  # showing the state mustn't tick the whole group
                show_select_all(check, sum(self.checks[i].get_active() for i in tickable), len(tickable))
            check.set_sensitive(bool(tickable))

    # ---- checking ----

    def reload(self):
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say("Looking for what's installed through APT, Snap, Flatpak and on PATH…")
        self.run_async(appmanager.check, self._on_check_done)

    def _on_check_done(self, statuses):
        self.bar.done()
        self.statuses = statuses
        for i in range(len(self.apps)):
            self._show_tile(i)
        self._refilter()
        self._show_summary()
        self.set_busy(False)
        if self.shown is not None and self.apps[self.shown] is _PHP:
            self.php.reload()

    def _show_summary(self):
        have = sum(s.installed for s in self.statuses)
        self.subtitle.set_text(f"{have} of {len(self.apps)} installed · checked {time.strftime('%H:%M')}")
        self.bar.say("Click an app for what it does and how to install it by hand. Installs through APT, Snap and "
                     "Flatpak; each source asks for your password once.")
        self._show_selection()

    # ---- installing ----

    def _on_install_clicked(self):
        chosen = [a for a, check in zip(self.apps, self.checks) if check.get_active()]
        if not chosen:
            info(self.window(), "Nothing selected", "Tick one or more apps that aren't installed yet.")
            return
        self._install(chosen)

    def _install(self, chosen):
        vendors = [a for a in chosen if a.repo]
        if vendors and not confirm(self.window(), "Add a vendor's repository?", [
                "Not in Ubuntu's own packages, so these come from their maker's APT repository:", "",
                *(f"{a.name}: adds {a.repo[2]} and its signing key {a.repo[1]}" for a in vendors), "",
                "Updates then come through the Updates page like any other package."], "Add and install"):
            return
        flatpak = self.apps.index(appmanager.FLATPAK_APP)
        jobs = appmanager.plan_jobs(chosen, self.statuses[flatpak].installed)
        order = [self.apps.index(a) for _source, batch in jobs for a in batch]
        for i in order:
            self.words[i] = "Queued"
            self._show_tile(i)
        self._show_selection()
        self.set_busy(True)
        self.terminal.clear()

        def work():
            failures, done = [], 0
            for source, batch in jobs:
                GLib.idle_add(self._on_job_start, source, batch, done, len(order))
                self.terminal.log(f"▶ {', '.join(a.name for a in batch)} · {source}")
                self.terminal.log(f"$ {shlex.join(appmanager.command_for(source, batch))}")
                _ok, text = appmanager.install(source, batch, on_line=self.terminal.log)
                statuses = appmanager.check()  # did it work? Ask the package managers, not the exit code
                missing = [a for a in batch if not statuses[self.apps.index(a)].installed]
                if missing:
                    failures.append((missing, text))
                for a in batch:
                    self.terminal.log(f"{'Failed' if a in missing else 'Installed'}: {a.name}")
                done += len(batch)
                GLib.idle_add(self._on_job_done, statuses, batch, missing, done, len(order))
            return len(order), failures

        self.run_async(work, self._on_all_done)

    def _on_job_start(self, source, batch, done, total):
        for a in batch:
            self.words[self.apps.index(a)] = "Installing…"
            self._show_tile(self.apps.index(a))
        names = batch[0].name if len(batch) == 1 else f"{len(batch)} {source} apps"
        self.bar.say(f"Installing {strong(names)} · {done + 1}–{done + len(batch)} of {total} · asks for your password")
        self.bar.slice(done / total, (done + len(batch)) / total)

    def _on_job_done(self, statuses, batch, missing, done, total):
        self.statuses = statuses
        for a in batch:
            i = self.apps.index(a)
            self.words[i] = "Failed" if a in missing else None
            self._show_tile(i)
        self.bar.settle(done / total, not missing)

    def _on_all_done(self, result):
        total, failures = result
        failed = sum(len(apps) for apps, _ in failures)
        self.set_busy(False)
        self._refilter()
        self._show_summary()
        self.bar.say(f"Installed {strong(str(total - failed))} of {total}" + (f" · {failed} failed" if failed else ""))
        if failures:
            info(self.window(), "Some apps weren't installed", "\n\n".join(
                f"{', '.join(a.name for a in apps)}:\n{tail(text, 4)}" for apps, text in failures))
