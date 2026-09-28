"""Defrag: every drive letter as a tile, grouped by the disk it's on, and
Windows' own Optimize-Volume run on the ones picked. Unlike Linux, Windows
has something to do for an SSD too: it sends TRIM, telling the drive which
blocks are free. See ai-knowledgebase.md ("Windows: Defrag")."""

from dataclasses import dataclass

from .elevate import powershell

_OPTIMIZABLE = {"NTFS", "REFS", "FAT", "FAT32"}  # what defrag.exe accepts
_VOLUMES = (
    "$disks = @{}; Get-PhysicalDisk | ForEach-Object { $disks[[string]$_.DeviceId] = $_ }\n"
    "foreach ($p in Get-Partition | Where-Object { \"$($_.DriveLetter)\" -match '^[A-Za-z]$' }) {\n"
    "  $v = $p | Get-Volume; $d = $disks[[string]$p.DiskNumber]\n"
    "  @($p.DriveLetter, $v.FileSystem, $v.FileSystemLabel, $v.Size, $v.SizeRemaining, $p.DiskNumber,"
    " $d.FriendlyName, $d.MediaType, $d.BusType) -join \"`t\"\n"
    "}\n"
)


@dataclass
class Volume:
    letter: str
    fs: str
    label: str
    size: int
    free: int
    disk: str  # "Disk 0 · Samsung SSD 970 EVO · SSD": the group it's shown in
    media: str  # SSD, HDD, or "" when Windows can't tell
    action: str  # "defragment", "trim", or "" when nothing will happen
    why: str


def plan(fs: str, media: str, bus: str) -> tuple[str, str]:
    """(action, what it means) for one drive: Optimize-Volume defragments a
    hard disk and trims an SSD by itself; this only says which, and why not."""
    if fs.upper() not in _OPTIMIZABLE:
        return "", f"Windows can't optimize {fs or 'an unformatted'} drives."
    if media == "SSD":
        return "trim", "SSD: Windows tells it which blocks are free (TRIM). Defragmenting would only wear it."
    if media == "HDD":
        return "defragment", "Hard disk: files in pieces are put back together."
    if bus == "USB":
        return "", "USB flash drive: nothing to gain, and it wears the drive."
    return "defragment", "Windows couldn't tell whether this is an SSD; Optimize-Volume decides."


def _int(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        return 0


def parse_volumes(text: str) -> list[Volume]:
    found = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) != 9 or len(parts[0]) != 1 or not parts[0].isalpha():
            continue
        letter, fs, label, size, free, number, model, media, bus = parts
        media = media if media in ("SSD", "HDD") else ""
        action, why = plan(fs, media, bus)
        disk = " · ".join(p for p in (f"Disk {number}", model, media) if p)
        found.append(Volume(f"{letter}:", fs, label, _int(size), _int(free), disk, media, action, why))
    return sorted(found, key=lambda v: (v.disk, v.letter))


def optimize_script(letters: list[str]) -> str:
    """One elevated run for every drive picked: one permission prompt. Each
    drive's failure is said and the rest still run."""
    wanted = ", ".join(f"'{letter[0]}'" for letter in letters if letter[:1].isalpha())
    return (
        "$failed = 0\n"
        f"foreach ($l in @({wanted})) {{\n"
        "  try { Optimize-Volume -DriveLetter $l -Verbose -ErrorAction Stop 4>&1 }\n"
        "  catch { \"${l}: $_\"; $failed = 1 }\n"
        "}\n"
        "exit $failed\n"
    )


# ---- IO below ----


def scan() -> list[Volume]:
    return parse_volumes(powershell(_VOLUMES)[1])


def optimize(volumes: list[Volume]) -> tuple[bool, str]:
    code, text = powershell(optimize_script([v.letter for v in volumes]), elevated=True)
    return code == 0, text
