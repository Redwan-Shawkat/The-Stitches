"""Tkinter/ttk GUI. One window, kept as one module — splitting a single
cohesive window into more files would be indirection, not structure.

Tkinter rather than GTK3: the Linux build uses PyGObject because Ubuntu ships
it, and the same rung of the ladder points the other way on Windows, where
tkinter is the binding that comes with Python and PyGObject is a multi-
hundred-megabyte MSYS2 runtime to redistribute. See ai-knowledgebase.md.
"""

import ctypes
import os
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from .models import Risk, Source, format_size
from .scanner import scan_all
from .uninstaller import clean_leftovers, uninstall

_ICON_PATH = os.path.join(os.path.dirname(__file__), "icon.ico")
_APP_ID = "io.github.windows-the-uninstaller"

# ttk's native "vista" theme draws widgets through the OS, which means it
# ignores the colours we set — including the progress bar's green/red. "clam"
# is the one built-in theme that honours every colour, so it backs both
# palettes rather than special-casing a theme per mode.
# "Graphite & Signal": dark-first, one lime accent; see ai-knowledgebase.md.
_PALETTES = {
    True: {  # dark — the default
        "bg": "#0f1012", "panel": "#17181b", "tray": "#1b1c20", "line": "#2a2b30",
        "fg": "#f2efe8", "muted": "#a3a29c", "accent": "#d4ff3a", "on_accent": "#0f1012",
        "accent_hover": "#e8ff94", "picked": "#1f2614",
        "safe": "#7fe3b0", "caution": "#ffc14d", "critical": "#ff5c5c",
        Source.INSTALLER: "#6e8bff", Source.STORE: "#c792ff",
        Source.CHOCOLATEY: "#e6a06b", Source.SCOOP: "#4fd1c5",
    },
    False: {  # light
        "bg": "#f4f1ea", "panel": "#fbfaf6", "tray": "#efebe2", "line": "#e3dfd4",
        "fg": "#16161a", "muted": "#5e5d58", "accent": "#16161a", "on_accent": "#d4ff3a",
        "accent_hover": "#3d3d44", "picked": "#eaf3c9",
        "safe": "#0f7a4a", "caution": "#8a5a00", "critical": "#c8102e",
        Source.INSTALLER: "#3b5bdb", Source.STORE: "#8e44d6",
        Source.CHOCOLATEY: "#9a4f12", Source.SCOOP: "#0f7a70",
    },
}

# Risk is told apart by shape as well as colour, so it survives colour-blindness.
_GLYPHS = {Risk.SAFE: "●", Risk.CAUTION: "▲", Risk.CRITICAL: "■"}

(COL_NAME, COL_SOURCE, COL_VERSION, COL_SIZE, COL_RISK, COL_SEL) = (
    "name", "source", "version", "size", "risk", "sel",
)
# Widths sum to less than the default window's list, so nothing is clipped;
# Name stretches to take whatever is left.
_COLUMNS = (
    (COL_SEL, "", 44, "center"),
    (COL_NAME, "Name", 220, "w"),
    (COL_SOURCE, "Installed via", 150, "w"),
    (COL_VERSION, "Version", 110, "w"),
    (COL_SIZE, "Size", 90, "e"),
    (COL_RISK, "Risk", 90, "w"),
)
_PICKED, _UNPICKED = "✓", "+"


def _pick_family(root, *names):
    """First installed family; Segoe UI Variable ships with Windows 11 only."""
    available = set(tkfont.families(root))
    return next((n for n in names if n in available), names[-1])


def _blend(colour, toward, amount):
    """Tk canvases have no alpha, so a dimmed segment is a mixed colour."""
    a = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(toward[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


def _glyph_image(colour, risk):
    """The row's risk shape, drawn into a 12px image: a Treeview can colour a
    whole row but not one cell, and the tree column takes an image."""
    image = tk.PhotoImage(width=12, height=12)
    for y in range(12):
        for x in range(12):
            if risk == Risk.SAFE:
                inside = (x - 5.5) ** 2 + (y - 5.5) ** 2 <= 25
            elif risk == Risk.CAUTION:
                inside = 1 <= y <= 11 and abs(x - 5.5) <= (y - 1) * 0.55 + 0.5
            else:
                inside = 1 <= x <= 10 and 1 <= y <= 10
            if inside:
                image.put(colour, (x, y))
    return image


class _Tooltip:
    """The risk reason on hover — ttk has no tooltip, and the reason is the
    whole point of the risk column, so it gets the ~20 lines."""

    def __init__(self, widget, text_for_row, colours):
        self.widget = widget
        self.text_for_row = text_for_row
        self.colours = colours
        self.window = None
        self.row = None
        widget.bind("<Motion>", self._on_motion, add="+")
        widget.bind("<Leave>", lambda _e: self._hide(), add="+")

    def _on_motion(self, event):
        row = self.widget.identify_row(event.y)
        if row == self.row:
            return
        self.row = row
        self._hide()
        text = self.text_for_row(row) if row else ""
        if not text:
            return
        c = self.colours()
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{event.x_root + 16}+{event.y_root + 20}")
        tk.Label(
            self.window, text=text, justify="left", wraplength=420,
            background=c["tray"], foreground=c["fg"], relief="solid", borderwidth=1,
            padx=10, pady=6,
        ).pack()

    def _hide(self):
        if self.window:
            self.window.destroy()
            self.window = None


class UninstallerWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("The Uninstaller")
        self.geometry("1180x760")
        self.minsize(900, 600)
        try:
            self.iconbitmap(default=_ICON_PATH)
        except tk.TclError:
            pass  # no .ico (running from a checkout on another OS) — not fatal

        self.apps: list = []
        self.selected: set[int] = set()
        self.visible_rows: list[int] = []
        self._tray_indices: list[int] = []
        self._anchor = None  # last clicked row, for Shift+click ranges
        self.search_text = ""
        self.source_filter = "All sources"
        self._dark = True
        self._placeholder_active = True
        self._progress_animating = False
        self._progress_job = None
        self._fonts = {
            "display": _pick_family(self, "Segoe UI Variable Display", "Segoe UI"),
            "body": _pick_family(self, "Segoe UI Variable Text", "Segoe UI"),
            "mono": _pick_family(self, "Cascadia Mono", "Consolas"),
        }

        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self._build_ui()
        self._apply_palette()
        self.reload()

    def _colours(self):
        return _PALETTES[self._dark]

    # ---- layout ----

    def _build_ui(self):
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True)
        root.rowconfigure(1, weight=1)
        root.columnconfigure(0, weight=1)
        self._build_hero(root).grid(row=0, column=0, sticky="ew")
        body = ttk.Frame(root, padding=(16, 8, 16, 16))
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self._build_list(body).grid(row=0, column=0, sticky="nsew")
        self._build_tray(body).grid(row=0, column=1, sticky="ns", padx=(12, 0))
        # Traced only once everything exists: setting the placeholder text
        # writes the variable, and the handler refilters the (not yet built)
        # tree.
        self.search_var.trace_add("write", lambda *_: self._on_search_changed())

    def _build_hero(self, parent):
        """Disk space by source is the headline — and the source filter: click
        a bar segment or its legend entry."""
        hero = ttk.Frame(parent, padding=(28, 18, 28, 8))
        hero.columnconfigure(1, weight=1)
        ttk.Label(hero, text="INSTALLED SOFTWARE", style="Caption.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.total_label = ttk.Label(hero, text="…", style="Display.TLabel")
        self.total_label.grid(row=1, column=0, sticky="w")
        self.summary_label = ttk.Label(
            hero, style="Muted.TLabel", wraplength=380, justify="left"
        )
        self.summary_label.grid(row=1, column=1, sticky="sw", padx=(20, 0), pady=(0, 10))

        tools = ttk.Frame(hero)
        tools.grid(row=1, column=2, sticky="se", pady=(0, 10))
        ttk.Button(
            tools, text="Show all", command=lambda: self._set_source_filter("All sources")
        ).pack(side="left")
        ttk.Button(tools, text="Rescan", command=self.reload).pack(side="left", padx=(6, 0))
        self.theme_button = ttk.Button(tools, width=11, command=self._on_theme_toggled)
        self.theme_button.pack(side="left", padx=(6, 0))

        self.disk_bar = tk.Canvas(hero, height=28, highlightthickness=0, borderwidth=0,
                                  cursor="hand2")
        self.disk_bar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(14, 10))
        self.disk_bar.bind("<Configure>", lambda _e: self._draw_disk_bar())

        legend = ttk.Frame(hero)
        legend.grid(row=3, column=0, columnspan=3, sticky="w")
        self.legend_labels = {}
        for source in Source:
            label = ttk.Label(legend, cursor="hand2")
            label.pack(side="left", padx=(0, 28))
            label.bind("<Button-1>", lambda _e, s=source: self._toggle_source(s))
            self.legend_labels[source] = label
        return hero

    def _placeholder(self, entry, text):
        """Tkinter entries have no placeholder property; this is the whole
        feature in six lines rather than a widget subclass."""
        self._placeholder_active = True
        entry.insert(0, text)
        entry.configure(foreground=self._colours()["muted"])

        def focus_in(_event):
            if self._placeholder_active:
                entry.delete(0, "end")
                entry.configure(foreground=self._colours()["fg"])
                self._placeholder_active = False

        def focus_out(_event):
            if not entry.get():
                self._placeholder_active = True
                entry.insert(0, text)
                entry.configure(foreground=self._colours()["muted"])

        entry.bind("<FocusIn>", focus_in)
        entry.bind("<FocusOut>", focus_out)

    def _build_list(self, parent):
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=(14, 12, 6, 6))
        panel.rowconfigure(2, weight=1)
        panel.columnconfigure(0, weight=1)

        head = ttk.Frame(panel, style="Panel.TFrame")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 8))
        head.columnconfigure(0, weight=1)
        self.search_var = tk.StringVar()
        search = ttk.Entry(head, textvariable=self.search_var, style="Search.TEntry")
        search.grid(row=0, column=0, sticky="ew", padx=(0, 16))
        self._placeholder(search, "filter by name…")
        ttk.Label(
            head, text="● safe   ▲ caution   ■ critical", style="PanelMono.TLabel"
        ).grid(row=0, column=1, padx=(0, 16))
        self.status_label = ttk.Label(head, text="", style="PanelMono.TLabel")
        self.status_label.grid(row=0, column=2)

        # 0-100 rather than 0-1: indeterminate mode steps by 1.0 per tick, so
        # a maximum of 1.0 would bounce a whole cycle every tick.
        self.progress = ttk.Progressbar(panel, maximum=100)
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 6), padx=(0, 8))

        self.tree = ttk.Treeview(
            panel, columns=[c[0] for c in _COLUMNS], show="tree headings", selectmode="none"
        )
        self.tree.column("#0", width=36, minwidth=36, stretch=False, anchor="center")
        for name, heading, width, anchor in _COLUMNS:
            self.tree.heading(name, text=heading, anchor=anchor)
            self.tree.column(name, width=width, anchor=anchor, stretch=(name == COL_NAME))
        scroll = ttk.Scrollbar(panel, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=2, column=0, sticky="nsew")
        scroll.grid(row=2, column=1, sticky="ns")
        self.tree.bind("<Button-1>", self._on_tree_click)
        _Tooltip(self.tree, self._reason_for_row, self._colours)
        return panel

    def _build_tray(self, parent):
        """The selection as a cart: what's queued, what it frees, one way on."""
        tray = ttk.Frame(parent, style="Tray.TFrame", padding=18, width=320)
        tray.grid_propagate(False)
        tray.columnconfigure(0, weight=1)
        tray.rowconfigure(1, weight=1)

        head = ttk.Frame(tray, style="Tray.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text="Removal tray", style="TrayTitle.TLabel").pack(side="left")
        self.tray_count = ttk.Label(head, style="TrayMono.TLabel")
        self.tray_count.pack(side="left", padx=(10, 0), pady=(6, 0))

        self.tray_list = tk.Listbox(
            tray, activestyle="none", borderwidth=0, highlightthickness=0, relief="flat"
        )
        self.tray_list.grid(row=1, column=0, sticky="nsew", pady=12)
        self.tray_list.bind("<Double-Button-1>", self._on_tray_double_click)

        self.tray_warning = ttk.Label(
            tray, style="TrayCritical.TLabel", wraplength=280, justify="left"
        )
        self.tray_warning.grid(row=2, column=0, sticky="ew", pady=(0, 12))

        frees = ttk.Frame(tray, style="Tray.TFrame")
        frees.grid(row=3, column=0, sticky="ew")
        ttk.Label(frees, text="FREES UP", style="TrayMono.TLabel").pack(side="left", anchor="s")
        self.tray_size = ttk.Label(frees, style="TrayBig.TLabel")
        self.tray_size.pack(side="right")

        buttons = ttk.Frame(tray, style="Tray.TFrame")
        buttons.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="Add all non-critical", command=self._on_select_all).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(buttons, text="Clear", command=self._on_select_none).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(
            tray, text="Review & uninstall  →", style="Accent.TButton",
            command=self._on_uninstall_clicked,
        ).grid(row=5, column=0, sticky="ew", pady=(12, 0))
        return tray

    # ---- theming ----

    def _apply_palette(self):
        c = self._colours()
        f = self._fonts
        s = self.style
        self.configure(background=c["bg"])
        s.configure(".", background=c["bg"], foreground=c["fg"], bordercolor=c["line"],
                    focuscolor=c["muted"], font=(f["body"], 10))
        s.configure("TFrame", background=c["bg"])
        s.configure("Panel.TFrame", background=c["panel"])
        s.configure("Tray.TFrame", background=c["tray"])

        s.configure("TLabel", background=c["bg"], foreground=c["fg"])
        s.configure("Caption.TLabel", foreground=c["muted"], font=(f["mono"], 9))
        s.configure("Muted.TLabel", foreground=c["muted"])
        s.configure("Critical.TLabel", foreground=c["critical"])
        s.configure("Display.TLabel", font=(f["display"], 36, "bold"))
        s.configure("Headline.TLabel", font=(f["display"], 24, "bold"))
        s.configure("Title.TLabel", font=(f["display"], 15, "bold"))
        s.configure("PanelMono.TLabel", background=c["panel"], foreground=c["muted"],
                    font=(f["mono"], 9))
        s.configure("TrayTitle.TLabel", background=c["tray"], font=(f["display"], 15, "bold"))
        s.configure("TrayMono.TLabel", background=c["tray"], foreground=c["muted"],
                    font=(f["mono"], 9))
        s.configure("TrayBig.TLabel", background=c["tray"], font=(f["display"], 24, "bold"))
        s.configure("TrayCritical.TLabel", background=c["tray"], foreground=c["critical"])

        s.configure("TButton", background=c["panel"], foreground=c["fg"], padding=(14, 7),
                    bordercolor=c["line"], lightcolor=c["panel"], darkcolor=c["panel"])
        s.map("TButton", background=[("disabled", c["bg"]), ("active", c["line"])],
              foreground=[("disabled", c["muted"])])
        s.configure("Accent.TButton", background=c["accent"], foreground=c["on_accent"],
                    bordercolor=c["accent"], lightcolor=c["accent"], darkcolor=c["accent"],
                    padding=(18, 11), font=(f["body"], 11, "bold"))
        s.map("Accent.TButton",
              background=[("disabled", c["line"]), ("active", c["accent_hover"])],
              foreground=[("disabled", c["muted"])])

        s.configure("TEntry", fieldbackground=c["panel"], foreground=c["fg"],
                    insertcolor=c["fg"], bordercolor=c["line"], lightcolor=c["panel"],
                    darkcolor=c["panel"])
        s.configure("Search.TEntry", padding=(8, 6), font=(f["mono"], 10))
        for name, background in (("TCheckbutton", c["bg"]), ("Panel.TCheckbutton", c["panel"])):
            s.configure(name, background=background, foreground=c["fg"],
                        indicatorbackground=c["panel"], indicatorforeground=c["fg"])
            s.map(name, background=[("active", background)])
        s.configure("Panel.TCheckbutton", font=(f["mono"], 10))

        rowheight = tkfont.Font(self, family=f["body"], size=10).metrics("linespace") * 2 + 4
        s.configure("Treeview", background=c["panel"], fieldbackground=c["panel"],
                    foreground=c["fg"], rowheight=rowheight, borderwidth=0,
                    font=(f["body"], 10))
        s.configure("Treeview.Heading", background=c["panel"], foreground=c["muted"],
                    relief="flat", borderwidth=0, font=(f["mono"], 9))
        s.map("Treeview.Heading", background=[("active", c["panel"])])
        # clam frames the tree in a focus-coloured border; the panel is the frame.
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.configure("Vertical.TScrollbar", background=c["line"], troughcolor=c["panel"],
                    bordercolor=c["panel"], arrowcolor=c["muted"], lightcolor=c["line"],
                    darkcolor=c["line"])
        for style_name, colour in (
            ("TProgressbar", c["accent"]),
            ("Success.Horizontal.TProgressbar", c["safe"]),
            ("Error.Horizontal.TProgressbar", c["critical"]),
        ):
            s.configure(style_name, background=colour, troughcolor=c["panel"],
                        bordercolor=c["panel"], lightcolor=colour, darkcolor=colour)

        self.tree.tag_configure("picked", background=c["picked"])
        self._glyph_images = {r: _glyph_image(c[r.name.lower()], r) for r in Risk}
        self.tray_list.configure(
            background=c["tray"], foreground=c["fg"], selectbackground=c["line"],
            selectforeground=c["fg"], font=(f["body"], 10),
        )
        self.theme_button.configure(text="Light mode" if self._dark else "Dark mode")
        self._refresh_rows()
        self._refresh_summary()
        self._refresh_tray()

    def _on_theme_toggled(self):
        self._dark = not self._dark
        self._apply_palette()

    # ---- disk bar, legend, tray ----

    def _source_weights(self):
        """Bytes per source; app counts instead when no source reports a size
        (only registry installs do — see features.md)."""
        present = [s for s in Source if any(a.source == s for a in self.apps)]
        sizes = {s: sum(a.size_bytes for a in self.apps if a.source == s) for s in present}
        if not any(sizes.values()):
            return [(s, sum(1 for a in self.apps if a.source == s)) for s in present]
        return [(s, sizes[s]) for s in present]

    def _draw_disk_bar(self):
        c = self._colours()
        bar = self.disk_bar
        bar.delete("all")
        bar.configure(background=c["bg"])
        weights = self._source_weights()
        if not weights:
            return
        gap = 3
        available = bar.winfo_width() - gap * (len(weights) - 1)
        total = sum(w for _, w in weights)
        # A source with no known size still gets a clickable sliver.
        raw = [max(8, available * w / total) for _, w in weights]
        scale = available / sum(raw)
        x = 0
        for (source, _), width in zip(weights, raw):
            width *= scale
            active = self.source_filter in ("All sources", source.value)
            fill = c[source] if active else _blend(c[source], c["bg"], 0.72)
            rect = bar.create_rectangle(x, 0, x + width, 28, fill=fill, width=0)
            bar.tag_bind(rect, "<Button-1>", lambda _e, s=source: self._toggle_source(s))
            x += width + gap

    def _refresh_summary(self):
        c = self._colours()
        total = sum(a.size_bytes for a in self.apps)
        sources = {a.source for a in self.apps}
        if self.apps:
            self.total_label.configure(
                text=format_size(total) if total else f"{len(self.apps)} apps"
            )
            self.summary_label.configure(
                text=f"{len(self.apps)} apps from {len(sources)} source(s) — one list, "
                "however they got here. Scanning is read-only."
            )
        for source, label in self.legend_labels.items():
            mine = [a for a in self.apps if a.source == source]
            size = sum(a.size_bytes for a in mine)
            active = self.source_filter == source.value
            label.configure(
                text=f"■  {source.value}   {len(mine)}" + (f" · {format_size(size)}" if size else ""),
                foreground=c[source],
                font=(self._fonts["body"], 10, "underline" if active else "normal"),
            )
        self._draw_disk_bar()

    def _refresh_tray(self):
        c = self._colours()
        self._tray_indices = sorted(self.selected)
        self.tray_list.delete(0, "end")
        for row, index in enumerate(self._tray_indices):
            app = self.apps[index]
            size = f"  ·  {app.size_human}" if app.size_bytes else ""
            self.tray_list.insert("end", f"{_GLYPHS[app.risk]}  {app.name}{size}")
            if app.risk != Risk.SAFE:
                self.tray_list.itemconfigure(row, foreground=c[app.risk.name.lower()])
        if not self._tray_indices:
            self.tray_list.insert("end", "Nothing here yet — click an app to add it.")
            self.tray_list.itemconfigure(0, foreground=c["muted"])

        picked = [self.apps[i] for i in self._tray_indices]
        freed = sum(a.size_bytes for a in picked)
        self.tray_count.configure(text=f"{len(picked)} app(s)")
        self.tray_size.configure(text=format_size(freed) if freed else "—")
        critical = sum(1 for a in picked if a.risk == Risk.CRITICAL)
        if critical:
            self.tray_warning.configure(
                text=f"■ {critical} critical item(s) in the tray — you'll have to "
                "confirm separately."
            )
            self.tray_warning.grid()
        else:
            self.tray_warning.grid_remove()

    def _on_tray_double_click(self, _event):
        chosen = self.tray_list.curselection()
        if chosen and chosen[0] < len(self._tray_indices):
            self._set_checked(self._tray_indices[chosen[0]], False)

    def _toggle_source(self, source):
        self._set_source_filter(
            "All sources" if self.source_filter == source.value else source.value
        )

    def _set_source_filter(self, value):
        self.source_filter = value
        self._refresh_rows()
        self._refresh_summary()

    # ---- rows ----

    def _row_visible(self, app) -> bool:
        if self.source_filter != "All sources" and app.source.value != self.source_filter:
            return False
        return self.search_text.lower() in app.name.lower()

    def _refresh_rows(self):
        """Rebuilds the visible rows. ponytail: a Treeview has no filter model
        like GTK's, and refilling a few hundred rows is instant — swap in an
        incremental diff only if a machine turns up where it isn't."""
        self.tree.delete(*self.tree.get_children())
        self.visible_rows = []
        for index, app in enumerate(self.apps):
            if not self._row_visible(app):
                continue
            self.visible_rows.append(index)
            picked = index in self.selected
            self.tree.insert(
                "", "end", iid=str(index), image=self._glyph_images[app.risk],
                values=(
                    _PICKED if picked else _UNPICKED, app.name, app.source.value,
                    app.version, app.size_human if app.size_bytes else "—", app.risk.value,
                ),
                tags=("picked",) if picked else (),
            )

    def _reason_for_row(self, row_id):
        if not row_id:
            return ""
        return self.apps[int(row_id)].risk_reason

    def _set_checked(self, index, checked):
        self.selected.add(index) if checked else self.selected.discard(index)
        if self.tree.exists(str(index)):
            self.tree.set(str(index), COL_SEL, _PICKED if checked else _UNPICKED)
            self.tree.item(str(index), tags=("picked",) if checked else ())
        self._refresh_tray()

    def _on_tree_click(self, event):
        # A click anywhere on a row toggles it; hovering (the risk-reason
        # tooltip) still selects nothing.
        if self.tree.identify_region(event.x, event.y) not in ("cell", "tree"):
            return
        row = self.tree.identify_row(event.y)
        if row:
            self._toggle_row(int(row), extend=bool(event.state & 0x0001))  # Shift

    def _toggle_row(self, index, extend=False):
        """Plain click toggles one row. Shift+click adds every visible row
        between the last click and this one — skipping Critical, same rule as
        Select All: those are picked one at a time."""
        if extend and self._anchor in self.visible_rows:
            a, b = sorted((self.visible_rows.index(self._anchor), self.visible_rows.index(index)))
            for i in self.visible_rows[a:b + 1]:
                if self.apps[i].risk != Risk.CRITICAL:
                    self._set_checked(i, True)
        else:
            self._set_checked(index, index not in self.selected)
        self._anchor = index

    def _on_search_changed(self):
        self.search_text = "" if self._placeholder_active else self.search_var.get()
        self._refresh_rows()

    def _on_select_all(self):
        for index in self.visible_rows:
            if self.apps[index].risk != Risk.CRITICAL:
                self._set_checked(index, True)

    def _on_select_none(self):
        for index in list(self.selected):
            self._set_checked(index, False)

    # ---- scanning ----

    def reload(self):
        self.status_label.configure(text="Scanning for installed software…")
        self._set_busy(True)
        self.progress.configure(style="TProgressbar", mode="indeterminate")
        self.progress.start(12)

        def worker():
            apps = scan_all()
            self.after(0, self._on_scan_done, apps)

        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_done(self, apps):
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        self.apps = sorted(apps, key=lambda a: a.size_bytes, reverse=True)
        self.selected.clear()
        self._anchor = None
        self._refresh_rows()
        self._refresh_summary()
        self._refresh_tray()
        self.status_label.configure(text=f"{len(apps)} item(s) · biggest first")
        self._set_busy(False)

    def _set_busy(self, busy):
        """Tk has no container-wide sensitivity like GTK's set_sensitive, so
        the state is pushed to the widgets that can start work."""
        state = "disabled" if busy else "!disabled"
        for child in self.winfo_children():
            for widget in (child, *self._descendants(child)):
                if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Combobox, ttk.Treeview)):
                    try:
                        widget.state([state])
                    except tk.TclError:
                        pass

    def _descendants(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self._descendants(child)

    # ---- uninstall flow ----

    def _on_uninstall_clicked(self):
        selected = [self.apps[i] for i in sorted(self.selected)]
        if not selected:
            self._info_dialog("The tray is empty", "Click one or more apps first.")
            return
        if self._confirm(selected):
            self._run_uninstall_async(selected)

    def _confirm(self, apps) -> bool:
        """CLAUDE.md non-negotiable: nothing is removed without this, and
        anything Critical needs the extra acknowledgement before OK unlocks."""
        c = self._colours()
        critical = [a for a in apps if a.risk == Risk.CRITICAL]
        freed = sum(a.size_bytes for a in apps)
        dialog = self._dialog(f"Uninstall {len(apps)} item(s)?")
        body = ttk.Frame(dialog, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="FINAL CHECK", style="Caption.TLabel").pack(anchor="w")
        headline = f"Remove {len(apps)} app{'' if len(apps) == 1 else 's'}."
        if freed:
            headline += f"\nFree up {format_size(freed)}."
        ttk.Label(body, text=headline, style="Headline.TLabel", justify="left").pack(
            anchor="w", pady=(4, 10)
        )
        ttk.Label(
            body, style="Muted.TLabel", wraplength=540, justify="left",
            text="They're removed one at a time, in this order. Anything installed for "
            "every user brings up Windows' own permission prompt — this app never asks "
            "for your password.",
        ).pack(anchor="w", pady=(0, 12))

        receipt = tk.Text(
            body, height=min(10, max(3, len(apps))), width=64, wrap="none", relief="flat",
            font=(self._fonts["mono"], 10), background=c["panel"], foreground=c["fg"],
            highlightthickness=0, padx=12, pady=10,
        )
        for risk in Risk:
            receipt.tag_configure(risk.name, foreground=c[risk.name.lower()])
        for app in apps:
            size = app.size_human if app.size_bytes else "—"
            receipt.insert("end", f"{_GLYPHS[app.risk]}  ", app.risk.name)
            receipt.insert("end", f"{app.name[:30]:<32}{app.source.value[:18]:<20}{size:>9}\n")
        receipt.configure(state="disabled")
        receipt.pack(fill="both", expand=True)

        result = {"ok": False}
        confirm_button = None
        if critical:
            for app in critical:
                ttk.Label(
                    body, style="Critical.TLabel", wraplength=540, justify="left",
                    text=f"■ {app.name} is critical. {app.risk_reason}",
                ).pack(anchor="w", pady=(12, 0))
            acknowledged = tk.BooleanVar(value=False)
            ttk.Checkbutton(
                body, variable=acknowledged,
                text="I understand this includes system-critical software",
                command=lambda: confirm_button.state(
                    ["!disabled" if acknowledged.get() else "disabled"]
                ),
            ).pack(anchor="w", pady=(8, 0))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(20, 0))
        confirm_button = ttk.Button(
            buttons, text=f"Uninstall {len(apps)}  →", style="Accent.TButton",
            command=lambda: (result.update(ok=True), dialog.destroy()),
        )
        confirm_button.pack(side="right")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 8))
        if critical:
            confirm_button.state(["disabled"])

        dialog.wait_window()
        return result["ok"]

    def _run_uninstall_async(self, apps):
        self._set_busy(True)
        self.progress.configure(value=0)
        total = len(apps)

        def worker():
            results = []
            for i, app in enumerate(apps):
                # Programs with no silent uninstall open their own window and
                # wait there — easy to miss behind this one.
                self.after(0, self._on_item_start,
                           f"Uninstalling {app.name}… finish any window it opens", i, total)
                try:
                    ok, message, leftovers = uninstall(app)
                except Exception as exc:  # noqa: BLE001 — a dead worker thread
                    # never reports back, stranding the window mid-progress
                    # with the error only on a console nobody sees.
                    ok, message, leftovers = False, f"Unexpected error: {exc}", []
                results.append((app, ok, message, leftovers))
                self.after(0, self._on_item_done, f"{app.name}", ok, message, i + 1, total)
            self.after(0, self._on_uninstall_done, results)

        threading.Thread(target=worker, daemon=True).start()

    def _start_progress_slice(self, start_frac, end_frac):
        """Animate the bar filling toward `end_frac` while the real operation
        (a blocking uninstaller with no progress of its own) runs in the
        background, so it reads as continuously advancing instead of jumping
        only when each item finishes."""
        self.progress.configure(
            style="Success.Horizontal.TProgressbar", value=start_frac * 100
        )
        self._progress_animating = True

        def tick():
            if not self._progress_animating:
                return
            # Crawl to 92% of the slice; the completion callback snaps the last
            # stretch so it never looks stuck short of the line.
            ceiling = (start_frac + (end_frac - start_frac) * 0.92) * 100
            self.progress.configure(
                value=min(ceiling, self.progress["value"] + (end_frac - start_frac) * 6)
            )
            self._progress_job = self.after(60, tick)

        tick()

    def _stop_progress_slice(self):
        self._progress_animating = False
        if self._progress_job:
            self.after_cancel(self._progress_job)
            self._progress_job = None

    def _on_item_start(self, label, index, total):
        self.status_label.configure(text=f"{label} ({index + 1}/{total})")
        self._start_progress_slice(index / total, (index + 1) / total)

    def _on_item_done(self, name, ok, message, done_count, total):
        self._stop_progress_slice()
        self.progress.configure(
            style=f"{'Success' if ok else 'Error'}.Horizontal.TProgressbar",
            value=done_count / total * 100,
        )
        self.status_label.configure(
            text=f"{name}: done ({done_count}/{total})" if ok else f"{name} failed: {message}"
        )

    def _on_uninstall_done(self, results):
        self._set_busy(False)
        all_leftovers, failures, warnings = [], [], []
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
            self._info_dialog(
                "Some items failed to uninstall",
                "\n".join(f"{a.name}: {msg}" for a, msg in failures),
            )
        if warnings:
            self._info_dialog(
                "Removed, with a warning",
                "\n".join(f"{a.name}: {msg}" for a, msg in warnings),
            )
        if all_leftovers:
            self._offer_leftover_cleanup(all_leftovers, app_freed)
        else:
            if app_freed:
                self._info_dialog(
                    "Uninstall complete", f"Freed {format_size(app_freed)} of disk space."
                )
            self.after(800, self.reload)

    def _offer_leftover_cleanup(self, paths, app_freed):
        """CLAUDE.md non-negotiable: leftovers are shown and opt-in, never
        deleted silently — and none start ticked."""
        c = self._colours()
        dialog = self._dialog("Leftover files found")
        body = ttk.Frame(dialog, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Left behind", style="Headline.TLabel").pack(anchor="w")
        ttk.Label(
            body, style="Muted.TLabel", wraplength=560, justify="left",
            text="The uninstallers didn't remove these. Delete them too? Only AppData "
            "and ProgramData were searched, and nothing goes unless you tick it.",
        ).pack(anchor="w", pady=(6, 12))

        # Packed before the list: a side="bottom" widget added after a
        # side="left" one lands in the right-hand strip, not along the bottom.
        chosen = {"paths": []}
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom", pady=(16, 0))

        list_frame = ttk.Frame(body, style="Panel.TFrame", padding=8)
        list_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(list_frame, height=220, width=560, highlightthickness=0,
                           background=c["panel"])
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, style="Panel.TFrame")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        checks = []
        for path in paths:
            variable = tk.BooleanVar(value=False)
            ttk.Checkbutton(
                inner, text=str(path), variable=variable, style="Panel.TCheckbutton"
            ).pack(anchor="w", pady=3)
            checks.append((variable, path))

        ttk.Button(
            buttons, text="Delete ticked", style="Accent.TButton",
            command=lambda: (
                chosen.update(paths=[p for v, p in checks if v.get()]), dialog.destroy()
            ),
        ).pack(side="right")
        ttk.Button(buttons, text="Keep them", command=dialog.destroy).pack(
            side="right", padx=(0, 8)
        )

        dialog.wait_window()
        if chosen["paths"]:
            self._run_leftover_cleanup_async(chosen["paths"], app_freed)
        else:
            if app_freed:
                self._info_dialog(
                    "Uninstall complete", f"Freed {format_size(app_freed)} of disk space."
                )
            self.reload()

    def _run_leftover_cleanup_async(self, paths, app_freed):
        self._set_busy(True)
        self.progress.configure(value=0)
        total = len(paths)

        def worker():
            freed_total = app_freed
            all_errors = []
            for i, path in enumerate(paths):
                self.after(0, self._on_item_start, f"Removing {path.name}…", i, total)
                freed, errors = clean_leftovers([path])
                freed_total += freed
                all_errors.extend(errors)
                self.after(0, self._on_item_done, path.name, not errors, "", i + 1, total)
            self.after(0, self._on_leftover_cleanup_done, freed_total, all_errors)

        threading.Thread(target=worker, daemon=True).start()

    def _on_leftover_cleanup_done(self, freed_bytes, errors):
        self._set_busy(False)
        self.after(800, self.reload)
        if errors:
            self._info_dialog(
                "Some leftovers couldn't be deleted",
                f"Freed {format_size(freed_bytes)}.\n\n"
                + "\n".join(f"{p}: {err}" for p, err in errors),
            )
        else:
            self._info_dialog(
                "Uninstall complete", f"Freed {format_size(freed_bytes)} of disk space."
            )

    # ---- dialogs ----

    def _dialog(self, title):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.configure(background=self._colours()["bg"])
        dialog.resizable(False, False)
        dialog.grab_set()  # modal, like GTK's modal=True
        return dialog

    def _info_dialog(self, title, text):
        dialog = self._dialog(title)
        body = ttk.Frame(dialog, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, style="Title.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(body, text=text, wraplength=520, justify="left").pack(anchor="w")
        ttk.Button(body, text="OK", style="Accent.TButton", command=dialog.destroy).pack(
            anchor="e", pady=(16, 0)
        )
        dialog.wait_window()


def main() -> int:
    if sys.platform == "win32":
        # Without this the shell treats us as generic "python.exe" and the
        # taskbar shows its icon, not ours — the same window-identity trap the
        # Linux build hit with the .desktop file's app-id. Set before any
        # window exists, or Windows has already made its mind up.
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_APP_ID)
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # or the UI renders blurry
        except (AttributeError, OSError):
            pass
    UninstallerWindow().mainloop()
    return 0
