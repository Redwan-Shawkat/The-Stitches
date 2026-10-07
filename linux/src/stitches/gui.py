"""The Stitches window: the selected tool's page, a dock of tool icons centred
under it in groups (names on hover; the logo is Home), and a toast for
Stitches' own updates.
Each page is its own module under pages/; what they share lives in widgets.py."""

import json
import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from . import __version__, selfupdate  # noqa: E402
from .pages.about import AboutPage  # noqa: E402
from .pages.apps import AppsPage  # noqa: E402
from .pages.cleanup import CleanupPage  # noqa: E402
from .pages.defrag import DefragPage  # noqa: E402
from .pages.diagnose import DiagnosePage  # noqa: E402
from .pages.drivers import DriversPage  # noqa: E402
from .pages.home import HomePage  # noqa: E402
from .pages.uninstall import UninstallPage  # noqa: E402
from .pages.webapps import WebAppsPage  # noqa: E402
from .pages.updates import UpdatesPage  # noqa: E402
from .shell import tail  # noqa: E402
from .widgets import CSS, DOCK_CSS, THEME_CSS, THEMES, ActionBar, esc, icon_button, label, run_async, strong  # noqa: E402

APP_ID = "io.github.stitches"
_SETTINGS = Path(GLib.get_user_config_dir()) / "stitches" / "settings.json"
_TOAST_SECONDS = 4
_ICON_PATH = os.path.join(os.path.dirname(__file__), "icon.svg")
# Our own symbolic icons, and stand-ins for ones some icon themes lack
# (cpu, memory…): a theme that has the name still wins.
_ICONS_DIR = os.path.join(os.path.dirname(__file__), "icons")
_THEME_DIRS = ("/usr/share/themes", os.path.expanduser("~/.themes"), os.path.expanduser("~/.local/share/themes"))
_VARIANT_SUFFIXES = ("-dark", "-light", "_dark", "_light", "dark", "light")


def _strip_theme_variant(name: str) -> str:
    """"ZorinPurple-Dark" -> "ZorinPurple", "Adwaita" -> "Adwaita"."""
    low = name.lower()
    for suffix in _VARIANT_SUFFIXES:
        if low.endswith(suffix):
            return name[: len(name) - len(suffix)].rstrip("-_")
    return name


def _list_installed_themes() -> set:
    names = set()
    for d in _THEME_DIRS:
        try:
            names.update(os.listdir(d))
        except OSError:
            pass
    return names


def _find_theme_variant(installed: set, family: str, want_dark: bool):
    """Find the installed theme name that is `family`'s dark/light sibling.

    GTK themes name variants two different ways: a shared base name plus
    "-dark" (Adwaita/Yaru), or two fully separate names (ZorinPurple-Dark /
    ZorinPurple-Light). Matching by stripped family name covers both without
    hardcoding either scheme.
    """
    target = "dark" if want_dark else "light"
    for name in installed:
        if target in name.lower() and _strip_theme_variant(name).lower() == family.lower():
            return name
    return None


def _load_settings() -> dict:
    try:
        return json.loads(_SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def _save_settings(settings: dict):
    try:
        _SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS.write_text(json.dumps(settings))
    except OSError:
        pass  # a theme that isn't remembered is not worth an error dialog


class StitchesWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Stitches")
        self.set_default_size(1180, 760)
        if os.path.exists(_ICON_PATH):
            self.set_icon_from_file(_ICON_PATH)
        visual = self.get_screen().get_rgba_visual()
        if visual and self.get_screen().is_composited():
            self.set_visual(visual)  # lets the Glass theme be see-through; opaque themes paint over it

        gtk_settings = Gtk.Settings.get_default()
        current_theme = gtk_settings.get_property("gtk-theme-name") or "Adwaita"
        self._installed_themes = _list_installed_themes()
        self._theme_family = _strip_theme_variant(current_theme)
        system_dark = "dark" in current_theme.lower() or bool(
            gtk_settings.get_property("gtk-application-prefer-dark-theme"))
        self.settings = _load_settings()
        self.theme_css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(self.get_screen(), self.theme_css,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        self.release = None  # a newer Stitches release, once one has been seen

        # Dock groups: look after the PC, get software, manage it, drivers and drives.
        self.groups = [[HomePage()], [DiagnosePage(), CleanupPage()], [AppsPage(), WebAppsPage()],
                       [UpdatesPage(), UninstallPage()], [DriversPage(), DefragPage()]]
        tools = [page for group in self.groups for page in group]
        self.about = AboutPage(_ICON_PATH, tools)  # in the dock after theme and update, not in a group
        self.pages = [*tools, self.about]
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        for page in self.pages:
            self.stack.add_named(page, page.title)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.pack_start(self.stack, True, True, 0)
        content.pack_start(self._build_dock(), False, False, 0)
        overlay = Gtk.Overlay()
        overlay.add(content)
        overlay.add_overlay(self._build_toast())
        self.add(overlay)
        self.show_all()  # widgets stay invisible in GTK3 until shown
        theme = self.settings.get("theme", "Dark" if system_dark else "Light")
        # Before the dock had its own choice, AMOLED and Glass styled it too.
        self._apply_theme(theme, self.settings.get("dock", theme if theme in ("AMOLED", "Glass") else "Dark"))
        for page in self.pages:
            page.reload()
        run_async(selfupdate.latest, self._on_release_checked, lambda _e: None)

    # ---- dock ----

    def _build_dock(self):
        """One row of icons centred under the page: the tools in their groups
        (one radio group, so exactly one is lit; the logo is Home), then
        theme, update and About, with a divider between each part."""
        dock = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER, margin=10, margin_top=0)
        dock.get_style_context().add_class("dock")
        radios = None  # the first button starts the radio group, and starts lit
        for group in self.groups:
            if radios:
                dock.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
            for page in group:
                button = self._dock_button(page, radios)
                radios = radios or button
                dock.pack_start(button, False, False, 0)
        dock.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        dock.pack_start(self._build_theme_menu(), False, False, 0)
        self.update_button = icon_button("emblem-synchronizing-symbolic", "Check for Stitches updates",
                                         self._on_update_button)
        dock.pack_start(self.update_button, False, False, 0)
        dock.pack_start(self._dock_button(self.about, radios), False, False, 0)
        return dock

    def _dock_button(self, page, group):
        button = Gtk.RadioButton(group=group, draw_indicator=False, tooltip_text=page.title)
        if page.icon:
            icon = Gtk.Image.new_from_icon_name(page.icon, Gtk.IconSize.BUTTON)
            icon.set_pixel_size(18)
            icon.set_margin_top(4)  # room in the corner for the badge, so it doesn't cover the icon
            icon.set_margin_bottom(4)
            icon.set_margin_start(4)
            icon.set_margin_end(4)
        else:  # Home: the logo, as big as an icon and its margins
            icon = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(_ICON_PATH, 26, 26))
            button.set_tooltip_text(f"Home · Stitches {__version__}")
        badge = label("", "badge", "badge-corner", halign=Gtk.Align.END, valign=Gtk.Align.START)
        badge.set_no_show_all(True)
        overlay = Gtk.Overlay()
        overlay.add(icon)
        overlay.add_overlay(badge)
        button.add(overlay)
        button.connect("toggled", lambda b: b.get_active() and self.stack.set_visible_child_name(page.title))
        page.dock_button = button
        page.on_count = lambda: self._show_badge(page, badge)
        return button

    @staticmethod
    def _show_badge(page, badge):
        badge.set_text(str(page.count))
        badge.set_visible(page.count > 0)
        page.dock_button.set_tooltip_text(f"{page.title} · {page.count}" if page.count else page.title)

    # ---- themes ----

    def _build_theme_menu(self):
        """Window and dock themes side by side, picked separately, so any
        mix works: a dark window with a white dock, a light one with a black
        or glass dock."""
        button = Gtk.MenuButton(tooltip_text="Theme", direction=Gtk.ArrowType.UP)
        button.add(Gtk.Image.new_from_icon_name("preferences-desktop-appearance-symbolic", Gtk.IconSize.BUTTON))
        popover = Gtk.Popover()
        options = Gtk.Grid(column_spacing=28, row_spacing=4, margin=10)
        self.theme_radios = {}
        for col, (part, title) in enumerate((("theme", "Window"), ("dock", "Dock"))):
            options.attach(label(title, "card-title"), col, 0, 1, 1)
            group = None
            for row, name in enumerate(THEMES, 1):
                radio = Gtk.RadioButton(label=name, group=group)
                group = group or radio
                radio.connect("toggled", lambda r, p=part, n=name: r.get_active() and self._apply_theme(**{p: n}))
                options.attach(radio, col, row, 1, 1)
                self.theme_radios[part, name] = radio
        options.show_all()
        popover.add(options)
        button.set_popover(popover)
        return button

    def _apply_theme(self, theme=None, dock=None):
        """Either one, or both at startup; the one not given stays as it is."""
        theme, dock = theme or self.settings["theme"], dock or self.settings["dock"]
        theme, dock = (name if name in THEMES else "Dark" for name in (theme, dock))
        dark = theme != "Light"  # AMOLED and Glass sit on the dark variant, for its text colours
        gtk_settings = Gtk.Settings.get_default()
        gtk_settings.set_property("gtk-application-prefer-dark-theme", dark)
        variant = _find_theme_variant(self._installed_themes, self._theme_family, dark)
        if variant:
            gtk_settings.set_property("gtk-theme-name", variant)
        elif not dark and self._theme_family in self._installed_themes:
            gtk_settings.set_property("gtk-theme-name", self._theme_family)
        self.theme_css.load_from_data(THEME_CSS.get(theme, b"") + DOCK_CSS.get(dock, b""))
        self.settings.update(theme=theme, dock=dock)  # before the radios: moving one calls back in here
        for radio in (self.theme_radios["theme", theme], self.theme_radios["dock", dock]):
            if not radio.get_active():
                radio.set_active(True)
        _save_settings(self.settings)

    # ---- Stitches' own updates ----

    def _build_toast(self):
        self.toast = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                                  halign=Gtk.Align.CENTER, valign=Gtk.Align.START, margin_top=14)
        self.toast_bar = ActionBar()
        self.toast_bar.get_style_context().add_class("toast")
        self.toast_bar.set_size_request(520, -1)
        self.toast.add(self.toast_bar)
        return self.toast

    def show_toast(self, markup, buttons=(), timeout=_TOAST_SECONDS, busy=False):
        """Busy: the line sweeps until the next toast replaces this one. Else
        with a timeout the line runs down, and the toast goes when it's out."""
        for child in self.toast_bar.buttons.get_children():
            self.toast_bar.buttons.remove(child)
        for text, callback in buttons:
            self.toast_bar.add_button(text, callback, "suggested-action")
        if not busy:
            self.toast_bar.add_icon_button("window-close-symbolic", "Dismiss", self.hide_toast)
        self.toast_bar.buttons.show_all()
        self.toast_bar.say(markup)
        if busy:
            self.toast_bar.pulse()
        elif timeout:
            self.toast_bar.countdown(timeout, self.hide_toast)
        else:
            self.toast_bar.done()
        self.toast.set_reveal_child(True)

    def hide_toast(self):
        self.toast_bar.done()  # stops a countdown still running
        self.toast.set_reveal_child(False)

    def _on_release_checked(self, outcome, manual=False):
        release, error = outcome
        if release:
            self.release = release
            self.update_button.get_style_context().add_class("has-update")
            self.update_button.set_tooltip_text(f"Update Stitches to {release['tag_name']}")
            self.show_toast(f"{strong('Stitches ' + release['tag_name'])} is out", [("Update", self._install_update)])
        elif not manual:
            return  # the check at startup; a failure there isn't worth saying
        elif error:
            self.show_toast(f"Couldn't ask GitHub for the newest Stitches: {esc(error)}")
        else:
            self.show_toast(f"Stitches {esc(__version__)} is the latest version.")

    def _on_update_button(self):
        if self.release:
            self._install_update()
        else:
            self.show_toast("Checking GitHub for a newer Stitches…", timeout=0, busy=True)
            run_async(selfupdate.latest, lambda r: self._on_release_checked(r, manual=True),
                      lambda e: self.show_toast(f"Couldn't check: {esc(e)}"))

    def _install_update(self):
        tag = self.release["tag_name"]
        self.show_toast(f"Downloading and installing {strong('Stitches ' + tag)}…", timeout=0, busy=True)
        run_async(lambda: selfupdate.install(self.release), lambda result: self._on_installed(tag, *result),
                  lambda e: self._on_installed(tag, False, str(e)))

    def _on_installed(self, tag, ok, message):
        if ok:
            self.show_toast(f"{strong('Stitches ' + tag)} is installed.", [("Restart", selfupdate.restart)], timeout=0)
        else:
            self.show_toast(f"Update failed: {esc(tail(message, 1))}", timeout=0)
            self.toast_bar.settle(1, ok=False)


class StitchesApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        (self.props.active_window or StitchesWindow(self)).present()


def main() -> int:
    # Without this, WM_CLASS defaults to the interpreter name ("python3"),
    # so the desktop shell can't match the running window to our .desktop
    # entry / icon — it shows a generic icon in the dock and alt-tab instead.
    GLib.set_prgname("stitches")
    GLib.set_application_name("Stitches")
    Gtk.IconTheme.get_default().append_search_path(_ICONS_DIR)
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    return StitchesApp().run(sys.argv)
