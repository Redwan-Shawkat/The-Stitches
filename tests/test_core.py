"""Runnable self-check for every pure (non-subprocess) function: parsers,
planners and the risk classifier. `python3 tests/test_core.py` or `pytest tests/`.
No fixtures, no framework — see CLAUDE.md / ponytail."""

import json
import os
import socket
import struct
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from datetime import date

from stitches import cleanup, defrag, diagnose, drivers, selfupdate, sysinfo, updates, vitals
from stitches.backends.local_backend import install_paths
from stitches.backends.apt_backend import build_apps, parse_dpkg_query, parse_showmanual
from stitches.backends.flatpak_backend import parse_flatpak_list, parse_size
from stitches.backends.snap_backend import parse_snap_list
from stitches.backends.wine_backend import parse_uninstall_keys
from stitches.leftovers import find_leftovers
from stitches.models import Risk
from stitches.risk import classify_apt, classify_runtime_name


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



def test_apt_upgradable_and_origin():
    out = (
        "Listing...\n"
        "code/stable 1.139.1-1790309529 amd64 [upgradable from: 1.138.0-1789458761]\n"
        "libaudit1/noble-updates,noble-updates 1:3.1.2-2.1ubuntu0.1 amd64 [upgradable from: 1:3.1.2-2.1build1.1]\n"
    )
    found = updates.parse_apt_upgradable(out)
    assert [(u.name, u.current, u.new) for u in found] == [
        ("code", "1.138.0-1789458761", "1.139.1-1790309529"),
        ("libaudit1", "1:3.1.2-2.1build1.1", "1:3.1.2-2.1ubuntu0.1"),
    ]
    policy = (
        "code:\n  Installed: 1.138.0-1789458761\n  Candidate: 1.139.1-1790309529\n  Version table:\n"
        "     1.139.1-1790309529 500\n        500 https://packages.microsoft.com/repos/code stable/main amd64 Packages\n"
        " *** 1.138.0-1789458761 100\n        100 /var/lib/dpkg/status\n"
        "libaudit1:\n  Installed: 1:3.1.2-2.1build1.1\n  Candidate: 1:3.1.2-2.1ubuntu0.1\n  Version table:\n"
        "     1:3.1.2-2.1ubuntu0.1 500\n        500 http://archive.ubuntu.com/ubuntu noble-updates/main amd64 Packages\n"
    )
    assert updates.parse_apt_policy(policy) == {"code": "packages.microsoft.com", "libaudit1": "archive.ubuntu.com"}


def test_snap_refresh_list():
    out = "Name     Version  Rev   Size   Publisher  Notes\nfirefox  131.0.2  4955  84MB   mozilla✓   -\n"
    assert updates.parse_snap_refresh_list(out) == [{"name": "firefox", "version": "131.0.2", "size": 84 * 1024**2}]
    assert updates.parse_snap_refresh_list("All snaps up to date.\n") == []


def _elf_with_update_info(info: bytes) -> bytes:
    """A minimal 64-bit ELF carrying only a .upd_info section, like the
    runtime at the front of every AppImage."""
    names = b"\0.shstrtab\0.upd_info\0"
    data = info + b"\0" * 8
    shoff = 64 + len(names) + len(data)
    header = b"\x7fELF\x02\x01\x01" + b"\0" * 9 + struct.pack(
        "<HHIQQQIHHHHHH", 2, 62, 1, 0, 0, shoff, 0, 64, 0, 0, 64, 3, 1)
    section = lambda name, off, size: struct.pack("<IIQQQQIIQQ", name, 3, 0, 0, off, size, 0, 0, 1, 0)
    return (header + names + data + section(0, 0, 0) + section(1, 64, len(names))
            + section(11, 64 + len(names), len(data)))


def test_appimage_update_info():
    info = "gh-releases-zsync|localsend|localsend|latest|LocalSend-*-linux-x86-64.AppImage.zsync"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp, "LocalSend-1.15.4-linux-x86-64.AppImage")
        path.write_bytes(_elf_with_update_info(info.encode()))
        assert updates.read_update_info(path) == info
        Path(tmp, "script.AppImage").write_bytes(b"#!/bin/sh\n")
        assert updates.read_update_info(Path(tmp, "script.AppImage")) == ""
    owner, repo, tag, pattern = updates.parse_update_info(info)
    assert (owner, repo, tag, pattern) == ("localsend", "localsend", "latest", "LocalSend-*-linux-x86-64.AppImage")
    assert updates.parse_update_info("zsync|https://example.com/x.zsync") is None
    release = {"assets": [{"name": "LocalSend-1.16.0-linux-x86-64.AppImage.zsync"},
                          {"name": "LocalSend-1.16.0-linux-x86-64.AppImage"}]}
    assert updates.pick_asset(release, pattern)["name"] == "LocalSend-1.16.0-linux-x86-64.AppImage"
    assert updates.version_label(pattern, "LocalSend-1.16.0-linux-x86-64.AppImage", "?") == "1.16.0"
    assert updates.version_label("linuxdeploy-x86_64.AppImage", "linuxdeploy-x86_64.AppImage", "2026-09-20") == "2026-09-20"


def test_update_jobs_batch_password_sources():
    u = lambda name, source: updates.Update(name, name, source, "1", "2")
    jobs = updates.plan_jobs([u("a", "APT"), u("f", "Flatpak"), u("b", "APT"), u("s", "Snap"), u("g", "GitHub")])
    assert [[x.name for x in job] for job in jobs] == [["a", "b"], ["s"], ["f"], ["g"]]
    assert updates.command_for(jobs[0])[:4] == ["pkexec", "apt-get", "install", "--only-upgrade"]
    assert updates.command_for(jobs[0])[-2:] == ["a", "b"]


def test_cleanup_parsers():
    snaps = (
        "Name     Version   Rev    Tracking       Publisher   Notes\n"
        "core22   20240823  1586   latest/stable  canonical✓  base,disabled\n"
        "core22   20240904  1621   latest/stable  canonical✓  base\n"
        "firefox  130.0     4793   latest/stable  mozilla✓    disabled\n"
    )
    assert cleanup.parse_snap_disabled(snaps) == [("core22", "1586"), ("firefox", "4793")]
    unused = (
        "\n        ID                               Branch    Op\n"
        " 1.     org.gnome.Platform               45        r\n"
        " 2.     org.gnome.Platform.Locale        45        r\n"
        "\nProceed with these changes to the system installation? [Y/n]: n\n"
    )
    assert cleanup.parse_flatpak_unused(unused) == [("org.gnome.Platform", "45"), ("org.gnome.Platform.Locale", "45")]
    assert cleanup.parse_flatpak_unused("Nothing unused to uninstall\n") == []


def test_stale_temp_skips_sockets_and_fresh_files():
    uid, cutoff = os.getuid(), time.time() - 86400
    old = cutoff - 60
    with tempfile.TemporaryDirectory() as tmp:
        stale = Path(tmp, "stale")
        stale.write_text("x")
        os.utime(stale, (old, old))
        fresh = Path(tmp, "fresh")
        fresh.write_text("x")
        agent = Path(tmp, "ssh-agent")
        agent.mkdir()
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(agent / "agent.1"))
        os.utime(agent / "agent.1", (old, old), follow_symlinks=False)
        os.utime(agent, (old, old))
        try:
            assert cleanup.is_stale(stale, uid, cutoff)
            assert not cleanup.is_stale(fresh, uid, cutoff)
            assert not cleanup.is_stale(agent, uid, cutoff)  # holds a live socket
            assert not cleanup.is_stale(stale, uid + 1, cutoff)  # someone else's
        finally:
            sock.close()


def test_driver_parsers():
    lspci = (
        "Slot:\t0000:01:00.0\nClass:\tVGA compatible controller [0300]\n"
        "Vendor:\tAdvanced Micro Devices, Inc. [AMD/ATI] [1002]\n"
        "Device:\tOland PRO [Radeon R7 240/340 / Radeon 520] [6613]\nDriver:\tamdgpu\nModule:\tradeon\n\n"
        "Slot:\t0000:00:17.0\nClass:\tSATA controller [0106]\nVendor:\tIntel Corporation [8086]\n"
        "Device:\tB150 Chipset SATA Controller [AHCI Mode] [a102]\nDriver:\tahci\n"
    )
    gpu, sata = drivers.parse_lspci(lspci)
    assert gpu == {"slot": "0000:01:00.0", "code": "0300", "driver": "amdgpu", "name": "AMD/ATI Radeon R7 240/340 / Radeon 520"}
    assert sata["name"] == "Intel B150 Chipset SATA Controller [AHCI Mode]"
    ud = (
        "== /sys/devices/pci0000:00/0000:00:01.0/0000:01:00.0 ==\n"
        "modalias : pci:v000010DEd00002520sv00001028sd00000A83bc03sc00i00\n"
        "vendor   : NVIDIA Corporation\nmodel    : GA106M [GeForce RTX 3060 Mobile / Max-Q]\n"
        "driver   : nvidia-driver-535 - distro non-free\n"
        "driver   : nvidia-driver-560 - distro non-free recommended\n"
        "driver   : xserver-xorg-video-nouveau - distro free builtin\n"
    )
    [nvidia] = drivers.parse_ubuntu_drivers(ud)
    assert nvidia["slot"] == "0000:01:00.0" and nvidia["recommended"] == "nvidia-driver-560"
    assert nvidia["name"] == "NVIDIA GeForce RTX 3060 Mobile / Max-Q"
    fw = ('{"Devices": [{"DeviceId": "abc", "Name": "System Firmware", "Version": "1.25", '
          '"Flags": ["updatable", "needs-reboot"], "Releases": [{"Version": "1.27", "Created": 1745920800}]},'
          '{"DeviceId": "def", "Name": "TPM", "Version": "7", "Flags": ["internal"]}]}')
    assert drivers.parse_fwupd(fw) == [{"id": "abc", "name": "System Firmware", "version": "1.25", "plugin": "",
                                        "flags": ["updatable", "needs-reboot"], "update": "1.27",
                                        "released": {"1.27": "2025-04-29"}}]
    assert drivers.parse_fwupd("No updatable devices") == []
    changelog = ("linux-firmware (20240318-0ubuntu3.3) noble; urgency=medium\n\n  * [SRU] Update DCN 3.5\n\n"
                 " -- Juerg Haefliger <juerg@canonical.com>  Fri, 28 Aug 2026 14:52:48 +0200\n\n"
                 "linux-firmware (20240318-0ubuntu3.2) noble; urgency=medium\n\n"
                 " -- Juerg Haefliger <juerg@canonical.com>  Tue, 14 Jul 2026 10:24:24 +0200\n")
    assert drivers.changelog_date(changelog) == "2026-08-28"  # the newest entry, not the last
    assert drivers.changelog_date("") == "" and drivers.changelog_date(" -- A <a@b>  not a date\n") == ""
    assert drivers.dmi_date("05/11/2016\n") == "2016-05-11" and drivers.dmi_date("") == ""
    d = lambda source: drivers.Driver("x", "", "1", "2", source, source)
    jobs = drivers.plan_jobs([d(drivers.FWUPD), d(drivers.UBUNTU_DRIVERS), d(drivers.LINUX_FIRMWARE)])
    assert [[x.source for x in job] for job in jobs] == [[drivers.UBUNTU_DRIVERS, drivers.LINUX_FIRMWARE], [drivers.FWUPD]]


def test_sysinfo_parsers():
    cpu = "processor\t: 0\nmodel name\t: Intel(R) Core(TM) i3-6100 CPU @ 3.70GHz\nphysical id\t: 0\ncpu cores\t: 2\n"
    assert sysinfo.parse_cpuinfo(cpu, 4) == "Intel Core i3-6100 · 2C / 4T"
    assert sysinfo.parse_meminfo("MemTotal:       16268388 kB\n") == "16 GB"
    assert sysinfo.parse_os_release('NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 24.04.1 LTS"\n') == "Ubuntu 24.04.1 LTS"
    assert sysinfo.pick_board({"sys_vendor": "System manufacturer", "product_name": "System Product Name",
                               "board_vendor": "ASUSTeK COMPUTER INC.", "board_name": "B150M-K",
                               "bios_version": "1801"}) == "ASUSTeK COMPUTER INC. B150M-K · BIOS 1801"
    assert sysinfo.pick_board({"sys_vendor": "Dell Inc.", "product_name": "XPS 15 9510"}) == "Dell Inc. XPS 15 9510"
    assert sysinfo.disk_label(1000204886016) == "1.0 TB" and sysinfo.disk_label(250059350016) == "250 GB"


def test_defrag_plan():
    lsblk = (
        '{"blockdevices": [{"name": "sda", "size": 2000000000000, "fstype": null, "mountpoint": null, '
        '"rota": true, "tran": "sata", "children": ['
        '{"name": "sda1", "size": 1000, "fstype": "ext4", "mountpoint": "/mnt/archive", "rota": true, "tran": null},'
        '{"name": "sda2", "size": 1000, "fstype": "ntfs", "mountpoint": null, "rota": true, "tran": null, '
        '"label": "Games", "parttypename": "Microsoft basic data"},'
        '{"name": "sda3", "size": 1000, "fstype": "swap", "mountpoint": "[SWAP]", "rota": true, "tran": null}]},'
        '{"name": "nvme0n1p2", "size": 1000, "fstype": "ext4", "mountpoint": "/", "rota": false, "tran": "nvme"},'
        '{"name": "sdc1", "size": 1000, "fstype": "btrfs", "mountpoint": "/media/usb", "rota": "1", "tran": "usb"}]}'
    )
    rows = defrag.parse_lsblk(lsblk)
    assert [r["name"] for r in rows] == ["sda1", "sda2", "nvme0n1p2", "sdc1"]  # swap isn't a filesystem
    have = lambda tool: tool == "e4defrag"
    hdd, ntfs, ssd, usb = (defrag.plan(r, which=have) for r in rows)
    assert hdd.ready and hdd.command == ["pkexec", "e4defrag", "/mnt/archive"] and hdd.kind == "HDD"
    assert not ntfs.ready and ntfs.status == "No Linux defrag tool for ntfs"
    assert ntfs.name == "Games" and ntfs.os == "Windows" and hdd.name == "/mnt/archive" and hdd.os == "Linux"
    assert defrag.os_of("vfat", "EFI System") == "Boot" and defrag.os_of("ntfs", "Windows recovery environment") == "Windows"
    assert defrag.os_of("vfat", "EFI (FAT-12/16/32)") == "Boot" and defrag.os_of("exfat", None) == "Other"
    assert not ssd.ready and ssd.kind == "SSD"
    assert not usb.ready and usb.kind == "USB" and usb.status == "Needs btrfs-progs"



def test_temperatures_and_usage():
    assert vitals.temp_status(46, 80, 100) == "Good"
    assert vitals.temp_status(85, 80, 100) == "Warning"
    assert vitals.temp_status(99, None, 100) == "Critical"  # no "high": 20° under critical
    assert vitals.temp_status(80) == "Warning" and vitals.temp_status(60) == "Good"
    cpu = vitals.group_temps("CPU", [("Package id 0", 50, 80, 100)] + [(f"Core {i}", 40 + i, 80, 100) for i in range(8)])
    assert [r.name for r in cpu] == ["CPU · Package id 0", "CPU · hottest of 8 more"] and cpu[1].value == 47
    assert [r.name for r in vitals.group_temps("Motherboard", [("", 27, None, None), ("", 29, None, None)])] == \
        ["Motherboard 1", "Motherboard 2"]
    assert vitals.usage_status(96, 100) == "Critical" and vitals.usage_status(86, 100) == "Warning"
    assert vitals.parse_meminfo("MemTotal:  1024 kB\nMemAvailable:  512 kB\n") == {"MemTotal": 1048576, "MemAvailable": 524288}


def test_drive_health_from_udisks():
    ata = lambda **props: {k: {"type": "x", "data": v} for k, v in props.items()}
    text = json.dumps({"type": "a{oa{sa{sv}}}", "data": [{
        "/org/freedesktop/UDisks2/drives/HDD": {
            "org.freedesktop.UDisks2.Drive": ata(Model="WDC WD10"),
            "org.freedesktop.UDisks2.Drive.Ata": ata(SmartSupported=True, SmartUpdated=1, SmartFailing=False,
                                                     SmartTemperature=312.15, SmartPowerOnSeconds=7200,
                                                     SmartNumBadSectors=3, SmartNumAttributesFailing=0)},
        "/org/freedesktop/UDisks2/drives/NVME": {
            "org.freedesktop.UDisks2.Drive": ata(Model="Samsung 980"),
            "org.freedesktop.UDisks2.NVMe.Controller": ata(SmartUpdated=1, SmartTemperature=310,
                                                           SmartPowerOnHours=5, SmartCriticalWarning=["spare"])},
        "/org/freedesktop/UDisks2/drives/USB": {"org.freedesktop.UDisks2.Drive": ata(Model="Flash")},
        "/org/freedesktop/UDisks2/block_devices/sda": {"org.freedesktop.UDisks2.Block": {}},
    }]})
    hdd, nvme, usb = vitals.parse_drives(text)
    assert (hdd["temp_c"], hdd["hours"], hdd["bad_sectors"]) == (39, 2, 3)
    assert vitals.drive_health(hdd)[0] == "Warning"
    assert nvme["failing"] and vitals.drive_health(nvme)[0] == "Critical"
    assert vitals.drive_health(usb)[0] == "Info"
    assert vitals.parse_drives("not json") == []


def test_firmware_in_words():
    rows = sysinfo.describe_firmware({"bios_vendor": "AMI", "bios_version": "1801", "bios_date": "05/11/2016",
                                      "uefi": True, "secure_boot": True, "tpm": "2", "virt_flag": True, "kvm": False},
                                     date(2026, 9, 28))
    by = {setting: (value, meaning, status) for setting, value, meaning, status in rows}
    assert by["BIOS"][0] == "AMI 1801" and "10 years ago" in by["BIOS"][1]
    assert by["Secure Boot"][::2] == ("On", "Good") and by["TPM"][0] == "2.0"
    assert by["Virtualization"][0] == "Available"  # the CPU can, KVM isn't loaded
    legacy = {s: v for s, v, _, _ in sysinfo.describe_firmware({"uefi": False}, date(2026, 1, 1))}
    assert legacy["Boot mode"] == "Legacy BIOS" and "Secure Boot" not in legacy and legacy["Virtualization"] == "Off"


def test_diagnose_parsers():
    verify = (
        "??5??????   /usr/bin/tampered\n"
        "??5?????? c /etc/edited.conf\n"
        "missing     /usr/lib/gone.so\n"
        "missing     /var/lib/secret (Permission denied)\n"
        "?????????   /boot/vmlinuz-7.0\n"
        "missing     /etc/gtk-3.0/settings.ini.real\n"
    )
    diverted = diagnose.parse_diversions("diversion of /etc/gtk-3.0/settings.ini to /etc/gtk-3.0/settings.ini.real by zorin\n")
    assert diagnose.parse_verify(verify, diverted) == (["/usr/bin/tampered"], ["/usr/lib/gone.so"], 2)
    assert diagnose.parse_owners("coreutils: /usr/bin/tampered\nlibfoo1:amd64, libfoo2: /usr/lib/gone.so\n") == \
        {"/usr/bin/tampered": "coreutils", "/usr/lib/gone.so": "libfoo1:amd64"}
    assert diagnose.parse_failed_units("cups.service loaded failed failed CUPS\n\n") == ["cups.service"]
    counts = diagnose.parse_journal('{"SYSLOG_IDENTIFIER": "kernel"}\n{"_COMM": "gdm3"}\n{"SYSLOG_IDENTIFIER": "kernel"}\nnoise\n')
    assert counts.most_common() == [("kernel", 2), ("gdm3", 1)]
    assert diagnose.memory_test(4 << 20) is None


def test_self_update():
    assert selfupdate.is_newer("v0.3.0", "0.2.0") and not selfupdate.is_newer("v0.2.0", "0.2.0")
    assert selfupdate.is_newer("v0.10.0", "0.9.9")  # numbers, not strings
    home = Path("/home/me")
    assert selfupdate.install_kind(Path("/usr/lib/stitches/stitches"), home) == "deb"
    assert selfupdate.install_kind(home / ".local/lib/stitches/stitches", home) == "user"
    assert selfupdate.install_kind(home / "src/Stitches/src/stitches", home) == "checkout"
    release = {"assets": [{"name": "TheUninstaller.exe"}, {"name": "stitches_0.3.0_all.deb"},
                          {"name": "stitches-0.3.0.tar.gz"}]}
    assert selfupdate.pick_asset(release, "deb")["name"] == "stitches_0.3.0_all.deb"
    assert selfupdate.pick_asset(release, "user")["name"] == "stitches-0.3.0.tar.gz"
    assert selfupdate.pick_asset(release, "checkout") is None


def test_local_install_and_driver_purpose():
    paths = install_paths(Path("/home/me"), "stitches", "io.github.stitches")
    assert [str(p) for p in paths] == ["/home/me/.local/lib/stitches", "/home/me/.local/bin/stitches",
                                       "/home/me/.local/share/applications/io.github.stitches.desktop",
                                       "/home/me/.local/share/icons/hicolor/scalable/apps/io.github.stitches.svg"]
    assert drivers.firmware_purpose("uefi_capsule").startswith("Your motherboard's BIOS/UEFI.")
    assert "Secure Boot" in drivers.firmware_purpose("uefi_kek") and "every OS" in drivers.firmware_purpose("ata")
    assert "AMD graphics" in drivers.linux_firmware_purpose("linux-firmware-amd-graphics")
    assert "Wi-Fi, Bluetooth and graphics" in drivers.linux_firmware_purpose("linux-firmware")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")
