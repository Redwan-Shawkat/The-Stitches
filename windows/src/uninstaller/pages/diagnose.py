"""Diagnose: the checks down the left, each with its verdict and a fix where
there is one, and a Terminal on the right showing every command and what it
prints. It waits for Scan instead of scanning when the window opens, as on
Linux. A fix that needs care says what will happen and asks first."""

import tkinter as tk
from tkinter import ttk

from .. import diagnose
from ..elevate import tail
from ..widgets import (FONTS, LINE, STATUS_TAG, THEME, Button, Dialog, Page, Rounded, info, later, px, recolour,
                       role, status_label)

_TAG = {diagnose.OK: STATUS_TAG["Good"], diagnose.WARNING: STATUS_TAG["Warning"],
        diagnose.PROBLEM: STATUS_TAG["Critical"], diagnose.INFO: STATUS_TAG["Info"]}
_INK = {diagnose.OK: "#6fcf97", diagnose.WARNING: "#e5b454", diagnose.PROBLEM: "#ff6b5e", diagnose.INFO: "#9aa6ff"}


class DiagnosePage(Page):
    title = "Diagnose"
    icon = "diagnose"
    auto_load = False  # every check takes a while; nothing runs until Scan

    def __init__(self, parent):
        super().__init__(parent)
        self.results, self.fix_buttons = {}, []
        self.subtitle.configure(text="Windows' own health tools, read without admin rights; fixes ask first")
        self.body.columnconfigure(0, weight=3, uniform="half")
        self.body.columnconfigure(1, weight=2, uniform="half")
        self.body.rowconfigure(0, weight=1)
        self._build_checks()
        self._build_terminal()
        self.bar.add_button("Scan", self.reload, "suggested")
        self.bar.say("Press Scan to run every check. Nothing changes until you press a fix.")

    def _build_checks(self):
        card = role(Rounded(self.body, radius=14, pad=6), bg="card", border="border")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, px(12)))
        canvas = tk.Canvas(card.inner, highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(card.inner, orient="vertical", command=canvas.yview, style="Thin.Vertical.TScrollbar")
        rows = tk.Frame(canvas)
        window = canvas.create_window((0, 0), window=rows, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.rows = []
        for check in diagnose.CHECKS:
            row = tk.Frame(rows)
            row.pack(fill="x", padx=px(10), pady=(px(10), 0))
            head = tk.Frame(row)
            head.pack(fill="x")
            tk.Label(head, text=check.title, font=FONTS["bold"]).pack(side="left")
            role(tk.Label(head, text=f"  {check.like}", font=FONTS["small"]), fg="dim").pack(side="left")
            status = tk.Frame(head)
            status.pack(side="right")
            summary = role(tk.Label(row, text="Not checked yet", anchor="w", justify="left"), fg="dim")
            summary.pack(fill="x")
            fix = tk.Frame(row)
            fix.pack(anchor="w")
            self.rows.append((row, status, summary, fix))

        def resized(event):
            canvas.itemconfigure(window, width=event.width)
            for _, _, summary, _ in self.rows:
                summary.configure(wraplength=event.width - px(24))

        canvas.bind("<Configure>", resized)
        rows.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-2 if e.delta > 0 else 2, "units"))

    def _build_terminal(self):
        panel = role(Rounded(self.body, radius=14, pad=10), bg="bar", fg="bar_text", border="bar_border")
        panel.grid(row=0, column=1, sticky="nsew")
        tk.Label(panel.inner, text="TERMINAL", font=FONTS["caps"], anchor="w").pack(fill="x", pady=(0, px(6)))
        self.terminal = tk.Text(panel.inner, wrap="word", relief="flat", borderwidth=0, highlightthickness=0,
                                font=("Consolas", 9), state="disabled")
        self.terminal.pack(fill="both", expand=True)
        self.terminal.tag_configure("command", foreground=LINE)
        self.terminal.tag_configure("check", font=("Consolas", 9, "bold"))
        for status, ink in _INK.items():
            self.terminal.tag_configure(status, foreground=ink)

    # ---- the terminal ----

    def _log(self, line: str):
        status = line.partition(":")[0]
        tag = "command" if line.startswith("$ ") else "check" if line.startswith("▶") else \
            status if status in _INK else ""
        self.terminal.configure(state="normal")
        if line.startswith("▶") and self.terminal.index("end-1c") != "1.0":
            self.terminal.insert("end", "\n")
        self.terminal.insert("end", line + "\n", tag)
        self.terminal.configure(state="disabled")
        self.terminal.see("end")

    # ---- checks ----

    def set_busy(self, busy: bool):
        super().set_busy(busy)
        for button in self.fix_buttons:
            button.set_enabled(not busy)

    def reload(self):
        """Scan: every check in turn."""
        if self.busy:
            return
        self.set_busy(True)
        self.terminal.configure(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.configure(state="disabled")
        checks = diagnose.CHECKS

        def work():
            for i, check in enumerate(checks):
                later(self._on_check_start, check, i, len(checks))
                later(self._show_result, i, diagnose.run_check(check, lambda line: later(self._log, line)))

        self.run_async(work, self._on_scan_done)

    def _on_check_start(self, check, index, total):
        self.bar.say(f"Checking {check.title.lower()} · {index + 1} of {total}")
        self.bar.slice(index / total, (index + 1) / total)

    def _show_result(self, index, result):
        self.results[index] = result
        row, status, summary, fix = self.rows[index]
        for child in (*status.winfo_children(), *fix.winfo_children()):
            if child in self.fix_buttons:
                self.fix_buttons.remove(child)
            child.destroy()
        status_label(status, result.status, _TAG[result.status]).pack()
        summary.configure(text=result.summary)
        summary.roles = {}  # read now, so no longer dim
        if result.fix:
            button = Button(fix, result.fix.label, lambda: self._on_fix(index, result.fix))
            button.pack(anchor="w", pady=(px(4), 0))
            button.set_enabled(not self.busy)
            self.fix_buttons.append(button)
        recolour(row, THEME["card"])
        self.bar.settle((index + 1) / len(diagnose.CHECKS), not any(
            r.status == diagnose.PROBLEM for r in self.results.values()))

    def _on_scan_done(self, _):
        self.set_busy(False)
        counts = {}
        for result in self.results.values():
            counts[result.status] = counts.get(result.status, 0) + 1
        self.bar.say(" · ".join(f"{n} {status}" for status, n in counts.items()))

    # ---- fixes ----

    def _on_fix(self, index, fix):
        if self.busy or (fix.caution and not self._ask(fix)):
            return
        self.set_busy(True)
        self.bar.say(f"{fix.label}… Windows asks for permission first")
        self.bar.slice(0, 1)
        check, log = diagnose.CHECKS[index], lambda line: later(self._log, line)

        def work():
            ok, text = diagnose.run_fix(fix, log)
            return ok, text, diagnose.run_check(check, log)

        self.run_async(work, lambda result: self._on_fix_done(index, fix, *result))

    def _ask(self, fix) -> bool:
        dialog = Dialog(self.winfo_toplevel(), fix.label)
        tk.Label(dialog.body, text=fix.caution, wraplength=px(440), justify="left", anchor="w").pack(fill="x")
        dialog.button("Cancel")
        dialog.button(fix.label, True, "suggested")
        return dialog.run() is True

    def _on_fix_done(self, index, fix, ok, text, result):
        self.set_busy(False)
        self._show_result(index, result)
        self.bar.settle(1, ok)
        self.bar.say(f"{fix.label}: {tail(text, 1) or 'done'}")
        if not ok:
            info(self.winfo_toplevel(), diagnose.CHECKS[index].title, tail(text, 6) or "It didn't finish.")
