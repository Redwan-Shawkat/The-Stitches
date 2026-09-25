"""Builds the real window, drives the parts that are easy to get wrong
(theme switch, row rendering, filtering, selection rules) against synthetic
apps, and tears it down. `python tests/test_gui_smoke.py`.

Separate from test_core.py because it needs tkinter and a desktop session:
it skips cleanly where there's neither, so the same command works on a
developer's Windows box and in CI.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from uninstaller.models import App, Risk, Source

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

    from uninstaller.gui import UninstallerWindow

    try:
        window = UninstallerWindow()
    except tkinter.TclError as exc:
        print(f"skip: no display available ({exc})")
        return 0

    window.withdraw()  # keep CI from flashing a window around
    window._on_scan_done(_FIXTURES)
    assert len(window.tree.get_children()) == 4, "every app should get a row"

    window._on_select_all()
    selected = {window.apps[i].name for i in window.selected}
    assert "Microsoft.VCLibs.140.00" not in selected, "Select All must skip Critical"
    assert len(selected) == 3
    assert window.tray_list.size() == 3, "the removal tray mirrors the selection"

    window._on_select_none()
    assert not window.selected
    assert window._tray_indices == []

    # Rows are sorted biggest first: Spotify, VC++, VCLibs, neovim.
    window._toggle_row(0)
    window._toggle_row(3, extend=True)
    selected = {window.apps[i].name for i in window.selected}
    assert "Microsoft.VCLibs.140.00" not in selected, "Shift+click range must skip Critical"
    assert len(selected) == 3
    window._toggle_row(0)
    assert len(window.selected) == 2, "a plain click toggles one row off"
    window._on_select_none()

    window.source_filter = Source.SCOOP.value
    window._refresh_rows()
    assert [window.apps[i].name for i in window.visible_rows] == ["neovim"]

    window.source_filter = "All sources"
    window.search_text = "vclibs"
    window._refresh_rows()
    assert len(window.visible_rows) == 1

    for _ in range(2):  # light -> dark -> light, both palettes applied for real
        window._on_theme_toggled()

    window._start_progress_slice(0.0, 0.5)
    window._stop_progress_slice()

    window.update()
    window.destroy()
    print("ok  window built, filtered, themed and torn down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
