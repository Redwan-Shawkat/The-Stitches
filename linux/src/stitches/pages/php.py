"""PHP's part of its App Manager details: the Laravel checklist, and every
extension of the chosen PHP version with a switch. Switches only mark
changes; Apply changes (or the Laravel button) shows exactly what will happen
first, then runs it all with one password and reads /etc/php again to say
what took. It borrows the App Manager page's action bar and Terminal."""

import shlex
import shutil

from gi.repository import Gtk, Pango

from .. import php
from ..shell import tail
from ..widgets import card, confirm, esc, info, label, scrolled, strong

_MARK = {  # state -> (mark, Pango attributes)
    php.ENABLED: ("✓", 'foreground="#1e8a4c" weight="600"'),
    php.BUILT_IN: ("✓", 'foreground="#1e8a4c" weight="600"'),
    php.DISABLED: ("○", 'foreground="#d99a00" weight="600"'),
    php.NOT_INSTALLED: ("✗", 'foreground="#c62f28" weight="600"'),
}


def _marked(text: str, state: str, detail: str = "") -> str:
    mark, attrs = _MARK[state]
    return f'<span {attrs}>{mark}</span>  {esc(text)}' + (f'  <span alpha="60%">{esc(detail)}</span>' if detail else "")


class PhpPanel(Gtk.Box):
    def __init__(self, page):
        super().__init__(spacing=16)
        self.page, self.state, self.version, self.switches = page, None, "", {}

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        left.pack_start(label("Laravel development", "card-title"), False, False, 0)
        left.pack_start(label("What a Laravel app needs from PHP", "dim"), False, False, 0)
        self.checklist = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=6)
        left.pack_start(scrolled(self.checklist), True, True, 0)
        self.laravel_button = Gtk.Button(label="Enable what Laravel needs", margin_top=8)
        self.laravel_button.connect("clicked", lambda _b: self._on_laravel())
        left.pack_start(self.laravel_button, False, False, 0)  # under the list, never scrolled away
        laravel = card(left)
        laravel.set_size_request(290, -1)
        self.pack_start(laravel, False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        heading = Gtk.Box(spacing=8)
        heading.pack_start(label("Extensions", "card-title"), True, True, 0)
        self.versions = Gtk.ComboBoxText(no_show_all=True, tooltip_text="More than one PHP is installed: the one to manage")
        self.versions_handler = self.versions.connect("changed", self._on_version)
        heading.pack_start(self.versions, False, False, 0)
        self.apply_button = Gtk.Button(label="Apply changes")
        self.apply_button.get_style_context().add_class("suggested-action")
        self.apply_button.connect("clicked", lambda _b: self._run(*self._pending()))
        heading.pack_start(self.apply_button, False, False, 0)
        right.pack_start(heading, False, False, 0)
        self.note = label("", "dim", wrap=True)
        right.pack_start(self.note, False, False, 0)
        self.tiles = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, min_children_per_line=2,
                                 max_children_per_line=4, column_spacing=24, row_spacing=8, margin_top=6)
        right.pack_start(scrolled(self.tiles), True, True, 0)
        self.pack_start(card(right), True, True, 0)

    # ---- reading ----

    def reload(self):
        self.page.set_busy(True)
        self.page.bar.pulse()
        self.page.bar.say("Reading /etc/php…")
        self.page.run_async(self._read, self._on_read)

    def _read(self):
        versions = php.versions()
        if not versions:
            return versions, None
        version = self.version if self.version in versions else php.default_version()
        return versions, php.read(version if version in versions else versions[0])

    def _on_read(self, result):
        versions, self.state = result
        self.page.bar.done()
        self.page.set_busy(False)
        with self.versions.handler_block(self.versions_handler):
            self.versions.remove_all()
            for v in versions:
                self.versions.append(v, f"PHP {v}")
            if self.state:
                self.version = self.state.version
                self.versions.set_active_id(self.version)
        self.versions.set_visible(len(versions) > 1)
        for box in (self.checklist, self.tiles):
            for child in box.get_children():
                child.destroy()
        self.switches = {}
        if not self.state:
            self._show_missing()
            return
        s = self.state
        self.note.set_text(f"PHP {s.full}. Each switch turns it on or off for every part of PHP {s.version} at once "
                           f"({', '.join(s.sapis)})"
                           + (f", then restarts {', '.join(s.restarts)} so it loads the change." if s.restarts else "."))
        self._show_checklist()
        for e in s.extensions:
            self.tiles.add(self._tile(e))
        self.checklist.show_all()
        self.tiles.show_all()
        self._show_pending()

    def _show_missing(self):
        where = shutil.which("php")
        self.note.set_text(f"{where} isn't from Ubuntu's packages, so it has no /etc/php to manage: its extensions "
                           "are set in its own php.ini." if where else
                           "PHP isn't installed yet. Install it, and its extensions show up here.")
        self.laravel_button.set_sensitive(False)
        self.apply_button.set_sensitive(False)

    def _show_checklist(self):
        s, rows = self.state, []
        fits = php.php_fits_laravel(s.version)
        rows.append(_marked(f"PHP {s.full}", php.ENABLED if fits else php.NOT_INSTALLED,
                            "" if fits else "Laravel needs %d.%d or newer" % php.LARAVEL_PHP))
        rows.append(_marked("Composer", php.ENABLED, s.composer) if s.composer
                    else _marked("Composer", php.NOT_INSTALLED, "in Developer Tools"))
        for name, state in php.laravel(s):
            rows.append(_marked(name, state, "" if state == php.ENABLED else state.lower()))
        for markup in rows:
            self.checklist.pack_start(label(markup, use_markup=True, ellipsize=Pango.EllipsizeMode.END), False, False, 0)
        fixes = php.laravel_fixes(s)
        self.laravel_button.set_sensitive(bool(fixes))
        self.laravel_button.set_label(f"Enable what Laravel needs · {len(fixes)}" if fixes else "Laravel has all it needs")

    def _tile(self, e):
        grid = Gtk.Grid(column_spacing=10, margin=4)
        grid.attach(label(f"<b>{esc(e.name)}</b>", use_markup=True, hexpand=True,
                          ellipsize=Pango.EllipsizeMode.END), 0, 0, 1, 1)
        detail = f"on for {', '.join(e.on_for)} only" if e.on_for else \
            f"installs {php.package(self.state.version, e.name)}" if e.state == php.NOT_INSTALLED else e.state
        grid.attach(label(detail, "dim", ellipsize=Pango.EllipsizeMode.END, tooltip_text=detail), 0, 1, 1, 1)
        switch = Gtk.Switch(active=e.state == php.ENABLED, valign=Gtk.Align.CENTER)
        switch.connect("notify::active", lambda *_: self._show_pending())
        self.switches[e.name] = switch
        grid.attach(switch, 1, 0, 1, 2)
        return grid

    def _on_version(self, combo):
        self.version = combo.get_active_id() or ""
        self.reload()

    # ---- changing ----

    def _pending(self):
        return php.changes(self.state, {n: s.get_active() for n, s in self.switches.items()})

    def _show_pending(self):
        n = sum(map(len, self._pending()))
        self.apply_button.set_sensitive(bool(n))
        self.apply_button.set_label(f"Apply changes · {n}" if n else "Apply changes")
        self.page.bar.say(f"{n} PHP change{'s' * (n != 1)} marked: nothing runs until you apply them." if n else
                          "Flip PHP's switches, then Apply changes. It asks for your password once.")

    def _on_laravel(self):
        self._run(*php.changes(self.state, php.laravel_fixes(self.state)))

    def _run(self, install, enable, disable):
        s, page = self.state, self.page
        lines = ([f"Install {n} ({php.package(s.version, n)})" for n in install] + [f"Turn on {n}" for n in enable]
                 + [f"Turn off {n}" for n in disable]
                 + [f"Restart {u}, so it loads the change" for u in s.restarts])
        if not confirm(page.window(), f"Change PHP {s.version}?", ["These changes will be made:", *lines], "Apply"):
            return
        page.set_busy(True)
        page.bar.pulse()
        page.bar.say(f"Changing PHP {strong(s.version)} · asks for your password")
        page.terminal.clear()

        def work():
            page.terminal.log(f"▶ PHP {s.version}: {len(install) + len(enable) + len(disable)} changes")
            page.terminal.log(f"$ {shlex.join(php.apply_command(s, install, enable, disable))}")
            _ok, text = php.apply(s, install, enable, disable, on_line=page.terminal.log)
            after = php.read(s.version)  # did it work? Read /etc/php, not the exit code
            failed = php.unchanged(s, after, install, enable, disable)
            for n in (*install, *enable, *disable):
                page.terminal.log(f"{'Failed' if n in failed else 'Done'}: {n}")
            return after, failed, text

        page.run_async(work, self._on_applied)

    def _on_applied(self, result):
        after, failed, text = result
        self._on_read((php.versions(), after))
        if failed:
            self.page.bar.say(f"{len(failed)} change{'s' * (len(failed) != 1)} didn't take: {esc(', '.join(failed))}")
            info(self.page.window(), "Some changes didn't take", f"{', '.join(failed)}\n\n{tail(text, 4)}")
        else:
            self.page.bar.say("Done: every PHP change is in place.")
