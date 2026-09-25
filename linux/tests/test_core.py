"""Runnable self-check for every pure (non-subprocess) function: parsers and
the risk classifier. `python3 tests/test_core.py` or `pytest tests/`.
No fixtures, no framework — see CLAUDE.md / ponytail."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from uninstaller.backends.apt_backend import build_apps, parse_dpkg_query, parse_showmanual
from uninstaller.backends.flatpak_backend import parse_flatpak_list, parse_size
from uninstaller.backends.snap_backend import parse_snap_list
from uninstaller.backends.wine_backend import parse_uninstall_keys
from uninstaller.leftovers import find_leftovers
from uninstaller.models import Risk
from uninstaller.risk import classify_apt, classify_runtime_name


def test_dpkg_query_parse():
    out = "firefox\t117.0\t334900\timportant\t\ngcc-12-base:amd64\t12.3.0\t100\trequired\tyes\n"
    fields = parse_dpkg_query(out)
    assert fields["firefox"]["priority"] == "important"
    assert fields["firefox"]["size_bytes"] == 334900 * 1024
    assert fields["gcc-12-base:amd64"]["essential"] == "yes"


def test_showmanual_and_build_apps():
    manual = parse_showmanual("firefox\nvlc\n\n")
    assert manual == {"firefox", "vlc"}
    fields = {"firefox": {"version": "117.0", "size_bytes": 1000, "priority": "important", "essential": ""}}
    apps = build_apps(manual, fields)
    names = {a.name for a in apps}
    assert names == {"firefox", "vlc"}
    vlc = next(a for a in apps if a.name == "vlc")
    assert vlc.risk == Risk.SAFE  # no dpkg info at all -> defaults safe


def test_classify_apt():
    risk, _reason, is_system = classify_apt("required", "yes")
    assert risk == Risk.CRITICAL and is_system
    risk, _reason, is_system = classify_apt("important", "")
    assert risk == Risk.CAUTION and is_system
    risk, _reason, is_system = classify_apt("optional", "")
    assert risk == Risk.SAFE and not is_system


def test_snap_list_parse_and_runtime_detection():
    out = (
        "Name    Version    Rev   Tracking       Publisher   Notes\n"
        "core20  20230622   1974  latest/stable  canonical✓  base\n"
        "firefox 117.0      3211  latest/stable  mozilla✓    -\n"
    )
    rows = parse_snap_list(out)
    names = {r["name"] for r in rows}
    assert names == {"core20", "firefox"}
    assert classify_runtime_name("core20") is not None
    assert classify_runtime_name("firefox") is None


def test_flatpak_parse():
    size = parse_size("529.4 MB")
    assert 500 * 1024 * 1024 < size < 600 * 1024 * 1024
    rows = parse_flatpak_list("Firefox\torg.mozilla.firefox\t155.0.1\t334.9 MB\n")
    assert rows[0]["id"] == "org.mozilla.firefox"


def test_wine_uninstall_key_parse():
    reg = (
        "[Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Uninstall\\\\MyApp_is1] 1700000000\n"
        "#time=1dd3d0d664bb132\n"
        '"DisplayName"="My Cool App"\n'
        '"DisplayVersion"="2.1"\n'
        '"UninstallString"="C:\\\\Program Files\\\\MyApp\\\\uninst.exe"\n'
        '"EstimatedSize"=dword:00002000\n'
        "\n"
        "[Software\\\\Classes\\\\Msi.Package] 1700000000\n"
        '"NotAnUninstallKey"="ignored"\n'
    )
    entries = parse_uninstall_keys(reg)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["name"] == "My Cool App"
    assert entry["uninstall_string"] == r"C:\Program Files\MyApp\uninst.exe"
    assert entry["size_bytes"] == 0x2000 * 1024


def test_leftovers_name_match():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        (home / ".config" / "coolapp").mkdir(parents=True)
        (home / ".cache" / "unrelated").mkdir(parents=True)
        found = find_leftovers("CoolApp", home=home)
        assert len(found) == 1
        assert found[0].name == "coolapp"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")
