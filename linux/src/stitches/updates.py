"""Update detection and bulk update across APT, Snap, Flatpak and AppImages
published as GitHub releases. Pure parsers first, then the subprocess and
network calls. See ai-knowledgebase.md ("Updates")."""

import fnmatch
import hashlib
import json
import os
import re
import struct
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .backends.flatpak_backend import parse_size
from .backends.snap_backend import parse_snap_list
from .shell import output as _out, run

APT, SNAP, FLATPAK, GITHUB = "APT", "Snap", "Flatpak", "GitHub"
SOURCES = (APT, SNAP, FLATPAK, GITHUB)
# No terminal to answer dpkg's "keep your changed config file?" question, so
# answer it up front: keep yours, which is apt's own default answer anyway.
APT_KEEP_CONFIG = ("-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold")

# ponytail: the usual places people keep AppImages, not a whole-disk search.
_APPIMAGE_DIRS = ("~/Applications", "~/AppImages", "~/.local/bin", "~/Downloads", "~/Desktop")
_GITHUB_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "Stitches"}
_APT_RE = re.compile(r"^([^/\s]+)/\S+ (\S+) \S+ \[upgradable from: ([^\]]+)\]")


@dataclass
class Update:
    name: str
    id: str  # apt package, snap name, flatpak ref, or AppImage path
    source: str
    current: str
    new: str
    size_bytes: int = 0
    detail: str = ""  # where it comes from: apt host, flatpak remote, GitHub repo
    url: str = ""  # AppImage download
    digest: str = ""  # "sha256:…" when GitHub publishes one for the asset


def parse_apt_upgradable(output: str) -> list[Update]:
    """`apt list --upgradable`: name/suite new arch [upgradable from: old]."""
    found = []
    for line in output.splitlines():
        m = _APT_RE.match(line)
        if m:
            name, new, current = m.groups()
            found.append(Update(name, name, APT, current, new))
    return found


def parse_apt_policy(output: str) -> dict[str, str]:
    """`apt-cache policy <pkgs…>` -> {package: host its candidate comes from}.
    That host is what tells a vendor's own repo (packages.microsoft.com)
    apart from the distro's."""
    hosts, pkg, candidate, in_candidate = {}, None, None, False
    for line in output.splitlines():
        stripped = line.strip()
        if line and not line[0].isspace() and line.endswith(":"):
            pkg, candidate, in_candidate = line[:-1], None, False
        elif stripped.startswith("Candidate:"):
            candidate = stripped.split(":", 1)[1].strip()
        elif candidate and stripped.lstrip("*").split()[:1] == [candidate]:
            in_candidate = True
        elif in_candidate:
            m = re.search(r"https?://([^/\s]+)", line)
            if m:
                hosts[pkg] = m.group(1)
                in_candidate = False
    return hosts


def parse_snap_refresh_list(output: str) -> list[dict]:
    """`snap refresh --list`: Name Version Rev Size Publisher Notes.
    Prints "All snaps up to date." instead of a table when there's nothing."""
    lines = output.splitlines()
    if not lines or not lines[0].startswith("Name"):
        return []
    rows = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 4:
            rows.append({"name": parts[0], "version": parts[1], "size": parse_size(parts[3])})
    return rows


def parse_flatpak_rows(output: str, columns: int) -> list[list[str]]:
    """Tab-separated `flatpak … --columns=` output (no header when piped)."""
    return [p for p in (line.split("\t") for line in output.splitlines()) if len(p) == columns]


def parse_update_info(info: str):
    """AppImage update information -> (owner, repo, tag, asset glob), or None.
    Only the GitHub form is understood: gh-releases-zsync|owner|repo|tag|glob.zsync"""
    parts = info.split("|")
    if len(parts) != 5 or parts[0] != "gh-releases-zsync":
        return None
    _, owner, repo, tag, pattern = parts
    return owner, repo, tag, pattern.removesuffix(".zsync")


def pick_asset(release: dict, pattern: str):
    return next((a for a in release.get("assets", []) if fnmatch.fnmatch(a["name"], pattern)), None)


def version_label(pattern: str, filename: str, fallback: str) -> str:
    """The part of `filename` the glob's first * stands for ("1.16.0" from
    LocalSend-1.16.0-linux-x86-64.AppImage); `fallback` for a fixed name."""
    m = re.fullmatch(re.escape(pattern).replace(r"\*", "(.+?)", 1).replace(r"\*", ".*"), filename)
    return m.group(1) if m and m.groups() else fallback


def plan_jobs(updates: list[Update]) -> list[list[Update]]:
    """APT and Snap go as one batch each — one password prompt, not one per
    package. Flatpak and AppImages need no prompt, so they go one at a time
    and each gets its own progress slice."""
    jobs = []
    for source in (APT, SNAP):
        batch = [u for u in updates if u.source == source]
        if batch:
            jobs.append(batch)
    jobs.extend([u] for u in updates if u.source in (FLATPAK, GITHUB))
    return jobs


def command_for(job: list[Update]) -> list[str]:
    ids = [u.id for u in job]
    source = job[0].source
    if source == APT:
        return ["pkexec", "apt-get", "install", "--only-upgrade", "-y", *APT_KEEP_CONFIG, *ids]
    if source == SNAP:
        return ["pkexec", "snap", "refresh", *ids]
    return ["flatpak", "update", "-y", "--noninteractive", *ids]


# ---- IO below ----


def _apt_updates() -> list[Update]:
    found = parse_apt_upgradable(_out(["apt", "list", "--upgradable"]))
    if found:
        # ponytail: as fresh as the system's last `apt update` (Software
        # Updater runs it daily); refreshing it here would cost a password.
        hosts = parse_apt_policy(_out(["apt-cache", "policy", *(u.id for u in found)]))
        for u in found:
            u.detail = hosts.get(u.id, "")
    return found


def _snap_updates() -> list[Update]:
    current = {r["name"]: r["version"] for r in parse_snap_list(_out(["snap", "list"]))}
    return [
        Update(r["name"], r["name"], SNAP, current.get(r["name"], ""), r["version"], r["size"], "Snap Store")
        for r in parse_snap_refresh_list(_out(["snap", "refresh", "--list"]))
    ]


def _flatpak_updates() -> list[Update]:
    installed = {ref: (name, version) for ref, name, version in
                 parse_flatpak_rows(_out(["flatpak", "list", "--columns=ref,name,version"]), 3)}
    found = []
    for ref, version, origin, size in parse_flatpak_rows(
        _out(["flatpak", "remote-ls", "--updates", "--columns=ref,version,origin,download-size"]), 4
    ):
        ref = ref.removeprefix("app/").removeprefix("runtime/")  # list prints refs without the kind
        name, current = installed.get(ref, (ref.split("/")[0], ""))
        found.append(Update(name, ref, FLATPAK, current, version or "newer build", parse_size(size), origin))
    return found


def read_update_info(path: Path) -> str:
    """The `.upd_info` ELF section every AppImage carries (empty when the
    author didn't fill it in). 64-bit little-endian only — which is every
    x86_64 and aarch64 AppImage."""
    with open(path, "rb") as f:
        head = f.read(64)
        if head[:6] != b"\x7fELF\x02\x01":
            return ""
        shoff, = struct.unpack_from("<Q", head, 0x28)
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", head, 0x3A)
        f.seek(shoff)
        table = f.read(shentsize * shnum)
        if len(table) < shentsize * shnum or shstrndx >= shnum:
            return ""
        sections = [struct.unpack_from("<I4xQQQQ", table, i * shentsize) for i in range(shnum)]
        _, _, _, names_off, names_size = sections[shstrndx]
        f.seek(names_off)
        names = f.read(names_size)
        for name_at, _, _, off, size in sections:
            if names[name_at:names.find(b"\0", name_at)] == b".upd_info":
                f.seek(off)
                return f.read(size).split(b"\0")[0].decode(errors="replace")
    return ""


def get_json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=_GITHUB_HEADERS), timeout=15) as r:
        return json.load(r)


def _github_updates() -> list[Update]:
    found = []
    for folder in _APPIMAGE_DIRS:
        base = Path(folder).expanduser()
        if not base.is_dir():
            continue
        for path in base.iterdir():
            if path.suffix.lower() != ".appimage" or not path.is_file():
                continue
            parsed = parse_update_info(read_update_info(path))
            if not parsed:
                continue
            owner, repo, tag, pattern = parsed
            which = "latest" if tag == "latest" else f"tags/{tag}"
            try:
                asset = pick_asset(get_json(f"https://api.github.com/repos/{owner}/{repo}/releases/{which}"), pattern)
            except (OSError, ValueError):
                continue  # offline, rate-limited, or the repo moved
            stat = path.stat()
            # ponytail: same size = same file. A release asset's size changing
            # between builds is near-certain; a sha256 would read every file.
            if asset and asset["size"] != stat.st_size:
                found.append(Update(
                    repo, str(path), GITHUB,
                    version_label(pattern, path.name, date.fromtimestamp(stat.st_mtime).isoformat()),
                    version_label(pattern, asset["name"], asset.get("updated_at", "")[:10]),
                    asset["size"], f"{owner}/{repo} · AppImage", asset["browser_download_url"],
                    asset.get("digest") or "",
                ))
    return found


def _safe(finder):
    try:
        return finder()
    except OSError:
        return []  # that tool isn't installed here


def find_updates() -> list[Update]:
    """Every source at once: three of the four wait on the network."""
    with ThreadPoolExecutor() as pool:
        results = pool.map(_safe, (_apt_updates, _snap_updates, _flatpak_updates, _github_updates))
    return sorted((u for r in results for u in r), key=lambda u: u.name.lower())


def download(url: str, dest: Path, size: int | None = None, digest: str = "") -> None:
    """Fetch `url` into `dest`; raises OSError unless it arrived whole and
    matches the sha256 GitHub publishes for it (when it publishes one)."""
    sha = hashlib.sha256()
    with urllib.request.urlopen(urllib.request.Request(url, headers=_GITHUB_HEADERS), timeout=30) as r, \
            open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            sha.update(chunk)
            f.write(chunk)
    if size is not None and dest.stat().st_size != size:
        raise OSError(f"downloaded {dest.stat().st_size} bytes, expected {size}")
    if digest.startswith("sha256:") and sha.hexdigest() != digest[7:]:
        raise OSError("download doesn't match the checksum GitHub published")


def _replace_appimage(update: Update) -> tuple[bool, str]:
    """Download next to the old file, check it, then swap it in under the same
    name, so launchers and menu entries that point at the path keep working.
    A cut-off or corrupted download never replaces a working app."""
    path = Path(update.id)
    part = path.with_name(path.name + ".part")
    try:
        download(update.url, part, update.size_bytes, update.digest)
        part.chmod(path.stat().st_mode)
        os.replace(part, path)
        return True, ""
    except OSError as exc:
        part.unlink(missing_ok=True)
        return False, str(exc)


def apply(job: list[Update]) -> tuple[bool, str]:
    if job[0].source == GITHUB:
        return _replace_appimage(job[0])
    return run(command_for(job))
