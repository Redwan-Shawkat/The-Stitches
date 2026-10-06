"""App Manager: which catalog apps are installed (through any source, not only
the one Stitches would use), at what version, and installing the rest, one
batch per source. Whether an install worked is decided by looking again, not
by the exit code. Pure helpers first, then the subprocess calls.
See ai-knowledgebase.md ("App Manager")."""

import os
import re
import shlex
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .backends.snap_backend import parse_snap_list
from .catalog import APT, CATALOG, FLATPAK, SNAP, App
from .shell import output, run
from .updates import APT_KEEP_CONFIG, parse_flatpak_rows

FLATHUB = "https://dl.flathub.org/repo/flathub.flatpakrepo"
FLATPAK_APP = next(a for a in CATALOG if a.package == "flatpak" and a.source == APT)
_VERSION_RE = re.compile(r"\d+(?:\.\d+)+[\w.+~-]*")
_CODENAME = "${UBUNTU_CODENAME:-$VERSION_CODENAME}"  # from /etc/os-release: Zorin and Mint have Ubuntu's too


@dataclass
class Status:
    installed: bool
    version: str = ""  # empty while installed means it couldn't be read, not that it's missing
    via: str = ""  # APT, Snap, Flatpak, or how a command on PATH got there (nvm, rustup…; just PATH if it can't tell)
    path: str = ""  # the command found on PATH, when that's how it was found


NOT_INSTALLED = Status(False)


def parse_dpkg(text: str) -> dict[str, str]:
    """`dpkg-query -W -f '${Package}\\t${Version}\\t${db:Status-Abbrev}\\n'` ->
    {package: version}, for packages that are actually installed ("ii"/"hi";
    "rc" means removed, its config files left)."""
    found = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2][1:2] == "i":
            found[parts[0]] = parts[1]
    return found


def via_path(path: str) -> str:
    """How a command on PATH most likely got there."""
    for marker, via in (("/.nvm/", "nvm"), ("/.cargo/", "rustup"), ("/snap/", "Snap"), ("/usr/local/", "a manual install"),
                        ("/.local/", "a per-user install"), ("/go/bin", "a manual install")):
        if marker in path:
            return via
    return "PATH"


def parse_version(text: str) -> str:
    """The first dotted number in a --version line: "git version 2.43.0",
    "v20.11.1", 'openjdk version "21.0.2"', "go version go1.22.2 linux/amd64"."""
    m = _VERSION_RE.search(text)
    return m.group(0) if m else ""


def short_version(version: str, source: str) -> str:
    """APT's "1:2.43.0-1ubuntu7.3" is upstream 2.43.0 with an epoch and the
    distro's own revision; the upstream part is what anyone recognises."""
    if source != APT:
        return version
    return re.split(r"[-+~]", version.split(":", 1)[-1])[0]


def detect(app: App, installed: dict[str, dict[str, str]], find_command) -> Status:
    """The source Stitches installs it from first, then the others it may have
    come through, then its command on PATH (an nvm Node, a rustup Rust)."""
    for source, package in ((app.source, app.package), *app.also):
        version = installed.get(source, {}).get(package)
        if version is not None:
            return Status(True, version, source)
    path = find_command(app.command) if app.command else None
    return Status(True, "", via_path(path), path) if path else NOT_INSTALLED


def plan_jobs(apps: list[App], have_flatpak: bool) -> list[tuple[str, list[App]]]:
    """One batch per source, so one password prompt each, in the order that
    lets Flatpak apps work on a system without Flatpak: APT (with flatpak
    itself added when it's needed), then Snap, then Flatpak."""
    batches = {source: [a for a in apps if a.source == source] for source in (APT, SNAP, FLATPAK)}
    if batches[FLATPAK] and not have_flatpak and FLATPAK_APP not in batches[APT]:
        batches[APT].append(FLATPAK_APP)
    return [(source, batch) for source, batch in batches.items() if batch]


def _repo_paths(repo) -> tuple[str, str]:
    name = repo[0]
    return f"/etc/apt/keyrings/{name}.asc", f"/etc/apt/sources.list.d/{name}.list"


def _add_repo(repo) -> str:
    """The vendor's key and source line, then an update of only that source (a
    broken repository elsewhere on the system mustn't stop this install). apt
    reads an armored key as it is when the file ends in .asc."""
    name, key, url = repo
    keyring, sources = _repo_paths(repo)
    return (f"install -d -m 755 /etc/apt/keyrings && {{ curl -fsSL {key} || wget -qO- {key}; }} > {keyring}"
            f" && chmod 644 {keyring}"
            f' && echo "deb [signed-by={keyring}] {url} {_CODENAME} main" > {sources}'
            f" && apt-get update -o Dir::Etc::sourcelist={sources} -o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0")


def command_for(source: str, apps: list[App]) -> list[str]:
    """Every name here comes from the catalog, never from what someone typed."""
    if source == APT:
        install = ["apt-get", "install", "-y", *APT_KEEP_CONFIG, *(a.package for a in apps)]
        repos = [a.repo for a in apps if a.repo]
        if not repos:
            return ["pkexec", *install]
        return ["pkexec", "sh", "-c", " && ".join([". /etc/os-release", *map(_add_repo, repos), shlex.join(install)])]
    if source == SNAP:
        # snap install takes --classic for all of its names or none, so one
        # install each, in one script: one password, and one failure doesn't
        # stop the rest.
        steps = [shlex.join(["snap", "install", a.package, *(["--classic"] if a.classic else [])]) + " || rc=1"
                 for a in apps]
        return ["pkexec", "sh", "-c", "rc=0; " + "; ".join(steps) + "; exit $rc"]
    # System-wide, like apt and snap; Flathub is added first if it isn't there.
    script = f'flatpak remote-add --if-not-exists flathub {FLATHUB} && flatpak install -y --noninteractive flathub "$@"'
    return ["pkexec", "sh", "-c", script, "sh", *(a.package for a in apps)]


def manual_steps(app: App) -> list[str]:
    """The same install, typed into a terminal by hand: shown in the app's details."""
    if app.source == APT and app.repo:
        name, key, url = app.repo
        keyring, sources = _repo_paths(app.repo)
        return ["# Once: the vendor's repository and its signing key", "sudo install -d -m 755 /etc/apt/keyrings",
                f"curl -fsSL {key} | sudo tee {keyring} > /dev/null",
                f'echo "deb [signed-by={keyring}] {url} $(. /etc/os-release; echo {_CODENAME}) main" | sudo tee {sources}',
                "sudo apt update", "", f"sudo apt install {app.package}"]
    if app.source == APT:
        return [f"sudo apt install {app.package}"]
    if app.source == SNAP:
        return [shlex.join(["sudo", "snap", "install", app.package, *(["--classic"] if app.classic else [])])]
    return ["# Once, if Flatpak isn't set up yet:", "sudo apt install flatpak",
            f"sudo flatpak remote-add --if-not-exists flathub {FLATHUB}", "", f"flatpak install flathub {app.package}"]


# ---- IO below ----


def _extra_paths() -> list[str]:
    """Where per-user tool managers put commands that a desktop session's PATH
    often lacks (they're added by ~/.bashrc, which a launcher never reads)."""
    home = Path.home()
    nvm = sorted((home / ".nvm/versions/node").glob("*/bin"), key=lambda p: [int(n) for n in re.findall(r"\d+", p.parent.name)])
    return [str(p) for p in (*nvm[-1:], home / ".local/bin", home / ".cargo/bin", home / "go/bin", Path("/usr/local/go/bin"))]


def find_command(name: str):
    return shutil.which(name, path=os.pathsep.join([os.environ.get("PATH", ""), *_extra_paths()]))


def _safe(read):
    try:
        return read()
    except OSError:
        return {}  # that package manager isn't on this system


def installed_packages() -> dict[str, dict[str, str]]:
    readers = {
        APT: lambda: parse_dpkg(output(["dpkg-query", "-W", "-f", "${Package}\t${Version}\t${db:Status-Abbrev}\n"])),
        SNAP: lambda: {r["name"]: r["version"] for r in parse_snap_list(output(["snap", "list"]))},
        FLATPAK: lambda: dict(parse_flatpak_rows(output(["flatpak", "list", "--app", "--columns=application,version"]), 2)),
    }
    with ThreadPoolExecutor() as pool:
        return dict(zip(readers, pool.map(_safe, readers.values())))


def _command_version(app: App, status: Status) -> Status:
    """Fill in the version of something found only as a command on PATH."""
    if status.installed and not status.version and status.path:
        argv = [status.path, *(app.version[1:] if app.version else ["--version"])]
        status.version = parse_version(run(argv)[1])  # run() has stderr too: java -version prints there
    return status


def check(apps=CATALOG) -> list[Status]:
    installed = installed_packages()
    statuses = [detect(a, installed, find_command) for a in apps]
    with ThreadPoolExecutor() as pool:
        return list(pool.map(_command_version, apps, statuses))


def install(source: str, apps: list[App], on_line=None) -> tuple[bool, str]:
    return run(command_for(source, apps), on_line=on_line)
