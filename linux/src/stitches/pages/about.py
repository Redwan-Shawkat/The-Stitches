"""About: which Stitches this is, what it's for, and a picture and a line or
two for each tool in the dock, in the dock's order."""

from gi.repository import GdkPixbuf, Gtk

from .. import __version__
from ..selfupdate import REPO
from ..widgets import Page, esc, label, scrolled

# What each tool does, by page title; a tool with no line here shows just its name.
_WHAT = {
    "Home": "What this PC is and how it's doing right now: the spec, the BIOS settings in plain words, "
            "temperatures and fans, memory and every partition, each rated Good, Warning or Critical.",
    "Diagnose": "Linux's sfc /scannow, chkdsk, disk health and memory test in one scan, with a fix "
                "where there is one. The Terminal shows every command as it runs.",
    "Cleanup": "Caches, old Snap revisions, logs, unused Flatpak runtimes, temp files and the Trash, each "
               "with where it lives and how safe it is to remove. Your own files are never touched.",
    "App Manager": "Install the apps and developer tools people set up a Linux PC with — VS Code, Docker, "
                   "Node.js, Spotify, qBittorrent… — through APT, Snap or Flatpak, in bulk. Shows what's "
                   "installed and at what version, however it got there. Click an app for what it does and "
                   "how to install it by hand; PHP's has a switch per extension and a Laravel check, MySQL's "
                   "and PostgreSQL's their users, passwords and databases.",
    "Web Apps": "Any website as an app: its own window, icon and menu entry, and its own login, so the same "
                "site can be added twice for two accounts.",
    "Updates": "Every pending update from APT, Snap, Flatpak and GitHub-released AppImages in one list, "
               "updated together with one password per source.",
    "Uninstall": "Everything installed, whatever installed it, with how risky removing it is. Removes it, "
                 "then offers to delete what it left behind.",
    "Drivers": "The hardware in this PC with the driver it uses, and driver and firmware updates from "
               "ubuntu-drivers, fwupd (LVFS) and linux-firmware.",
    "Defrag": "Every drive, grouped by the OS it belongs to. Hard disks are defragmented, SSDs trimmed.",
}


class AboutPage(Page):
    title = "About"
    icon = "help-about-symbolic"

    def __init__(self, logo_path: str, tools: list):
        super().__init__()
        self.subtitle.set_text(f"Stitches {__version__}")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22, margin_bottom=12)
        intro = Gtk.Box(spacing=18)
        intro.pack_start(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(logo_path, 88, 88)),
                         False, False, 0)
        words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
        words.pack_start(label(f"<span size='x-large' weight='600'>Stitches</span>  "
                               f"<span alpha='60%'>version {esc(__version__)}</span>", use_markup=True), False, False, 0)
        words.pack_start(label("Looks after a Linux PC in one window: what's installed and what it left behind, "
                               "updates and drivers, drives and health — whatever installed the software. "
                               "Every change asks first, and anything that needs admin rights asks for your "
                               "password through the system's own prompt.", wrap=True, max_width_chars=90),
                         False, False, 0)
        words.pack_start(label(f"<a href='https://github.com/{REPO}'>github.com/{esc(REPO)}</a> · MIT licence · "
                               "also for Windows and Android", use_markup=True), False, False, 0)
        intro.pack_start(words, True, True, 0)
        box.pack_start(intro, False, False, 0)

        grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, min_children_per_line=2,
                           max_children_per_line=3, column_spacing=28, row_spacing=18)
        for page in tools:
            grid.add(self._tool(page, logo_path))
        box.pack_start(grid, False, False, 0)
        self.body.pack_start(scrolled(box), True, True, 0)
        self.bar.say("Made for people who'd rather not remember dozens of terminal commands.")

    @staticmethod
    def _tool(page, logo_path):
        row = Gtk.Box(spacing=14, valign=Gtk.Align.START)
        if page.icon:
            image = Gtk.Image.new_from_icon_name(page.icon, Gtk.IconSize.DIALOG)
            image.set_pixel_size(36)
            image.get_style_context().add_class("group-icon")
        else:  # Home: its dock button is the logo
            image = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(logo_path, 36, 36))
        row.pack_start(image, False, False, 0)
        words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        words.pack_start(label(page.title, "row-title"), False, False, 0)
        words.pack_start(label(_WHAT.get(page.title, ""), "dim", wrap=True, max_width_chars=48), False, False, 0)
        row.pack_start(words, True, True, 0)
        return row

    def reload(self):
        pass  # nothing here changes while Stitches runs
