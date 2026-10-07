"""Builds the real window, drives the parts that are easy to get wrong
(all four themes, row drawing, filtering, the select-all circle's rules,
Home's rows, every other tool's page, the update notice, the line loader)
against synthetic data, and tears it down.
`python tests/test_gui_smoke.py`.

Separate from test_core.py because it needs tkinter and a desktop session:
it skips cleanly where there's neither, so the same command works on a
developer's Windows box and in CI.
"""

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from uninstaller.cleanup import Location
from uninstaller.defrag import Volume
from uninstaller.diagnose import Fix, Result
from uninstaller.drivers import Driver
from uninstaller.models import App, Risk, Source
from uninstaller.updates import WINDOWS_UPDATE, WINGET, Update

_FIXTURES = [
    App(name="Spotify", id="Spotify", source=Source.INSTALLER, version="1.2.3",
        size_bytes=180 * 1024 * 1024, risk=Risk.SAFE, risk_reason="A standalone app."),
    App(name="Microsoft Visual C++ 2022 Redistributable", id="{guid}",
        source=Source.INSTALLER, version="14.38", risk=Risk.CAUTION,
        risk_reason="A shared runtime other programs are built against."),
    App(name="Microsoft.VCLibs.140.00", id="Microsoft.VCLibs.140.00_14.0_x64__8we",
        source=Source.STORE, version="14.0", risk=Risk.CRITICAL,
        risk_reason="A shared framework package."),
    App(name="neovim", id="neovim", source=Source.SCOOP, version="0.9.5", risk=Risk.SAFE,
        risk_reason="Lives inside your Scoop directory."),
]


def main() -> int:
    try:
        import tkinter
    except ImportError:
        print("skip: tkinter is not installed")
        return 0

    from uninstaller import appmanager, databases, gui
    from uninstaller.catalog import CATALOG
    from uninstaller.webapps import READY_ICONS
    from uninstaller.widgets import THEMES

    gui._SETTINGS = Path(tempfile.mkdtemp()) / "settings.json"  # leave the real theme choice alone
    try:
        window = gui.UninstallerWindow()
    except tkinter.TclError as exc:
        print(f"skip: no display available ({exc})")
        return 0

    window.withdraw()  # keep CI from flashing a window around
    pages = {p.title: p for p in window.pages}
    home, page = pages["Home"], pages["Uninstall"]
    deadline = time.monotonic() + 30
    while page.busy and time.monotonic() < deadline:  # the real scan at startup, or it lands on the fixtures
        window.update()
        time.sleep(0.02)
    page._on_scan_done(_FIXTURES)
    assert len(page.visible) == 4, "every app should get a row"

    page._on_select_all()
    selected = {page.apps[i].name for i in page.selected}
    assert "Microsoft.VCLibs.140.00" not in selected, "the circle must skip Critical"
    assert len(selected) == 3 and page._ticked() == "all"
    page._on_select_all()
    assert not page.selected and page._ticked() == "none", "a full circle clears"

    critical = next(i for i, app in enumerate(page.apps) if app.risk == Risk.CRITICAL)
    page.selected.add(critical)  # ticked by hand
    assert page._ticked() == "some"
    page.source_filter = Source.STORE.value
    page._refresh_rows()
    assert [page.apps[i].name for i in page.visible] == ["Microsoft.VCLibs.140.00"]
    page._on_select_all()
    assert not page.selected, "with only Critical rows on screen, the circle clears them"

    page.source_filter = "All sources"
    page.search_text = "vclibs"
    page._refresh_rows()
    assert len(page.visible) == 1

    home._on_static(([("Windows", "Windows 11 Pro 24H2")], "3 h 2 min",
                     [("Secure Boot", "On", "Only signed boot loaders can start.", "Good")]))
    home._on_live(((6 << 30, 16 << 30), [("C:", "Windows · NTFS", 460 << 30, 476 << 30)]))
    # The other tools, on synthetic rows. Their own scans may still be running;
    # a result landing afterwards only replaces what's drawn.
    updates_page = pages["Updates"]
    updates_page._on_found([Update("Firefox", "Mozilla.Firefox", WINGET, "128.0", "129.0", detail="winget"),
                            Update("2024-09 Cumulative Update (KB5043076)", "abc", WINDOWS_UPDATE, "", "KB5043076",
                                   500 << 20, "KB5043076")])
    updates_page.table.toggle_all()
    assert len(updates_page.table.chosen()) == 2
    updates_page._on_filter(WINGET)
    assert len(updates_page.table.visible) == 1

    drivers_page = pages["Drivers"]
    drivers_page._on_scanned([Driver("Intel UHD", "Display", "30.0", "2022-01-01", "Windows driver", "u1", "31.0"),
                              Driver("Realtek Audio", "Audio", "6.0", "2021-05-05", "Windows driver")])
    drivers_page.table.toggle_all()
    assert [d.name for d in drivers_page.table.chosen()] == ["Intel UHD"], "only rows with an update tick"

    cleanup_page = pages["Cleanup"]
    cleanup_page._on_scanned([Location("Crash dumps", "CrashDumps", Risk.SAFE, "Snapshots.", [("a", 10)]),
                              Location("Recycle Bin", "Clear-RecycleBin", Risk.CAUTION, "Yours.", [("bin", 99)],
                                       "Clear-RecycleBin")])
    cleanup_page._on_filter("Caution")
    assert [loc.name for loc in (cleanup_page.table.items[i] for i in cleanup_page.table.visible)] == ["Recycle Bin"]

    defrag_page = pages["Defrag"]
    defrag_page._on_scanned([Volume("C:", "NTFS", "Windows", 500 << 30, 100 << 30, "Disk 0 · SSD", "SSD", "trim", "SSD"),
                             Volume("E:", "exFAT", "Stick", 32 << 30, 1 << 30, "Disk 1", "", "", "Can't.")])
    defrag_page.ticks["C:"].set(True)
    assert [v.letter for v in defrag_page._chosen()] == ["C:"]

    diagnose_page = pages["Diagnose"]
    diagnose_page.terminal.print("▶ Services · services.msc")
    diagnose_page.terminal.print("$ Get-CimInstance Win32_Service")
    diagnose_page._show_result(3, Result("Problem", "1 service failed.", ["Spooler: error 1"],
                                         Fix("Start 1 service", "Start-Service -Name 'Spooler'")))
    assert diagnose_page.fix_buttons, "a fix gets its button"

    apps_page = pages["App Manager"]
    apps_page._on_checked([appmanager.Status(i % 2 == 0, "1.0", "winget") for i in range(len(CATALOG))])
    apps_page.table.toggle_all()
    assert apps_page.table.chosen() and not any(apps_page.statuses[a].installed for a in apps_page.table.chosen()), \
        "only apps not installed tick"
    apps_page._set(state="Installed")
    assert all(apps_page.statuses[apps_page.table.items[i]].installed for i in apps_page.table.visible)
    apps_page._set(state="Any status")

    # An app's details: what it does, the manual command, the "After installing"
    # card only for apps that have steps, and the database panel only for the
    # two servers. Closing puts the panel away and forgets any password typed.
    by_name = {a.name: a for a in CATALOG}
    apps_page._open(by_name["Cloudflare WARP"])
    above = lambda w: apps_page.body.winfo_children().index(w)
    assert above(apps_page.details) > above(apps_page.table), "the details are raised over the tiles"
    assert apps_page.detail_name.cget("text") == "Cloudflare WARP"
    assert "winget install --id Cloudflare.Warp" in apps_page.detail_steps.cget("text")
    assert apps_page.setup_card.winfo_manager(), "WARP has steps after installing"
    apps_page._open(by_name["VLC"])
    assert not apps_page.setup_card.winfo_manager(), "VLC has none"
    assert not any(p.winfo_manager() for p in apps_page.panels.values()), "and no panel"
    apps_page._open(by_name["MySQL"])
    panel = apps_page.panels[by_name["MySQL"]]
    assert panel.winfo_manager(), "MySQL's details carry its panel"
    panel.server = databases.MySQL(client=("mysql",))
    panel.server.root_password = "kept for this visit"
    panel.listing = databases.parse_listing("u\troot\t@localhost\nu\tapp\t@localhost\nd\tmysql\t\nd\tshop\tapp\n")
    panel._show_listing()
    rows = [r.winfo_children() for r in panel.users.winfo_children()]
    assert len(rows) == 2 and len(rows[0]) < len(rows[1]), "root is locked down, app is not"
    assert len(panel.databases.winfo_children()) == 2
    apps_page._close()
    assert panel.server.root_password is None and panel.listing is None, "the password goes with the visit"
    assert above(apps_page.table) > above(apps_page.details), "and the tiles back over them"

    web_page = pages["Web Apps"]
    web_page._set_icon(next(READY_ICONS.glob("*/*.png")).read_bytes())  # squared and saved through Tk
    assert web_page.icon_png[:8] == b"\x89PNG\r\n\x1a\n"
    web_page._show_icons(group="Google")  # one group, then a search across them all
    assert 0 < len(web_page.ready.winfo_children()) < 30
    web_page._show_icons(words="notion")
    assert len(web_page.ready.winfo_children()) == 1

    for name in THEMES:  # every palette applied for real, pages redrawn in it
        window.apply_theme(name)
    for i in reversed(range(len(window.pages))):
        window.show(i)
    window._on_checked(({"tag_name": "v9.9.9"}, ""), quiet=True)  # the update notice and the dock's mark
    assert window.update_button.marked
    # A check that couldn't reach GitHub says so instead of claiming this is the
    # newest, and says nothing at all when it ran by itself at startup.
    window._on_checked((None, "getaddrinfo failed"), quiet=False)
    assert "Couldn't ask GitHub" in window.notice.status.cget("text")
    window.notice.place_forget()
    window._on_checked((None, "getaddrinfo failed"), quiet=True)
    assert not window.notice.winfo_ismapped()
    window._on_checked((None, ""), quiet=False)
    assert "is the newest" in window.notice.status.cget("text")

    page.bar.slice(0.0, 0.5)
    page.bar.settle(0.5, ok=False)
    page.bar.pulse()
    page.bar.done()

    window.update()
    window.destroy()
    print("ok  window built, filtered, themed and torn down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
