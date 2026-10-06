"""Web Apps: paste an address, and the site's name and icon are filled in (or
typed and picked by hand when the site can't be read, or picked from the
ready-made ones: site logos and every emoji, in groups as on a keyboard, with
a search). Adding it puts it in the app menu straight away, with a
login of its own. The list on the right opens and removes them; removing
asks first, because the app's login goes with it."""

import io

import cairo
from gi.repository import Gio, GdkPixbuf, GLib, Gtk, Pango, PangoCairo

from .. import webapps
from ..widgets import Page, card, confirm, esc, info, label, scrolled, strong

_ICON_SIZE = 256  # what's saved; GTK and the dock scale it down
_ALL_SITES = "All sites"
# GTK's emoji groups, as Unicode numbers them; 2 is the skin-tone swatches, not emoji to pick.
_EMOJI_GROUPS = {0: "Smileys & people", 1: "Smileys & people", 3: "Animals & nature", 4: "Food & drink",
                 5: "Travel & places", 6: "Activities", 7: "Objects", 8: "Symbols", 9: "Flags"}
_SHOWN = 300  # a search shows at most this many: thousands of buttons take seconds to lay out


def _ready_icons() -> list[tuple]:
    """(group, name, search words, file or emoji): the site logos in
    webicons/<group>/, then GTK's own emoji list, the one its emoji picker
    uses. A GTK that keeps that list some other way just has no emoji."""
    items = [(path.parent.name, path.stem, f"{path.stem} {path.parent.name}".lower(), path)
             for path in sorted(webapps.READY_ICONS.glob("*/*.png"))]
    try:
        data = Gio.resources_lookup_data("/org/gtk/libgtk/emoji/en.data", Gio.ResourceLookupFlags.NONE)
        rows = GLib.Variant.new_from_bytes(GLib.VariantType("a(ausasu)"), data, False).unpack()
    except GLib.Error:
        rows = []
    # A 0 marks where a skin tone would go; without one it's the plain emoji.
    return items + [(_EMOJI_GROUPS[group], name, f"{name} {' '.join(words)}", "".join(chr(c) for c in points if c))
                    for points, name, words, group in rows if group in _EMOJI_GROUPS]


def _emoji_png(text: str) -> bytes:
    """One emoji drawn as a picture, in the colour emoji font."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, _ICON_SIZE, _ICON_SIZE)
    context = cairo.Context(surface)
    layout = PangoCairo.create_layout(context)
    font = Pango.FontDescription()
    font.set_absolute_size(180 * Pango.SCALE)
    layout.set_font_description(font)
    layout.set_text(text, -1)
    ink, _logical = layout.get_pixel_extents()
    scale = min(1.0, 0.9 * _ICON_SIZE / max(ink.width, ink.height, 1))
    context.translate(_ICON_SIZE / 2, _ICON_SIZE / 2)
    context.scale(scale, scale)
    context.move_to(-ink.x - ink.width / 2, -ink.y - ink.height / 2)
    PangoCairo.show_layout(context, layout)
    png = io.BytesIO()
    surface.write_to_png(png)
    return png.getvalue()


def _square_png(data: bytes) -> bytes:
    """Any picture as a square PNG, centred on transparency, so a wide logo
    isn't stretched. Raises GLib.Error for something that isn't a picture."""
    loader = GdkPixbuf.PixbufLoader()
    loader.write(data)
    loader.close()
    picture = loader.get_pixbuf()
    side = max(picture.get_width(), picture.get_height())
    square = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, side, side)
    square.fill(0)
    picture.copy_area(0, 0, picture.get_width(), picture.get_height(), square,
                      (side - picture.get_width()) // 2, (side - picture.get_height()) // 2)
    return square.scale_simple(_ICON_SIZE, _ICON_SIZE, GdkPixbuf.InterpType.BILINEAR).save_to_bufferv("png", [], [])[1]


def _pixbuf(data: bytes, size: int):
    loader = GdkPixbuf.PixbufLoader()
    loader.write(data)
    loader.close()
    return loader.get_pixbuf().scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)


class WebAppsPage(Page):
    title = "Web Apps"
    icon = "web-browser-symbolic"

    def __init__(self):
        super().__init__()
        self.browsers, self.icon_png = [], b""
        self.subtitle.set_text("Any website as an app: its own window, icon and login")
        self.header_button("view-refresh-symbolic", "Look again", self.reload)
        self.body.pack_start(self._build_form(), False, False, 0)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        mine = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10)
        mine.pack_start(label("My web apps", "card-title"), False, False, 0)
        mine.pack_start(label("Add the same site twice for two separate logins — a personal and a work "
                              "account, say.", "dim", wrap=True), False, False, 0)
        mine.pack_start(scrolled(self.list), True, True, 0)
        self.body.pack_start(card(mine), True, True, 0)
        self.add_button = self.bar.add_button("Add web app", self._on_add, "suggested-action")

    # ---- the form ----

    def _build_form(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=10)
        box.pack_start(label("Add a website", "card-title"), False, False, 0)
        box.pack_start(label("Paste a link. The name and icon are filled in for you.", "dim", wrap=True), False, False, 0)
        row = Gtk.Box(spacing=8)
        self.url = Gtk.Entry(placeholder_text="facebook.com", hexpand=True)
        self.url.connect("activate", lambda _e: self._on_fetch())
        row.pack_start(self.url, True, True, 0)
        self.fetch_button = Gtk.Button(label="Fetch")
        self.fetch_button.connect("clicked", lambda _b: self._on_fetch())
        row.pack_start(self.fetch_button, False, False, 0)
        box.pack_start(row, False, False, 0)

        details = Gtk.Grid(column_spacing=12, row_spacing=6, margin_top=8)
        self.preview = Gtk.Image.new_from_icon_name("web-browser", Gtk.IconSize.DIALOG)
        self.preview.set_pixel_size(64)
        details.attach(self.preview, 0, 0, 1, 3)
        change = Gtk.Button(label="Change icon…")
        change.connect("clicked", lambda _b: self._pick_icon())
        details.attach(change, 0, 3, 1, 1)
        self.name = Gtk.Entry(placeholder_text="App name", hexpand=True)
        self.address = Gtk.Entry(placeholder_text="Address")
        self.browser = Gtk.ComboBoxText()
        for row_at, (text, widget) in enumerate((("Name", self.name), ("Address", self.address),
                                                 ("Opens in", self.browser))):
            details.attach(label(text, "dim"), 1, row_at, 1, 1)
            details.attach(widget, 2, row_at, 1, 1)
        box.pack_start(details, False, False, 0)

        self.ready_icons = _ready_icons()
        row = Gtk.Box(spacing=8, margin_top=8)
        row.pack_start(label("Or pick an icon", "dim"), False, False, 0)
        self.icon_search = Gtk.SearchEntry(placeholder_text="Search icons", width_chars=12)
        self.icon_search.connect("search-changed", lambda _e: self._show_icons())
        row.pack_end(self.icon_search, False, False, 0)
        self.icon_group = Gtk.ComboBoxText()
        for group in dict.fromkeys((_ALL_SITES, *(g for g, *_ in self.ready_icons))):
            self.icon_group.append_text(group)
        self.icon_group.set_active(0)
        self.icon_group.connect("changed", lambda _c: self._show_icons())
        row.pack_end(self.icon_group, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.ready = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=8,
                                 max_children_per_line=10, homogeneous=True, valign=Gtk.Align.START)
        icons = scrolled(self.ready)
        icons.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.pack_start(icons, True, True, 0)
        self._show_icons()
        form = card(box)
        form.set_size_request(460, -1)
        return form

    def _show_icons(self):
        """The group picked, as a keyboard's emoji panel shows one; a search looks through every group."""
        words, group = self.icon_search.get_text().strip().lower(), self.icon_group.get_active_text()
        if words:
            shown = [i for i in self.ready_icons if words in i[2]][:_SHOWN]
        else:
            shown = [i for i in self.ready_icons if i[0] == group or (group == _ALL_SITES and not isinstance(i[3], str))]
        for child in self.ready.get_children():
            child.destroy()
        for _group, name, _words, what in shown:
            button = Gtk.Button(tooltip_text=name, relief=Gtk.ReliefStyle.NONE)
            if isinstance(what, str):  # an emoji
                button.add(label(f'<span size="xx-large">{esc(what)}</span>', use_markup=True, xalign=0.5))
                button.connect("clicked", lambda _b, e=what: self._set_icon(_emoji_png(e)))
            else:
                button.add(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(str(what), 28, 28)))
                button.connect("clicked", lambda _b, p=what: self._set_icon(p.read_bytes()))
            self.ready.add(button)
        if not shown:
            self.ready.add(label("No icon by that name.", "dim", margin=8))
        self.ready.show_all()

    def _set_icon(self, data: bytes):
        try:
            self.icon_png = _square_png(data)
            self.preview.set_from_pixbuf(_pixbuf(self.icon_png, 64))
        except GLib.Error:
            self.icon_png = b""
            self.preview.set_from_icon_name("web-browser", Gtk.IconSize.DIALOG)
            self.bar.say("That file isn't a picture GTK can read; pick another.")

    def _pick_icon(self):
        dialog = Gtk.FileChooserDialog(title="Pick an icon (any shape — it gets squared off)",
                                       transient_for=self.window(), action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Use", Gtk.ResponseType.OK)
        pictures = Gtk.FileFilter()
        pictures.set_name("Pictures")
        pictures.add_pixbuf_formats()
        dialog.add_filter(pictures)
        if dialog.run() == Gtk.ResponseType.OK:
            try:
                with open(dialog.get_filename(), "rb") as f:
                    self._set_icon(f.read())
            except OSError as exc:
                self.bar.say(f"Couldn't read it: {esc(exc.strerror)}")
        dialog.destroy()

    def _on_fetch(self):
        text = self.url.get_text().strip()
        if not text:
            return
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say(f"Reading {strong(text)}…")
        self.run_async(lambda: webapps.fetch_meta(text), self._on_fetched)

    def _on_fetched(self, meta):
        url, name, icon, guessed = meta
        self.bar.done()
        self.set_busy(False)
        self.address.set_text(url)
        self.name.set_text(name)
        if icon:
            self._set_icon(icon)
        else:
            self.icon_png = b""
            self.preview.set_from_icon_name("web-browser", Gtk.IconSize.DIALOG)
        self.bar.say("The site couldn't be read, so the name is a guess from the address — check it." if guessed
                     else "Check the name and icon, then add it.")

    # ---- the list ----

    def reload(self):
        self.browsers = webapps.find_browsers()
        self.browser.remove_all()
        for b in self.browsers:
            self.browser.append_text(b.name)
        self.browser.set_active(0)
        self.add_button.set_sensitive(bool(self.browsers))
        self.bar.say("Each web app opens in its own window, with its own login." if self.browsers else "")
        if not self.browsers:
            self.bar.say("Web Apps runs on Chrome, Chromium, Brave, Edge or Vivaldi. Install Chromium or Brave "
                         "from App Manager first.")
        self._show_apps()

    def _show_apps(self):
        for child in self.list.get_children():
            child.destroy()
        apps = webapps.list_apps()
        for app in apps:
            self.list.add(self._app_row(app))
        if not apps:
            self.list.add(label("Nothing added yet.", "dim", margin=12))
        self.list.show_all()
        self.set_count(0)

    def _app_row(self, app):
        row = Gtk.Box(spacing=12, margin=8)
        try:
            image = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(app.icon, 32, 32))
        except GLib.Error:
            image = Gtk.Image.new_from_icon_name("web-browser", Gtk.IconSize.DND)
        row.pack_start(image, False, False, 0)
        words = label(f"<b>{esc(app.name)}</b>\n<span size='small' alpha='60%'>{esc(app.url)} · {esc(app.browser)}</span>",
                      use_markup=True, ellipsize=Pango.EllipsizeMode.END)
        row.pack_start(words, True, True, 0)
        remove = Gtk.Button.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON)
        remove.set_tooltip_text("Remove")
        remove.connect("clicked", lambda _b: self._on_remove(app))
        row.pack_end(remove, False, False, 0)
        open_button = Gtk.Button(label="Open")
        open_button.connect("clicked", lambda _b: webapps.launch(app))
        row.pack_end(open_button, False, False, 0)
        return row

    def _on_add(self):
        name, url = self.name.get_text().strip(), self.address.get_text().strip() or self.url.get_text().strip()
        if not url or "." not in webapps.host_of(webapps.normalise(url)):
            info(self.window(), "No address", "Paste the site's address and press Fetch first.")
            return
        name = name or webapps.pretty_host(webapps.host_of(webapps.normalise(url)))
        browser = self.browsers[self.browser.get_active()]
        try:
            webapps.create(name, url, self.icon_png, browser)
        except OSError as exc:
            info(self.window(), "Couldn't add it", str(exc))
            return
        self.bar.say(f"{strong(name)} is in your app menu, opening in {esc(browser.name)}.")
        for entry in (self.url, self.name, self.address):
            entry.set_text("")
        self.icon_png = b""
        self.preview.set_from_icon_name("web-browser", Gtk.IconSize.DIALOG)
        self._show_apps()

    def _on_remove(self, app):
        if not confirm(self.window(), f"Remove {app.name}?",
                       ["Its menu entry and icon go, and so does its login: you'd sign in again if you add it back.",
                        "Nothing on the website itself changes."], "Remove"):
            return
        webapps.remove(app)
        self.bar.say(f"{strong(app.name)} removed.")
        self._show_apps()
