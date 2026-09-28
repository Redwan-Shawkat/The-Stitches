"""Drivers: the hardware in this machine, what each device runs on, what it
is (and whether it's a Linux driver at all), when its maker released it, and
what can be updated. Where it comes from is an icon; clicking it says. What
an update prints is only shown when it fails, like on Updates."""

from gi.repository import GLib, Gtk

from .. import drivers
from ..shell import tail
from ..widgets import Page, arrow, esc, info, label, make_table, show_select_all, strong, two_lines

COL_SELECTED, COL_DEVICE, COL_PURPOSE, COL_DRIVER, COL_RELEASED, COL_SOURCE, COL_ENABLED, COL_IDX, COL_TIP = range(9)
# source -> (its icon, what clicking the icon says)
_SOURCES = {
    drivers.KERNEL: ("computer-symbolic", "Built into the Linux kernel. It updates with the kernel, in Updates."),
    drivers.UBUNTU_DRIVERS: ("system-software-install-symbolic",
                             "The maker's own driver (NVIDIA, Broadcom…), packaged by Ubuntu and installed with "
                             "ubuntu-drivers."),
    drivers.FWUPD: ("weather-overcast-symbolic",
                    "Firmware the device's maker publishes on the Linux Vendor Firmware Service (LVFS), installed "
                    "with fwupd."),
    drivers.LINUX_FIRMWARE: ("package-x-generic-symbolic",
                             "Ubuntu's linux-firmware package: files from the chip makers that Linux loads into the "
                             "hardware."),
}


class DriversPage(Page):
    title = "Drivers"
    icon = "cpu-symbolic"

    def __init__(self):
        super().__init__()
        self.found: list = []
        self.store = Gtk.ListStore(bool, str, str, str, str, str, bool, int, str)
        self.header_button("view-refresh-symbolic", "Detect again", self.reload)

        table, tree, self.select_all = make_table(
            self.store,
            [("DEVICE", COL_DEVICE, True), ("WHAT IT IS", COL_PURPOSE, "wrap"), ("DRIVER", COL_DRIVER, False),
             ("RELEASED", COL_RELEASED, False)],
            on_toggle=self._on_toggled, toggle_col=COL_SELECTED, enabled_col=COL_ENABLED, on_toggle_all=self._select,
        )
        self.source_column = Gtk.TreeViewColumn("SOURCE", Gtk.CellRendererPixbuf(xpad=14), icon_name=COL_SOURCE)
        tree.append_column(self.source_column)
        tree.set_tooltip_column(COL_TIP)
        tree.connect("button-release-event", self._on_tree_click)
        self.source_about = label("", use_markup=True, wrap=True, max_width_chars=38, margin=10)
        self.source_about.show()
        self.source_popover = Gtk.Popover(relative_to=tree)
        self.source_popover.add(self.source_about)
        self.body.pack_start(table, True, True, 0)
        self.update_button = self.bar.add_button("Update selected", self._on_update_clicked, "suggested-action")

    def _on_toggled(self, path):
        self.store[path][COL_SELECTED] = not self.store[path][COL_SELECTED]
        self._show_selection()

    def _select(self, value):
        for row in self.store:
            row[COL_SELECTED] = value and row[COL_ENABLED]
        self._show_selection()

    def _on_tree_click(self, tree, event):
        """A click on a source icon says what that source is, in a popover."""
        hit = tree.get_path_at_pos(int(event.x), int(event.y))
        if not hit or hit[1] != self.source_column:
            return False
        d = self.found[self.store[hit[0]][COL_IDX]]
        self.source_about.set_markup(f"<b>{esc(d.source)}</b>\n{esc(_SOURCES[d.source][1])}")
        area = tree.get_cell_area(hit[0], hit[1])
        area.x, area.y = tree.convert_bin_window_to_widget_coords(area.x, area.y)
        self.source_popover.set_pointing_to(area)
        self.source_popover.popup()
        return True

    def _selected(self):
        return [self.found[row[COL_IDX]] for row in self.store if row[COL_SELECTED]]

    def _show_selection(self):
        n = len(self._selected())
        self.update_button.set_label(f"Update selected · {n}" if n else "Update selected")
        show_select_all(self.select_all, n, sum(row[COL_ENABLED] for row in self.store))
        self.bar.say(f"{strong(f'{n} selected')} · asks for your password" if n else
                     "Most Linux drivers live in the kernel and update with it.")

    # ---- detecting ----

    def reload(self):
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say("Detecting hardware and checking ubuntu-drivers, fwupd and linux-firmware…")
        self.run_async(drivers.find_drivers, self._on_detect_done)

    def _on_detect_done(self, found):
        self.bar.done()
        self.found = found
        self.store.clear()
        for idx, d in enumerate(found):
            detail = " · ".join(p for p in (d.kind, d.note) if p)
            if d.new:
                driver = arrow(d.current, d.new)
            elif d.source == drivers.KERNEL:
                driver = f'<span foreground="#1e8a4c">✓</span> {esc(d.current)}'
            else:
                driver = f'<span foreground="#1e8a4c">✓</span> Up to date\n<span size="small" alpha="60%">{esc(d.current)}</span>'
            self.store.append([False, two_lines(d.device, detail), f'<span size="small">{esc(d.purpose)}</span>',
                               driver, esc(d.released) or '<span alpha="60%">—</span>', _SOURCES[d.source][0],
                               bool(d.new), idx, f"<b>{esc(d.device)}</b> · {esc(d.kind)}\n{esc(d.purpose)}"])
        pending = [d for d in found if d.new]
        sources = sorted({d.source for d in pending})
        self.subtitle.set_text(f"{len(pending)} update{'s' * (len(pending) != 1)} from {', '.join(sources)}"
                               if pending else f"Everything is up to date · {len(found)} devices detected")
        self.set_count(len(pending))
        self._show_selection()
        self.set_busy(False)

    # ---- updating ----

    def _on_update_clicked(self):
        chosen = self._selected()
        if not chosen:
            info(self.window(), "Nothing selected", "Check one or more devices with an update first.")
            return
        self.set_busy(True)
        jobs, total = drivers.plan_jobs(chosen), len(chosen)

        def work():
            done, failures, reboot = 0, [], False
            for job in jobs:
                GLib.idle_add(self._on_job_start, job, done, total)
                ok, text = drivers.apply(job)
                done += len(job)
                failures += [] if ok else [(job, text)]
                reboot |= ok and any(d.note for d in job)
                GLib.idle_add(self.bar.settle, done / total, ok)
            return total, failures, reboot

        self.run_async(work, self._on_all_done)

    def _on_job_start(self, job, done, total):
        names = job[0].device if len(job) == 1 else f"{len(job)} driver packages"
        self.bar.say(f"Updating {strong(names)} · {done + 1} of {total} · asks for your password")
        self.bar.slice(done / total, (done + len(job)) / total)

    def _on_all_done(self, result):
        total, failures, reboot = result
        failed = sum(len(job) for job, _ in failures)
        self.set_busy(False)
        self.bar.say(f"Updated {strong(str(total - failed))} of {total}"
                     + (f" · {failed} failed" if failed else "")
                     + (" · firmware installs on the next reboot" if reboot else ""))
        self.run_async(drivers.find_drivers, self._after_update_detect)
        if failures:
            info(self.window(), "Some drivers weren't updated", "\n\n".join(
                f"{', '.join(d.device for d in job)}:\n{tail(text, 4)}" for job, text in failures))

    def _after_update_detect(self, result):
        status = self.bar.status.get_label()
        self._on_detect_done(result)
        self.bar.say(status)
