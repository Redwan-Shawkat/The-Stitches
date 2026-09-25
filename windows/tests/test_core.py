"""Runnable self-check for every pure (non-subprocess, non-registry) function:
parsers and the risk classifier. `python tests/test_core.py` or `pytest tests/`.
No fixtures, no framework — see CLAUDE.md / ponytail.

These run on any OS on purpose: the backends keep their parsing separate from
their `winreg`/PowerShell calls, so the logic is checkable without a Windows
machine (or a particular machine's installed software) to fixture against.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from uninstaller.backends.choco_backend import build_apps as build_choco_apps, parse_nuspec
from uninstaller.backends.registry_backend import (
    build_apps as build_registry_apps,
    is_listable,
    uninstall_command_line,
)
from uninstaller.backends.scoop_backend import parse_manifest, read_packages
from uninstaller.backends.store_backend import build_apps as build_store_apps, parse_appx_csv
from uninstaller.leftovers import find_leftovers
from uninstaller.models import Risk, Source
from uninstaller.risk import classify_installer, classify_store_package

_MSI_KEY = "{11111111-2222-3333-4444-555555555555}"


def test_registry_entry_filtering():
    assert is_listable({"name": "Spotify"})
    assert not is_listable({"name": ""})  # no DisplayName: a stub key, not a program
    assert not is_listable({"name": "KB5031354", "release_type": "Security Update"})
    assert not is_listable({"name": "Patch", "parent": "{parent-guid}"})


def test_uninstall_command_line():
    # An MSI's own UninstallString opens the interactive repair dialog, so it
    # gets rewritten to a real quiet removal.
    assert uninstall_command_line(
        {"key": _MSI_KEY, "windows_installer": True, "uninstall_string": f"MsiExec.exe /I{_MSI_KEY}"}
    ) == f"msiexec /x {_MSI_KEY} /qn /norestart"
    # A published silent uninstall wins over everything else.
    assert uninstall_command_line(
        {"key": _MSI_KEY, "windows_installer": True, "quiet_uninstall_string": "quiet.exe /S"}
    ) == "quiet.exe /S"
    # A plain EXE installer is used as registered.
    assert uninstall_command_line(
        {"key": "Spotify", "uninstall_string": r"C:\Users\me\Spotify\Uninstall.exe /S"}
    ) == r"C:\Users\me\Spotify\Uninstall.exe /S"
    assert uninstall_command_line({"key": "Nothing"}) == ""


def test_split_command():
    # Windows' own argv parser, via ctypes — so Windows-only. IObit's real
    # QuietUninstallString: a quoted path with spaces, then a switch.
    if sys.platform != "win32":
        return
    from uninstaller.elevate import split_command

    exe = r"C:\Program Files (x86)\IObit\IObit Uninstaller\unins000.exe"
    assert split_command(f'"{exe}" /SILENT') == [exe, "/SILENT"]


def test_elevated_cmd_params():
    # Pure string building, so it runs anywhere; the Windows-only check below
    # actually hands it to cmd.exe, which is the part that went wrong.
    from uninstaller.elevate import elevated_cmd_params

    exe = r"C:\Program Files\Windows Defender\MpCmdRun.exe"
    log = Path(tempfile.gettempdir(), "elevated_cmd_test.txt")
    params = elevated_cmd_params([exe, "-h"], log)
    assert params.startswith('/c "'), "the switch must stay outside the quotes"
    if sys.platform != "win32" or not Path(exe).exists():
        return
    import subprocess

    log.unlink(missing_ok=True)
    assert subprocess.run(f"cmd.exe {params}", capture_output=True).returncode == 0
    assert "Antimalware" in log.read_text(errors="replace"), "the spaced path must run"
    log.unlink()


def test_family_of():
    # launcher 10 -> unins000 20 (exited, so absent) -> _iu.tmp 30 -> child 40;
    # 99 is unrelated. The dead 20 is known from an earlier poll.
    from uninstaller.elevate import family_of

    processes = {30: (20, "_iu14D2N.tmp"), 40: (30, "IObitUninstaler.exe"), 99: (1, "x.exe")}
    assert family_of(10, processes, {10, 20}) == {10, 20, 30, 40}
    # Launcher 20 came and went between polls: the chain is broken, but an
    # installer temp copy that's new since launch, with a dead parent, is
    # adopted — along with what it started.
    assert family_of(10, processes, {10}, frozenset({99})) == {10, 30, 40}
    # The same copy already running before launch isn't ours.
    assert family_of(10, processes, {10}, frozenset({30, 40, 99})) == {10}
    # An ordinary orphan (not a temp copy) isn't guessed at.
    assert family_of(10, {50: (20, "notepad.exe")}, {10}) == {10}


def test_classify_installer():
    risk, _reason, is_system = classify_installer("Realtek High Definition Audio Driver", False, "")
    assert risk == Risk.CRITICAL and is_system
    risk, _reason, is_system = classify_installer("Some Bundled Thing", True, "")
    assert risk == Risk.CRITICAL and is_system  # SystemComponent=1: hidden by Windows
    risk, _reason, is_system = classify_installer(
        "Microsoft Visual C++ 2015-2022 Redistributable (x64)", False, ""
    )
    assert risk == Risk.CAUTION and is_system
    risk, _reason, is_system = classify_installer("Spotify", False, "")
    assert risk == Risk.SAFE and not is_system


def test_registry_build_apps():
    apps = build_registry_apps(
        [
            {"key": "Spotify", "name": "Spotify", "version": "1.2.3", "size_bytes": 2048,
             "uninstall_string": "u.exe", "scope": "user"},
            {"key": "KB1", "name": "Update for Windows", "release_type": "Update"},
        ]
    )
    assert [a.name for a in apps] == ["Spotify"]  # the patch row is filtered out
    assert apps[0].source == Source.INSTALLER
    assert apps[0].extra["scope"] == "user"  # per-user install: no UAC prompt needed


def test_appx_parse_and_framework_detection():
    out = (
        '"Name","PackageFullName","Version","IsFramework","NonRemovable"\n'
        '"Microsoft.VCLibs.140.00","Microsoft.VCLibs.140.00_14.0.33519.0_x64__8we","14.0.33519.0","True","False"\n'
        '"SpotifyAB.SpotifyMusic","SpotifyAB.SpotifyMusic_1.2.3.0_x86__zpdnekdrzrea0","1.2.3.0","False","False"\n'
    )
    rows = parse_appx_csv(out)
    assert {r["name"] for r in rows} == {"Microsoft.VCLibs.140.00", "SpotifyAB.SpotifyMusic"}
    apps = {a.name: a for a in build_store_apps(rows)}
    assert apps["Microsoft.VCLibs.140.00"].risk == Risk.CRITICAL
    assert apps["SpotifyAB.SpotifyMusic"].risk == Risk.SAFE
    # Removal targets the full name, which is what Remove-AppxPackage needs.
    assert apps["SpotifyAB.SpotifyMusic"].id.startswith("SpotifyAB.SpotifyMusic_1.2.3.0")
    assert classify_store_package("Microsoft.Windows.Photos", False, False)[0] == Risk.CRITICAL


def test_nuspec_parse_and_manager_is_critical():
    nuspec = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://schemas.microsoft.com/packaging/2015/06/nuspec.xsd">'
        "<metadata><id>git</id><version>2.43.0</version><title>Git</title></metadata></package>"
    )
    fields = parse_nuspec(nuspec)
    assert fields == {"id": "git", "version": "2.43.0", "title": "Git"}
    assert parse_nuspec("not xml at all") == {}
    apps = {a.id: a for a in build_choco_apps(
        [{"id": "git", "name": "Git", "version": "2.43.0"},
         {"id": "chocolatey", "name": "Chocolatey", "version": "2.2.2"}]
    )}
    assert apps["git"].risk == Risk.SAFE
    assert apps["chocolatey"].risk == Risk.CRITICAL


def test_scoop_manifest_and_directory_scan():
    assert parse_manifest('{"version": "1.2.3", "bin": "x.exe"}') == "1.2.3"
    assert parse_manifest("{oops") == ""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp, "scoop")
        (root / "apps" / "neovim" / "current").mkdir(parents=True)
        (root / "apps" / "neovim" / "current" / "manifest.json").write_text('{"version":"0.9.5"}')
        (root / "apps" / "half-installed").mkdir(parents=True)  # no manifest: skipped
        packages = read_packages([(root, "user")])
        assert len(packages) == 1
        assert packages[0]["name"] == "neovim" and packages[0]["version"] == "0.9.5"


def test_leftovers_name_match():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        (home / "AppData" / "Roaming" / "CoolApp").mkdir(parents=True)
        (home / "AppData" / "Local" / "unrelated").mkdir(parents=True)
        found = find_leftovers("coolapp", home=home)
        assert len(found) == 1
        assert found[0].name == "CoolApp"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")
