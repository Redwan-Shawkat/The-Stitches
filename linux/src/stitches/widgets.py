"""What every page is built from: the page scaffold (title, subtitle, and the
dark action bar with its line loader), the checkbox table, Pango-markup
helpers for tags, and the confirm/info dialogs. All styling is the one CSS
block below; everything not styled here follows the system theme, so
dark mode keeps working the way it always has."""

import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from .models import Risk  # noqa: E402

ACCENT = "#4c5ce6"

# GTK themes paint gradients on buttons, rows and progress fills, so every
# override clears background-image as well as setting background-color.
CSS = b"""
.dock { background-color: #111217; border-radius: 18px; padding: 6px;
    box-shadow: 0 6px 20px alpha(black, 0.25); }
.dock button { background-color: transparent; background-image: none; border: none; box-shadow: none;
    border-radius: 12px; padding: 5px; text-shadow: none; }
.dock button:hover { background-color: #262833; }
.dock button:checked, .dock button.has-update { background-color: #4c5ce6; }
.dock button image { color: #c9cad3; }
.dock button:checked image, .dock button.has-update image { color: #ffffff; }
.dock separator { background-color: #2a2c38; min-width: 1px; margin: 8px 4px; }
.badge { background-color: #4c5ce6; color: #ffffff; border-radius: 9px; font-size: 9px; font-weight: 600;
    padding: 0 4px; }
.dock button:checked .badge { background-color: #ffffff; color: #4c5ce6; }

.page-title { font-size: 22px; font-weight: 600; }
.page-subtitle { opacity: 0.62; }
.card { background-color: @theme_base_color; border: 1px solid alpha(@theme_fg_color, 0.1);
    border-radius: 14px; }
.card treeview.view { background-color: transparent; }
.card treeview header button { background-color: transparent; background-image: none; border: none;
    box-shadow: none; padding: 4px 8px; }
.card treeview header button label { font-size: 11px; font-weight: 600; opacity: 0.55; }
.card treeview header button check { border-radius: 999px; }  /* round, like the row ticks under it */
.card list { background-color: transparent; }
.card-title { font-weight: 600; }
.console { background-color: #0d0e12; border-radius: 14px; }
.console .card-title { color: #9a9ca6; }
.console scrolledwindow, .console textview, .console textview text { background-color: transparent; }
.console textview text { color: #c9cad3; font-family: monospace; font-size: 11px; }
.dim { opacity: 0.6; }
.mono { font-family: monospace; font-size: 11px; }
.compact label { font-size: 12px; }
.compact .card-title { font-size: 11px; font-weight: 700; opacity: 0.7; }
.compact .note { font-size: 11px; opacity: 0.6; }
.group-icon { color: #7d8bff; }

.actionbar { background-color: #111217; border-radius: 14px; }
.actionbar label { color: #b9bbc6; }
.actionbar .line trough { min-height: 3px; background-color: #262833; background-image: none;
    border: none; border-radius: 2px; box-shadow: none; }
.actionbar .line progress { min-height: 3px; background-color: #7d8bff; background-image: none;
    border: none; border-radius: 2px; box-shadow: 0 0 10px #7d8bff; }
.actionbar .line.op-error progress { background-color: #ff6b5e; box-shadow: 0 0 10px #ff6b5e; }
.actionbar button { background-color: #262833; background-image: none; border: none; box-shadow: none;
    border-radius: 10px; padding: 7px 14px; text-shadow: none; }
.actionbar button label { color: #ffffff; }
.actionbar button:hover { background-color: #30323f; }
.actionbar button.suggested-action { background-color: #4c5ce6; }
.actionbar button.suggested-action:hover { background-color: #5b6af0; }
.actionbar button.destructive-action { background-color: #c62f28; }
.actionbar button.destructive-action:hover { background-color: #d63a33; }
.actionbar button:disabled { opacity: 0.45; }
.actionbar button image { color: #ffffff; }
.toast { box-shadow: 0 8px 28px alpha(black, 0.35); }

.os-switch { background-color: alpha(@theme_fg_color, 0.08); border-radius: 999px; padding: 3px; }
.os-switch button { background-color: transparent; background-image: none; border: none; box-shadow: none;
    border-radius: 999px; padding: 3px 14px; min-height: 0; text-shadow: none; }
.os-switch button:checked { background-color: #4c5ce6; box-shadow: 0 2px 8px alpha(#4c5ce6, 0.45); }
.os-switch button:checked label { color: #ffffff; font-weight: 600; }
.os-switch button:disabled label { opacity: 0.45; }

.row-title { font-weight: 600; }
levelbar.horizontal trough { min-height: 6px; border: none; border-radius: 3px; background-color: alpha(@theme_fg_color, 0.1); }
levelbar block.filled { border: none; border-radius: 3px; background-image: none; background-color: #4c5ce6; }
levelbar.warning block.filled { background-color: #d99a00; }
levelbar.critical block.filled { background-color: #c62f28; }
levelbar block.empty { background-color: transparent; border: none; }
"""

THEMES = ("Light", "Dark", "AMOLED", "Glass")
# Loaded on top of CSS for the two window themes that aren't just the system
# theme's light/dark variant. Both sit on the dark variant, for its text colours.
THEME_CSS = {
    "AMOLED": b"""
window.background { background-color: #000000; }
.card { background-color: #070707; border-color: #1b1b1b; }
.actionbar { background-color: #0a0a0a; border: 1px solid #1c1c1c; }
""",
    # GTK3 can't blur what's behind a window, so glass here is translucency
    # plus light edges; it needs a compositor (every modern desktop has one).
    "Glass": b"""
window.background { background-color: rgba(22, 24, 36, 0.74); }
.card { background-color: rgba(255, 255, 255, 0.06); border-color: rgba(255, 255, 255, 0.14); }
.actionbar { background-color: rgba(8, 9, 14, 0.70); border: 1px solid rgba(255, 255, 255, 0.12); }
viewport, .card list, .card row { background-color: transparent; }
""",
}
# The dock picks its own theme from the same four, on top of the window's;
# Dark is the one in CSS above.
DOCK_CSS = {
    "Light": b"""
.dock { background-color: #ffffff; border: 1px solid #dfe1ea; box-shadow: 0 6px 20px alpha(black, 0.12); }
.dock button:hover { background-color: #eceef5; }
.dock button image { color: #4a4d5a; }
.dock separator { background-color: #dfe1ea; }
""",
    "AMOLED": b"""
.dock { background-color: #0a0a0a; border: 1px solid #1c1c1c; }
.dock button:hover { background-color: #161616; }
""",
    "Glass": b"""
.dock { background-color: rgba(8, 9, 14, 0.55); border: 1px solid rgba(255, 255, 255, 0.14); }
.dock button:hover { background-color: rgba(255, 255, 255, 0.10); }
""",
}

RISK_TAG = {
    Risk.SAFE: ("#17663a", "#e6f5ec"),
    Risk.CAUTION: ("#7a4d00", "#fff4dc"),
    Risk.CRITICAL: ("#a3231a", "#fde9e7"),
}
# Health words (Home, Diagnose) in the same three colours, plus a neutral one.
STATUS_TAG = {
    "Good": RISK_TAG[Risk.SAFE], "OK": RISK_TAG[Risk.SAFE],
    "Warning": RISK_TAG[Risk.CAUTION],
    "Critical": RISK_TAG[Risk.CRITICAL], "Problem": RISK_TAG[Risk.CRITICAL],
    "Info": ("#3441b0", "#eef1ff"), "Not checked": ("#5a5c66", "#ececef"),
}


def esc(text) -> str:
    return GLib.markup_escape_text(str(text))


def tag(text: str, colors: tuple[str, str]) -> str:
    """A coloured label inside a table cell (Pango can't round the corners)."""
    fg, bg = colors
    return f'<span foreground="{fg}" background="{bg}" size="small" weight="500"> {esc(text)} </span>'


def two_lines(title: str, detail: str = "") -> str:
    return f'{esc(title)}\n<span size="small" alpha="60%">{esc(detail)}</span>' if detail else esc(title)


def strong(text: str) -> str:
    """Bold white, for the name in an action bar status line."""
    return f'<span foreground="#ffffff" weight="600">{esc(text)}</span>'


def arrow(current: str, new: str) -> str:
    """New version on top, the installed one under it: apt versions run long,
    and side by side they'd crowd out the app names."""
    return f'<b>{esc(new)}</b>\n<span size="small" alpha="60%">from {esc(current)}</span>' if current else f"<b>{esc(new)}</b>"


def make_table(store, columns, on_toggle=None, toggle_col=None, enabled_col=None, on_toggle_all=None):
    """A table in a rounded card. `columns` is [(title, store column, expand)],
    where expand is False, True (takes spare width, ellipsized) or "wrap"
    (takes spare width, wraps instead). Every text cell renders Pango markup,
    so it can hold a tag or a dimmed second line. With `toggle_col`, the first
    column is a checkbox that calls on_toggle(path), with one more in its
    header that calls on_toggle_all(checked) (keep it in step with
    show_select_all); `enabled_col` greys out rows with nothing to do.
    Returns (card, tree, header checkbox or None)."""
    tree, select_all = Gtk.TreeView(model=store), None
    if toggle_col is not None:
        toggle = Gtk.CellRendererToggle(xpad=10)
        toggle.connect("toggled", lambda _r, path: on_toggle(path))
        attrs = {"active": toggle_col}
        if enabled_col is not None:
            attrs.update(activatable=enabled_col, sensitive=enabled_col)
        column = Gtk.TreeViewColumn("", toggle, **attrs)
        select_all = Gtk.CheckButton(tooltip_text="Select all")
        select_all.show()
        column.set_widget(select_all)
        column.set_clickable(True)  # the header button takes the click, not the checkbox inside it
        column.connect("clicked", lambda _c: on_toggle_all(not select_all.get_active()))
        tree.append_column(column)
    for title, col, expand in columns:
        cell = Gtk.CellRendererText(ypad=8, xpad=8)
        if expand == "wrap":
            cell.set_property("wrap-mode", Pango.WrapMode.WORD)
            cell.set_property("wrap-width", 210)
        elif expand:  # ellipsized, but never squeezed below a readable name
            cell.set_property("ellipsize", Pango.EllipsizeMode.END)
            cell.set_property("width-chars", 22)
        column = Gtk.TreeViewColumn(title, cell, markup=col)
        column.set_expand(bool(expand))
        column.set_resizable(True)
        tree.append_column(column)
    return card(scrolled(tree)), tree, select_all


def show_select_all(check, selected: int, selectable: int):
    """The header checkbox: ticked when every row that can be is, a dash when
    only some are."""
    check.set_active(selectable > 0 and selected == selectable)
    check.set_inconsistent(0 < selected < selectable)


def os_switch(this_os: str, other_os: str):
    """A Linux | Windows pill, lit on the OS Stitches is running on. The other
    side is locked: each OS's apps are installed by Stitches on that OS."""
    box = Gtk.Box(valign=Gtk.Align.CENTER)
    box.get_style_context().add_class("os-switch")
    lit = Gtk.RadioButton(label=this_os, draw_indicator=False, tooltip_text=f"Apps for {this_os}")
    other = Gtk.RadioButton(label=other_os, group=lit, draw_indicator=False, sensitive=False,
                            tooltip_text=f"Open Stitches on {other_os} for its apps")
    for button in sorted((lit, other), key=lambda b: b.get_label() != "Linux"):  # Linux always on the left
        box.pack_start(button, False, False, 0)
    return box


def scrolled(child):
    # Scrolls sideways too, so a wide table never forces the window wider
    # than a small laptop screen.
    box = Gtk.ScrolledWindow()
    box.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    box.add(child)
    return box


def icon_button(icon: str, tooltip: str, callback):
    """Icon only; its name shows on hover."""
    button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
    button.set_tooltip_text(tooltip)
    button.set_valign(Gtk.Align.CENTER)
    button.connect("clicked", lambda _b: callback())
    return button


def run_async(work, done, failed):
    """work() on a thread, then done(result) — or failed(exception) — back on
    the GTK thread. Widgets are never touched off it; progress inside work()
    goes through GLib.idle_add too."""

    def worker():
        try:
            result = work()
        except Exception as exc:  # a bug here mustn't leave the UI locked forever
            GLib.idle_add(failed, exc)
            return
        GLib.idle_add(done, result)

    threading.Thread(target=worker, daemon=True).start()


def card(child, style="card"):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.get_style_context().add_class(style)
    box.set_border_width(6)  # keeps the child inside the rounded corners
    box.pack_start(child, True, True, 0)
    return box


def label(text="", *styles, xalign=0.0, **props):
    widget = Gtk.Label(label=text, xalign=xalign, **props)
    for style in styles:
        widget.get_style_context().add_class(style)
    return widget


class ActionBar(Gtk.Box):
    """The floating dark bar at the bottom of every page: a thin line loader
    along its top edge, a status line, and the page's buttons."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.get_style_context().add_class("actionbar")
        self.line = Gtk.ProgressBar(pulse_step=0.08, margin_start=14, margin_end=14)
        self.line.get_style_context().add_class("line")
        self.line.set_no_show_all(True)
        self.pack_start(self.line, False, False, 0)
        row = Gtk.Box(spacing=8, margin=8, margin_start=16)
        self.status = label(use_markup=True, ellipsize=Pango.EllipsizeMode.END)
        row.pack_start(self.status, True, True, 0)
        self.buttons = Gtk.Box(spacing=8)
        row.pack_end(self.buttons, False, False, 0)
        self.pack_start(row, False, False, 0)
        self._tick = None

    def add_button(self, text, callback, style=None):
        button = Gtk.Button(label=text)
        button.connect("clicked", lambda _b: callback())
        if style:
            button.get_style_context().add_class(style)
        self.buttons.pack_start(button, False, False, 0)
        return button

    def add_icon_button(self, icon, tooltip, callback):
        button = icon_button(icon, tooltip, callback)
        self.buttons.pack_start(button, False, False, 0)
        return button

    def say(self, markup: str):
        self.status.set_markup(markup)

    def pulse(self):
        """Indeterminate: the line sweeps back and forth while scanning."""
        self._start(0.0)
        self._tick = GLib.timeout_add(80, lambda: (self.line.pulse(), True)[1])

    def slice(self, start: float, end: float):
        """Crawl toward `end` while a blocking call with no progress of its
        own runs (a pkexec'd apt, a file delete). It stops at 92% of the
        slice; settle() snaps the rest, so it never looks stuck short."""
        self._start(start)
        step, ceiling = (end - start) * 0.06, start + (end - start) * 0.92

        def tick():
            self.line.set_fraction(min(ceiling, self.line.get_fraction() + step))
            return True

        self._tick = GLib.timeout_add(60, tick)

    def countdown(self, seconds: float, then):
        """The line runs down from full over `seconds`, then calls then()."""
        self._start(1.0)
        start = GLib.get_monotonic_time()

        def tick():
            left = 1 - (GLib.get_monotonic_time() - start) / (seconds * 1e6)
            self.line.set_fraction(max(left, 0))
            if left > 0:
                return True
            self._tick = None
            then()
            return False

        self._tick = GLib.timeout_add(30, tick)

    def settle(self, fraction: float, ok: bool = True):
        self._stop()
        self.line.show()
        self.line.set_fraction(fraction)
        if not ok:
            self.line.get_style_context().add_class("op-error")

    def done(self):
        self._stop()
        self.line.hide()

    def _start(self, fraction):
        self._stop()
        self.line.get_style_context().remove_class("op-error")
        self.line.set_fraction(fraction)
        self.line.show()

    def _stop(self):
        if self._tick:
            GLib.source_remove(self._tick)
            self._tick = None


class Page(Gtk.Box):
    """Title and subtitle on top, the page's own content in `body`, the
    action bar underneath. Header controls go into `header` with pack_end."""

    title = ""
    icon = ""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.count = 0  # shown as a badge on its dock icon
        self.on_count = None  # set by the window
        self.header = Gtk.Box(spacing=8, margin_top=16, margin_bottom=12, margin_start=28, margin_end=28)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        titles.pack_start(label(self.title, "page-title"), False, False, 0)
        self.subtitle = label("", "page-subtitle", ellipsize=Pango.EllipsizeMode.END)
        titles.pack_start(self.subtitle, False, False, 0)
        self.header.pack_start(titles, True, True, 0)
        self.pack_start(self.header, False, False, 0)
        self.body = Gtk.Box(spacing=16, margin_start=28, margin_end=28)
        self.pack_start(self.body, True, True, 0)
        self.bar = ActionBar()
        self.bar.set_margin_top(12)
        self.bar.set_margin_bottom(10)
        self.bar.set_margin_start(24)
        self.bar.set_margin_end(24)
        self.pack_start(self.bar, False, False, 0)

    def header_button(self, icon, tooltip, callback):
        button = icon_button(icon, tooltip, callback)
        self.header.pack_end(button, False, False, 0)
        return button

    def set_count(self, n: int):
        self.count = n
        if self.on_count:
            self.on_count()

    def set_busy(self, busy: bool):
        """Only this page locks while it works: the dock stays live, so an
        update can run while you look at something else."""
        for part in (self.header, self.body, self.bar.buttons):
            part.set_sensitive(not busy)

    def run_async(self, work, done):
        run_async(work, done, self._failed)

    def _failed(self, exc):
        self.bar.done()
        self.bar.say(f"Something went wrong: {esc(exc)}")
        self.set_busy(False)

    def window(self):
        return self.get_toplevel()


class Terminal(Gtk.Box):
    """The dark panel that shows each command and what it prints, as it
    prints it. A line starting "▶ " is a heading, "$ " a command; one
    starting with a key of `colors` (and a colon) is shown in that colour."""

    def __init__(self, placeholder: str, colors: dict | None = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.colors = colors or {}
        self.view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 left_margin=4, right_margin=4)
        self.out = self.view.get_buffer()
        self.out.create_tag("head", weight=Pango.Weight.BOLD, foreground="#ffffff", pixels_above_lines=10)
        self.out.create_tag("cmd", foreground="#7d8bff")
        for key, color in self.colors.items():
            self.out.create_tag(key, foreground=color)
        self.out_end = self.out.create_mark(None, self.out.get_end_iter(), False)
        self.out.set_text(placeholder)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        box.pack_start(label("Terminal", "card-title"), False, False, 0)
        box.pack_start(scrolled(self.view), True, True, 0)
        self.pack_start(card(box, "console"), True, True, 0)

    def clear(self):
        self.out.set_text("")

    def log(self, line: str):
        """From a worker thread: onto the panel, on the GTK thread."""
        GLib.idle_add(self.print, line)

    def print(self, line: str):
        key = line.partition(":")[0]
        style = "head" if line.startswith("▶") else "cmd" if line.startswith("$ ") else \
            key if key in self.colors else None
        end = self.out.get_end_iter()
        if style:
            self.out.insert_with_tags_by_name(end, f"\n{line}", style)
        else:
            self.out.insert(end, f"\n{line}")
        self.view.scroll_mark_onscreen(self.out_end)


def confirm(parent, title: str, lines: list[str], action: str, critical_ack: str = "") -> bool:
    """The confirmation every destructive action goes through (CLAUDE.md
    non-negotiable). `critical_ack` adds a checkbox that has to be ticked
    before the action button enables."""
    dialog = Gtk.MessageDialog(
        transient_for=parent, modal=True, buttons=Gtk.ButtonsType.NONE, text=title,
        message_type=Gtk.MessageType.WARNING if critical_ack else Gtk.MessageType.QUESTION,
    )
    dialog.format_secondary_text("\n".join(lines))
    dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, action, Gtk.ResponseType.OK)
    ok_button = dialog.get_widget_for_response(Gtk.ResponseType.OK)
    ok_button.get_style_context().add_class("destructive-action")
    if critical_ack:
        check = Gtk.CheckButton(label=critical_ack)
        dialog.get_content_area().pack_start(check, False, False, 6)
        check.show()
        ok_button.set_sensitive(False)
        check.connect("toggled", lambda c: ok_button.set_sensitive(c.get_active()))
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.OK


def info(parent, title: str, text: str):
    dialog = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=Gtk.MessageType.INFO,
                               buttons=Gtk.ButtonsType.OK, text=title)
    dialog.format_secondary_text(text)
    dialog.run()
    dialog.destroy()
