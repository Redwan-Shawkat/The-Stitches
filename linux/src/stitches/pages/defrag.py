"""Defrag: every partition as a tile, grouped by the OS it belongs to (one
card per group, its tiles side by side inside it). Hard disks with ext4,
btrfs or XFS are defragmented and SSDs trimmed. Those get a checkbox (and
their group one that ticks them all); the rest say why not."""

from gi.repository import GLib, Gtk, Pango

from .. import defrag
from ..models import format_size
from ..shell import tail
from ..widgets import Page, card, esc, info, label, scrolled, show_select_all, strong

_ICON = {"HDD": "drive-harddisk-symbolic", "SSD": "drive-harddisk-solidstate-symbolic",
         "USB": "drive-removable-media-symbolic"}
_GROUP_NOTE = {"Boot": "starts the PC, for every OS on it"}


def _status(text: str, ready: bool) -> str:
    return f'<span foreground="#4c5ce6" weight="600">{esc(text)}</span>' if ready else \
        f'<span alpha="60%">{esc(text)}</span>'


class DefragPage(Page):
    title = "Defrag"
    icon = "drive-harddisk-symbolic"

    def __init__(self):
        super().__init__()
        self.drives: list = []
        self.checks, self.statuses, self.groups = {}, {}, []  # by index into drives; groups: (checkbox, handler, indexes)
        self.header_button("view-refresh-symbolic", "Look again", self.reload)
        self.tiles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.body.pack_start(scrolled(self.tiles), True, True, 0)
        self.defrag_button = self.bar.add_button("Optimize selected", self._on_defrag_clicked, "suggested-action")

    def _group(self, name, members):
        """One card: a heading (with a checkbox for the whole group when any
        can be defragmented) over its partitions' tiles, side by side."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=8)
        heading = Gtk.Box(spacing=8)
        ready = [i for i, d in members if d.ready]
        if ready:
            check = Gtk.CheckButton(tooltip_text=f"Select all {name}")
            handler = check.connect("toggled", self._tick_group, ready)
            self.groups.append((check, handler, ready))
            heading.pack_start(check, False, False, 0)
        size = format_size(sum(d.size_bytes for _, d in members))
        heading.pack_start(label(name, "card-title"), False, False, 0)
        heading.pack_start(label(" · ".join([f"{len(members)} partition{'s' * (len(members) != 1)}", size]
                                            + ([_GROUP_NOTE[name]] if name in _GROUP_NOTE else [])), "dim"),
                           False, False, 0)
        box.pack_start(heading, False, False, 0)
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, min_children_per_line=2,
                           max_children_per_line=4, column_spacing=24, row_spacing=12)
        for i, d in members:
            flow.add(self._tile(i, d))
        box.pack_start(flow, False, False, 0)
        return card(box)

    def _tile(self, i, d):
        grid = Gtk.Grid(column_spacing=10, row_spacing=2, margin=4)
        icon = Gtk.Image.new_from_icon_name(_ICON[d.kind], Gtk.IconSize.DND)
        icon.set_pixel_size(28)
        grid.attach(icon, 0, 0, 1, 3)
        grid.attach(label(f"<b>{esc(d.name)}</b>", use_markup=True, hexpand=True,
                          ellipsize=Pango.EllipsizeMode.MIDDLE), 1, 0, 1, 1)
        grid.attach(label(f"{d.device} · {d.fstype} · {format_size(d.size_bytes)} · {d.kind}", "dim"), 1, 1, 2, 1)
        self.statuses[i] = label(_status(d.status, d.ready), use_markup=True, ellipsize=Pango.EllipsizeMode.END,
                                 tooltip_text=d.status)
        grid.attach(self.statuses[i], 1, 2, 2, 1)
        if d.ready:
            self.checks[i] = Gtk.CheckButton(valign=Gtk.Align.START)
            self.checks[i].connect("toggled", lambda _c: self._show_selection())
            grid.attach(self.checks[i], 2, 0, 1, 1)
        return grid

    def _tick_group(self, check, ready):
        on = check.get_active()  # read once: each tick below redraws this checkbox
        for i in ready:
            self.checks[i].set_active(on)

    def _selected(self):
        return [self.drives[i] for i, check in self.checks.items() if check.get_active()]

    def _show_selection(self):
        n = len(self._selected())
        self.defrag_button.set_label(f"Optimize selected · {n}" if n else "Optimize selected")
        for check, handler, ready in self.groups:
            with check.handler_block(handler):  # showing the state mustn't tick the whole group
                show_select_all(check, sum(self.checks[i].get_active() for i in ready), len(ready))

    def reload(self):
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say("Looking at drives…")
        self.run_async(defrag.find_drives, self._on_scan_done)

    def _on_scan_done(self, drives):
        self.bar.done()
        self.drives = drives
        for child in self.tiles.get_children():
            child.destroy()
        self.checks, self.statuses, self.groups = {}, {}, []
        for name in defrag.GROUPS:
            members = [(i, d) for i, d in enumerate(drives) if d.os == name]
            if members:
                self.tiles.pack_start(self._group(name, members), False, False, 0)
        self.tiles.show_all()
        ready = sum(d.ready for d in drives)
        self.subtitle.set_text("Hard disks are defragmented, SSDs trimmed · "
                               + (f"{ready} of {len(drives)} can be optimized" if ready else "nothing to do here"))
        self.bar.say("Defrag: ext4, btrfs and XFS on hard disks. TRIM: SSDs. Runs as root; large drives take a while.")
        self._show_selection()
        self.set_busy(False)

    def _set_status(self, drive, text, ready=False):
        self.statuses[self.drives.index(drive)].set_markup(_status(text, ready))

    def _on_defrag_clicked(self):
        chosen = self._selected()
        if not chosen:
            info(self.window(), "Nothing selected", "Tick one or more drives marked Ready.")
            return
        self.set_busy(True)
        total = len(chosen)

        def work():
            failures = []
            for i, d in enumerate(chosen):
                GLib.idle_add(self._on_drive_start, d, i, total)
                ok, text = defrag.defrag(d)
                if not ok:
                    failures.append((d, text))
                GLib.idle_add(self._on_drive_done, d, ok, i + 1, total)
            return failures

        self.run_async(work, self._on_all_done)

    def _on_drive_start(self, drive, index, total):
        self._set_status(drive, f"{drive.command[1]} running…", ready=True)
        self.bar.say(f"{'Trimming' if drive.kind == 'SSD' else 'Defragmenting'} {strong(drive.name)} · {index + 1} of {total} · asks for your password")
        self.bar.slice(index / total, (index + 1) / total)

    def _on_drive_done(self, drive, ok, done, total):
        self._set_status(drive, "Done" if ok else "Failed")
        self.bar.settle(done / total, ok)

    def _on_all_done(self, failures):
        self.set_busy(False)
        self.bar.say("Optimize finished" + (f" · {len(failures)} failed" if failures else ""))
        if failures:
            info(self.window(), "Some drives weren't optimized",
                 "\n\n".join(f"{d.name}:\n{tail(text, 4)}" for d, text in failures))
