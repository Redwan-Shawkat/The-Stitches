"""Drivers: the hardware a person would recognise, what each device runs
on, when its maker released that, and the updates Windows Update offers.
Every chosen update installs in one go, behind one permission prompt."""

from .. import drivers
from ..elevate import tail
from ..models import format_size
from ..widgets import STATUS_TAG, Page, Table, info

_UPDATE, _CURRENT = ("Update", STATUS_TAG["Info"]), ("Up to date", STATUS_TAG["Good"])


class DriversPage(Page):
    title = "Drivers"
    icon = "chip"

    def __init__(self, parent):
        super().__init__(parent)
        self.header_button("refresh", "Check again", self.reload)
        self.table = Table(self.body, [("DEVICE", 0, "w"), ("WHAT IT IS", 280, "w"), ("VERSION", 170, "w"),
                                       ("RELEASED", 90, "w"), ("STATUS", 90, "w")],
                           self._cells, self._show_selection, tickable=lambda d: bool(d.update_id),
                           tooltip=lambda d: d.purpose, locked=lambda: self.busy, circle="Select every update")
        self.table.pack(fill="both", expand=True)
        self.bar.add_button("Update selected", self._on_update, "suggested")

    @staticmethod
    def _cells(d):
        version = f"{d.version or '—'} → {d.new_version}" if d.update_id else d.version or "—"
        text, colours = _UPDATE if d.update_id else _CURRENT
        return [[d.name, ("dim", d.kind)], [("dim", d.purpose)], version, d.released or "—",
                [("tag", text, colours)]]

    def _show_selection(self):
        chosen = self.table.chosen()
        if chosen:
            self.bar.say(f"{len(chosen)} selected · {format_size(sum(d.size_bytes for d in chosen))} to download")
        elif not self.busy:
            waiting = sum(1 for d in self.table.items if d.update_id)
            self.bar.say(f"{waiting} update{'s' * (waiting != 1)} from Windows Update" if waiting else
                         "Windows Update has no newer drivers for this PC")

    def reload(self):
        if self.busy:
            return
        self.set_busy(True)
        self.bar.pulse()
        self.bar.say("Reading devices and asking Windows Update…")
        self.run_async(drivers.scan, self._on_scanned)

    def _on_scanned(self, found):
        self.bar.done()
        self.set_busy(False)
        self.table.show(found, "No devices found")
        self.subtitle.configure(text=f"{len(found)} devices · display, network, audio, storage, Bluetooth, firmware")

    def _on_update(self):
        chosen = self.table.chosen()
        if not chosen:
            info(self.winfo_toplevel(), "Nothing selected", "Tick one or more updates first.")
            return
        self.set_busy(True)
        self.bar.say(f"Updating {len(chosen)} driver(s) through Windows Update…")
        self.bar.slice(0, 1)
        self.run_async(lambda: drivers.update(chosen), self._on_done)

    def _on_done(self, result):
        ok, text = result
        self.set_busy(False)
        self.bar.settle(1, ok)
        self.bar.say("Drivers updated" if ok else "Some drivers didn't update")
        if not ok:
            info(self.winfo_toplevel(), "Some drivers didn't update", tail(text, 6))
        elif "restart" in text:
            info(self.winfo_toplevel(), "Restart to finish", "Windows needs a restart to finish installing them.")
        self.after(800, self.reload)
