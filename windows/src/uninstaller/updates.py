"""Update detection and bulk update across Windows Update, winget, Chocolatey
and Scoop, and the GitHub download the self-updater shares. Pure parsers
first, then the subprocess and network calls. See ai-knowledgebase.md
("Windows: Updates")."""

import hashlib
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .backends.scoop_backend import install_roots
from .elevate import powershell, run

WINDOWS_UPDATE, WINGET, CHOCOLATEY, SCOOP = "Windows Update", "winget", "Chocolatey", "Scoop"
SOURCES = (WINDOWS_UPDATE, WINGET, CHOCOLATEY, SCOOP)
_GITHUB_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "Stitches"}
_WINGET_SOURCES = {"winget", "msstore"}


@dataclass
class Update:
    name: str
    id: str  # Windows Update's UpdateID, a winget id, or a Chocolatey/Scoop package
    source: str
    current: str
    new: str
    size_bytes: int = 0
    detail: str = ""  # the KB article, or the winget source


def wu_search_script(kind: str) -> str:
    """What the Windows Update agent would install, without installing it:
    `kind` is "Software" or "Driver". Searching needs no admin rights. One
    tab-separated line per update (titles hold commas and pipes): id, title,
    download size, KB articles, driver class, driver model, driver date."""
    return (
        "$r = (New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher()"
        f".Search(\"IsInstalled=0 and IsHidden=0 and Type='{kind}'\")\n"
        "foreach ($u in $r.Updates) {\n"
        "  $d = if ($u.DriverVerDate) { $u.DriverVerDate.ToString('yyyy-MM-dd') } else { '' }\n"
        "  @($u.Identity.UpdateID, $u.Title, $u.MaxDownloadSize, ($u.KBArticleIDs -join ','),"
        " $u.DriverClass, $u.DriverModel, $d) -join \"`t\"\n"
        "}\n"
    )


def parse_wu(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 7:
            continue
        uid, title, size, kb, driver_class, model, released = (p.strip() for p in parts)
        try:
            size_bytes = int(float(size))
        except ValueError:
            size_bytes = 0
        rows.append({"id": uid, "title": title, "size": size_bytes, "kb": kb, "class": driver_class,
                     "model": model, "released": released})
    return rows


def wu_install_script(ids: list[str]) -> str:
    """Finds the chosen updates again by id (a search result can't cross
    processes), then downloads and installs them in one go. Exits 0 only when
    every one went in. A restart Windows wants is said, never done."""
    wanted = ", ".join(f"'{i}'" for i in ids if re.fullmatch(r"[0-9a-fA-F-]+", i))
    return (
        "$s = New-Object -ComObject Microsoft.Update.Session\n"
        "$r = $s.CreateUpdateSearcher().Search('IsInstalled=0 and IsHidden=0')\n"
        "$c = New-Object -ComObject Microsoft.Update.UpdateColl\n"
        f"$want = @({wanted})\n"
        "foreach ($u in $r.Updates) { if ($want -contains $u.Identity.UpdateID) { $u.AcceptEula(); [void]$c.Add($u) } }\n"
        "if ($c.Count -eq 0) { 'Windows Update no longer offers these.'; exit 1 }\n"
        "$d = $s.CreateUpdateDownloader(); $d.Updates = $c; [void]$d.Download()\n"
        "$i = $s.CreateUpdateInstaller(); $i.Updates = $c; $res = $i.Install()\n"
        "$words = 'not started', 'in progress', 'installed', 'installed with errors', 'failed', 'cancelled'\n"
        "for ($n = 0; $n -lt $c.Count; $n++) { \"$($c.Item($n).Title): $($words[$res.GetUpdateResult($n).ResultCode])\" }\n"
        "if ($res.RebootRequired) { 'Windows needs a restart to finish.' }\n"
        "exit [int]($res.ResultCode -ne 2)\n"
    )


def build_wu_updates(rows: list[dict]) -> list[Update]:
    return [Update(r["title"], r["id"], WINDOWS_UPDATE, "", f"KB{r['kb']}" if r["kb"] else "new", r["size"],
                   f"KB{r['kb']}" if r["kb"] else "") for r in rows]


def parse_winget(text: str) -> list[Update]:
    """`winget upgrade`'s table. Read from the right: Id, Version, Available
    and Source never hold a space, Name does (and winget cuts it short with
    …), and the column headers are translated, so they're no use to find
    columns by. "< 1.2" is how winget writes a version it can't pin down."""
    rows, table = [], False
    for line in text.splitlines():
        line = line.rsplit("\r", 1)[-1].rstrip()  # the spinner winget draws before the table
        if not table:
            table = len(line) > 10 and not line.strip("-")
            continue
        if not line:
            break  # the table ends at a blank line; notes follow it
        tokens = line.split()
        source = tokens.pop() if tokens and tokens[-1] in _WINGET_SOURCES else ""
        if len(tokens) < 4:
            continue
        new, current = tokens.pop(), tokens.pop()
        if tokens[-1] in ("<", ">"):
            current = f"{tokens.pop()} {current}"
        ident = tokens.pop()
        if tokens:
            rows.append(Update(" ".join(tokens), ident, WINGET, current, new, detail=source))
    return rows


def parse_choco_outdated(text: str) -> list[Update]:
    """`choco outdated -r`: name|current|available|pinned. A pinned package
    is left out, since choco won't upgrade it."""
    rows = []
    for line in text.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 4 and parts[3].strip().lower() != "true":
            rows.append(Update(parts[0], parts[0], CHOCOLATEY, parts[1], parts[2]))
    return rows


def parse_scoop_status(text: str) -> list[Update]:
    """`scoop status`: a table of Name, Installed Version, Latest Version,
    Missing Dependencies and Info. Header names have spaces, so columns are
    cut where the dashes under them start."""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if "-" in line and not line.replace("-", "").strip():
            starts = [m.start() for m in re.finditer(r"-+", line)]
            break
    else:
        return []
    rows = []
    for line in lines[n + 1:]:
        if not line.strip():
            continue
        cells = [line[a:b].strip() for a, b in zip(starts, [*starts[1:], None])]
        if len(cells) >= 3 and cells[0] and cells[2]:
            rows.append(Update(cells[0], cells[0], SCOOP, cells[1], cells[2]))
    return rows


def plan_jobs(updates: list[Update]) -> list[list[Update]]:
    """Windows Update and Chocolatey go as one batch each: one permission
    prompt, not one per package. Scoop needs none and goes as one batch too.
    winget goes one at a time, since each installer asks for itself if it
    needs to, and gets its own progress slice."""
    jobs = []
    for source in (WINDOWS_UPDATE, CHOCOLATEY, SCOOP):
        batch = [u for u in updates if u.source == source]
        if batch:
            jobs.append(batch)
    jobs.extend([u] for u in updates if u.source == WINGET)
    return jobs


def winget_command(update: Update) -> list[str]:
    source = ["--source", update.detail] if update.detail else []
    return ["winget", "upgrade", "--id", update.id, "--exact", *source, "--silent", "--accept-package-agreements",
            "--accept-source-agreements", "--disable-interactivity"]


# ---- IO below ----


def _scoop() -> str:
    shim = install_roots()[0][0] / "shims" / "scoop.cmd"
    return str(shim) if shim.is_file() else "scoop"


def _windows_updates() -> list[Update]:
    return build_wu_updates(parse_wu(powershell(wu_search_script("Software"))[1]))


def _winget_updates() -> list[Update]:
    # winget writes UTF-8 when its output isn't a console, whatever the code page.
    return parse_winget(run(["winget", "upgrade", "--accept-source-agreements", "--disable-interactivity"],
                            encoding="utf-8")[1])


def _choco_updates() -> list[Update]:
    return parse_choco_outdated(run(["choco", "outdated", "-r"])[1])


def _scoop_updates() -> list[Update]:
    return parse_scoop_status(run([_scoop(), "status"])[1])


def find_updates() -> list[Update]:
    """Every source at once: they all wait on the network. A source whose
    tool isn't installed just finds nothing."""
    with ThreadPoolExecutor() as pool:
        results = pool.map(lambda find: find(), (_windows_updates, _winget_updates, _choco_updates, _scoop_updates))
    return sorted((u for r in results for u in r), key=lambda u: u.name.lower())


def apply(job: list[Update]) -> tuple[bool, str]:
    source, ids = job[0].source, [u.id for u in job]
    if source == WINDOWS_UPDATE:
        code, text = powershell(wu_install_script(ids), elevated=True)
    elif source == CHOCOLATEY:
        code, text = run(["choco", "upgrade", *ids, "-y", "--no-progress"], elevated=True)
    elif source == SCOOP:
        code, text = run([_scoop(), "update", *ids])
    else:
        code, text = run(winget_command(job[0]), encoding="utf-8")
    return code == 0, text


def get_json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=_GITHUB_HEADERS), timeout=15) as r:
        return json.load(r)


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
