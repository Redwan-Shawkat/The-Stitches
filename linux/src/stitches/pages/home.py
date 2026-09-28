"""Home: what this PC is, what its BIOS settings mean, and how it's doing right
now — temperatures, fans, memory and every partition, each with a plain
Good / Warning / Critical. Live values refresh every few seconds while the
page is on screen. Laid out in three columns plus a storage strip, in a
smaller font, so it all fits on one screen without scrolling: groups with an
icon by each heading, no borders, each only as tall as what it holds."""

import time

from gi.repository import GLib, Gtk, Pango

from .. import sysinfo, vitals
from ..models import format_size
from ..widgets import STATUS_TAG, Page, esc, label, scrolled, tag

_REFRESH_SECONDS = 5
_GAP = 18  # between groups: with no borders, the space is what sets them apart


def _section(title: str, icon: str):
    """A group: its icon and title over a grid to fill; returns (group, grid)."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    heading = Gtk.Box(spacing=6)
    image = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU)
    image.get_style_context().add_class("group-icon")
    heading.pack_start(image, False, False, 0)
    heading.pack_start(label(title.upper(), "card-title"), False, False, 0)
    box.pack_start(heading, False, False, 0)
    grid = Gtk.Grid(column_spacing=10, row_spacing=3)
    # Wrapping, so the grid sizes height-for-width: GTK3 settles that once,
    # the first time the grid is measured, and an empty one would stay sized
    # as if every wrapped line were squeezed to one word wide.
    grid.attach(label("Reading…", "note", wrap=True), 0, 0, 1, 1)
    box.pack_start(grid, False, False, 0)
    return box, grid


def _column(*groups):
    """Groups stacked top to bottom, none stretched past what it holds."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=_GAP, valign=Gtk.Align.START)
    for part in groups:
        box.pack_start(part, False, False, 0)
    return box


def _clear(grid):
    for child in grid.get_children():
        grid.remove(child)


def _bar(used: int, size: int, status: str):
    bar = Gtk.LevelBar(min_value=0, max_value=1, value=used / size if size else 0, hexpand=True,
                       valign=Gtk.Align.CENTER)
    for offset in ("low", "high", "full"):  # the theme's own colours; ours follow the status instead
        bar.remove_offset_value(offset)
    if status != vitals.GOOD:
        bar.get_style_context().add_class(status.lower())
    return bar


class HomePage(Page):
    title = "Home"  # no icon: its dock button is the logo

    def __init__(self):
        super().__init__()
        self._busy = False
        self.header_button("view-refresh-symbolic", "Refresh", self.reload)
        pc, self.pc = _section("This PC", "computer-symbolic")
        fw, self.firmware = _section("BIOS / UEFI settings", "application-x-firmware-symbolic")
        temps, self.temps = _section("Temperatures & fans", "sensors-temperature-symbolic")
        memory, self.memory = _section("Memory", "memory-symbolic")
        storage, self.storage = _section("Storage, per partition", "drive-harddisk-symbolic")
        columns = Gtk.Box(spacing=_GAP, homogeneous=True)
        columns.pack_start(_column(pc, memory), True, True, 0)
        columns.pack_start(_column(fw), True, True, 0)
        columns.pack_start(_column(temps), True, True, 0)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=_GAP)
        page.get_style_context().add_class("compact")
        page.pack_start(columns, False, False, 0)
        page.pack_start(storage, False, False, 0)
        self.body.pack_start(scrolled(page), True, True, 0)  # scrolls only in a window too small for it
        GLib.timeout_add_seconds(_REFRESH_SECONDS, self._tick)

    def reload(self):
        self.bar.pulse()
        self.bar.say("Reading this PC…")
        self.run_async(lambda: (sysinfo.read_spec(), sysinfo.read_firmware()), self._on_static)
        self._refresh()

    def _on_static(self, result):
        spec, firmware = result
        self.bar.done()
        _clear(self.pc)
        for row, (key, value) in enumerate([*spec, ("Up", vitals.uptime())]):
            self.pc.attach(label(key, "dim", yalign=0), 0, row, 1, 1)
            self.pc.attach(label(value, wrap=True, selectable=True, hexpand=True), 1, row, 1, 1)
        _clear(self.firmware)
        for row, (setting, value, meaning, status) in enumerate(firmware):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True, margin_bottom=4)
            box.pack_start(label(f"<b>{esc(setting)}</b>  {esc(value)}", use_markup=True), False, False, 0)
            box.pack_start(label(meaning, "note", wrap=True, max_width_chars=40), False, False, 0)
            self.firmware.attach(box, 0, row, 1, 1)
            self.firmware.attach(label(tag(status, STATUS_TAG[status]), use_markup=True, yalign=0), 1, row, 1, 1)
        self.pc.show_all()
        self.firmware.show_all()
        os_name = next((v for k, v in spec if k == "OS"), "Linux")
        self.subtitle.set_text(f"{os_name} · live readings refresh every {_REFRESH_SECONDS} seconds")

    # ---- live readings ----

    def _tick(self):
        if self.get_mapped() and not self._busy:  # only while on screen
            self._refresh()
        return True

    def _refresh(self):
        self._busy = True
        self.run_async(lambda: (vitals.read_sensors(), vitals.read_drives(), vitals.read_memory(),
                                vitals.read_partitions()), self._on_live)

    def _on_live(self, result):
        (temps, fans), drives, memory, partitions = result
        self._busy = False
        for d in drives:
            if d["temp_c"] is not None:  # drive makers rate most disks for 60 °C and up
                temps.append(vitals.Reading(f"Disk · {d['model']}", d["temp_c"], vitals.temp_status(d["temp_c"], 55, 65)))
        rows = [(r.name, f"{r.value:.0f} °C", r.status) for r in temps] + [(r.name, f"{r.value:.0f} RPM", "") for r in fans]
        self._fill_rows(self.temps, rows, "No temperature sensors are exposed to Linux on this PC.")
        if not fans:
            self.temps.attach(label("Fans: not exposed to Linux on this board.", "note", margin_top=6, tooltip_text=(
                "Usually its sensor chip driver (nct6775, it87…) isn't loaded, or the BIOS keeps the fans to itself.")),
                0, max(len(rows), 1), 3, 1)
            self.temps.show_all()

        _clear(self.memory)
        swap, swap_free = memory.get("SwapTotal", 0), memory.get("SwapFree", 0)
        total, free = memory.get("MemTotal", 0), memory.get("MemAvailable", 0)
        for row, (name, used, size) in enumerate([("RAM", total - free, total), ("Swap", swap - swap_free, swap)]):
            if size:
                self._usage_row(self.memory, row, label(name), used, size, vitals.usage_status(used, size))
        self.memory.show_all()

        _clear(self.storage)
        mounted = [p for p in partitions if p.name != "Not mounted"]
        for row, p in enumerate(mounted):
            name = label(f"<b>{esc(p.name)}</b>  <small>{esc(p.device)} · {esc(p.fstype)}</small>", use_markup=True,
                         width_chars=24, ellipsize=Pango.EllipsizeMode.END)
            self._usage_row(self.storage, row, name, p.used, p.size, p.status)
        idle = [f"{p.device} {p.fstype} {format_size(p.size)}" for p in partitions if p.name == "Not mounted"]
        if idle:
            self.storage.attach(label("Not mounted: " + " · ".join(idle), "note", wrap=True), 0, len(mounted), 4, 1)
        self.storage.show_all()
        self.bar.say(f"Live readings · updated {time.strftime('%H:%M:%S')}")

    @staticmethod
    def _usage_row(grid, row, name, used, size, status):
        """name · bar · "used of size · share" · status tag."""
        grid.attach(name, 0, row, 1, 1)
        grid.attach(_bar(used, size, status), 1, row, 1, 1)
        grid.attach(label(f"{format_size(used)} of {format_size(size)} · {used / size if size else 0:.0%}", "note", xalign=1),
                    2, row, 1, 1)
        grid.attach(label(tag(status, STATUS_TAG[status]), use_markup=True), 3, row, 1, 1)

    @staticmethod
    def _fill_rows(grid, rows, empty: str):
        _clear(grid)
        if not rows:
            grid.attach(label(empty, "note", wrap=True), 0, 0, 3, 1)
        for row, (name, value, status) in enumerate(rows):
            grid.attach(label(name, hexpand=True, ellipsize=Pango.EllipsizeMode.END), 0, row, 1, 1)
            grid.attach(label(value, xalign=1), 1, row, 1, 1)
            if status:
                grid.attach(label(tag(status, STATUS_TAG[status]), use_markup=True), 2, row, 1, 1)
        grid.show_all()
