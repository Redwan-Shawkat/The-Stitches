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
_PALETTES = {
    False: {  # light
        "bg": "#f3f4f6", "surface": "#ffffff", "fg": "#1f2937", "muted": "#4b5563",
        "border": "#c9ccd1", "select": "#dbeafe", "heading": "#e5e7eb",
        "safe": "#2e7d32", "caution": "#a16207", "critical": "#c62828",
    },
    True: {  # dark
        "bg": "#1f2937", "surface": "#111827", "fg": "#e5e7eb", "muted": "#9ca3af",
        "border": "#374151", "select": "#374151", "heading": "#374151",
        "safe": "#4ade80", "caution": "#fbbf24", "critical": "#f87171",
    },
}

(COL_SEL, COL_NAME, COL_SOURCE, COL_VERSION, COL_SIZE, COL_RISK) = (
    "sel", "name", "source", "version", "size", "risk",
)
_COLUMNS = (
    (COL_SEL, "", 36, "center"),
    (COL_NAME, "Name", 300, "w"),
    (COL_SOURCE, "Installed via", 150, "w"),
    (COL_VERSION, "Version", 120, "w"),
    (COL_SIZE, "Size", 90, "e"),
    (COL_RISK, "Risk to remove", 120, "w"),
)
_SOURCES = (Source.INSTALLER.value, Source.STORE.value, Source.CHOCOLATEY.value, Source.SCOOP.value)
_CHECKED, _UNCHECKED = "☑", "☐"


class _Tooltip:
    """The risk reason on hover — ttk has no tooltip, and the reason is the
    whole point of the risk column, so it gets the ~20 lines."""

    def __init__(self, widget, text_for_row):
        self.widget = widget
        self.text_for_row = text_for_row
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
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{event.x_root + 16}+{event.y_root + 20}")
        tk.Label(
            self.window, text=text, justify="left", wraplength=420,
            background="#ffffe0", foreground="#1f2937", relief="solid", borderwidth=1,
            padx=6, pady=4,
        ).pack()

    def _hide(self):
        if self.window:
            self.window.destroy()
            self.window = None


class UninstallerWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("The Uninstaller")
        self.geometry("900x560")
        self.minsize(720, 420)
        try:
            self.iconbitmap(default=_ICON_PATH)
        except tk.TclError:
            pass  # no .ico (running from a checkout on another OS) — not fatal

        self.apps: list = []
        self.selected: set[int] = set()
        self.visible_rows: list[int] = []
        self.search_text = ""
        self.source_filter = "All sources"
        self._dark = False
        self._placeholder_active = True
        self._progress_animating = False
        self._progress_job = None

        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self._build_ui()
        self._apply_palette()
        self.reload()

    # ---- layout ----

    def _build_ui(self):
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)
        root.rowconfigure(1, weight=1)
        root.columnconfigure(0, weight=1)
        self._build_toolbar(root).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._build_list(root).grid(row=1, column=0, sticky="nsew")
        self._build_progress(root).grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self._build_actionbar(root).grid(row=3, column=0, sticky="ew", pady=(6, 0))
        # Traced only once everything exists: setting the placeholder text
        # writes the variable, and the handler refilters the (not yet built)
        # tree.
        self.search_var.trace_add("write", lambda *_: self._on_search_changed())

    def _build_toolbar(self, parent):
        bar = ttk.Frame(parent)
        bar.columnconfigure(0, weight=1)

        self.search_var = tk.StringVar()
        search = ttk.Entry(bar, textvariable=self.search_var)
        search.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._placeholder(search, "Search installed software…")

        self.source_combo = ttk.Combobox(
            bar, values=("All sources", *_SOURCES), state="readonly", width=20
        )
        self.source_combo.current(0)
        self.source_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_source_changed())
        self.source_combo.grid(row=0, column=1, padx=(0, 6))

        ttk.Button(bar, text="Refresh", command=self.reload).grid(row=0, column=2, padx=(0, 6))
        self.theme_button = ttk.Button(bar, text="🌙", width=3, command=self._on_theme_toggled)
        self.theme_button.grid(row=0, column=3)
        return bar

    def _placeholder(self, entry, text):
        """Tkinter entries have no placeholder property; this is the whole
        feature in six lines rather than a widget subclass."""
        self._placeholder_active = True
        entry.insert(0, text)
        entry.configure(foreground=_PALETTES[self._dark]["muted"])

        def focus_in(_event):
            if self._placeholder_active:
                entry.delete(0, "end")
                entry.configure(foreground=_PALETTES[self._dark]["fg"])
                self._placeholder_active = False

        def focus_out(_event):
            if not entry.get():
                self._placeholder_active = True
                entry.insert(0, text)
                entry.configure(foreground=_PALETTES[self._dark]["muted"])

        entry.bind("<FocusIn>", focus_in)
        entry.bind("<FocusOut>", focus_out)

    def _build_list(self, parent):
        frame = ttk.Frame(parent)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            frame, columns=[c[0] for c in _COLUMNS], show="headings", selectmode="none"
        )
        for name, heading, width, anchor in _COLUMNS:
            self.tree.heading(name, text=heading)
            self.tree.column(name, width=width, anchor=anchor, stretch=(name == COL_NAME))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Button-1>", self._on_tree_click)
        _Tooltip(self.tree, self._reason_for_row)
        return frame

    def _build_progress(self, parent):
        # 0-100 rather than 0-1: indeterminate mode steps by 1.0 per tick, so
        # a maximum of 1.0 would bounce a whole cycle every tick.
        self.progress = ttk.Progressbar(parent, maximum=100)
        return self.progress

    def _build_actionbar(self, parent):
        bar = ttk.Frame(parent)
        bar.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(bar, text="")
        self.status_label.grid(row=0, column=0, sticky="w")
        ttk.Button(bar, text="Select All (non-critical)", command=self._on_select_all).grid(
            row=0, column=1, padx=(6, 0)
        )
        ttk.Button(bar, text="Select None", command=self._on_select_none).grid(
            row=0, column=2, padx=(6, 0)
        )
        ttk.Button(
            bar, text="Uninstall Selected", style="Destructive.TButton",
            command=self._on_uninstall_clicked,
        ).grid(row=0, column=3, padx=(6, 0))
        return bar

    # ---- theming ----

    def _apply_palette(self):
        c = _PALETTES[self._dark]
        self.configure(background=c["bg"])
        self.style.configure(".", background=c["bg"], foreground=c["fg"], bordercolor=c["border"])
        self.style.configure("TFrame", background=c["bg"])
        self.style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        self.style.configure("TButton", background=c["heading"], foreground=c["fg"])
        self.style.map("TButton", background=[("active", c["select"])])
        self.style.configure(
            "Destructive.TButton", background=c["critical"], foreground="#ffffff"
        )
        self.style.map("Destructive.TButton", background=[("active", c["critical"])])
        for widget in ("TEntry", "TCombobox"):
            self.style.configure(
                widget, fieldbackground=c["surface"], background=c["surface"],
                foreground=c["fg"], insertcolor=c["fg"], arrowcolor=c["fg"],
            )
        self.style.map(
            "TCombobox", fieldbackground=[("readonly", c["surface"])],
            selectbackground=[("readonly", c["surface"])],
            selectforeground=[("readonly", c["fg"])],
        )
        self.style.configure(
            "Treeview", background=c["surface"], fieldbackground=c["surface"],
            foreground=c["fg"], rowheight=24,
        )
        self.style.configure(
            "Treeview.Heading", background=c["heading"], foreground=c["fg"], relief="flat"
        )
        self.style.map("Treeview.Heading", background=[("active", c["select"])])
        for style_name, colour in (
            ("TProgressbar", c["select"]),
            ("Success.Horizontal.TProgressbar", c["safe"]),
            ("Error.Horizontal.TProgressbar", c["critical"]),
        ):
            self.style.configure(
                style_name, background=colour, troughcolor=c["bg"], bordercolor=c["border"]
            )
        self.tree.tag_configure("risk_safe", foreground=c["safe"])
        self.tree.tag_configure("risk_caution", foreground=c["caution"])
        self.tree.tag_configure("risk_critical", foreground=c["critical"])

    def _on_theme_toggled(self):
        self._dark = not self._dark
        self.theme_button.configure(text="☀" if self._dark else "🌙")
        self._apply_palette()

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
            self.tree.insert(
                "", "end", iid=str(index),
                values=(
                    _CHECKED if index in self.selected else _UNCHECKED,
                    app.name, app.source.value, app.version, app.size_human, app.risk.value,
                ),
                tags=(f"risk_{app.risk.name.lower()}",),
            )

    def _reason_for_row(self, row_id):
        if not row_id:
            return ""
        return self.apps[int(row_id)].risk_reason

    def _set_checked(self, index, checked):
        self.selected.add(index) if checked else self.selected.discard(index)
        if self.tree.exists(str(index)):
            self.tree.set(str(index), COL_SEL, _CHECKED if checked else _UNCHECKED)

    def _on_tree_click(self, event):
        # Only the checkbox column toggles: the rest of the row is hovered to
        # read the risk reason, and hovering must not select anything.
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        row = self.tree.identify_row(event.y)
        if not row:
            return
        index = int(row)
        self._set_checked(index, index not in self.selected)

    def _on_search_changed(self):
        self.search_text = "" if self._placeholder_active else self.search_var.get()
        self._refresh_rows()

    def _on_source_changed(self):
        self.source_filter = self.source_combo.get()
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
        self.apps = apps
        self.selected.clear()
        self._refresh_rows()
        self.status_label.configure(text=f"{len(apps)} item(s) found")
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
            self._info_dialog("Nothing selected", "Check one or more items first.")
            return
        if self._confirm(selected):
            self._run_uninstall_async(selected)

    def _confirm(self, apps) -> bool:
        """CLAUDE.md non-negotiable: nothing is removed without this, and
        anything Critical needs the extra acknowledgement before OK unlocks."""
        critical = [a for a in apps if a.risk == Risk.CRITICAL]
        dialog = self._dialog(f"Uninstall {len(apps)} item(s)?")
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body, text=f"Uninstall {len(apps)} item(s)?", font=("", 11, "bold")
        ).pack(anchor="w", pady=(0, 8))
        listing = tk.Text(body, height=min(12, max(3, len(apps))), width=64, wrap="none")
        listing.insert(
            "1.0", "\n".join(f"• {a.name} — {a.source.value} — {a.risk.value}" for a in apps)
        )
        listing.configure(state="disabled", background=_PALETTES[self._dark]["surface"],
                          foreground=_PALETTES[self._dark]["fg"], relief="flat")
        listing.pack(fill="both", expand=True, pady=(0, 8))

        result = {"ok": False}
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom")
        confirm_button = ttk.Button(
            buttons, text="Uninstall", style="Destructive.TButton",
            command=lambda: (result.update(ok=True), dialog.destroy()),
        )
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
        confirm_button.pack(side="right", padx=(0, 6))

        if critical:
            acknowledged = tk.BooleanVar(value=False)
            confirm_button.state(["disabled"])
            ttk.Checkbutton(
                body, variable=acknowledged,
                text="I understand this includes system-critical software",
                command=lambda: confirm_button.state(
                    ["!disabled" if acknowledged.get() else "disabled"]
                ),
            ).pack(anchor="w", side="bottom", pady=(0, 8))

        dialog.wait_window()
        return result["ok"]

    def _run_uninstall_async(self, apps):
        self._set_busy(True)
        self.progress.configure(value=0)
        total = len(apps)

        def worker():
            results = []
            for i, app in enumerate(apps):
                self.after(0, self._on_item_start, f"Uninstalling {app.name}…", i, total)
                ok, message, leftovers = uninstall(app)
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
        deleted silently."""
        dialog = self._dialog("Leftover files found")
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body, text="These weren't removed by the uninstaller. Delete them too?"
        ).pack(anchor="w", pady=(0, 8))

        # Packed before the list: a side="bottom" widget added after a
        # side="left" one lands in the right-hand strip, not along the bottom.
        chosen = {"paths": []}
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom", pady=(8, 0))

        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(list_frame, height=220, highlightthickness=0,
                           background=_PALETTES[self._dark]["surface"])
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        checks = []
        for path in paths:
            variable = tk.BooleanVar(value=True)
            ttk.Checkbutton(inner, text=str(path), variable=variable).pack(anchor="w")
            checks.append((variable, path))

        ttk.Button(buttons, text="Skip", command=dialog.destroy).pack(side="right")
        ttk.Button(
            buttons, text="Delete Selected", style="Destructive.TButton",
            command=lambda: (
                chosen.update(paths=[p for v, p in checks if v.get()]), dialog.destroy()
            ),
        ).pack(side="right", padx=(0, 6))

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
        dialog.configure(background=_PALETTES[self._dark]["bg"])
        dialog.resizable(False, False)
        dialog.grab_set()  # modal, like GTK's modal=True
        return dialog

    def _info_dialog(self, title, text):
        dialog = self._dialog(title)
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, font=("", 11, "bold")).pack(anchor="w", pady=(0, 6))
        ttk.Label(body, text=text, wraplength=520, justify="left").pack(anchor="w")
        ttk.Button(body, text="OK", command=dialog.destroy).pack(anchor="e", pady=(12, 0))
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
