"""About, as on Linux: which Stitches this is, what it's for, and a picture
and a line or two for each tool in the dock, in the dock's order."""

import tkinter as tk

from .. import __version__
from ..selfupdate import REPO
from ..widgets import FONTS, LINE, Icon, Page, px, role

# What each tool does, by page title; a tool with no line here shows just its name.
_WHAT = {
    "Home": "What this PC is and how it's doing: model, Windows, CPU, GPU and memory, the BIOS/UEFI settings "
            "in plain words, and every drive rated Good, Warning or Critical.",
    "Diagnose": "Windows' own health tools in one scan — drive health, chkdsk, failed services, errors since "
                "startup, a memory test — with DISM and sfc as fixes. The Terminal shows every command.",
    "Cleanup": "Windows Update downloads, browser and shader caches, crash dumps, error reports, old temp files "
               "and the Recycle Bin, each with how safe it is to remove. Your own files are never touched.",
    "App Manager": "Install the apps and developer tools people set up a PC with — VS Code, Docker, Node.js, "
                   "Spotify, qBittorrent… — through winget, in bulk. Shows what's installed and at what version.",
    "Web Apps": "Any website as an app: its own Start menu entry, window and icon, and its own login, so the same "
                "site can be added twice for two accounts.",
    "Updates": "Every pending update from Windows Update, winget, Chocolatey and Scoop in one list, updated "
               "together with one permission prompt per source.",
    "Uninstall": "Everything installed — installers, Store apps, Chocolatey and Scoop — with how risky removing "
                 "it is. Removes it, then offers to delete what it left behind.",
    "Drivers": "The display, network, audio, storage and Bluetooth devices with their driver, its release date, "
               "and driver updates from Windows Update.",
    "Defrag": "Every drive, grouped by disk. Hard disks are defragmented and SSDs trimmed, with one prompt for all.",
}


class AboutPage(Page):
    title = "About"
    icon = "about"
    auto_load = False  # nothing here changes while Stitches runs

    def __init__(self, parent, logo, small_logo, tools: list):
        super().__init__(parent)
        self.subtitle.configure(text=f"Stitches {__version__}")
        intro = tk.Frame(self.body)
        intro.pack(fill="x", pady=(0, px(20)))
        if logo:
            tk.Label(intro, image=logo).pack(side="left", padx=(0, px(16)))
        words = tk.Frame(intro)
        words.pack(side="left", fill="x", expand=True)
        tk.Label(words, text=f"Stitches {__version__}", font=FONTS["heading"], anchor="w").pack(fill="x")
        tk.Label(words, anchor="w", justify="left", wraplength=px(820), text=(
            "Looks after a Windows PC in one window: what's installed and what it left behind, updates and drivers, "
            "drives and health — whatever installed the software. Every change asks first, and anything that "
            "needs admin rights asks through Windows' own prompt.")).pack(fill="x")
        role(tk.Label(words, text=f"github.com/{REPO} · MIT licence · also for Linux and Android", anchor="w"),
             fg="dim").pack(fill="x", pady=(px(4), 0))
        grid = tk.Frame(self.body)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure((0, 1), weight=1, uniform="tools")
        for i, page in enumerate(tools):
            self._tool(grid, page, small_logo).grid(row=i // 2, column=i % 2, sticky="nw", padx=(0, px(24)), pady=px(8))
        self.bar.say("Made for people who'd rather not remember dozens of commands.")

    @staticmethod
    def _tool(parent, page, logo):
        row = tk.Frame(parent)
        if page.icon:
            Icon(row, page.icon, 30, LINE).pack(side="left", anchor="n", padx=(0, px(12)))
        elif logo:  # Home: its dock button is the logo
            tk.Label(row, image=logo).pack(side="left", anchor="n", padx=(0, px(12)))
        words = tk.Frame(row)
        words.pack(side="left", fill="x")
        tk.Label(words, text=page.title, font=FONTS["bold"], anchor="w").pack(fill="x")
        role(tk.Label(words, text=_WHAT.get(page.title, ""), anchor="w", justify="left", wraplength=px(430)),
             fg="dim").pack(fill="x")
        return row
