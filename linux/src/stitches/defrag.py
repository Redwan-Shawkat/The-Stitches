"""Defrag, for the three filesystems Linux has a defragmenter for: ext4
(e4defrag), btrfs (btrfs filesystem defragment) and XFS (xfs_fsr), on
spinning disks; SSDs are trimmed instead (fstrim), as Windows' Optimize does.
Every drive is listed, grouped by the OS it belongs to; the ones that can't
be optimized say why. See ai-knowledgebase.md ("Defrag")."""

import json
import shutil
from dataclasses import dataclass

from .shell import output, run

# filesystem -> (command, the package that provides it)
_TOOLS = {
    "ext4": (["e4defrag"], "e2fsprogs"),
    "btrfs": (["btrfs", "filesystem", "defragment", "-r"], "btrfs-progs"),
    "xfs": (["xfs_fsr"], "xfsprogs"),
}
# Filesystem signatures that aren't a filesystem you store files on.
_NOT_FILES = {"swap", "squashfs", "iso9660", "udf", "LVM2_member", "crypto_LUKS", "linux_raid_member"}
GROUPS = ("Linux", "Windows", "macOS", "Boot", "Other")
_LINUX_FS = {"ext2", "ext3", "ext4", "btrfs", "xfs", "f2fs", "jfs"}
_MAC_FS = {"apfs", "hfs", "hfsplus"}
# Filesystems whose Linux driver answers fstrim.
_TRIMS = {"ext4", "btrfs", "xfs", "f2fs", "vfat", "exfat"}


@dataclass
class Drive:
    name: str  # mountpoint, or "Not mounted"
    device: str
    size_bytes: int
    fstype: str
    kind: str  # HDD, SSD or USB
    status: str
    command: list[str]  # empty = can't be defragmented here
    os: str = "Other"  # one of GROUPS

    @property
    def ready(self) -> bool:
        return bool(self.command)


def parse_lsblk(text: str) -> list[dict]:
    """`lsblk -J -b -o NAME,SIZE,FSTYPE,MOUNTPOINT,ROTA,TRAN`, flattened to
    every device carrying a filesystem. Partitions inherit their disk's
    transport, which is only reported on the disk itself."""
    rows = []

    def walk(devices, tran):
        for d in devices:
            tran_here = d.get("tran") or tran
            if d.get("fstype") and d["fstype"] not in _NOT_FILES:
                rows.append({**d, "tran": tran_here})
            walk(d.get("children", []), tran_here)

    walk(json.loads(text or "{}").get("blockdevices", []), None)
    return rows


def os_of(fstype: str, parttype: str | None) -> str:
    """The OS a partition belongs to: by its partition type where the disk
    has one ("Microsoft basic data", "EFI System", "Linux filesystem"), else
    by its filesystem."""
    kind = (parttype or "").lower()
    if kind.startswith("efi") or kind == "bios boot":
        return "Boot"
    if kind.startswith(("microsoft", "windows")) or fstype == "ntfs":
        return "Windows"
    if kind.startswith("linux") or fstype in _LINUX_FS:
        return "Linux"
    if kind.startswith("apple") or fstype in _MAC_FS:
        return "macOS"
    return "Other"


def plan(row: dict, which=shutil.which) -> Drive:
    fs, mount = row["fstype"], row.get("mountpoint")
    spinning = row.get("rota") in (True, 1, "1")  # a bool on new util-linux, "0"/"1" on old
    kind = "USB" if row.get("tran") == "usb" else "HDD" if spinning else "SSD"
    tool, package = _TOOLS.get(fs, (None, None))
    if kind == "SSD":
        # Defragmenting an SSD only wears it; TRIM is what keeps one fast.
        tool, package = (["fstrim", "-v"], "util-linux") if fs in _TRIMS else (None, None)
    if tool is None:
        status = f"{fs} on an SSD can't be trimmed from Linux" if kind == "SSD" else "NTFS: defrag it from Windows" if fs == "ntfs" else f"No Linux defrag tool for {fs}"
    elif not mount:
        status = "Not mounted"
    elif not which(tool[0]):
        status = f"Needs {package}"
    elif kind == "SSD":
        status = "Ready · TRIM, SSDs aren't defragmented"
    else:
        # btrfs defrag copies extents that snapshots share, so it can use more space.
        status = "Ready · unshares snapshots" if fs == "btrfs" else "Ready"
    command = ["pkexec", *tool, mount] if status.startswith("Ready") else []
    return Drive(mount or row.get("label") or "Not mounted", row["name"], int(row.get("size") or 0), fs, kind,
                 status, command, os_of(fs, row.get("parttypename")))


def find_drives() -> list[Drive]:
    rows = parse_lsblk(output(["lsblk", "-J", "-b", "-o", "NAME,SIZE,FSTYPE,MOUNTPOINT,ROTA,TRAN,LABEL,PARTTYPENAME"]))
    return sorted((plan(r) for r in rows), key=lambda d: not d.ready)


def defrag(drive: Drive) -> tuple[bool, str]:
    return run(drive.command)
