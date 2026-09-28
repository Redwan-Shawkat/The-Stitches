"""Uninstall: every installed program from the registry, the Microsoft Store,
Chocolatey and Scoop in one list, with where it came from and how risky it
is to remove. The list is drawn on a canvas, row by row: a Treeview can't
colour one cell, and a Text widget paints a tag's background the full height
of its row, so neither can hold the tags."""

import tkinter as tk
from tkinter import ttk

from ..models import Risk, Source, format_size
from ..scanner import scan_all
from ..uninstaller import clean_leftovers, uninstall
from ..widgets import (FONTS, RISK_TAG, THEME, Dialog, Page, Rounded, Tick, Tooltip, confirm, draw_tag, filter_pill,
                       fit_text as _fit, info, later, on_theme, px, role, search_pill, tick_picture)

_SOURCE_TAG = {
    Source.INSTALLER: ("#8a4200", "#fff1e6"),
    Source.STORE: ("#3441b0", "#eef1ff"),
    Source.CHOCOLATEY: ("#16664b", "#e7f6f0"),
    Source.SCOOP: ("#9b1f5b", "#fdeef5"),
}
_ALL = "All sources"
_ROW, _TICK_X, _NAME_X, _GAP = 38, 20, 42, 18  # pixels at 96 DPI


class UninstallPage(Page):
    title = "Uninstall"
    icon = "uninstall"  # apps, with one taken out

    def __init__(self, parent):
        super().__init__(parent)
        self.apps, self.selected, self.visible = [], set(), []
        self.search_text, self.source_filter, self.empty, self._width = "", _ALL, "Scanning…", 0

        self.header_button("refresh", "Scan again", self.reload)
        filter_pill(self.header, [_ALL, *(s.value for s in Source)], self._on_filter)
        search_pill(self.header, "Search installed software", self._on_search)

        card = role(Rounded(self.body, radius=14, pad=6), bg="card", border="border")
        card.pack(fill="both", expand=True)
        card.inner.rowconfigure(1, weight=1)
        card.inner.columnconfigure(0, weight=1)
        self.head = tk.Canvas(card.inner, height=px(30), highlightthickness=0, borderwidth=0)
        self.head.grid(row=0, column=0, sticky="ew")
        self.canvas = tk.Canvas(card.inner, highlightthickness=0, borderwidth=0, yscrollincrement=px(_ROW))
        self.canvas.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(card.inner, orient="vertical", command=self.canvas.yview,
                               style="Thin.Vertical.TScrollbar")
        scroll.grid(row=1, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scroll.set)

        self.head.bind("<Button-1>", lambda e: e.x < px(_NAME_X) and self._on_select_all())
        Tooltip(self.head, lambda e: "Select all, except system-critical" if e.x < px(_NAME_X) else "")
        self.head.bind("<Configure>", lambda _e: self._draw_header())
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _e: self.canvas.itemconfigure("hover", state="hidden"))
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-3 if e.delta > 0 else 3, "units"))
        for button, rows in (("<Button-4>", -3), ("<Button-5>", 3)):  # the wheel on X11 with Tk 8.6
            self.canvas.bind(button, lambda _e, n=rows: self.canvas.yview_scroll(n, "units"))
        Tooltip(self.canvas, self._reason_at)  # after the bindings above, which it adds to
        on_theme(self._draw)

        self.bar.add_button("Uninstall selected", self._on_uninstall_clicked, "destructive")

    def _on_filter(self, choice):
        self.source_filter = choice
        self._refresh_rows()

    def _on_search(self, text):
        self.search_text = text
        self._refresh_rows()

    # ---- the list ----

    def _columns(self, width):
        """x of the source, version, size (its right edge) and risk columns; the name gets what's left."""
        caps, tag = FONTS["caps"], lambda text: FONTS["small"].measure(text) + 2 * px(6)
        risk = width - px(12) - max(caps.measure("RISK TO REMOVE"), *(tag(r.value) for r in Risk))
        size_end = risk - px(_GAP)
        version = size_end - px(70 + _GAP + 110)
        source = version - px(_GAP) - max(caps.measure("INSTALLED VIA"), *(tag(s.value) for s in Source))
        return source, version, size_end, risk

    def _draw(self):
        self._draw_rows()
        self._draw_header()

    def _draw_header(self):
        c = self.head
        c.configure(background=THEME["card"])
        c.delete("all")
        source, version, size_end, risk = self._columns(c.winfo_width())
        y = px(15)
        c.create_image(px(_TICK_X), y, image=tick_picture(self._ticked(), THEME["card"]))
        for x, text, anchor in ((px(_NAME_X), "APP", "w"), (source, "INSTALLED VIA", "w"), (version, "VERSION", "w"),
                                (size_end, "SIZE", "e"), (risk, "RISK TO REMOVE", "w")):
            c.create_text(x, y, text=text, anchor=anchor, font=FONTS["caps"], fill=THEME["dim"])

    def _draw_rows(self):
        c, width, row, base = self.canvas, self.canvas.winfo_width(), px(_ROW), FONTS["base"]
        c.configure(background=THEME["card"])
        c.delete("all")
        source, version, size_end, risk = self._columns(width)
        c.create_rectangle(0, 0, 0, 0, fill=THEME["hover"], width=0, state="hidden", tags="hover")
        for n, index in enumerate(self.visible):
            app, y = self.apps[index], n * row + row / 2
            c.create_image(px(_TICK_X), y, image=self._tick(index), tags=f"tick{n}")
            c.create_text(px(_NAME_X), y, text=_fit(app.name, source - px(_GAP + _NAME_X), base), anchor="w",
                          font=base, fill=THEME["fg"])
            self._tag(source, y, app.source.value, _SOURCE_TAG[app.source])
            c.create_text(version, y, text=_fit(app.version, px(110), base), anchor="w", font=base, fill=THEME["dim"])
            c.create_text(size_end, y, text=app.size_human if app.size_bytes else "—", anchor="e", font=base,
                          fill=THEME["dim"])
            self._tag(risk, y, app.risk.value, RISK_TAG[app.risk])
        if not self.visible:
            c.create_text(width / 2, row, text=self.empty, font=base, fill=THEME["dim"])
        c.configure(scrollregion=(0, 0, width, len(self.visible) * row))

    def _tag(self, x, y, text, colours):
        draw_tag(self.canvas, x, y, text, colours)

    def _tick(self, index):
        return tick_picture("all" if index in self.selected else "none", THEME["card"])

    def _row_at(self, event):
        n = int(self.canvas.canvasy(event.y) // px(_ROW))
        return n if 0 <= n < len(self.visible) else None

    def _reason_at(self, event) -> str:
        n = self._row_at(event)
        return "" if n is None else self.apps[self.visible[n]].risk_reason

    def _on_resize(self, event):
        if event.width != self._width:
            self._width = event.width
            self._draw()

    def _on_motion(self, event):
        n = self._row_at(event)
        if n is None:
            self.canvas.itemconfigure("hover", state="hidden")
            return
        self.canvas.coords("hover", 0, n * px(_ROW), self.canvas.winfo_width(), (n + 1) * px(_ROW))
        self.canvas.itemconfigure("hover", state="normal")

    # ---- filtering and selection ----

    def _row_visible(self, app) -> bool:
        if self.source_filter != _ALL and app.source.value != self.source_filter:
            return False
        return self.search_text.lower() in app.name.lower()

    def _refresh_rows(self):
        self.visible = [i for i, app in enumerate(self.apps) if self._row_visible(app)]
        self.canvas.yview_moveto(0)
        self._draw_rows()
        self._show_selection()

    def _on_click(self, event):
        n = self._row_at(event)
        if n is None or self.busy:
            return
        self.selected ^= {self.visible[n]}
        self.canvas.itemconfigure(f"tick{n}", image=self._tick(self.visible[n]))
        self._show_selection()

    @staticmethod
    def _pickable(app) -> bool:
        return app.risk != Risk.CRITICAL  # those stay one at a time, on purpose

    def _ticked(self) -> str:
        """The select-all circle: "all" when every app on screen that it
        picks is ticked, "some" when any app on screen is."""
        pickable = [i for i in self.visible if self._pickable(self.apps[i])]
        if pickable and all(i in self.selected for i in pickable):
            return "all"
        return "some" if any(i in self.selected for i in self.visible) else "none"

    def _on_select_all(self):
        """Ticks every app on screen that isn't Critical. Once they all are,
        or there are none, it clears the screen instead, so an app ticked by
        hand among Critical rows can still be cleared with it."""
        if self.busy:
            return
        pickable = [i for i in self.visible if self._pickable(self.apps[i])]
        if all(i in self.selected for i in pickable):
            self.selected.difference_update(self.visible)
        else:
            self.selected.update(pickable)
        self._draw_rows()
        self._show_selection()

    def _show_selection(self):
        chosen = [self.apps[i] for i in self.selected]
        self.bar.say(f"{len(chosen)} selected · {format_size(sum(a.size_bytes for a in chosen))}"
                     if chosen else f"{len(self.apps)} apps")
        self._draw_header()

    # ---- scanning ----

    def reload(self):
        if self.busy:
            return
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say("Scanning for installed software…")
        self.run_async(scan_all, self._on_scan_done)

    def _on_scan_done(self, apps):
        self.bar.done()
        self.apps, self.selected = apps, set()
        found = sorted({a.source.value for a in apps}, key=[s.value for s in Source].index)
        self.subtitle.configure(text=f"{len(apps)} apps from {', '.join(found)}" if apps else "Nothing found")
        self.empty = "Nothing matches" if apps else "Nothing found"
        self._refresh_rows()
        self.set_busy(False)

    # ---- uninstall flow ----

    def _on_uninstall_clicked(self):
        chosen = [self.apps[i] for i in sorted(self.selected)]
        if not chosen:
            info(self.winfo_toplevel(), "Nothing selected", "Tick one or more apps first.")
            return
        critical = any(a.risk == Risk.CRITICAL for a in chosen)
        if confirm(self.winfo_toplevel(), f"Uninstall {len(chosen)} item(s)?",
                   [f"• {a.name} — {a.source.value} — {a.risk.value}" for a in chosen], "Uninstall",
                   "I understand this includes system-critical software" if critical else ""):
            self._run_uninstall_async(chosen)

    def _run_uninstall_async(self, apps):
        self.set_busy(True)
        total = len(apps)

        def work():
            results = []
            for i, app in enumerate(apps):
                later(self._on_item_start, f"Uninstalling {app.name} · {i + 1} of {total}", i, total)
                ok, message, leftovers = uninstall(app)
                results.append((app, ok, message, leftovers))
                later(self._on_item_done, ok, i + 1, total,
                           f"{app.name} removed" if ok else f"{app.name} failed: {message}")
            return results

        self.run_async(work, self._on_uninstall_done)

    def _on_item_start(self, text, index, total):
        self.bar.say(text)
        self.bar.slice(index / total, (index + 1) / total)

    def _on_item_done(self, ok, done_count, total, text):
        self.bar.settle(done_count / total, ok)
        self.bar.say(text)

    def _on_uninstall_done(self, results):
        self.set_busy(False)
        window, all_leftovers, failures, warnings = self.winfo_toplevel(), [], [], []
        app_freed = 0
        for app, ok, message, leftovers in results:
            if ok:
                app_freed += app.size_bytes
                all_leftovers.extend(leftovers)
                if message:
                    warnings.append((app, message))
            else:
                failures.append((app, message))
        if failures:
            info(window, "Some items failed to uninstall", "\n".join(f"{a.name}: {m}" for a, m in failures))
        if warnings:
            info(window, "Removed, with a warning", "\n".join(f"{a.name}: {m}" for a, m in warnings))
        if all_leftovers:
            # The uninstall's own last line stays up until the leftover
            # question is answered, instead of flashing away under the dialog.
            self._offer_leftover_cleanup(all_leftovers, app_freed)
        else:
            if app_freed:
                info(window, "Uninstall complete", f"Freed {format_size(app_freed)} of disk space.")
            self.after(800, self.reload)

    def _offer_leftover_cleanup(self, paths, app_freed):
        """CLAUDE.md non-negotiable: leftovers are shown and opt-in, never
        deleted silently."""
        dialog = Dialog(self.winfo_toplevel(), "Leftover files found")
        tk.Label(dialog.body, text="These weren't removed by the uninstaller. Delete them too?",
                 anchor="w").pack(fill="x", pady=(0, px(8)))
        box = role(Rounded(dialog.body, radius=12, pad=6), bg="card", border="border")
        box.pack(fill="both", expand=True)
        canvas = tk.Canvas(box.inner, width=px(520), height=px(220), highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(box.inner, orient="vertical", command=canvas.yview, style="Thin.Vertical.TScrollbar")
        rows = tk.Frame(canvas)
        rows.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=rows, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        checks = []
        for path in paths:
            ticked = tk.BooleanVar(value=True)
            Tick(rows, str(path), ticked).pack(anchor="w", pady=px(2))
            checks.append((ticked, path))
        box.fit()
        dialog.button("Skip")
        dialog.button("Delete selected", True, "destructive")
        to_delete = [p for ticked, p in checks if ticked.get()] if dialog.run() is True else []
        if to_delete:
            self._run_leftover_cleanup_async(to_delete, app_freed)
        else:
            if app_freed:
                info(self.winfo_toplevel(), "Uninstall complete", f"Freed {format_size(app_freed)} of disk space.")
            self.reload()

    def _run_leftover_cleanup_async(self, paths, app_freed):
        self.set_busy(True)
        total = len(paths)

        def work():
            freed_total, all_errors = app_freed, []
            for i, path in enumerate(paths):
                later(self._on_item_start, f"Removing {path.name} · {i + 1} of {total}", i, total)
                freed, errors = clean_leftovers([path])
                freed_total += freed
                all_errors.extend(errors)
                later(self._on_item_done, not errors, i + 1, total, f"Removed {path.name}")
            return freed_total, all_errors

        self.run_async(work, self._on_leftover_cleanup_done)

    def _on_leftover_cleanup_done(self, result):
        freed_bytes, errors = result
        self.set_busy(False)
        self.after(800, self.reload)
        if errors:
            info(self.winfo_toplevel(), "Some leftovers couldn't be deleted",
                 f"Freed {format_size(freed_bytes)}.\n\n" + "\n".join(f"{p}: {err}" for p, err in errors))
        else:
            info(self.winfo_toplevel(), "Uninstall complete", f"Freed {format_size(freed_bytes)} of disk space.")
