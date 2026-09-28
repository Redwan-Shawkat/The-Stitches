"""Diagnose: nine checks for what goes wrong on a Linux PC, each with the
Windows tool it stands in for, what was found, and a fix where one exists.
Anything that needs a restart says so and asks first. The terminal panel
on the right shows each command and what it prints, as it prints it."""

import shlex

from gi.repository import GLib, Gtk, Pango

from .. import diagnose
from ..shell import run, tail
from ..widgets import STATUS_TAG, Page, card, confirm, esc, info, label, scrolled, strong, tag

# STATUS_TAG's colours are for a light tag background; on the dark panel these read.
_ON_DARK = {"OK": "#5fd38d", "Good": "#5fd38d", "Warning": "#f0b429", "Problem": "#ff6b5e",
            "Critical": "#ff6b5e", "Info": "#8f9bff", "Not checked": "#9a9ca6"}


class CheckRow(Gtk.Box):
    def __init__(self, check, on_fix):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
        self.check, self.result = check, None
        top = Gtk.Box(spacing=12)
        self.status = label(use_markup=True, valign=Gtk.Align.START, width_chars=8)
        top.pack_start(self.status, False, False, 0)
        words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        words.pack_start(label(f'<span weight="600">{esc(check.title)}</span>  '
                               f'<span size="small" alpha="60%">{esc(check.like)}</span>', use_markup=True),
                         False, False, 0)
        self.summary = label("", "dim", wrap=True)
        words.pack_start(self.summary, False, False, 0)
        top.pack_start(words, True, True, 0)
        self.fix = Gtk.Button(valign=Gtk.Align.START)
        self.fix.connect("clicked", lambda _b: on_fix(self))
        self.fix.set_no_show_all(True)
        top.pack_end(self.fix, False, False, 0)
        self.pack_start(top, False, False, 0)
        self.details = Gtk.Expander(label="Details", margin_start=84)
        self.detail_text = label("", "mono", wrap=True, selectable=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        self.details.add(self.detail_text)
        self.details.set_no_show_all(True)
        self.pack_start(self.details, False, False, 0)
        self.show_result(diagnose.Result("Not checked", "Press Scan to check."))

    def show_result(self, result):
        self.result = result
        self.status.set_markup(tag(result.status, STATUS_TAG[result.status]))
        self.summary.set_text(result.summary)
        self.detail_text.set_text("\n".join(result.details))
        self.details.set_visible(bool(result.details))
        self.detail_text.show()
        if result.fix:
            self.fix.set_label(result.fix.label)
            self.fix.set_tooltip_text(" ".join(result.fix.command[1:4]) + "…")
        self.fix.set_visible(bool(result.fix))


class DiagnosePage(Page):
    title = "Diagnose"
    icon = "device-diagnostics-symbolic"

    def __init__(self):
        super().__init__()
        self.subtitle.set_text("Linux's sfc /scannow, chkdsk, disk health and memory test, in one scan")
        rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.rows = [CheckRow(check, self._on_fix) for check in diagnose.CHECKS]
        for row in self.rows:
            rows.add(row)
        self.body.pack_start(card(scrolled(rows)), True, True, 0)
        self.body.pack_start(self._build_output(), False, False, 0)
        self.scan_button = self.bar.add_button("Scan", self._scan, "suggested-action")
        self.bar.say("Nothing changes until you press a fix; every check only reads.")

    def _build_output(self):
        self.view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 left_margin=4, right_margin=4)
        self.out = self.view.get_buffer()
        self.out.create_tag("head", weight=Pango.Weight.BOLD, foreground="#ffffff", pixels_above_lines=10)
        self.out.create_tag("cmd", foreground="#7d8bff")
        for status, color in _ON_DARK.items():
            self.out.create_tag(status, foreground=color)
        self.out_end = self.out.create_mark(None, self.out.get_end_iter(), False)
        self.out.set_text("Each check's commands and what they print show up here as they run.")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        box.pack_start(label("Terminal", "card-title"), False, False, 0)
        box.pack_start(scrolled(self.view), True, True, 0)
        panel = card(box, "console")
        panel.set_size_request(420, -1)
        return panel

    def _log(self, line: str):
        """From the worker thread: onto the panel, on the GTK thread."""
        GLib.idle_add(self._print, line)

    def _print(self, line: str):
        status = line.partition(":")[0]
        tag = "head" if line.startswith("▶") else "cmd" if line.startswith("$ ") else \
            status if status in _ON_DARK else None
        end = self.out.get_end_iter()
        if tag:
            self.out.insert_with_tags_by_name(end, f"\n{line}", tag)
        else:
            self.out.insert(end, f"\n{line}")
        self.view.scroll_mark_onscreen(self.out_end)

    def reload(self):
        pass  # the file-by-file check reads every installed file, so scanning waits to be asked

    def _scan(self):
        self.set_busy(True)
        self.out.set_text("")
        total = len(self.rows)

        def work():
            problems = 0
            for i, row in enumerate(self.rows):
                GLib.idle_add(self._on_check_start, row, i, total)
                result = diagnose.run_check(row.check, self._log)
                problems += result.status in (diagnose.PROBLEM, diagnose.WARNING)
                GLib.idle_add(self._on_check_done, row, result, i + 1, total)
            return problems

        self.run_async(work, self._on_scan_done)

    def _on_check_start(self, row, index, total):
        row.show_result(diagnose.Result("Not checked", "Checking…"))
        self.bar.say(f"Checking {strong(row.check.title)} · {index + 1} of {total}")
        self.bar.slice(index / total, (index + 1) / total)

    def _on_check_done(self, row, result, done, total):
        row.show_result(result)
        self.bar.settle(done / total, result.status != diagnose.PROBLEM)

    def _on_scan_done(self, problems):
        self.set_busy(False)
        self.set_count(problems)
        self.bar.say(f"{strong(str(problems))} to look at" if problems else "No problems found")

    # ---- fixing ----

    def _on_fix(self, row):
        fix = row.result.fix
        if fix.caution and not confirm(self.window(), f"{fix.label}?", [fix.caution], fix.label):
            return
        self.set_busy(True)
        self.bar.say(f"{strong(fix.label)} · asks for your password" if fix.command[0] == "pkexec"
                     else strong(fix.label))
        self.bar.slice(0, 1)
        self._print(f"▶ {fix.label}")
        self._print(f"$ {shlex.join(fix.command)}")
        self.run_async(lambda: run(fix.command, on_line=self._log), lambda result: self._on_fixed(row, fix, *result))

    def _on_fixed(self, row, fix, ok, text):
        self.set_busy(False)
        self.bar.settle(1, ok)
        if not ok:
            self.bar.say(f"{strong(fix.label)} failed")
            info(self.window(), f"{fix.label} failed", tail(text, 8))
            return
        if fix.restart:
            self.bar.say(f"{strong(fix.label)}: set for the next restart")
            if confirm(self.window(), "Restart now?", ["Save your work first. You can also restart later; "
                                                        "it happens on the next restart either way."], "Restart"):
                run(["systemctl", "reboot"])
            return
        self.bar.say(f"{strong(fix.label)}: done. Checking again…")
        self.run_async(lambda: diagnose.run_check(row.check, self._log), row.show_result)
