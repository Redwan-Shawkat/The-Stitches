"""Web Apps, as on Linux: paste an address, and the site's name and icon are
filled in (or typed and picked by hand when the site can't be read, or picked
from the ready-made icons). Adding it puts it in the Start menu straight
away, with a login of its own. The list on the right opens and removes them;
removing asks first, because the app's login goes with it."""

import base64
import os
import tempfile
import tkinter as tk
from tkinter import filedialog

from .. import webapps
from ..widgets import (FONTS, THEME, Button, Icon, Page, Rounded, Tooltip, confirm, filter_pill, info, px, recolour,
                       role, search_pill)

_SIZE = 256  # what's saved; Windows scales it down
_ALL_SITES = "All sites"
_SHOWN = 72  # eight rows of nine: what fits under the form without scrolling it


def _photo(data: bytes, master) -> tk.PhotoImage:
    """PNG or GIF, which is what Tk 8.6 reads. Raises TclError for anything else."""
    return tk.PhotoImage(master=master, data=base64.b64encode(data).decode())


def _square_png(data: bytes, master) -> bytes:
    """Any PNG or GIF as a square PNG no bigger than 256, centred on
    transparency, so a wide logo isn't stretched."""
    picture = _photo(data, master)
    factor = -(-max(picture.width(), picture.height()) // _SIZE)
    if factor > 1:
        picture = picture.subsample(factor)
    side = max(picture.width(), picture.height())
    square = tk.PhotoImage(master=master, width=side, height=side)
    square.tk.call(square, "copy", picture, "-to", (side - picture.width()) // 2, (side - picture.height()) // 2)
    handle, path = tempfile.mkstemp(suffix=".png")
    os.close(handle)
    try:
        square.write(path, format="png")
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)


def _shrunk(picture: tk.PhotoImage, size: int) -> tk.PhotoImage:
    factor = max(1, max(picture.width(), picture.height()) // size)
    return picture.subsample(factor) if factor > 1 else picture


def _field(parent):
    pill = role(Rounded(parent, radius=10, pad=3), bg="window", border="border")
    entry = tk.Entry(pill.inner, relief="flat", borderwidth=0, highlightthickness=0, width=34)
    entry.pack(fill="x", padx=px(8), pady=px(5))
    pill.fit()
    return pill, entry


class WebAppsPage(Page):
    title = "Web Apps"
    icon = "web"

    def __init__(self, parent):
        super().__init__(parent)
        self.browsers, self.browser, self.icon_png, self.pictures = [], None, b"", []
        self.subtitle.configure(text="Any website as an app: its own window, icon and login")
        self.header_button("refresh", "Look again", self.reload)
        self.body.columnconfigure(1, weight=1)
        self.body.rowconfigure(0, weight=1)
        self._build_form().grid(row=0, column=0, sticky="nsew", padx=(0, px(12)))
        mine = role(Rounded(self.body, radius=14, pad=12), bg="card", border="border")
        mine.grid(row=0, column=1, sticky="nsew")
        tk.Label(mine.inner, text="My web apps", font=FONTS["bold"], anchor="w").pack(fill="x")
        role(tk.Label(mine.inner, anchor="w", justify="left", text="Add the same site twice for two separate "
                      "logins — a personal and a work account, say."), fg="dim").pack(fill="x", pady=(0, px(8)))
        self.list = tk.Frame(mine.inner)
        self.list.pack(fill="both", expand=True)
        self.add_button = self.bar.add_button("Add web app", self._on_add, "suggested")

    # ---- the form ----

    def _build_form(self):
        form = role(Rounded(self.body, radius=14, pad=12), bg="card", border="border")
        box = form.inner
        tk.Label(box, text="Add a website", font=FONTS["bold"], anchor="w").pack(fill="x")
        role(tk.Label(box, text="Paste a link. The name and icon are filled in for you.", anchor="w"),
             fg="dim").pack(fill="x", pady=(0, px(8)))
        row = tk.Frame(box)
        row.pack(fill="x")
        pill, self.url = _field(row)
        pill.pack(side="left", fill="x", expand=True)
        self.url.bind("<Return>", lambda _e: self._on_fetch())
        Button(row, "Fetch", self._on_fetch).pack(side="left", padx=(px(8), 0))

        details = tk.Frame(box)
        details.pack(fill="x", pady=(px(12), 0))
        self.preview = tk.Label(details)
        self.preview.grid(row=0, column=0, rowspan=3, padx=(0, px(12)))
        self.placeholder = Icon(details, "web", 56, "dim")  # until there's a picture
        self.placeholder.grid(row=0, column=0, rowspan=3, padx=(0, px(12)))
        Button(details, "Pick an icon", self._pick_icon).grid(row=3, column=0, pady=(px(6), 0))
        self.name_pill, self.name = _field(details)
        self.address_pill, self.address = _field(details)
        self.browser_row = tk.Frame(details)
        for r, (text, widget) in enumerate((("Name", self.name_pill), ("Address", self.address_pill),
                                            ("Opens in", self.browser_row))):
            role(tk.Label(details, text=text), fg="dim").grid(row=r, column=1, sticky="w", padx=(0, px(8)))
            widget.grid(row=r, column=2, sticky="w", pady=px(2))

        self.ready_icons = webapps.ready_icons()
        row = tk.Frame(box)
        row.pack(fill="x", pady=(px(12), px(4)))
        role(tk.Label(row, text="Or pick an icon", anchor="w"), fg="dim").pack(side="left")
        search_pill(row, "Search icons", lambda text: self._show_icons(words=text.strip().lower()))
        groups = dict.fromkeys(group for group, _name, _path in self.ready_icons)
        filter_pill(row, [_ALL_SITES, *groups], lambda group: self._show_icons(group=group))
        self.ready = tk.Frame(box)
        self.ready.pack(anchor="w")
        self.icon_group, self.icon_words = _ALL_SITES, ""
        self._show_icons()
        form.fit()  # it doesn't stretch across, so it has to be as wide as what it holds
        return form

    def _show_icons(self, group=None, words=None):
        """One group at a time, as on Linux; a search looks through every
        group. Redrawn on each change: 94 labels are cheap, and keeping them
        all alive would make the card as tall as the whole set."""
        if group is not None:
            self.icon_group = group
        if words is not None:
            self.icon_words = words
        shown = [i for i in self.ready_icons if self.icon_words in f"{i[1]} {i[0]}".lower()] if self.icon_words                 else [i for i in self.ready_icons if self.icon_group in (_ALL_SITES, i[0])]
        for child in self.ready.winfo_children():
            child.destroy()
        self.icon_pictures = []  # Tk drops an image nothing holds on to
        for i, (_group, name, path) in enumerate(shown[:_SHOWN]):
            picture = _shrunk(_photo(path.read_bytes(), self), px(28))
            self.icon_pictures.append(picture)
            icon = tk.Label(self.ready, image=picture, cursor="hand2", padx=px(4), pady=px(4))
            icon.grid(row=i // 9, column=i % 9)
            icon.bind("<Button-1>", lambda _e, p=path: self._set_icon(p.read_bytes()))
            Tooltip(icon, lambda _e, n=name: n)
        if not shown:
            role(tk.Label(self.ready, text="No icon by that name."), fg="dim").grid(row=0, column=0, pady=px(8))
        elif len(shown) > _SHOWN:  # never cut quietly: say how many are left and how to reach them
            role(tk.Label(self.ready, text=f"+{len(shown) - _SHOWN} more — pick a group, or search"), fg="dim")                 .grid(row=_SHOWN // 9 + 1, column=0, columnspan=9, sticky="w", pady=(px(4), 0))

    def _set_icon(self, data: bytes):
        try:
            self.icon_png = _square_png(data, self)
        except tk.TclError:
            self._clear_icon()
            self.bar.say("That picture can't be read: use a PNG or a GIF.")
            return
        picture = _shrunk(_photo(self.icon_png, self), px(64))
        self.pictures.append(picture)
        self.preview.configure(image=picture)
        self.preview.tkraise()

    def _clear_icon(self):
        self.icon_png = b""
        self.placeholder.tkraise()

    def _pick_icon(self):
        path = filedialog.askopenfilename(parent=self, title="Pick an icon (any shape — it gets squared off)",
                                          filetypes=[("PNG or GIF", "*.png *.gif")])
        if path:
            try:
                with open(path, "rb") as f:
                    self._set_icon(f.read())
            except OSError as exc:
                self.bar.say(f"Couldn't read it: {exc.strerror}")

    def _on_fetch(self):
        text = self.url.get().strip()
        if not text or self.busy:
            return
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say(f"Reading {text}…")
        self.run_async(lambda: webapps.fetch_meta(text), self._on_fetched)

    def _on_fetched(self, meta):
        url, name, icon, guessed = meta
        self.bar.done()
        self.set_busy(False)
        for entry, value in ((self.address, url), (self.name, name)):
            entry.delete(0, "end")
            entry.insert(0, value)
        if icon:
            self._set_icon(icon)
        self.bar.say("The site couldn't be read, so the name is a guess from the address — check it." if guessed
                     else "Check the name and icon, then add it.")

    # ---- the list ----

    def reload(self):
        self.browsers = webapps.find_browsers()
        for child in self.browser_row.winfo_children():
            child.destroy()
        if self.browsers:
            self.browser = self.browsers[0]
            filter_pill(self.browser_row, [b.name for b in self.browsers],
                        lambda name: setattr(self, "browser", next(b for b in self.browsers if b.name == name)))
            recolour(self.browser_row, THEME["card"])
            self.bar.say("Each web app opens in its own window, with its own login.")
        else:
            self.bar.say("Web Apps runs on Edge, Chrome or Brave, and none was found.")
        self.add_button.set_enabled(bool(self.browsers))
        self._show_apps()

    def _show_apps(self):
        for child in self.list.winfo_children():
            child.destroy()
        apps = webapps.list_apps()
        for app in apps:
            self._app_row(app)
        if not apps:
            role(tk.Label(self.list, text="Nothing added yet.", anchor="w"), fg="dim").pack(fill="x", pady=px(8))
        recolour(self.list, THEME["card"])

    def _app_row(self, app):
        row = tk.Frame(self.list)
        row.pack(fill="x", pady=px(4))
        data, picture = webapps.icon_png(app), None
        try:
            picture = _shrunk(_photo(data, self), px(32)) if data else None
        except tk.TclError:
            pass
        if picture:
            self.pictures.append(picture)
            tk.Label(row, image=picture).pack(side="left", padx=(0, px(10)))
        else:  # added with no picture: the shortcut has the browser's icon
            Icon(row, "web", 32, "dim").pack(side="left", padx=(0, px(10)))
        words = tk.Frame(row)
        words.pack(side="left", fill="x", expand=True)
        tk.Label(words, text=app.name, font=FONTS["bold"], anchor="w").pack(fill="x")
        role(tk.Label(words, text=f"{app.url} · {app.browser}", anchor="w"), fg="dim").pack(fill="x")
        Button(row, "Remove", lambda: self._on_remove(app), "destructive").pack(side="right")
        Button(row, "Open", lambda: webapps.launch(app)).pack(side="right", padx=(0, px(6)))

    def _on_add(self):
        url = self.address.get().strip() or self.url.get().strip()
        if not self.browser:
            info(self.winfo_toplevel(), "No browser", "Web Apps runs on Edge, Chrome or Brave. Install one from "
                 "App Manager first.")
            return
        if not url or "." not in webapps.host_of(webapps.normalise(url)):
            info(self.winfo_toplevel(), "No address", "Paste the site's address and press Fetch first.")
            return
        name = self.name.get().strip() or webapps.pretty_host(webapps.host_of(webapps.normalise(url)))
        try:
            webapps.create(name, url, self.icon_png, self.browser)
        except OSError as exc:
            info(self.winfo_toplevel(), "Couldn't add it", str(exc))
            return
        self.bar.say(f"{name} is in the Start menu, opening in {self.browser.name}.")
        for entry in (self.url, self.name, self.address):
            entry.delete(0, "end")
        self._clear_icon()
        self._show_apps()

    def _on_remove(self, app):
        if not confirm(self.winfo_toplevel(), f"Remove {app.name}?",
                       ["Its Start menu shortcut and icon go, and so does its login:",
                        "you'd sign in again if you add it back. Nothing on the website changes."], "Remove"):
            return
        webapps.remove(app)
        self.bar.say(f"{app.name} removed.")
        self._show_apps()
