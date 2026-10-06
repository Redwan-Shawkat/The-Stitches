"""PHP: which extensions Ubuntu's PHP has, which are on, and switching them
with phpenmod/phpdismod — plus the Laravel check. It reads /etc/php/<version>
(each extension's ini in mods-available, a link in <sapi>/conf.d per SAPI it's
on for), never assumes a version, and changes things through one fixed pkexec
script: one password, extension names and the version passed as arguments
after checking their shape, never pasted into it. Whether a change worked is
decided by reading /etc/php again. Pure helpers first, then the IO.
See ai-knowledgebase.md ("PHP")."""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .shell import output, run
from .updates import APT_KEEP_CONFIG

ETC = Path("/etc/php")
ENABLED, DISABLED, BUILT_IN, NOT_INSTALLED = "Enabled", "Disabled", "Built in", "Not installed"
# What Laravel's docs ask for, plus what most Laravel apps add (images, zips,
# money maths, intl, both databases). json, openssl and pcre are compiled in.
LARAVEL = ("bcmath", "ctype", "curl", "dom", "fileinfo", "gd", "intl", "json", "mbstring", "openssl", "pcre",
           "pdo", "pdo_mysql", "pdo_pgsql", "tokenizer", "xml", "zip")
LARAVEL_PHP = (8, 2)

_NAME = re.compile(r"[a-z0-9_]+")
_VERSION = re.compile(r"\d+\.\d+")
_CONF = re.compile(r"\d+-(.+)\.ini")
# Each step is an argument, "install:x", "on:x", "off:x" or "restart:x", run in order;
# one failing doesn't stop the rest, and the exit code says whether any did.
_SCRIPT = ('v=$1; shift; rc=0; for a; do case $a in '
           f'install:*) apt-get install -y {" ".join(APT_KEEP_CONFIG)} "php$v-${{a#install:}}" || rc=1;; '
           'on:*) phpenmod -v "$v" "${a#on:}" || rc=1;; '
           'off:*) phpdismod -v "$v" "${a#off:}" || rc=1;; '
           'restart:*) systemctl restart "${a#restart:}" || rc=1;; '
           'esac; done; exit $rc')


@dataclass(frozen=True)
class Extension:
    name: str
    state: str
    on_for: tuple = ()  # the SAPIs it's on for, when that's only some of them

    @property
    def on(self) -> bool:
        return self.state in (ENABLED, BUILT_IN)


@dataclass
class State:
    version: str  # "8.3", as /etc/php names it
    full: str  # "8.3.6"
    sapis: list  # cli, apache2, fpm…
    extensions: list  # Extension, the ones that can be switched, by name, then the missing Laravel ones
    built_in: set  # loaded but not switchable (compiled in)
    restarts: list  # services that load PHP and are running, so a change needs them restarted
    composer: str  # its path, or ""


def enabled_in(names) -> set:
    """conf.d file names ("20-mbstring.ini") -> the extensions they turn on."""
    return {m.group(1) for n in names if (m := _CONF.fullmatch(n))}


def extensions(available: set, sapis: dict, loaded: set) -> list:
    """`sapis` is {sapi: extensions on for it}; `loaded` what the CLI has
    loaded, lowercased. A Laravel extension in neither is NOT_INSTALLED."""
    found = []
    for name in sorted(available):
        on_for = tuple(s for s, on in sapis.items() if name in on)
        state = ENABLED if sapis and len(on_for) == len(sapis) else DISABLED
        found.append(Extension(name, state, on_for if state == DISABLED else ()))
    return found + [Extension(n, NOT_INSTALLED) for n in LARAVEL if n not in available and n not in loaded]


def parse_versions(text: str) -> tuple[str, set]:
    """What _PROBE prints -> ("8.3.6", {loaded extensions, lowercased})."""
    full, *names = text.strip().splitlines() or [""]
    return full.strip(), {n.strip().lower() for n in names if n.strip()}


def laravel(state: State) -> list[tuple[str, str]]:
    """The Laravel checklist: (extension, state) in LARAVEL's order."""
    by_name = {e.name: e.state for e in state.extensions}
    return [(n, BUILT_IN if n in state.built_in else by_name.get(n, NOT_INSTALLED)) for n in LARAVEL]


def php_fits_laravel(version: str) -> bool:
    return tuple(int(p) for p in version.split(".")) >= LARAVEL_PHP


def changes(state: State, wanted: dict) -> tuple[list, list, list]:
    """`wanted` is {extension: on?} -> (install, enable, disable), only what
    differs from now. A partly-on extension shows as off: switched on, it's
    enabled for every SAPI; left off, it's left as it is."""
    now = {e.name: e for e in state.extensions}
    install = [n for n, on in wanted.items() if on and now[n].state == NOT_INSTALLED]
    enable = [n for n, on in wanted.items() if on and now[n].state == DISABLED]
    disable = [n for n, on in wanted.items() if not on and now[n].state == ENABLED]
    return install, enable, disable


def laravel_fixes(state: State) -> dict:
    """Only what Laravel needs and doesn't have: {extension: True}."""
    return {n: True for n, s in laravel(state) if s in (DISABLED, NOT_INSTALLED)}


def package(version: str, name: str) -> str:
    """Ubuntu's package for an extension; for most it's a name the real
    package provides (php8.3-pdo-pgsql is in php8.3-pgsql), which apt follows."""
    return f"php{version}-{name.replace('_', '-')}"


def apply_command(state: State, install, enable, disable) -> list[str]:
    """The one pkexec call for a set of changes, then a restart of whatever
    serves PHP. Raises ValueError for a name that isn't an extension's shape —
    they come from /etc/php and the fixed Laravel list, but this is the line."""
    if not _VERSION.fullmatch(state.version) or not all(_NAME.fullmatch(n) for n in (*install, *enable, *disable)):
        raise ValueError("not a PHP version or extension name")
    steps = ([f"install:{n.replace('_', '-')}" for n in install] + [f"on:{n}" for n in enable]
             + [f"off:{n}" for n in disable] + [f"restart:{s}" for s in state.restarts])
    return ["pkexec", "sh", "-c", _SCRIPT, "sh", state.version, *steps]


def unchanged(before: State, after: State, install, enable, disable) -> list[str]:
    """What didn't take: read back from /etc/php, not trusted from the exit code."""
    now = {e.name: e for e in after.extensions}
    missing = lambda n: n not in now or now[n].state == NOT_INSTALLED
    return ([n for n in install if missing(n)] + [n for n in enable if missing(n) or now[n].state != ENABLED]
            + [n for n in disable if n in now and now[n].state == ENABLED])


# ---- IO below ----

_PROBE = 'echo PHP_VERSION, "\\n", implode("\\n", get_loaded_extensions());'


def versions(root: Path = ETC) -> list[str]:
    """PHP versions installed from Ubuntu's (or Ondřej's) packages, newest first."""
    found = [d.name for d in root.glob("*") if _VERSION.fullmatch(d.name) and (d / "mods-available").is_dir()]
    return sorted(found, key=lambda v: tuple(map(int, v.split("."))), reverse=True)


def default_version() -> str:
    """The version `php` runs, or ""."""
    return output(["php", "-r", "echo PHP_MAJOR_VERSION, '.', PHP_MINOR_VERSION;"]).strip()


def _active(unit: str) -> bool:
    return run(["systemctl", "is-active", "--quiet", unit])[0]


def read(version: str, root: Path = ETC) -> State:
    base = root / version
    available = {p.stem for p in (base / "mods-available").glob("*.ini")}
    sapis = {d.name: enabled_in(p.name for p in (d / "conf.d").iterdir())
             for d in sorted(base.iterdir()) if (d / "conf.d").is_dir()}
    full, loaded = parse_versions(output([f"php{version}", "-r", _PROBE])) if shutil.which(f"php{version}") \
        else (version, set())
    restarts = [u for u in (f"php{version}-fpm",) if _active(u)]
    if (Path("/etc/apache2/mods-enabled") / f"php{version}.load").exists() and _active("apache2"):
        restarts.append("apache2")
    return State(version, full or version, list(sapis), extensions(available, sapis, loaded), loaded - available,
                 restarts, shutil.which("composer") or "")


def apply(state: State, install, enable, disable, on_line=None) -> tuple[bool, str]:
    return run(apply_command(state, install, enable, disable), on_line=on_line)
