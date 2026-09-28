"""Runnable self-check for every pure (non-subprocess, non-registry) function:
parsers, the risk classifier, and the verdicts and plans behind each tool. `python tests/test_core.py` or `pytest tests/`.
No fixtures, no framework — see CLAUDE.md / ponytail.

These run on any OS on purpose: the backends keep their parsing separate from
their `winreg`/PowerShell calls, so the logic is checkable without a Windows
machine (or a particular machine's installed software) to fixture against.
"""

import os
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from uninstaller import cleanup, defrag, diagnose, drivers, selfupdate, updates
from uninstaller.backends.choco_backend import build_apps as build_choco_apps, parse_nuspec
from uninstaller.elevate import clean_output
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
from uninstaller.sysinfo import cpu_name, describe_firmware, pick_model, uptime_text, usage_status, windows_name

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


def test_home_readings_in_words():
    # Windows 11 still calls itself "Windows 10" in ProductName; the build says which.
    assert windows_name("Windows 10 Pro", "24H2", "26100", 4061) == "Windows 11 Pro 24H2 · build 26100.4061"
    assert windows_name("Windows 10 Home", "22H2", "19045", 3803) == "Windows 10 Home 22H2 · build 19045.3803"
    assert cpu_name("Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz", 8) == "Intel Core i7-8550U · 8 threads"
    assert cpu_name("AMD Ryzen 7 5800X 8-Core Processor           ", 16) == "AMD Ryzen 7 5800X · 16 threads"
    # A self-built desktop's BIOS leaves the product blank; the board names it instead.
    assert pick_model({"SystemManufacturer": "LENOVO", "SystemProductName": "20XK0015US"}) == "LENOVO 20XK0015US"
    assert pick_model({"SystemManufacturer": "System manufacturer", "SystemProductName": "System Product Name",
                       "BaseBoardManufacturer": "ASUSTeK COMPUTER INC.", "BaseBoardProduct": "PRIME B550M-A"}
                      ) == "ASUSTeK COMPUTER INC. PRIME B550M-A"
    assert uptime_text(2 * 86400 + 5 * 3600 + 12 * 60) == "2 days 5 h 12 min"
    assert uptime_text(3600 + 60) == "1 h 1 min"
    assert [usage_status(u, 100) for u in (50, 85, 95)] == ["Good", "Warning", "Critical"]
    rows = {r[0]: r for r in describe_firmware(
        {"bios_version": "1.0", "bios_date": "01/02/2017", "uefi": False, "secure_boot": False, "tpm": "",
         "virt": None}, date(2026, 1, 1))}
    assert "newer one" in rows["BIOS"][2]  # 9 years old
    assert rows["Boot mode"][1] == "Legacy BIOS" and "Secure Boot" not in rows  # no Secure Boot without UEFI
    assert rows["TPM"][1] == "Not found" and "Virtualization" not in rows  # Windows couldn't say: left out


def test_winget_table():
    out = (
        "\r   - \r   \\ \r"  # the spinner winget draws before the table
        "Name                               Id                     Version      Available    Source\r\n"
        "-----------------------------------------------------------------------------------------\r\n"
        "Microsoft Visual C++ 2015-2022 Re… Microsoft.VCRedist.2015+.x64 14.36.32532.0 14.40.33810.0 winget\r\n"
        "Mozilla Firefox (x64 en-US)        Mozilla.Firefox        < 128.0      129.0        winget\r\n"
        "5 upgrades available.\r\n"
        "\r\n"
        "1 package has version numbers that cannot be determined. Use --include-unknown to see all results.\r\n"
    )
    found = updates.parse_winget(out)
    assert [u.id for u in found] == ["Microsoft.VCRedist.2015+.x64", "Mozilla.Firefox"]
    assert found[0].name == "Microsoft Visual C++ 2015-2022 Re…" and found[0].new == "14.40.33810.0"
    assert found[1].current == "< 128.0" and found[1].detail == "winget"
    assert updates.parse_winget("No installed package found matching input criteria.") == []


def test_choco_scoop_and_windows_update_parsing():
    choco = updates.parse_choco_outdated("git|2.43.0|2.44.0|false\nnodejs|20.1.0|21.0.0|true\n")
    assert [(u.id, u.current, u.new) for u in choco] == [("git", "2.43.0", "2.44.0")]  # pinned: skipped
    scoop = updates.parse_scoop_status(
        "Name   Installed Version Latest Version Missing Dependencies Info\n"
        "----   ----------------- -------------- -------------------- ----\n"
        "7zip   19.00             23.01\n"
        "gone   1.0                                                   Manifest removed\n")
    assert [(u.name, u.current, u.new) for u in scoop] == [("7zip", "19.00", "23.01")]
    wu = updates.parse_wu("abc-123\t2024-09 Cumulative Update (KB5043076)\t524288000\t5043076\t\t\t\n"
                          "def-456\tIntel - Display - 31.0.101.4502\t0\t\tDisplay\tIntel(R) UHD Graphics\t2023-06-01\n")
    assert wu[0]["kb"] == "5043076" and wu[0]["size"] == 524288000
    assert updates.build_wu_updates(wu[:1])[0].new == "KB5043076"
    assert "'abc-123'" in updates.wu_install_script(["abc-123", "x'; bad"])
    assert "bad" not in updates.wu_install_script(["x'; bad"])  # ids go into PowerShell: only hex and dashes


def test_update_jobs_batch_per_prompt():
    u = lambda n, s: updates.Update(n, n, s, "1", "2")
    jobs = updates.plan_jobs([u("a", updates.WINGET), u("b", updates.WINDOWS_UPDATE), u("c", updates.CHOCOLATEY),
                              u("d", updates.WINDOWS_UPDATE), u("e", updates.WINGET)])
    assert [[x.id for x in job] for job in jobs] == [["b", "d"], ["c"], ["a"], ["e"]]


def test_elevated_output_cleaned():
    # sfc writes UTF-16 and redraws its progress after a carriage return.
    assert clean_output("V\x00e\x00r\x00 1%\r\x00V\x00e\x00r\x00 100%\r\x00\n\x00Done\r\n") == "Ver 100%\r\nDone"


def test_cleanup_temp_and_browser_caches():
    with tempfile.TemporaryDirectory() as tmp:
        root, now = Path(tmp), time.time()
        old, fresh = root / "old", root / "fresh"
        old.mkdir()
        (old / "a.txt").write_text("x")
        fresh.mkdir()
        (fresh / "b.txt").write_text("x")  # a setup still unpacking: the folder is old, its file isn't
        for path in (old, old / "a.txt", fresh):
            os.utime(path, (now - 3 * 86400, now - 3 * 86400))
        assert cleanup.is_stale(old, now - 86400) and not cleanup.is_stale(fresh, now - 86400)
        (root / "Google/Chrome/User Data/Default/Cache").mkdir(parents=True)
        (root / "Google/Chrome/User Data/Default/Bookmarks").write_text("{}")
        (root / "Mozilla/Firefox/Profiles/abc.default/cache2").mkdir(parents=True)
        assert [p.name for p in cleanup.browser_caches(root)] == ["Cache", "cache2"]


def test_drivers_parse_and_merge():
    devices = drivers.parse_devices(
        "Intel(R) UHD Graphics\tDISPLAY\t30.0.1\t2022-01-01\tIntel Corporation\tPCI\\VEN_8086\n"
        "WAN Miniport (IP)\tNET\t10.0\t2006-06-21\tMicrosoft\tSWD\\MSRRAS\\MS_NDISWANIP\n"
        "USB Root Hub\tUSB\t10.0\t2006-06-21\tMicrosoft\tUSB\\ROOT_HUB30\n")
    assert [d.name for d in devices] == ["Intel(R) UHD Graphics"]  # virtual and unlisted classes left out
    rows = drivers.merge(devices, [
        {"id": "u1", "title": "Intel - Display - 31.0.101.4502", "size": 1, "class": "Display",
         "model": "Intel(R) UHD Graphics", "released": "2023-06-01"},
        {"id": "u2", "title": "Lenovo - Firmware - 1.2", "size": 1, "class": "Firmware", "model": "System Firmware",
         "released": ""}])
    assert rows[0].new_version == "31.0.101.4502" and rows[0].released == "2023-06-01"
    assert rows[1].kind == "Firmware" and "whatever OS" in rows[1].purpose
    assert drivers.version_from_title("Some Driver Update") == ""


def test_defrag_plan_and_parse():
    assert defrag.plan("NTFS", "SSD", "NVMe")[0] == "trim"
    assert defrag.plan("NTFS", "HDD", "SATA")[0] == "defragment"
    assert defrag.plan("exFAT", "HDD", "USB")[0] == ""
    assert defrag.plan("FAT32", "", "USB")[0] == ""  # a flash drive
    volumes = defrag.parse_volumes("C\tNTFS\tWindows\t500\t100\t0\tSamsung SSD 970\tSSD\tNVMe\n"
                                   "\x00\tNTFS\t\t1\t1\t0\t\t\t\n")
    assert [(v.letter, v.disk, v.action) for v in volumes] == [("C:", "Disk 0 · Samsung SSD 970 · SSD", "trim")]
    assert "'C', 'D'" in defrag.optimize_script(["C:", "D:"])


def test_diagnose_verdicts():
    assert diagnose.judge_disks([["WD Blue", "HDD", "Healthy", "OK"]]).status == diagnose.OK
    assert diagnose.judge_disks([["WD Blue", "HDD", "Unhealthy", "OK"]]).status == diagnose.PROBLEM
    result = diagnose.judge_volumes([["C", "NTFS", "Healthy", "OK"], ["D", "NTFS", "Warning", "Scan Needed"]])
    assert result.status == diagnose.PROBLEM and result.fix.script == "chkdsk C: /scan; chkdsk D: /scan"
    assert diagnose.failed_services([["a", "A", "1"], ["b", "B", "1077"]]) == [["a", "A", "1"]]
    assert diagnose.count_events("Disk\nDisk\nDCOM\n").most_common(1) == [("Disk", 2)]
    assert diagnose.memory_test(4 << 20) is None


def test_selfupdate_choices():
    assert selfupdate.is_newer("v0.3.0", "0.2.0") and not selfupdate.is_newer("v0.2.0", "0.2.0")
    pf = Path("C:/Program Files")
    assert selfupdate.install_kind(True, pf / "Stitches/Stitches.exe", pf) == "msi"
    assert selfupdate.install_kind(True, Path("C:/Users/me/Downloads/Stitches.exe"), pf) == "exe"
    assert selfupdate.install_kind(False, Path("C:/Python/python.exe"), pf) == "checkout"
    release = {"assets": [{"name": "Stitches.exe"}, {"name": "Stitches-0.3.0-x64.msi"}]}
    assert selfupdate.pick_asset(release, "msi")["name"] == "Stitches-0.3.0-x64.msi"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")
