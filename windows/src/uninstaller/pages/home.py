"""Home: what this PC is, what its BIOS/UEFI settings mean, and how its
memory and drives are doing, each with a plain Good / Warning / Critical.
Laid out as Home is on Linux: groups with an icon by each heading, no
borders. Memory and drives are read again every few seconds while the page
is on screen. There are no temperatures: Windows gives those only to an
admin, through WMI, and most boards don't report them there anyway."""

import time
import tkinter as tk

from .. import sysinfo
from ..models import format_size
from ..widgets import (ACCENT, CRITICAL_FILL, FONTS, LINE, STATUS_TAG, THEME, WARNING_FILL, Icon, Page, mix,
                       on_theme, px, recolour, role, status_label)

_REFRESH_MS = 5000
_GAP = 18  # between groups: with no borders, the space is what sets them apart
_FILL = {sysinfo.GOOD: ACCENT, sysinfo.WARNING: WARNING_FILL, sysinfo.CRITICAL: CRITICAL_FILL}


def _clear(grid):
    for child in grid.winfo_children():
        child.destroy()


def _tag(parent, status):
    return status_label(parent, status, STATUS_TAG[status])


def _note(grid, text):
    role(tk.Label(grid, text=text, font=FONTS["small"], anchor="w"), fg="dim").grid(row=0, column=0, sticky="w")


class HomePage(Page):
    title = "Home"  # no icon: its dock button is the logo

    def __init__(self, parent):
        super().__init__(parent)
        self.static = self.live = None
        self._reading = False
        self.header_button("refresh", "Refresh", self.reload)
        top = tk.Frame(self.body)
        top.pack(fill="x")
        top.columnconfigure((0, 1), weight=1, uniform="half")
        left, right = tk.Frame(top), tk.Frame(top)
        left.grid(row=0, column=0, sticky="new", padx=(0, px(_GAP)))
        right.grid(row=0, column=1, sticky="new")
        self.pc = self._group(left, "This PC", "pc")
        self.memory = self._group(left, "Memory", "memory")
        self.firmware = self._group(right, "BIOS / UEFI settings", "chip")
        self.storage = self._group(self.body, "Storage", "drive")
        on_theme(self._render)
        self.after(_REFRESH_MS, self._tick)

    @staticmethod
    def _group(parent, title, icon):
        """A group: its icon and title over a grid to fill; returns the grid."""
        box = tk.Frame(parent)
        box.pack(fill="x", pady=(0, px(_GAP)))
        heading = tk.Frame(box)
        heading.pack(fill="x", pady=(0, px(6)))
        Icon(heading, icon, 14, LINE).pack(side="left", padx=(0, px(6)))
        role(tk.Label(heading, text=title.upper(), font=FONTS["caps"]), fg="dim").pack(side="left")
        grid = tk.Frame(box)
        grid.pack(fill="x")
        _note(grid, "Reading…")
        return grid

    # ---- reading ----

    def reload(self):
        self.bar.pulse()
        self.bar.say("Reading this PC…")
        self.run_async(lambda: (sysinfo.read_spec(), sysinfo.read_uptime(), sysinfo.read_firmware()), self._on_static)
        self._refresh()

    def _on_static(self, result):
        self.bar.done()
        self.static = result
        self._render()
        windows = dict(result[0]).get("Windows", "Windows")
        self.subtitle.configure(text=f"{windows} · memory and drives refresh every {_REFRESH_MS // 1000} seconds")

    def _tick(self):
        if self.winfo_ismapped() and not self._reading:  # only while on screen
            self._refresh()
        self.after(_REFRESH_MS, self._tick)

    def _refresh(self):
        self._reading = True
        self.run_async(lambda: (sysinfo.read_memory(), sysinfo.read_drives()), self._on_live)

    def _on_live(self, result):
        self._reading = False
        self.live = result
        self._render()
        self.bar.say(f"Live readings · updated {time.strftime('%H:%M:%S')}")

    def _failed(self, exc):
        self._reading = False
        super()._failed(exc)

    # ---- drawing ----

    def _render(self):
        """Every row again, from the last readings: on each reading, and on a theme change."""
        if self.static:
            spec, uptime, firmware = self.static
            _clear(self.pc)
            self.pc.columnconfigure(1, weight=1)
            for row, (key, value) in enumerate([*spec, ("Up", uptime)]):
                role(tk.Label(self.pc, text=key, anchor="nw"), fg="dim").grid(row=row, column=0, sticky="nw",
                                                                              padx=(0, px(12)), pady=px(1))
                tk.Label(self.pc, text=value, anchor="w", justify="left", wraplength=px(330)).grid(
                    row=row, column=1, sticky="w", pady=px(1))
            _clear(self.firmware)
            self.firmware.columnconfigure(0, weight=1)
            for row, (setting, value, meaning, status) in enumerate(firmware):
                cell = tk.Frame(self.firmware)
                cell.grid(row=row, column=0, sticky="ew", pady=(0, px(6)))
                tk.Label(cell, text=f"{setting}   ", font=FONTS["bold"]).pack(side="left", anchor="nw")
                text = tk.Frame(cell)
                text.pack(side="left", fill="x", expand=True)
                tk.Label(text, text=value, anchor="w").pack(fill="x")
                role(tk.Label(text, text=meaning, font=FONTS["small"], anchor="w", justify="left",
                              wraplength=px(300)), fg="dim").pack(fill="x")
                _tag(self.firmware, status).grid(row=row, column=1, sticky="ne", padx=(px(10), 0), pady=px(2))
            if not firmware:
                _note(self.firmware, "Windows didn't report its firmware settings.")
        if self.live:
            (used, total), drives = self.live
            _clear(self.memory)
            if total:
                self._usage(self.memory, 0, "RAM", "", used, total)
            else:
                _note(self.memory, "Windows didn't report its memory.")
            _clear(self.storage)
            for row, (letter, detail, used, size) in enumerate(drives):
                self._usage(self.storage, row, letter, detail, used, size)
            if not drives:
                _note(self.storage, "No drives found.")
        recolour(self.body)

    def _usage(self, grid, row, name, detail, used, size):
        """name · detail · bar · "used of size · share" · status tag."""
        status = sysinfo.usage_status(used, size)
        grid.columnconfigure(2, weight=1)
        tk.Label(grid, text=name, font=FONTS["bold"], anchor="w").grid(row=row, column=0, sticky="w", pady=px(2))
        role(tk.Label(grid, text=detail, anchor="w"), fg="dim").grid(row=row, column=1, sticky="w",
                                                                   padx=(px(8), px(12)))
        self._bar(grid, used / size if size else 0, status).grid(row=row, column=2, sticky="ew")
        role(tk.Label(grid, text=f"{format_size(used)} of {format_size(size)} · {used / size if size else 0:.0%}",
                      font=FONTS["small"]), fg="dim").grid(row=row, column=3, sticky="e", padx=(px(12), px(8)))
        _tag(grid, status).grid(row=row, column=4, sticky="e")

    @staticmethod
    def _bar(parent, share, status):
        trough, fill = mix(THEME["window"], THEME["fg"], 0.1), _FILL[status]
        bar = role(tk.Canvas(parent, width=px(80), height=px(6), highlightthickness=0, borderwidth=0,
                             background=THEME["window"]), fixed=True)

        def draw(event):
            bar.delete("all")
            bar.create_rectangle(0, 0, event.width, event.height, fill=trough, width=0)
            bar.create_rectangle(0, 0, event.width * share, event.height, fill=fill, width=0)

        bar.bind("<Configure>", draw)
        return bar
