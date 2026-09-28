"""The Stitches window, as on Linux: the open page, and a dock centred under
it in groups — Home (the logo) | Diagnose, Cleanup | Updates, Uninstall |
Drivers, Defrag | theme, update. Each page is its own module under pages/;
what they share lives in widgets.py. The window also asks GitHub once
whether a newer Stitches is out, and says so in a notice that runs down.

Tkinter rather than GTK3: the Linux build uses PyGObject because Ubuntu ships
it, and the same rung of the ladder points the other way on Windows, where
tkinter is the binding that comes with Python and PyGObject is a multi-
hundred-megabyte MSYS2 runtime to redistribute. See ai-knowledgebase.md.
"""

import base64
import ctypes
import json
import os
import struct
import sys
import threading
import tkinter as tk
from pathlib import Path

from . import __version__, selfupdate
from .pages.cleanup import CleanupPage
from .pages.defrag import DefragPage
from .pages.diagnose import DiagnosePage
from .pages.drivers import DriversPage
from .pages.home import HomePage
from .pages.uninstall import UninstallPage
from .pages.updates import UpdatesPage
from .widgets import THEMES, ActionBar, Dialog, IconButton, Rounded, later, px, role, set_theme, setup

_NOTICE_SECONDS = 4

_ICON_PATH = os.path.join(os.path.dirname(__file__), "icon.ico")
_APP_ID = "io.github.windows-the-uninstaller"
_SETTINGS = Path(os.environ.get("APPDATA") or Path.home() / ".config") / "Stitches" / "settings.json"


def ico_pictures(path) -> dict:
    """The .ico's pictures by size. make_icon.py writes each one as a PNG,
    which Tk reads, see-through edges and all."""
    data = Path(path).read_bytes()
    pictures = {}
    for i in range(struct.unpack_from("<H", data, 4)[0]):
        width, *_, length, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        pictures[width or 256] = tk.PhotoImage(data=base64.b64encode(data[offset:offset + length]).decode())
    return pictures


def _system_theme() -> str:
    """Windows' own app mode, for the first run."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return "Light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "Dark"
    except (ImportError, OSError):
        return "Light"


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


class UninstallerWindow(tk.Tk):
    def __init__(self):
        super().__init__(className="Stitches")
        self.title("Stitches")
        setup(self)
        self.geometry(f"{px(1100)}x{px(720)}")
        self.minsize(px(880), px(560))
        self.icons = ico_pictures(_ICON_PATH) if os.path.exists(_ICON_PATH) else {}
        if self.icons:
            self.iconphoto(True, *(self.icons[size] for size in sorted(self.icons, reverse=True)))
        self.settings = _load_settings()
        self.theme = tk.StringVar()

        content = tk.Frame(self)
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        self.groups = [[HomePage(content)], [DiagnosePage(content), CleanupPage(content)],
                       [UpdatesPage(content), UninstallPage(content)], [DriversPage(content), DefragPage(content)]]
        self.pages = [page for group in self.groups for page in group]
        for page in self.pages:
            page.grid(row=0, column=0, sticky="nsew")
        self._build_dock().pack(side="bottom", pady=(0, px(10)))
        content.pack(fill="both", expand=True)
        self.release, self.updating = None, False
        self._build_notice()

        self.apply_theme(self.settings.get("theme") or _system_theme())
        self.show(0)
        for page in self.pages:
            if page.auto_load:
                page.reload()
        self._check_for_update(quiet=True)

    # ---- dock ----

    def _build_dock(self):
        """One row of icons centred under the page: the pages in their groups
        (the logo is Home), then the theme and update buttons, with a divider
        between each group."""
        dock = role(Rounded(self, radius=18, pad=6), bg="dock", fg="dock_icon", border="bar_border")
        logo = self.icons.get(min(self.icons, key=lambda size: abs(size - px(26)))) if self.icons else None
        self.dock_buttons = []
        for g, group in enumerate(self.groups):
            if g:
                self._separator(dock.inner)
            for page in group:
                name = page.title if page.icon else f"Home · Stitches {__version__}"
                button = IconButton(dock.inner, page.icon or "pc", name,
                                    lambda i=len(self.dock_buttons): self.show(i), hover="dock_hover",
                                    logo=None if page.icon else logo)
                button.pack(side="left", padx=px(2))
                self.dock_buttons.append(button)
        self._separator(dock.inner)
        self.theme_button = IconButton(dock.inner, "theme", "Theme", self._pick_theme, hover="dock_hover")
        self.theme_button.pack(side="left", padx=px(2))
        self.theme_menu = role(tk.Menu(self, tearoff=False), fixed=True)
        for name in THEMES:
            self.theme_menu.add_radiobutton(label=name, value=name, variable=self.theme,
                                            command=lambda n=name: self.apply_theme(n))
        self.update_button = IconButton(dock.inner, "upgrade", f"Stitches {__version__} · check for a newer one",
                                        self._on_update_clicked, hover="dock_hover")
        self.update_button.pack(side="left", padx=px(2))
        dock.fit()
        return dock

    @staticmethod
    def _separator(parent):
        role(tk.Frame(parent, width=1), bg="dock_separator").pack(side="left", fill="y", padx=px(4), pady=px(8))

    def show(self, index: int):
        for i, (page, button) in enumerate(zip(self.pages, self.dock_buttons)):
            button.select(i == index)
            if i == index:
                page.grid()
            else:
                page.grid_remove()

    # ---- self-update ----

    def _build_notice(self):
        """A dark bar over the top of the page, like an action bar, for what
        the updater has to say. A click on its text puts it away."""
        self.notice = ActionBar(self)
        self.notice.action = self.notice.add_button("Update", self._on_update_clicked, "suggested")
        self.notice.status.bind("<Button-1>", lambda _e: self.notice.place_forget())

    def _notify(self, text: str, action=False, busy=False, seconds=None):
        """Show `text`: sweeping while busy, running down over `seconds`, or
        staying until clicked away. `action` offers the Update button."""
        notice = self.notice
        notice.say(text)
        if action:
            notice.action.pack(side="left", padx=(px(8), 0))
        else:
            notice.action.pack_forget()
        notice.fit()
        notice.place(relx=0.5, y=px(14), anchor="n")
        notice.lift()
        if busy:
            notice.pulse()
        elif seconds:
            notice.countdown(seconds, notice.place_forget)
        else:
            notice.done()

    def _check_for_update(self, quiet: bool):
        """Asks GitHub on a thread; `quiet` says nothing when there's nothing new."""
        threading.Thread(target=lambda: later(self._on_checked, selfupdate.latest(), quiet), daemon=True).start()

    def _on_checked(self, release, quiet):
        if release:
            self.release = release
            tag = release.get("tag_name", "")
            self.update_button.mark(True)
            self.update_button.tooltip = f"Update to Stitches {tag}"
            self._notify(f"Stitches {tag} is out. You have {__version__}.", action=True, seconds=_NOTICE_SECONDS)
        elif not quiet:
            self._notify(f"Stitches {__version__} is the newest.", seconds=_NOTICE_SECONDS)

    def _on_update_clicked(self):
        if self.updating:
            return
        if not self.release:
            self._notify("Looking for a newer Stitches…", busy=True)
            self._check_for_update(quiet=False)
            return
        tag = self.release.get("tag_name", "")
        dialog = Dialog(self, f"Update to Stitches {tag}?")
        tk.Label(dialog.body, wraplength=px(440), justify="left", anchor="w", text=(
            "Stitches downloads the new version from its GitHub releases and checks it against GitHub's checksum "
            "before anything is replaced. Then it closes, and the new version opens (after an installed copy, "
            "once Windows Installer is done).")).pack(fill="x")
        dialog.button("Not now")
        dialog.button("Update", True, "suggested")
        if dialog.run() is not True:
            return
        self.updating = True
        self._notify(f"Downloading Stitches {tag}…", busy=True)
        release = self.release
        threading.Thread(target=lambda: later(self._on_installed, *selfupdate.install(release)), daemon=True).start()

    def _on_installed(self, ok, message):
        self.updating = False
        if not ok:
            self._notify(f"Couldn't update: {message}")
            self.notice.settle(1, ok=False)
            return
        selfupdate.restart()
        self.destroy()

    # ---- themes ----

    def _pick_theme(self):
        button, menu = self.theme_button, self.theme_menu
        menu.update_idletasks()
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() - menu.winfo_reqheight() - px(6))

    def apply_theme(self, name: str):
        name = name if name in THEMES else "Dark"
        set_theme(self, name)
        self.attributes("-alpha", 0.9 if name == "Glass" else 1.0)
        self._dark_title_bar(name != "Light")
        self.theme.set(name)
        self.settings["theme"] = name
        _save_settings(self.settings)

    def _dark_title_bar(self, dark: bool):
        """Windows draws the title bar, white unless asked; a white bar over a
        dark window looks broken."""
        if sys.platform != "win32":
            return
        self.update_idletasks()
        hwnd, value = int(self.wm_frame(), 16), ctypes.c_int(dark)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE; 19 before Windows 10 20H1
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                          ctypes.sizeof(value)) == 0:
                break


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
    selfupdate.tidy()
    UninstallerWindow().mainloop()
    return 0
