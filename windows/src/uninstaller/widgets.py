"""What every page is built from, as widgets.py is on the Linux build: the
four palettes and the walk that applies one, the pictures Tk can't draw
itself (round ticks, icons, round corners), the page scaffold with its dark
action bar and line loader, the ticked table, header pills, tooltips, and
the dialogs.

Tk has no CSS. Instead each widget may carry `roles`, the palette colours it
takes (bg, fg, border); a widget without them takes its parent's, and
set_theme() walks the tree once. Widgets drawn as pictures have a
repaint(outside, bg, fg) that the walk calls instead, and whole pages that
draw on a canvas register with on_theme().

Tk draws neither round corners nor smooth edges, so those are pictures:
shapes on a 16-unit grid, like a symbolic icon, sampled 4×4 per pixel into
a PhotoImage over the colour behind them. Each shape's coverage is worked
out once per size; a theme change only recolours it.
"""

import math
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .models import Risk

ACCENT = "#4c5ce6"
LINE, LINE_ERROR = "#7d8bff", "#ff6b5e"
WARNING_FILL, CRITICAL_FILL = "#d99a00", "#c62f28"
# The action bar and the dock are dark in every theme, as on Linux.
_DARK_PARTS = dict(bar="#111217", bar_border=None, bar_text="#b9bbc6", dock="#111217", dock_hover="#262833",
                   dock_icon="#c9cad3", dock_separator="#2a2c38")
THEMES = {
    "Light": dict(window="#f4f5f8", card="#ffffff", border="#e2e3e8", fg="#1f2024", dim="#6b6d78",
                  hover="#f2f3f7", tick="#8e909c", **_DARK_PARTS),
    "Dark": dict(window="#17181d", card="#202128", border="#2e2f36", fg="#e6e7eb", dim="#9a9ca6",
                 hover="#292a32", tick="#8e909c", **_DARK_PARTS),
    "AMOLED": dict(window="#000000", card="#070707", border="#1b1b1b", fg="#e6e7eb", dim="#8e909a",
                   hover="#141414", tick="#6e707a", bar="#0a0a0a", bar_border="#1c1c1c", bar_text="#b9bbc6",
                   dock="#0a0a0a", dock_hover="#161616", dock_icon="#c9cad3", dock_separator="#1c1c1c"),
    # Tk can't make only the background see-through, so Glass is the whole
    # window at 90% (gui.py), over colours that still read well through it.
    "Glass": dict(window="#161824", card="#1f2231", border="#363a4e", fg="#eceef4", dim="#a3a6b4",
                  hover="#2a2d3e", tick="#8e909c", bar="#0b0c13", bar_border="#2b2e3d", bar_text="#b9bbc6",
                  dock="#0b0c13", dock_hover="#23263a", dock_icon="#c9cad3", dock_separator="#2b2e3d"),
}
THEME = dict(THEMES["Dark"])  # the palette in use, replaced in place by set_theme(); a real one
# from the start, because a page can draw before the window applies the chosen theme

RISK_TAG = {  # (text, background), the Linux build's
    Risk.SAFE: ("#17663a", "#e6f5ec"),
    Risk.CAUTION: ("#7a4d00", "#fff4dc"),
    Risk.CRITICAL: ("#a3231a", "#fde9e7"),
}
STATUS_TAG = {"Good": RISK_TAG[Risk.SAFE], "Warning": RISK_TAG[Risk.CAUTION],
              "Critical": RISK_TAG[Risk.CRITICAL], "Info": ("#3441b0", "#eef1ff")}

FONTS = {}
_scale = 1.0
_on_theme = []
_calls = queue.Queue()  # (function, args) from worker threads, run on Tk's


def px(n: float) -> int:
    """Linux's sizes are pixels at 96 DPI; Windows at 150% wants half as many again."""
    return round(n * _scale)


def setup(root):
    """Scale, fonts and the thin scrollbar, once the Tk root exists."""
    global _scale
    _scale = root.winfo_fpixels("1i") / 96
    base = tkfont.nametofont("TkDefaultFont")
    base.configure(size=10)
    tkfont.nametofont("TkTextFont").configure(size=10)
    family = base.actual("family")
    FONTS.update(base=base, bold=tkfont.Font(root=root, family=family, size=10, weight="bold"),
                 title=tkfont.Font(root=root, family=family, size=16, weight="bold"),
                 heading=tkfont.Font(root=root, family=family, size=12, weight="bold"),
                 small=tkfont.Font(root=root, family=family, size=8),
                 caps=tkfont.Font(root=root, family=family, size=8, weight="bold"))
    style = ttk.Style(root)
    style.theme_use("clam")  # the one built-in ttk theme that takes the colours it's given
    style.layout("Thin.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    _drain(root)


def later(function, *args):
    """Run function(*args) on Tk's thread: what a worker does instead of
    touching a widget. Not Tk's own after(), which from another thread needs
    a threaded Tcl and a running mainloop, and otherwise blocks for good."""
    _calls.put((function, args))


def _drain(root):
    root.after(30, _drain, root)  # first, so one failing call can't stop the rest for good
    while not _calls.empty():
        function, args = _calls.get()
        function(*args)


def role(widget, **roles):
    """Which palette colours `widget` takes: bg, fg, border (THEMES keys), or fixed=True for none."""
    widget.roles = roles
    return widget


def on_theme(callback):
    _on_theme.append(callback)


def set_theme(root, name: str):
    THEME.clear()
    THEME.update(THEMES[name])
    ttk.Style(root).configure("Thin.Vertical.TScrollbar", troughcolor=THEME["card"], bordercolor=THEME["card"],
                              background=mix(THEME["card"], THEME["dim"], 0.45),
                              lightcolor=mix(THEME["card"], THEME["dim"], 0.45),
                              darkcolor=mix(THEME["card"], THEME["dim"], 0.45),
                              arrowsize=px(9), gripcount=0, gripsize=0)  # no grip: Tk 8.6 counts, 9 sizes
    recolour(root)
    for callback in _on_theme:
        callback()


def recolour(widget, bg=None, fg=None):
    """Give `widget` and everything in it the colours its roles ask for."""
    roles = getattr(widget, "roles", {})
    if roles.get("fixed"):
        return
    outside = bg or THEME["window"]
    bg, fg = THEME.get(roles.get("bg"), outside), THEME.get(roles.get("fg"), fg or THEME["fg"])
    if hasattr(widget, "repaint"):
        bg = widget.repaint(outside, bg, fg) or bg
    else:
        options = widget.keys()
        widget.configure(**{o: v for o, v in (("background", bg), ("foreground", fg), ("insertbackground", fg))
                            if o in options})
    for child in widget.winfo_children():
        recolour(child, bg, fg)


def mix(a: str, b: str, t: float) -> str:
    """The colour `t` of the way from a to b."""
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(_rgb(a), _rgb(b)))


def _rgb(colour: str) -> tuple:
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


# ---- pictures ----


def _disc(cx, cy, r):
    return lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _ring(cx, cy, r, width):
    return lambda x, y: (r - width) ** 2 <= (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _line(ax, ay, bx, by, width):
    """A stroke with round ends."""
    dx, dy, reach = bx - ax, by - ay, width * width / 4
    length = dx * dx + dy * dy or 1e-9

    def inside(x, y):
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length))
        return (x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2 <= reach

    return inside


def _box(x0, y0, x1, y1, r):
    """A rectangle with round corners."""

    def inside(x, y):
        qx, qy = max(x0 + r - x, x - x1 + r, 0), max(y0 + r - y, y - y1 + r, 0)
        return x0 <= x <= x1 and y0 <= y <= y1 and qx * qx + qy * qy <= r * r

    return inside


def _triangle(a, b, c):
    def side(x, y, p, q):
        return (q[0] - p[0]) * (y - p[1]) - (q[1] - p[1]) * (x - p[0])

    def inside(x, y):
        s = side(x, y, a, b), side(x, y, b, c), side(x, y, c, a)
        return min(s) >= 0 or max(s) <= 0

    return inside


def _any(*shapes):
    return lambda x, y: any(s(x, y) for s in shapes)


def _cut(shape, *holes):
    return lambda x, y: shape(x, y) and not any(h(x, y) for h in holes)


SHAPES = {
    # Round ticks, as the Linux build's theme draws them.
    "tick_ring": _ring(8, 8, 7.3, 1.3),
    "tick_disc": _disc(8, 8, 7.6),
    "check": _any(_line(4.6, 8.3, 7.1, 10.7, 1.7), _line(7.1, 10.7, 11.4, 5.7, 1.7)),
    "dash": _line(4.8, 8, 11.2, 8, 1.7),
    # Backgrounds: a button, and a whole disc for a panel's four corners.
    "button": _box(0, 0, 16, 16, 5.3),
    "disc": _disc(8, 8, 8),
    # Icons. Uninstall is the Linux build's own: apps, with one taken out.
    "uninstall": _any(_box(1, 1, 7, 7, 1.5), _box(1, 9, 7, 15, 1.5), _box(9, 9, 15, 15, 1.5), _box(9, 3, 15, 5, 1)),
    "theme": _any(_ring(8, 8, 6.8, 1.5), lambda x, y: x >= 8 and (x - 8) ** 2 + (y - 8) ** 2 <= 6.8 ** 2),
    "refresh": _any(
        _cut(_ring(8, 8.6, 5.6, 1.7), lambda x, y: -90 < math.degrees(math.atan2(y - 8.6, x - 8)) < -25),
        _triangle((7.6, 0.9), (7.6, 6.9), (11.2, 3.9))),
    "search": _any(_ring(6.5, 6.5, 5, 1.6), _line(10.2, 10.2, 14.5, 14.5, 2)),
    "pc": _any(_cut(_box(1, 2, 15, 11.5, 1.5), _box(2.6, 3.6, 13.4, 9.9, 0.4)),
               _line(8, 11.5, 8, 13.6, 1.6), _line(4.8, 14.2, 11.2, 14.2, 1.6)),
    "chip": _any(_cut(_box(3.5, 3.5, 12.5, 12.5, 1.5), _box(5.1, 5.1, 10.9, 10.9, 0.5)),
                 *(_line(a, 1.2, a, 3.5, 1.2) for a in (6, 8, 10)), *(_line(a, 12.5, a, 14.8, 1.2) for a in (6, 8, 10)),
                 *(_line(1.2, a, 3.5, a, 1.2) for a in (6, 8, 10)), *(_line(12.5, a, 14.8, a, 1.2) for a in (6, 8, 10))),
    "memory": _any(_cut(_box(1, 3.5, 15, 10.5, 1), *(_box(a, 5.3, a + 2.6, 8.7, 0.3) for a in (2.8, 6.7, 10.6))),
                   *(_line(a, 10.5, a, 13, 1.1) for a in (3, 5, 7, 9, 11, 13))),
    "drive": _any(_cut(_box(1, 4, 15, 12, 1.5), _box(2.6, 5.6, 13.4, 10.4, 0.5)),
                  _disc(11.4, 8, 1.1), _line(4.4, 8, 8, 8, 1.2)),
    # The dock's other tools, drawn after the Linux build's: a screen with a
    # magnifier, a brush, a download, blocks packed together, and an update.
    "diagnose": _any(_cut(_box(1, 2, 15, 11.5, 1.5), _box(2.6, 3.6, 13.4, 9.9, 0.4)),
                     _line(8, 11.5, 8, 13.6, 1.6), _line(4.8, 14.2, 11.2, 14.2, 1.6),
                     _ring(7.3, 6.4, 2.1, 1.1), _line(8.8, 7.9, 10.6, 9.4, 1.2)),
    "cleanup": _any(_line(14.5, 1.5, 10, 6, 1.8), _line(10.6, 5.4, 8.6, 7.4, 3.4),
                    _triangle((6.2, 5.8), (10.2, 9.8), (6.4, 15.2)), _triangle((6.2, 5.8), (6.4, 15.2), (0.8, 9.6))),
    "updates": _any(_line(8, 1.6, 8, 8.6, 1.8), _triangle((4.2, 6.6), (11.8, 6.6), (8, 10.8)),
                    _line(2, 11, 2, 14, 1.6), _line(2, 14, 14, 14, 1.6), _line(14, 11, 14, 14, 1.6)),
    "defrag": _any(*(_box(x, y, x + 3.8, y + 3.8, 0.8) for y, xs in ((1.5, (1.5, 6.1, 10.7)), (6.1, (1.5, 6.1)),
                                                                      (10.7, (1.5,))) for x in xs)),
    "upgrade": _any(_ring(8, 8, 6.8, 1.5), _line(8, 11.6, 8, 6.4, 1.6), _triangle((4.8, 7.6), (11.2, 7.6), (8, 4))),
    # App Manager, Web Apps and About, after the Linux build's: a download in
    # a disc, a compass, and an i.
    "apps": _cut(_disc(8, 8, 7.4), _line(8, 3.8, 8, 8.4, 1.9), _triangle((4.6, 7.4), (11.4, 7.4), (8, 11.6))),
    "web": _any(_ring(8, 8, 7, 1.4), _triangle((11.4, 4.6), (6.9, 6.9), (9.1, 9.1)),
                _triangle((4.6, 11.4), (9.1, 9.1), (6.9, 6.9))),
    "about": _cut(_disc(8, 8, 7.4), _disc(8, 4.6, 1.15), _box(6.95, 6.6, 9.05, 12, 0.5)),
    "dot": _disc(13.4, 2.6, 2.4),  # a mark in a dock button's corner: an update is waiting
    # An app's details: back to the tiles, and copy the install command.
    "back": _any(_line(13, 8, 3.4, 8, 1.7), _line(3.4, 8, 8.2, 3.2, 1.7), _line(3.4, 8, 8.2, 12.8, 1.7)),
    "copy": _any(_cut(_box(5.5, 5.5, 14.5, 14.5, 1.3), _box(6.9, 6.9, 13.1, 13.1, 0.4)),
                 _cut(_box(1.5, 1.5, 10.5, 10.5, 1.3), _box(2.9, 2.9, 9.1, 9.1, 0.4),
                      _box(4.6, 4.6, 15.5, 15.5, 1.3))),
}
_SS = 4
_masks, _pictures = {}, {}


def _shape(key, size):
    if key == "disc_in":  # a disc 1 px smaller: what's left of "disc" is a 1 px border
        return _disc(8, 8, 8 - 16 / size)
    if isinstance(key, tuple):  # (shape, share): the shape shrunk into the middle `share` of the picture
        inner, share = SHAPES[key[0]], key[1]
        return lambda x, y: inner((x - 8) / share + 8, (y - 8) / share + 8)
    return SHAPES[key]


def _mask(key, size):
    """How much of each pixel the shape covers, 0 to 1. Five probes first:
    most pixels are all in or all out, and only edges need all 16 samples."""
    if (key, size) not in _masks:
        shape, k = _shape(key, size), 16 / size
        samples = [(i + 0.5) / _SS for i in range(_SS)]
        cover = []
        for y in range(size):
            for x in range(size):
                probe = [shape((x + a) * k, (y + b) * k) for a, b in ((.125, .125), (.875, .125), (.125, .875), (.875, .875), (.5, .5))]
                if all(probe) or not any(probe):
                    cover.append(float(probe[0]))
                else:
                    cover.append(sum(shape((x + a) * k, (y + b) * k) for b in samples for a in samples) / _SS ** 2)
        _masks[key, size] = cover
    return _masks[key, size]


def picture(size: int, outside: str, *layers) -> tk.PhotoImage:
    """A size×size picture of `layers`, each (shape, colour), painted in
    order over `outside`, the colour behind it. Tk 8.6 can't put
    see-through pixels, so the edges are blended with it here."""
    key = (size, outside, layers)
    if key not in _pictures:
        pixels = [_rgb(outside)] * (size * size)
        for shape, colour in layers:
            c = _rgb(colour)
            pixels = [tuple(round(v + (w - v) * a) for v, w in zip(p, c)) if a else p
                      for p, a in zip(pixels, _mask(shape, size))]
        image = tk.PhotoImage(width=size, height=size)
        image.put(" ".join("{" + " ".join("#%02x%02x%02x" % p for p in pixels[y * size:(y + 1) * size]) + "}"
                           for y in range(size)))
        _pictures[key] = image
    return _pictures[key]


def tick_picture(state: str, bg: str) -> tk.PhotoImage:
    """A round tick: "none", "all" (ticked) or "some" (a dash, for the select-all circle)."""
    if state == "none":
        return picture(px(18), bg, ("tick_ring", THEME["tick"]))
    return picture(px(18), bg, ("tick_disc", ACCENT), ("check" if state == "all" else "dash", "#ffffff"))


# ---- widgets ----


class Rounded(tk.Canvas):
    """A panel with round corners, which Tk frames can't have: the canvas
    draws the shape, and `inner`, a plain frame, sits `pad` in from its
    edge, clear of the corners. fit() sizes the panel to what's in `inner`;
    packed to fill, it stretches `inner` instead."""

    def __init__(self, parent, radius, pad, **roles):
        super().__init__(parent, width=1, height=1, highlightthickness=0, borderwidth=0)
        self.radius, self.pad, self.roles, self.colours = px(radius), px(pad), roles, None
        self.inner = tk.Frame(self)
        self.create_window(self.pad, self.pad, window=self.inner, anchor="nw", tags="inner")
        self.bind("<Configure>", lambda _e: self._draw())

    def fit(self):
        self.inner.update_idletasks()
        self.configure(width=self.inner.winfo_reqwidth() + 2 * self.pad,
                       height=self.inner.winfo_reqheight() + 2 * self.pad)

    def repaint(self, outside, bg, _fg):
        self.colours = (outside, bg, THEME.get(self.roles.get("border")))
        self.configure(background=outside)
        self._draw()
        return bg

    def _draw(self):
        if not self.colours:
            return
        outside, fill, border = self.colours
        w, h, r = self.winfo_width(), self.winfo_height(), self.radius
        self.delete("shape")
        disc = picture(2 * r, outside, ("disc", border or fill), ("disc_in", fill))
        for x, y in ((0, 0), (r, 0), (0, r), (r, r)):  # each corner gets its quarter of the disc
            self.create_image(x and w - r, y and h - r, image=_quarter(disc, x, y, r), anchor="nw", tags="shape")
        self.create_rectangle(r, 0, w - r, h, fill=fill, width=0, tags="shape")
        self.create_rectangle(0, r, w, h - r, fill=fill, width=0, tags="shape")
        if border:
            for line in ((r, 0, w - r, 0), (r, h - 1, w - r, h - 1), (0, r, 0, h - r), (w - 1, r, w - 1, h - r)):
                self.create_line(*line, fill=border, tags="shape")
        self.tag_lower("shape")
        self.itemconfigure("inner", width=max(1, w - 2 * self.pad), height=max(1, h - 2 * self.pad))


class Button(Rounded):
    """A rounded text button, as in the Linux build's action bar."""

    _COLOURS = {"": ("#262833", "#30323f"), "destructive": ("#c62f28", "#d63a33"), "suggested": (ACCENT, "#5b6af0")}

    def __init__(self, parent, text, command, style=""):
        super().__init__(parent, radius=10, pad=3)
        self.style, self.enabled, self.hovered, self.outside = style, True, False, None
        self.label = role(tk.Label(self.inner, text=text, font=FONTS["bold"], padx=px(11), pady=px(4)), fixed=True)
        self.label.pack()
        self.label.bind("<Enter>", lambda _e: self._hover(True))
        self.label.bind("<Leave>", lambda _e: self._hover(False))
        self.label.bind("<Button-1>", lambda _e: self.enabled and command())
        self.fit()

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self._restyle()

    def _hover(self, hovered):
        self.hovered = hovered
        self._restyle()

    def _restyle(self):
        if self.outside:
            self.repaint(self.outside, None, None)

    def repaint(self, outside, _bg, _fg):
        self.outside = outside
        normal, hover = self._COLOURS[self.style]
        fill = hover if self.hovered and self.enabled else normal
        if not self.enabled:  # 45%, as the Linux CSS dims it
            fill = mix(outside, fill, 0.45)
        self.label.configure(background=fill, foreground=mix(fill, "#ffffff", 1 if self.enabled else 0.45))
        return super().repaint(outside, fill, None)


class Icon(tk.Label):
    """One of SHAPES as a small picture in `ink` (a palette key or a colour;
    the text colour if none): a group heading's icon, the search glass."""

    def __init__(self, parent, shape, size, ink=None):
        super().__init__(parent, borderwidth=0, padx=0, pady=0, image=_blank(px(size)))
        self.shape, self.size, self.ink = shape, px(size), ink

    def repaint(self, _outside, bg, fg):
        ink = THEME.get(self.ink, self.ink) or fg
        self.configure(background=bg, image=picture(self.size, bg, (self.shape, ink)))


class IconButton(tk.Label):
    """An icon on a rounded square that lights on hover: the dock's buttons
    (the open page's in the accent colour) and ↻ in a page header. `logo`,
    a picture, stands in for the shape: Home is the logo."""

    def __init__(self, parent, shape, tooltip, command, size=36, icon=18, hover="hover", logo=None):
        super().__init__(parent, borderwidth=0, padx=0, pady=0, image=_blank(px(size)))
        self.shape, self.size, self.share, self.hover, self.logo = shape, px(size), icon / size, hover, logo
        self.selected = self.hovered = self.marked = False
        self.bg = self.fg = None
        self.tooltip = tooltip
        self.bind("<Enter>", lambda _e: self._set(hovered=True))
        self.bind("<Leave>", lambda _e: self._set(hovered=False))
        self.bind("<Button-1>", lambda _e: command())
        Tooltip(self, lambda _e: self.tooltip)

    def select(self, selected: bool):
        self._set(selected=selected)

    def mark(self, marked: bool):
        """A dot in the corner: something is waiting behind this button."""
        self._set(marked=marked)

    def _set(self, **state):
        self.__dict__.update(state)
        if self.bg:
            self._draw()

    def repaint(self, _outside, bg, fg):
        self.bg, self.fg = bg, fg
        self._draw()

    def _draw(self):
        fill = ACCENT if self.selected else THEME[self.hover] if self.hovered else self.bg
        back = [("button", fill)] if fill != self.bg else []
        if self.logo:
            image = _over(picture(self.size, self.bg, *back), self.logo)
        else:
            image = picture(self.size, self.bg, *back, ((self.shape, self.share), "#ffffff" if self.selected else self.fg),
                            *([("dot", LINE)] if self.marked else []))
        self.configure(image=image, background=self.bg)


def _blank(size):
    """Holds an icon's place until the theme paints it, so a panel that fits
    itself to its content measures the real size."""
    return picture(size, "#000000")


_derived = {}


def _over(base, top):
    """`top` (a picture with see-through edges, like the logo) centred on `base`."""
    key = ("over", str(base), str(top))
    if key not in _derived:
        image = tk.PhotoImage(width=base.width(), height=base.height())
        image.tk.call(image, "copy", base)
        image.tk.call(image, "copy", top, "-to", (base.width() - top.width()) // 2, (base.height() - top.height()) // 2)
        _derived[key] = image
    return _derived[key]


def _quarter(disc, x, y, r):
    key = ("quarter", str(disc), x, y)
    if key not in _derived:
        image = tk.PhotoImage(width=r, height=r)
        image.tk.call(image, "copy", disc, "-from", x, y, x + r, y + r)
        _derived[key] = image
    return _derived[key]


class Tick(tk.Checkbutton):
    """A round tick with its label, as in the app list: the dialogs' checkboxes."""

    def __init__(self, parent, text, variable, command=None):
        super().__init__(parent, text=f"  {text}", variable=variable, command=command, indicatoron=False,
                         compound="left", relief="flat", offrelief="flat", overrelief="flat", borderwidth=0,
                         highlightthickness=0, anchor="w", justify="left", cursor="hand2")

    def repaint(self, _outside, bg, fg):
        self.configure(image=tick_picture("none", bg), selectimage=tick_picture("all", bg), background=bg,
                       activebackground=bg, selectcolor=bg, foreground=fg, activeforeground=fg)


class Tooltip:
    """Text on hover, in the action bar's colours: the dock's names, an
    app's risk reason. `text_at(event)` says what, or ""."""

    def __init__(self, widget, text_at):
        self.widget, self.text_at, self.window, self.text = widget, text_at, None, ""
        widget.bind("<Motion>", lambda e: self._show(self.text_at(e), e), add="+")
        widget.bind("<Leave>", lambda _e: self._show(""), add="+")
        widget.bind("<Button-1>", lambda _e: self._show(""), add="+")

    def _show(self, text, event=None):
        if text == self.text:
            return
        self.text = text
        if self.window:
            self.window.destroy()
            self.window = None
        if not text:
            return
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        tk.Label(self.window, text=text, justify="left", wraplength=px(420), background="#111217",
                 foreground="#e6e7eb", padx=px(8), pady=px(5)).pack()
        self.window.update_idletasks()
        y = event.y_root + px(18)
        if y + self.window.winfo_reqheight() > self.widget.winfo_screenheight():  # the dock: show it above
            y = event.y_root - self.window.winfo_reqheight() - px(10)
        self.window.wm_geometry(f"+{event.x_root + px(12)}+{y}")


class ActionBar(Rounded):
    """The floating dark bar at the bottom of every page: a thin line loader
    along its top edge, a status line, and the page's buttons."""

    def __init__(self, parent):
        super().__init__(parent, radius=14, pad=6, bg="bar", fg="bar_text", border="bar_border")
        self.line = tk.Canvas(self.inner, height=px(3), highlightthickness=0, borderwidth=0)
        self.line.pack(fill="x", padx=px(8))
        row = tk.Frame(self.inner)
        row.pack(fill="x")
        self.status = tk.Label(row, anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=(px(10), 0), pady=px(5))
        self.buttons = tk.Frame(row)
        self.buttons.pack(side="right")
        self.fraction, self.ok, self.sweep, self._step, self._job = None, True, None, 0.03, None
        self.line.bind("<Configure>", lambda _e: self._draw_line())
        self.fit()

    def add_button(self, text, command, style=""):
        button = Button(self.buttons, text, command, style)
        button.pack(side="left", padx=(px(8), 0))
        self.fit()
        return button

    def say(self, text: str):
        self.status.configure(text=text)

    def pulse(self):
        """The line sweeps back and forth while looking."""
        self._stop()
        self.sweep = 0.0

        def tick():
            if not 0 <= self.sweep + self._step <= 1:
                self._step = -self._step
            self.sweep += self._step
            self._draw_line()
            self._job = self.after(30, tick)

        tick()

    def slice(self, start: float, end: float):
        """Crawl toward `end` while a blocking uninstaller with no progress of
        its own runs. It stops at 92% of the slice; settle() snaps the rest,
        so it never looks stuck short."""
        self._stop()
        self.fraction, self.ok = start, True
        step, ceiling = (end - start) * 0.06, start + (end - start) * 0.92

        def tick():
            self.fraction = min(ceiling, self.fraction + step)
            self._draw_line()
            self._job = self.after(60, tick)

        tick()

    def settle(self, fraction: float, ok: bool = True):
        self._stop()
        self.fraction, self.ok = fraction, ok
        self._draw_line()

    def countdown(self, seconds: float, then):
        """The line starts full and runs down over `seconds`, then then():
        how long a notice has left. Timed by the clock, so it can't drift."""
        self._stop()
        self.ok, start = True, time.monotonic()

        def tick():
            self.fraction = 1 - (time.monotonic() - start) / seconds
            if self.fraction <= 0:
                self.done()
                then()
                return
            self._draw_line()
            self._job = self.after(30, tick)

        tick()

    def done(self):
        self._stop()
        self.fraction = None
        self._draw_line()

    def _stop(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self.sweep = None

    def _draw_line(self):
        c, w, h = self.line, self.line.winfo_width(), px(3)
        c.delete("all")
        if self.sweep is None and self.fraction is None:
            return
        c.create_rectangle(0, 0, w, h, fill="#262833", width=0)
        if self.sweep is not None:
            c.create_rectangle(self.sweep * w * 0.75, 0, (self.sweep * 0.75 + 0.25) * w, h, fill=LINE, width=0)
        else:
            c.create_rectangle(0, 0, w * self.fraction, h, fill=LINE if self.ok else LINE_ERROR, width=0)


class Page(tk.Frame):
    """Title and subtitle on top, the page's own content in `body`, the
    action bar underneath. Header controls pack into `header` from the right."""

    title = ""
    icon = None  # a SHAPES name for its dock button; None is Home, the logo
    auto_load = True  # reload() when the window opens

    def __init__(self, parent):
        super().__init__(parent)
        self.busy = False
        self.header = tk.Frame(self)
        self.header.pack(fill="x", padx=px(28), pady=(px(16), px(12)))
        titles = tk.Frame(self.header)
        titles.pack(side="left", fill="x", expand=True)
        tk.Label(titles, text=self.title, font=FONTS["title"], anchor="w").pack(fill="x")
        self.subtitle = role(tk.Label(titles, anchor="w"), fg="dim")
        self.subtitle.pack(fill="x")
        self.bar = ActionBar(self)
        self.bar.pack(side="bottom", fill="x", padx=px(24), pady=(px(12), px(10)))
        self.body = tk.Frame(self)
        self.body.pack(fill="both", expand=True, padx=px(28))

    def header_button(self, shape, tooltip, command):
        button = IconButton(self.header, shape, tooltip, command, size=34, icon=16, hover="border")
        button.pack(side="right", padx=(px(8), 0))
        return button

    def set_busy(self, busy: bool):
        """Only this page locks while it works: the dock stays live."""
        self.busy = busy
        for button in self.bar.buttons.winfo_children():
            button.set_enabled(not busy)

    def run_async(self, work, done):
        """work() on a thread, then done(result) back on Tk's. Widgets are
        never touched off it; a bug in work() mustn't leave the page locked."""

        def worker():
            try:
                result = work()
            except Exception as exc:
                later(self._failed, exc)
                return
            later(done, result)

        threading.Thread(target=worker, daemon=True).start()

    def _failed(self, exc):
        self.bar.done()
        self.bar.say(f"Something went wrong: {exc}")
        self.set_busy(False)


def fit_text(text: str, width: int, font) -> str:
    """`text`, cut short with … to fit `width` pixels."""
    if font.measure(text) <= width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid] + "…") <= width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def draw_tag(canvas, x, y, text, colours) -> int:
    """A coloured label on a canvas, square like the Linux build's; returns its right edge."""
    fg, bg = colours
    font = FONTS["small"]
    half, right = font.metrics("linespace") / 2 + px(2), x + font.measure(text) + 2 * px(6)
    canvas.create_rectangle(x, y - half, right, y + half, fill=bg, width=0)
    canvas.create_text(x + px(6), y, text=text, anchor="w", font=font, fill=fg)
    return right


def filter_pill(header, choices: list, on_change):
    """A pill in a page header naming the chosen filter; a click opens the
    rest. on_change(choice) when one is picked."""
    pill = role(Rounded(header, radius=10, pad=3), bg="card", border="border")
    pill.pack(side="right", padx=(px(8), 0))
    label = tk.Label(pill.inner, text=f"{choices[0]}  ▾", padx=px(10), pady=px(5), cursor="hand2")
    label.pack()
    choice = tk.StringVar(value=choices[0])
    menu = role(tk.Menu(header, tearoff=False), fixed=True)  # a native menu on Windows; it has its own colours

    def chosen():
        label.configure(text=f"{choice.get()}  ▾")
        pill.fit()
        on_change(choice.get())

    for text in choices:
        menu.add_radiobutton(label=text, value=text, variable=choice, command=chosen)
    label.bind("<Button-1>", lambda _e: menu.tk_popup(pill.winfo_rootx(), pill.winfo_rooty() + pill.winfo_height()))
    pill.fit()


def search_pill(header, hint: str, on_change):
    """A search box in a page header; on_change(text) on every keystroke."""
    pill = role(Rounded(header, radius=10, pad=3), bg="card", border="border")
    pill.pack(side="right", padx=(px(8), 0))
    Icon(pill.inner, "search", 14, "dim").pack(side="left", padx=(px(9), px(5)))
    text = tk.StringVar()
    entry = tk.Entry(pill.inner, textvariable=text, width=26, relief="flat", borderwidth=0, highlightthickness=0)
    entry.pack(side="left", pady=px(5), padx=(0, px(10)))
    # Tk entries have no placeholder; this label sits in the empty entry instead.
    label = role(tk.Label(pill.inner, text=hint, padx=0, pady=0, borderwidth=0), fg="dim")
    label.bind("<Button-1>", lambda _e: entry.focus_set())

    def changed(*_):
        if text.get():
            label.place_forget()
        else:
            label.place(in_=entry, x=0, rely=0.5, anchor="w")
        on_change(text.get())

    text.trace_add("write", changed)
    label.place(in_=entry, x=0, rely=0.5, anchor="w")
    pill.fit()


class Table(Rounded):
    """The ticked list on Updates, Cleanup and Drivers, in a card: the
    select-all circle and the column names over rows drawn on a canvas, as
    on Uninstall (a Treeview can't colour one cell).

    `columns` are (title, width, anchor): width in 96-DPI pixels, 0 for the
    one column that takes what's left; anchor "e" right-aligns (sizes).
    `cells(item)` gives a row's cells, each a string or a list of parts
    drawn one after another: a string, ("dim", text), ("bold", text) or ("tag", text,
    (fg, bg)). Only rows `tickable(item)` get a tick; the circle ticks only
    the rows on screen that are `pickable(item)` too. `on_change()` after
    every change to what's shown or ticked."""

    ROW, TICK_X, FIRST_X, GAP = 38, 20, 42, 18  # pixels at 96 DPI

    def __init__(self, parent, columns, cells, on_change, tickable=None, pickable=None, tooltip=None,
                 locked=lambda: False, circle="Select all"):
        super().__init__(parent, radius=14, pad=6, bg="card", border="border")
        self.columns, self.cells, self.on_change, self.locked = columns, cells, on_change, locked
        self.tickable = tickable or (lambda _item: True)
        self.pickable = pickable or self.tickable
        self.items, self.visible, self.selected, self.empty, self._width = [], [], set(), "Reading…", 0
        self.inner.rowconfigure(1, weight=1)
        self.inner.columnconfigure(0, weight=1)
        self.head = tk.Canvas(self.inner, height=px(30), highlightthickness=0, borderwidth=0)
        self.head.grid(row=0, column=0, sticky="ew")
        self.canvas = tk.Canvas(self.inner, highlightthickness=0, borderwidth=0, yscrollincrement=px(self.ROW))
        self.canvas.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self.inner, orient="vertical", command=self.canvas.yview,
                               style="Thin.Vertical.TScrollbar")
        scroll.grid(row=1, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scroll.set)

        self.head.bind("<Button-1>", lambda e: e.x < px(self.FIRST_X) and self.toggle_all())
        Tooltip(self.head, lambda e: circle if e.x < px(self.FIRST_X) else "")
        self.head.bind("<Configure>", lambda _e: self._draw_header())
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _e: self.canvas.itemconfigure("hover", state="hidden"))
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-3 if e.delta > 0 else 3, "units"))
        for button, rows in (("<Button-4>", -3), ("<Button-5>", 3)):  # the wheel on X11 with Tk 8.6
            self.canvas.bind(button, lambda _e, n=rows: self.canvas.yview_scroll(n, "units"))
        if tooltip:  # after the bindings above, which it adds to
            Tooltip(self.canvas, lambda e: "" if (n := self._row_at(e)) is None else tooltip(self.items[self.visible[n]]))
        on_theme(self.redraw)

    # ---- what's shown ----

    def show(self, items: list, empty: str, keep=lambda _item: True):
        """New rows, none ticked; `empty` is said when none are on screen."""
        self.items, self.selected, self.empty = items, set(), empty
        self.filter(keep)

    def filter(self, keep):
        """Only rows keep(item) on screen. A ticked row filtered out stays ticked."""
        self.visible = [i for i, item in enumerate(self.items) if keep(item)]
        self.canvas.yview_moveto(0)
        self.redraw()
        self.on_change()

    def chosen(self) -> list:
        return [self.items[i] for i in sorted(self.selected)]

    # ---- ticking ----

    def ticked(self) -> str:
        """The select-all circle: "all" when every row on screen it picks is
        ticked, "some" when any row on screen is."""
        pickable = [i for i in self.visible if self.pickable(self.items[i])]
        if pickable and all(i in self.selected for i in pickable):
            return "all"
        return "some" if any(i in self.selected for i in self.visible) else "none"

    def toggle_all(self):
        """Ticks every pickable row on screen. Once they all are, or there are
        none, it clears the screen instead, so a row ticked by hand among the
        ones it skips can still be cleared with it."""
        if self.locked():
            return
        pickable = [i for i in self.visible if self.pickable(self.items[i])]
        if all(i in self.selected for i in pickable):
            self.selected.difference_update(self.visible)
        else:
            self.selected.update(pickable)
        self.redraw()
        self.on_change()

    def _on_click(self, event):
        n = self._row_at(event)
        if n is None or self.locked() or not self.tickable(self.items[self.visible[n]]):
            return
        self.selected ^= {self.visible[n]}
        self.canvas.itemconfigure(f"tick{n}", image=self._tick(self.visible[n]))
        self._draw_header()
        self.on_change()

    # ---- drawing ----

    def redraw(self):
        self._draw_rows()
        self._draw_header()

    def _xs(self, width) -> list[tuple[int, int, str]]:
        """(x, width, anchor) of each column."""
        fixed = sum(px(w) for _, w, _ in self.columns) + px(self.GAP) * (len(self.columns) - 1)
        stretch = max(px(60), width - px(self.FIRST_X) - px(12) - fixed)
        xs, x = [], px(self.FIRST_X)
        for _, w, anchor in self.columns:
            xs.append((x, px(w) if w else stretch, anchor))
            x += xs[-1][1] + px(self.GAP)
        return xs

    def _draw_header(self):
        c = self.head
        c.configure(background=THEME["card"])
        c.delete("all")
        y = px(15)
        c.create_image(px(self.TICK_X), y, image=tick_picture(self.ticked(), THEME["card"]))
        for (x, w, anchor), (title, _, _) in zip(self._xs(c.winfo_width()), self.columns):
            c.create_text(x + w if anchor == "e" else x, y, text=title, anchor=anchor, font=FONTS["caps"],
                          fill=THEME["dim"])

    def _draw_rows(self):
        c, width, row = self.canvas, self.canvas.winfo_width(), px(self.ROW)
        c.configure(background=THEME["card"])
        c.delete("all")
        xs = self._xs(width)
        c.create_rectangle(0, 0, 0, 0, fill=THEME["hover"], width=0, state="hidden", tags="hover")
        for n, index in enumerate(self.visible):
            item, y = self.items[index], n * row + row / 2
            if self.tickable(item):
                c.create_image(px(self.TICK_X), y, image=self._tick(index), tags=f"tick{n}")
            for (x, w, anchor), cell in zip(xs, self.cells(item)):
                self._draw_cell(x, w, anchor, y, cell)
        if not self.visible:
            c.create_text(width / 2, row, text=self.empty, font=FONTS["base"], fill=THEME["dim"])
        c.configure(scrollregion=(0, 0, width, len(self.visible) * row))

    def _draw_cell(self, x, width, anchor, y, cell):
        c, font, end = self.canvas, FONTS["base"], x + width
        if anchor == "e":
            c.create_text(end, y, text=fit_text(cell, width, font), anchor="e", font=font, fill=THEME["dim"])
            return
        parts = cell if isinstance(cell, list) else [cell]
        for n, part in enumerate(parts):
            kind, text = ("fg", part) if isinstance(part, str) else part[:2]
            if not text or x >= end:
                continue
            if kind == "tag":
                x = draw_tag(c, x, y, text, part[2]) + px(6)
            else:
                # Tags after the text keep their room: a narrow window cuts a
                # long reason short, never the risk label that ends it.
                room = sum(FONTS["small"].measure(p[1]) + px(18) for p in parts[n + 1:]
                           if not isinstance(p, str) and p[0] == "tag")
                face = FONTS["bold"] if kind == "bold" else font
                text = fit_text(text, end - x - room, face)
                c.create_text(x, y, text=text, anchor="w", font=face, fill=THEME["dim" if kind == "dim" else "fg"])
                x += face.measure(text) + px(6)

    def _tick(self, index):
        return tick_picture("all" if index in self.selected else "none", THEME["card"])

    def _row_at(self, event):
        n = int(self.canvas.canvasy(event.y) // px(self.ROW))
        return n if 0 <= n < len(self.visible) else None

    def _on_resize(self, event):
        if event.width != self._width:
            self._width = event.width
            self.redraw()

    def _on_motion(self, event):
        n = self._row_at(event)
        if n is None:
            self.canvas.itemconfigure("hover", state="hidden")
            return
        self.canvas.coords("hover", 0, n * px(self.ROW), self.canvas.winfo_width(), (n + 1) * px(self.ROW))
        self.canvas.itemconfigure("hover", state="normal")


class Tiles(Table):
    """Table's ticking, filtering and select-all, its rows laid out side by
    side as tiles with a picture each: `cells(item)` gives a tile's three
    lines (each drawn as a Table cell is), `picture(item)` a PhotoImage of
    about 32 pixels at 96 DPI. `on_open(item)` is a click on the tile itself,
    not on its tick. With `group(item)`, tiles sit under a heading per group,
    each heading with a select-all of its own — as on Linux, where a group is
    a card with a CheckButton."""

    ROW, WIDE, HEAD = 70, 300, 28  # a tile's height, the narrowest it gets, a heading's height

    def __init__(self, parent, title, cells, picture, on_change, on_open=None, group=None, **options):
        self.picture, self.on_open, self.group = picture, on_open, group
        self._tile_at, self._headings, self._height = {}, [], 0
        super().__init__(parent, [(title, 0, "w")], cells, on_change, **options)

    # ---- where everything goes ----

    def _per_line(self) -> int:
        return max(1, self.canvas.winfo_width() // px(self.WIDE))

    def _plan(self):
        """Each tile's column and top, and each group heading's. Worked out
        once per draw and then read by _box, _row_at and the drawing, so the
        three can't disagree about where a tile is."""
        per, row, head = self._per_line(), px(self.ROW), px(self.HEAD)
        self._tile_at, self._headings, y = {}, [], 0
        groups = {}
        for n, index in enumerate(self.visible):
            groups.setdefault(self.group(self.items[index]) if self.group else "", []).append(n)
        for name, members in groups.items():
            if name:
                self._headings.append((name, y, members))
                y += head
            for k, n in enumerate(members):
                self._tile_at[n] = ((k % per), y + (k // per) * row)
            y += -(-len(members) // per) * row
        self._height = y

    def _box(self, n):
        """Tile n's left, top and width."""
        column, y = self._tile_at.get(n, (0, 0))
        width = self.canvas.winfo_width() / self._per_line()
        return column * width, y, width

    def _heading_at(self, event):
        """(name, members) of the group heading the click is on, or None."""
        y = self.canvas.canvasy(event.y)
        return next(((name, members) for name, top, members in self._headings
                     if top <= y < top + px(self.HEAD)), None)

    def _row_at(self, event):
        x, y = event.x, self.canvas.canvasy(event.y)
        row, width = px(self.ROW), self.canvas.winfo_width() / self._per_line()
        for n, (column, top) in self._tile_at.items():
            if top <= y < top + row and column * width <= x < (column + 1) * width:
                return n
        return None

    # ---- ticking ----

    def _on_click(self, event):
        """The tick ticks; anywhere else on the tile opens it. On Linux the
        tick is a CheckButton inside the tile, so its click never reaches the
        FlowBox that opens one; here one canvas gets both, split by where.
        A group heading's tick takes that group's tiles."""
        if self.locked():
            return
        heading = self._heading_at(event)
        if heading:
            if event.x < px(self.FIRST_X):
                self._toggle_group(heading[1])
            return
        n = self._row_at(event)
        if n is None:
            return
        x, _y, _width = self._box(n)
        if event.x - x < px(self.FIRST_X) or not self.on_open:
            super()._on_click(event)
        else:
            self.on_open(self.items[self.visible[n]])

    def _toggle_group(self, members):
        """Every tile in this group that can be ticked, or none of them —
        the same rule as the select-all circle, over one group."""
        pickable = [self.visible[n] for n in members if self.pickable(self.items[self.visible[n]])]
        if all(i in self.selected for i in pickable):
            self.selected.difference_update(self.visible[n] for n in members)
        else:
            self.selected.update(pickable)
        self.redraw()
        self.on_change()

    def _group_ticked(self, members) -> str:
        pickable = [self.visible[n] for n in members if self.pickable(self.items[self.visible[n]])]
        if pickable and all(i in self.selected for i in pickable):
            return "all"
        return "some" if any(self.visible[n] in self.selected for n in members) else "none"

    # ---- drawing ----

    def _draw_rows(self):
        c, row = self.canvas, px(self.ROW)
        c.configure(background=THEME["card"])
        c.delete("all")
        self._plan()
        c.create_rectangle(0, 0, 0, 0, fill=THEME["hover"], width=0, state="hidden", tags="hover")
        for name, top, members in self._headings:
            mid = top + px(self.HEAD) / 2
            c.create_image(px(self.TICK_X), mid, image=tick_picture(self._group_ticked(members), THEME["card"]))
            c.create_text(px(self.FIRST_X), mid, text=name.upper(), anchor="w", font=FONTS["caps"],
                          fill=THEME["dim"])
        for n, index in enumerate(self.visible):
            item, (x, y, width) = self.items[index], self._box(n)
            mid = y + row / 2
            if self.tickable(item):
                c.create_image(x + px(self.TICK_X), mid, image=self._tick(index), tags=f"tick{n}")
            c.create_image(x + px(self.FIRST_X + 18), mid, image=self.picture(item))
            text_x = x + px(self.FIRST_X + 46)
            for cell, dy in zip(self.cells(item), (-19, 0, 19)):
                self._draw_cell(text_x, x + width - text_x - px(12), "w", mid + px(dy), cell)
        if not self.visible:
            c.create_text(c.winfo_width() / 2, row / 2, text=self.empty, font=FONTS["base"], fill=THEME["dim"])
        c.configure(scrollregion=(0, 0, c.winfo_width(), self._height))

    def _on_motion(self, event):
        n = self._row_at(event)
        if n is None:
            self.canvas.itemconfigure("hover", state="hidden")
            return
        x, y, width = self._box(n)
        self.canvas.coords("hover", x, y, x + width, y + px(self.ROW))
        self.canvas.itemconfigure("hover", state="normal")


class Terminal(Rounded):
    """The dark panel that shows each command and what it prints, as it
    prints it. A line starting "▶ " is a heading, "$ " a command; one
    starting with a key of `colours` (and a colon) is shown in that colour."""

    def __init__(self, parent, placeholder: str = "", colours: dict | None = None):
        super().__init__(parent, radius=14, pad=10, bg="bar", fg="bar_text", border="bar_border")
        tk.Label(self.inner, text="TERMINAL", font=FONTS["caps"], anchor="w").pack(fill="x", pady=(0, px(6)))
        self.text = tk.Text(self.inner, wrap="word", relief="flat", borderwidth=0, highlightthickness=0,
                            font=("Consolas", 9), state="disabled")
        self.text.pack(fill="both", expand=True)
        self.text.tag_configure("command", foreground=LINE)
        self.text.tag_configure("check", font=("Consolas", 9, "bold"))
        self.inks = colours or {}  # not "colours": Rounded keeps its own under that name
        for key, ink in self.inks.items():
            self.text.tag_configure(key, foreground=ink)
        if placeholder:
            self.print(placeholder)

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def log(self, line: str):
        """From a worker thread: onto the panel, on Tk's."""
        later(self.print, line)

    def print(self, line: str):
        key = line.partition(":")[0]
        tag = "command" if line.startswith("$ ") else "check" if line.startswith("▶") else \
            key if key in self.inks else ""
        self.text.configure(state="normal")
        if line.startswith("▶") and self.text.index("end-1c") != "1.0":
            self.text.insert("end", "\n")
        self.text.insert("end", line + "\n", tag)
        self.text.configure(state="disabled")
        self.text.see("end")


def os_switch(header, this_os: str, other_os: str):
    """A Linux | Windows pill in a page header, lit on the OS Stitches is
    running on. The other side is locked: each OS's apps are installed by
    Stitches on that OS."""
    pill = role(Rounded(header, radius=12, pad=3), bg="card", border="border")
    pill.pack(side="right", padx=(px(8), 0))
    for name in sorted((this_os, other_os), key=lambda n: n != "Linux"):  # Linux always on the left
        if name == this_os:
            Button(pill.inner, name, lambda: None, "suggested").pack(side="left")
        else:
            other = role(tk.Label(pill.inner, text=name, padx=px(12), pady=px(4)), fg="dim")
            other.pack(side="left")
            Tooltip(other, lambda _e: f"Open Stitches on {other_os} for its apps")
    pill.fit()


def status_label(parent, text: str, colours) -> tk.Label:
    """A verdict as a coloured tag, fixed in every theme: Home's and Diagnose's."""
    fg, bg = colours
    return role(tk.Label(parent, text=f" {text} ", foreground=fg, background=bg, font=FONTS["small"]), fixed=True)


class Dialog(tk.Toplevel):
    """A modal dialog in the theme's colours: fill `body`, add buttons, then
    run(), which returns the answer of the button pressed (None if closed)."""

    def __init__(self, parent, title):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.answer = None
        self.body = tk.Frame(self, padx=px(20), pady=px(16))
        self.body.pack(fill="both", expand=True)
        tk.Label(self.body, text=title, font=FONTS["heading"], anchor="w").pack(fill="x", pady=(0, px(8)))
        self.buttons = tk.Frame(self.body)

    def button(self, text, answer=None, style=""):
        button = Button(self.buttons, text, lambda: self._close(answer), style)
        button.pack(side="left", padx=(px(8), 0))
        return button

    def _close(self, answer):
        self.answer = answer
        self.destroy()

    def run(self):
        self.buttons.pack(anchor="e", pady=(px(16), 0))
        recolour(self)
        self.update_idletasks()
        parent = self.master
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_reqwidth()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.wait_visibility()  # X11 refuses a grab on a window not yet shown
        self.grab_set()  # modal
        self.wait_window()
        return self.answer


def info(parent, title: str, text: str):
    dialog = Dialog(parent, title)
    tk.Label(dialog.body, text=text, wraplength=px(480), justify="left", anchor="w").pack(fill="x")
    dialog.button("OK", style="suggested")
    dialog.run()


def confirm(parent, title: str, lines: list, action: str, critical_ack: str = "") -> bool:
    """The confirmation every uninstall goes through (CLAUDE.md
    non-negotiable). `critical_ack` adds a tick that has to be set before
    the action button enables."""
    dialog = Dialog(parent, title)
    listing = role(tk.Text(dialog.body, height=min(12, max(3, len(lines))), width=64, wrap="none", relief="flat",
                           borderwidth=0, highlightthickness=0, padx=px(10), pady=px(8), font=FONTS["base"]), bg="card")
    listing.insert("1.0", "\n".join(lines))
    listing.configure(state="disabled")
    listing.pack(fill="both", expand=True)
    acknowledged = tk.BooleanVar(value=not critical_ack)
    if critical_ack:
        Tick(dialog.body, critical_ack, acknowledged,
             command=lambda: go.set_enabled(acknowledged.get())).pack(anchor="w", pady=(px(12), 0))
    dialog.button("Cancel")
    go = dialog.button(action, True, "destructive")
    go.set_enabled(acknowledged.get())
    return dialog.run() is True
