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

from stitches import (appmanager, catalog, cleanup, databases, defrag, diagnose, drivers, php, selfupdate, sysinfo, updates,
                      vitals, webapps)
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
    assert "--ignore-running" in updates.command_for(jobs[1])  # a running snap mustn't fail the batch


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
    assert not ntfs.ready and ntfs.status == "NTFS: defrag it from Windows"
    assert ntfs.name == "Games" and ntfs.os == "Windows" and hdd.name == "/mnt/archive" and hdd.os == "Linux"
    assert defrag.os_of("vfat", "EFI System") == "Boot" and defrag.os_of("ntfs", "Windows recovery environment") == "Windows"
    assert defrag.os_of("vfat", "EFI (FAT-12/16/32)") == "Boot" and defrag.os_of("exfat", None) == "Other"
    assert ssd.kind == "SSD" and not ssd.ready and ssd.status == "Needs util-linux"  # no fstrim in `have`
    ssd = defrag.plan(rows[2], which=lambda tool: True)
    assert ssd.ready and ssd.command == ["pkexec", "fstrim", "-v", "/"]
    assert defrag.plan({**rows[1], "rota": False}).status == "ntfs on an SSD can't be trimmed from Linux"
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


def test_app_manager_detection():
    dpkg = "git\t1:2.43.0-1ubuntu7.3\tii \nvlc\t3.0.20-3\trc \nnodejs\t18.19.1+dfsg-6ubuntu5\thi \n"
    assert appmanager.parse_dpkg(dpkg) == {"git": "1:2.43.0-1ubuntu7.3", "nodejs": "18.19.1+dfsg-6ubuntu5"}  # rc = removed
    assert appmanager.short_version("1:2.43.0-1ubuntu7.3", "APT") == "2.43.0"
    assert appmanager.short_version("2:8.3+93ubuntu2", "APT") == "8.3"
    assert appmanager.short_version("1.2.95.453.g0eeebbed", "Snap") == "1.2.95.453.g0eeebbed"
    assert appmanager.parse_version("go version go1.22.2 linux/amd64") == "1.22.2"
    assert appmanager.parse_version('openjdk version "21.0.2" 2024-01-16') == "21.0.2"
    assert appmanager.parse_version("v20.11.1\n") == "20.11.1" and appmanager.parse_version("nothing") == ""
    assert appmanager.via_path("/home/u/.nvm/versions/node/v20.11.1/bin/node") == "nvm"
    assert appmanager.via_path("/home/u/.cargo/bin/rustc") == "rustup" and appmanager.via_path("/usr/bin/java") == "PATH"
    code = next(a for a in catalog.CATALOG if a.name == "Visual Studio Code")
    node = next(a for a in catalog.CATALOG if a.name == "Node.js")
    none = lambda _c: None
    found = appmanager.detect(code, {"Flatpak": {"com.visualstudio.code": "1.139.1"}}, none)
    assert found.installed and found.version == "1.139.1" and found.via == "Flatpak"  # installed some other way
    nvm = appmanager.detect(node, {"APT": {}}, lambda c: f"/home/u/.nvm/versions/node/v20/bin/{c}")
    assert nvm.installed and nvm.version == "" and nvm.via == "nvm"  # version unknown is not "not installed"
    assert not appmanager.detect(code, {}, none).installed


def test_app_manager_catalog_and_jobs():
    names = [a.name for a in catalog.CATALOG]
    assert len(names) == len(set(names)) and {"qBittorrent", "Spotify"} <= set(names)
    assert all(a.source in catalog.SOURCES and a.category in catalog.CATEGORIES for a in catalog.CATALOG)
    assert all(a.icon.is_file() for a in catalog.CATALOG), "every app has its icon in appicons/"
    pick = lambda *n: [a for a in catalog.CATALOG if a.name in n]
    jobs = appmanager.plan_jobs(pick("Spotify", "Git", "LocalSend", "Visual Studio Code"), have_flatpak=False)
    assert [(s, [a.name for a in b]) for s, b in jobs] == [
        ("APT", ["Git", "Flatpak"]), ("Snap", ["Visual Studio Code", "Spotify"]), ("Flatpak", ["LocalSend"])]
    assert appmanager.plan_jobs(pick("LocalSend"), have_flatpak=True)[0][0] == "Flatpak"
    apt, snap, flat = (appmanager.command_for(s, b) for s, b in jobs)
    assert apt[:4] == ["pkexec", "apt-get", "install", "-y"] and apt[-2:] == ["git", "flatpak"]
    assert snap[:3] == ["pkexec", "sh", "-c"] and "snap install code --classic || rc=1" in snap[3]
    assert "snap install spotify || rc=1" in snap[3] and snap[3].endswith("exit $rc")
    assert flat[3].startswith("flatpak remote-add --if-not-exists flathub") and flat[4:] == ["sh", "org.localsend.localsend_app"]
    assert all(a.about and a.site.startswith("https://") for a in catalog.CATALOG), "every app has its details"
    vs_code, git, local_send = pick("Visual Studio Code")[0], pick("Git")[0], pick("LocalSend")[0]
    assert appmanager.manual_steps(git) == ["sudo apt install git"]
    assert appmanager.manual_steps(vs_code) == ["sudo snap install code --classic"]
    assert appmanager.manual_steps(local_send)[-1] == "flatpak install flathub org.localsend.localsend_app"
    warp = pick("Cloudflare WARP")[0]
    assert all(a.source == "APT" for a in catalog.CATALOG if a.repo), "a vendor repository is an APT one"
    script = appmanager.command_for("APT", [git, warp])[3]  # the repository first, one password for the batch
    assert script.startswith(". /etc/os-release && install -d -m 755 /etc/apt/keyrings && ")
    assert "> /etc/apt/sources.list.d/cloudflare-warp.list && apt-get update -o Dir::Etc::sourcelist=" in script
    assert script.endswith(" git cloudflare-warp")
    assert appmanager.manual_steps(warp)[-1] == "sudo apt install cloudflare-warp"
    assert pick("Avro Phonetic")[0].setup, "Avro's details say how to turn it on"


def test_databases():
    d = databases
    assert d.valid_name("laravel_2") == "" and d.valid_name("thoth-analytics") == "" and d.valid_name("")
    assert d.valid_name("2x") and d.valid_name("a b") and d.valid_name("a`b")
    assert d.valid_name('x"; DROP') and d.valid_name("a" * 33) and d.valid_name("a" * 32) == ""
    assert d.valid_password("p", "p") == "" and d.valid_password("p", "q") and d.valid_password("a\nb", "a\nb")
    assert d.my_create_user("u", "it's\\", True) == ["CREATE USER 'u'@'localhost' IDENTIFIED BY 'it\\'s\\\\';",
                                                    "CREATE DATABASE `u`;",
                                                    "GRANT ALL PRIVILEGES ON `u`.* TO 'u'@'localhost';"]
    pg = d.pg_create_user("u", "secret", True)
    assert pg[0].startswith("CREATE ROLE \"u\" LOGIN PASSWORD 'SCRAM-SHA-256$4096:") and "secret" not in pg[0]
    assert pg[1] == 'CREATE DATABASE "u" OWNER "u";'
    verifier = d.scram("pencil", b"0123456789abcdef")
    assert verifier == d.scram("pencil", b"0123456789abcdef") and verifier != d.scram("pencil")  # a new salt each time
    assert d.my_create_database("shop_1", "u")[1] == "GRANT ALL PRIVILEGES ON `shop\\_1`.* TO 'u'@'localhost';"
    assert d.pg_drop_database('x"y') == ['DROP DATABASE "x""y";'] and d.my_drop_database("x`y") == ["DROP DATABASE `x``y`;"]
    assert d.shown(d.my_password("u", "%", "a'b\\c")[0]) == "ALTER USER 'u'@'%' IDENTIFIED BY '••••••';"
    assert "SCRAM" not in d.shown(d.pg_password("u", "x")[0])
    try:
        d.my_drop_user("u", "x'; DROP")
        raise AssertionError("a host with a quote got into SQL")
    except ValueError:
        pass
    assert d.my_option_file("u", 'a"b\\') == '[client]\nuser=u\npassword="a\\"b\\\\"\n'
    listing = d.parse_listing("u\troot\t@localhost\nu\tlaravel\t@%\nd\tshop\tlaravel\n")
    assert listing.user("laravel", "%") and listing.user("laravel", "localhost") is None
    assert listing.database("shop").owner == "laravel"
    assert d.parse_listing("u\tpostgres\tsuperuser\n").users[0] == d.User("postgres", "", "superuser")
    clusters = d.parse_clusters("16  main    5433 down   postgres /var/lib/x /var/log/x\n"
                                "18  main    5432 online postgres /var/lib/y /var/log/y\n")
    assert [(c.version, c.port, c.online, c.unit) for c in clusters] == [
        ("16", "5433", False, "postgresql@16-main.service"), ("18", "5432", True, "postgresql@18-main.service")]
    assert d.parse_unit("Id=mysql.service\nLoadState=not-found\nActiveState=inactive\n\n"
                        "Id=mariadb.service\nLoadState=loaded\nActiveState=active\n") == ("mariadb.service", "active")
    assert d.my_error("ERROR 1698 (28000): Access denied for user 'root'@'localhost'") == "1698"


def test_php():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "9.9"  # no php9.9 binary here, so nothing reads as loaded
        (base / "mods-available").mkdir(parents=True)
        for name in ("mbstring", "intl", "xsl", "pdo"):
            (base / "mods-available" / f"{name}.ini").write_text(f"extension={name}.so\n")
        for sapi, on in (("cli", ("mbstring", "xsl", "pdo")), ("apache2", ("mbstring", "pdo"))):
            (base / sapi / "conf.d").mkdir(parents=True)
            for name in on:
                (base / sapi / "conf.d" / f"20-{name}.ini").write_text("")
        (Path(tmp) / "8.10" / "mods-available").mkdir(parents=True)
        (Path(tmp) / "conf.d").mkdir()  # not a version
        assert php.versions(Path(tmp)) == ["9.9", "8.10"]
        state = php.read("9.9", Path(tmp))
    by = {e.name: e for e in state.extensions}
    assert by["mbstring"].state == php.ENABLED and by["intl"].state == php.DISABLED
    assert by["xsl"].state == php.DISABLED and by["xsl"].on_for == ("cli",), "on for some SAPIs reads as off"
    assert by["gd"].state == php.NOT_INSTALLED, "a Laravel extension that isn't there"
    assert "dom" in by and "ffi" not in by, "only Laravel's are listed when missing"
    assert php.parse_versions("8.3.6\nCore\nPDO\nZend OPcache\n") == ("8.3.6", {"core", "pdo", "zend opcache"})
    assert php.php_fits_laravel("8.2") and not php.php_fits_laravel("7.4") and php.php_fits_laravel("8.10")
    # Switches: only what differs. xsl, partly on and left off, is left alone.
    wanted = {e.name: e.state == php.ENABLED for e in state.extensions} | {"intl": True, "mbstring": False, "gd": True}
    assert php.changes(state, wanted) == (["gd"], ["intl"], ["mbstring"])
    fixes = php.laravel_fixes(state)
    assert "intl" in fixes and "gd" in fixes and "mbstring" not in fixes and "xsl" not in fixes
    state.restarts = ["apache2"]
    argv = php.apply_command(state, ["pdo_pgsql"], ["intl"], ["mbstring"])
    assert argv[:3] == ["pkexec", "sh", "-c"] and argv[4:] == [
        "sh", "9.9", "install:pdo-pgsql", "on:intl", "off:mbstring", "restart:apache2"]
    assert php.package("8.3", "pdo_pgsql") == "php8.3-pdo-pgsql"
    for bad in (["x; rm -rf ~"], ["$(id)"], ["Intl"]):
        try:
            php.apply_command(state, bad, [], [])
            raise AssertionError(f"{bad} reached the script")
        except ValueError:
            pass
    after = php.State("9.9", "9.9", [], [php.Extension("intl", php.ENABLED), php.Extension("mbstring", php.ENABLED),
                                          php.Extension("pdo_pgsql", php.DISABLED)], set(), [], "")
    assert php.unchanged(state, after, ["pdo_pgsql", "gd"], ["intl"], ["mbstring"]) == ["gd", "mbstring"]


def test_web_apps():
    assert webapps.normalise(" facebook.com ") == "https://facebook.com"
    assert webapps.host_of("https://web.whatsapp.com/path?x") == "web.whatsapp.com"
    assert webapps.pretty_host("www.facebook.com") == "Facebook"
    assert webapps.title_of("<title>\n GitHub · Change is constant </title>") == "GitHub"
    assert webapps.title_of("<TITLE>Tom &amp; Jerry - Home</TITLE>") == "Tom & Jerry" and webapps.title_of("<p>") is None
    page = ('<link rel="icon" href="/favicon.ico"><link rel="apple-touch-icon" sizes="180x180" href="/a180.png">'
            '<link rel="icon" sizes="32x32" href="//cdn.x.com/i32.png?v=2">')
    assert webapps.icon_link(page, "https://x.com/home") == "https://x.com/a180.png"  # the biggest PNG
    assert webapps.icon_link('<link rel="icon" href="/f.svg">', "https://x.com") is None
    assert webapps.resolve("img/i.png", "https://x.com/a/b") == "https://x.com/img/i.png"
    assert webapps.desktop_quote("--app=https://x.com/?q=100%") == '"--app=https://x.com/?q=100%%"'
    assert webapps.desktop_quote("/usr/bin/brave") == "/usr/bin/brave"
    assert webapps.desktop_quote('a "b" $c') == '"a \\"b\\" \\$c"'
    assert webapps.new_id("Facebook") != webapps.new_id("Facebook")  # two Facebooks, two logins
    browser = webapps.Browser("Brave", ["/usr/bin/brave-browser"], Path("/p"))
    entry = webapps.parse_desktop(webapps.desktop_entry("Work\nmail", "https://x.com", browser, "work-1",
                                                        Path("/p/work-1/profile"), Path("/p/work-1/icon.png")))
    assert entry["Name"] == "Work mail" and entry["StartupWMClass"] == "stitches-webapp-work-1"
    assert entry["Exec"].endswith("--user-data-dir=/p/work-1/profile --class=stitches-webapp-work-1")
    assert "--ozone-platform=x11 --app=" in entry["Exec"]  # on Wayland, --class only names an XWayland window
    icons = list(webapps.READY_ICONS.rglob("*.png"))
    assert len(icons) > 90 and all(i.parent.parent == webapps.READY_ICONS for i in icons), "webicons/<group>/<name>.png"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")
