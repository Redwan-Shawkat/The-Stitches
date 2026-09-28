"""Defrag: every drive letter as a tile, one card per disk, as the Linux
build groups them by OS. Only drives Windows can optimize get a tick, and a
disk's heading ticks all of its own. Everything picked goes in one
Optimize-Volume run, behind one permission prompt."""

import tkinter as tk

from .. import defrag
from ..elevate import tail
from ..models import format_size
from ..widgets import FONTS, Icon, Page, Rounded, Tick, Tooltip, info, px, recolour, role

_ACTION = {"defragment": "Defragment", "trim": "Trim"}


class DefragPage(Page):
    title = "Defrag"
    icon = "defrag"

    def __init__(self, parent):
        super().__init__(parent)
        self.volumes, self.ticks, self.tick_widgets = [], {}, []
        self.header_button("refresh", "Look again", self.reload)
        self.groups = tk.Frame(self.body)
        self.groups.pack(fill="both", expand=True)
        self.bar.add_button("Optimize selected", self._on_optimize, "suggested")

    def set_busy(self, busy: bool):
        super().set_busy(busy)
        for tick in self.tick_widgets:
            tick.configure(state="disabled" if busy else "normal")

    # ---- drawing ----

    def _render(self):
        for child in self.groups.winfo_children():
            child.destroy()
        self.ticks, self.tick_widgets = {}, []
        by_disk = {}
        for v in self.volumes:
            by_disk.setdefault(v.disk, []).append(v)
        for disk, volumes in by_disk.items():
            card = role(Rounded(self.groups, radius=14, pad=14), bg="card", border="border")
            card.pack(fill="x", pady=(0, px(12)))
            heading = tk.Frame(card.inner)
            heading.pack(fill="x", pady=(0, px(8)))
            ready = [v for v in volumes if v.action]
            if ready:
                group = tk.BooleanVar()
                tick = Tick(heading, disk, group, command=lambda g=group, r=ready: self._tick_group(g, r))
                tick.configure(font=FONTS["bold"])
                tick.pack(side="left")
                self.tick_widgets.append(tick)
            else:
                tk.Label(heading, text=disk, font=FONTS["bold"]).pack(side="left")
            tiles = tk.Frame(card.inner)
            tiles.pack(fill="x")
            for n, v in enumerate(volumes):
                self._tile(tiles, v, ready, group if ready else None).grid(
                    row=n // 3, column=n % 3, sticky="nw", padx=(0, px(24)), pady=px(4))
            card.fit()
        if not self.volumes:
            role(tk.Label(self.groups, text="No drives found."), fg="dim").pack(anchor="w")
        recolour(self.groups)
        self._show_selection()

    def _tile(self, parent, v, ready, group):
        tile = tk.Frame(parent, width=px(230))
        top = tk.Frame(tile)
        top.pack(fill="x")
        Icon(top, "drive", 20).pack(side="left", padx=(0, px(8)))
        tk.Label(top, text=f"{v.letter} {v.label}".strip(), font=FONTS["bold"], anchor="w").pack(side="left")
        role(tk.Label(tile, text=f"{v.fs or 'No file system'} · {format_size(v.size)} · {format_size(v.free)} free",
                      anchor="w"), fg="dim").pack(fill="x")
        if v.action:
            self.ticks[v.letter] = var = tk.BooleanVar()
            tick = Tick(tile, _ACTION[v.action], var, command=lambda: self._tick_one(group, ready))
            tick.pack(anchor="w", pady=(px(4), 0))
            self.tick_widgets.append(tick)
            Tooltip(tick, lambda _e: v.why)
        else:
            role(tk.Label(tile, text=v.why, anchor="w", justify="left", wraplength=px(230), font=FONTS["small"]),
                 fg="dim").pack(fill="x", pady=(px(4), 0))
        return tile

    # ---- ticking ----

    def _tick_group(self, group, ready):
        for v in ready:
            self.ticks[v.letter].set(group.get())
        self._show_selection()

    def _tick_one(self, group, ready):
        group.set(all(self.ticks[v.letter].get() for v in ready))  # a variable set in code fires no command
        self._show_selection()

    def _chosen(self):
        return [v for v in self.volumes if v.action and self.ticks[v.letter].get()]

    def _show_selection(self):
        chosen = self._chosen()
        if chosen:
            self.bar.say(f"{len(chosen)} selected: " + ", ".join(f"{_ACTION[v.action].lower()} {v.letter}"
                                                                for v in chosen))
        elif not self.busy:
            self.bar.say("Hard disks get defragmented, SSDs trimmed; Windows picks which by itself.")

    # ---- reading and optimizing ----

    def reload(self):
        if self.busy:
            return
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say("Reading drives…")
        self.run_async(defrag.scan, self._on_scanned)

    def _on_scanned(self, volumes):
        self.bar.done()
        self.volumes = volumes
        self.set_busy(False)
        self._render()
        ready = sum(1 for v in volumes if v.action)
        self.subtitle.configure(text=f"{len(volumes)} drives · {ready} Windows can optimize")

    def _on_optimize(self):
        chosen = self._chosen()
        if not chosen:
            info(self.winfo_toplevel(), "Nothing selected", "Tick one or more drives first.")
            return
        self.set_busy(True)
        self.bar.say(f"Optimizing {', '.join(v.letter for v in chosen)}… a hard disk can take an hour")
        self.bar.slice(0, 1)
        self.run_async(lambda: defrag.optimize(chosen), self._on_done)

    def _on_done(self, result):
        ok, text = result
        self.set_busy(False)
        self.bar.settle(1, ok)
        self.bar.say("Done" if ok else "Some drives weren't optimized")
        if not ok:
            info(self.winfo_toplevel(), "Some drives weren't optimized", tail(text, 6))
