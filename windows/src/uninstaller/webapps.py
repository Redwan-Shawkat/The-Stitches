"""Web Apps, as on Linux: any website as an app of its own — a Start menu
shortcut with its own icon and window, and its own login, so the same site
can be added twice. It's Edge (always there), Chrome or Brave in app mode
with a profile per app; nothing is compiled. The name and icon are read from
the site, as PWA Builder does. Pure helpers first, then the IO.
See ai-knowledgebase.md ("Windows: Web Apps")."""

import html
import json
import os
import re
import secrets
import shutil
import struct
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
READY_ICONS = Path(__file__).parent / "webicons"  # webicons/<group>/<name>.png


def ready_icons() -> list[tuple[str, str, Path]]:
    """(group, name, file) for every ready-made site logo. The folder is the
    group and the file name is both the name shown and what a search matches,
    so there's no list to keep in step — as on Linux."""
    return [(path.parent.name, path.stem, path) for path in sorted(READY_ICONS.glob("*/*.png"))]
# (name, the exe App Paths registers it under). App mode and a profile of its
# own are Chromium options; Firefox dropped its app mode.
_BROWSERS = (("Microsoft Edge", "msedge.exe"), ("Google Chrome", "chrome.exe"), ("Brave", "brave.exe"))
_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW
# The shortcut is made by Windows' own WScript.Shell; every value reaches it
# through the environment, so nothing typed is ever part of the script.
_SHORTCUT = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SW_LNK); $s.TargetPath = $env:SW_EXE; "
             "$s.Arguments = $env:SW_ARGS; $s.IconLocation = $env:SW_ICON; $s.Description = $env:SW_NAME; $s.Save()")


@dataclass
class Browser:
    name: str
    exe: str


@dataclass
class WebApp:
    name: str
    url: str
    browser: str
    folder: Path  # icon, profile and app.json
    shortcut: Path
    exe: str
    args: str


def normalise(text: str) -> str:
    text = text.strip()
    return text if text.startswith(("http://", "https://")) else f"https://{text}"


def host_of(url: str) -> str:
    return url.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0]


def pretty_host(host: str) -> str:
    """"www.facebook.com" -> "Facebook"."""
    base = host.removeprefix("www.").split(".")[0]
    return base[:1].upper() + base[1:]


def title_of(page: str):
    """The app name in a page's <title>: "Name - tagline" gives "Name"."""
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
    if not m:
        return None
    text = " ".join(html.unescape(m.group(1)).split())
    name = re.split(r" \| | - | – | · ", text)[0].strip() or text
    return name[:60] or None


def resolve(href: str, page_url: str) -> str:
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("//"):
        return f"https:{href}"
    origin = page_url.split("://", 1)[0] + "://" + host_of(page_url)
    return f"{origin}{href}" if href.startswith("/") else f"{origin}/{href}"


def icon_link(page: str, page_url: str):
    """The page's own PNG icon (largest declared size first); None if it has none."""
    found = []
    for tag in re.findall(r"<link[^>]+>", page, re.I):
        if not re.search(r"""rel=["']?[^"'>]*icon""", tag, re.I):
            continue
        href = re.search(r"""href=["']([^"']+)["']""", tag, re.I)
        if href and href.group(1).split("?")[0].lower().endswith(".png"):
            size = re.search(r"""sizes=["']?(\d+)""", tag, re.I)
            found.append((int(size.group(1)) if size else 0, resolve(html.unescape(href.group(1).strip()), page_url)))
    return max(found)[1] if found else None


def favicon_service(host: str) -> str:
    """Always answers with a PNG, given only the host: the fallback for sites
    that block robots or offer no PNG icon."""
    return f"https://www.google.com/s2/favicons?domain={host}&sz=256"


def png_size(png: bytes) -> tuple[int, int]:
    return struct.unpack(">II", png[16:24]) if png[:8] == b"\x89PNG\r\n\x1a\n" else (0, 0)


def ico_from_png(png: bytes) -> bytes:
    """A one-picture .ico holding the PNG as it is, which Windows reads since
    Vista. Sizes of 256 and up are written as 0, the format's "256"."""
    width, height = png_size(png)
    return struct.pack("<HHHBBBBHHII", 0, 1, 1, width if width < 256 else 0, height if height < 256 else 0,
                       0, 0, 1, 32, len(png), 22) + png


def safe_file_name(name: str) -> str:
    """A Start menu shortcut name: what Windows forbids in a file name taken out."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")[:60] or "Web app"


def new_id(name: str) -> str:
    """Random per app, never from the URL alone: two Facebook apps must not
    share a profile, or they'd share one login."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "app"
    return f"{slug}-{secrets.token_hex(3)}"


def browser_args(url: str, profile: Path) -> str:
    return subprocess.list2cmdline([f"--app={url}", f"--user-data-dir={profile}"])


# ---- IO below ----


def _data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "Stitches" / "WebApps"


def _menu_dir() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming") / \
        "Microsoft/Windows/Start Menu/Programs/Stitches Web Apps"


def find_browsers() -> list[Browser]:
    """From App Paths, where every browser installer registers its exe."""
    try:
        import winreg
    except ImportError:
        return []
    found = []
    for name, exe in _BROWSERS:
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as key:
                    path = winreg.QueryValue(key, None).strip('"')
            except OSError:
                continue
            if os.path.exists(path):
                found.append(Browser(name, path))
                break
    return found


def _get(url: str, limit: int = 2 << 20) -> tuple[str, bytes]:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": _UA}), timeout=15) as r:
        return r.geturl(), r.read(limit)


def fetch_meta(text: str) -> tuple[str, str, bytes, bool]:
    """(address after redirects, name, icon bytes, guessed). An unreadable page
    isn't an error: Facebook and others answer robots with a login wall, so the
    name comes from the address and the icon from the favicon service."""
    url = normalise(text)
    host = host_of(url)
    if "." not in host:
        raise ValueError("that doesn't look like a web address")
    name, icon_url, guessed = pretty_host(host), None, True
    try:
        url, page = _get(url)
        page = page.decode("utf-8", "replace")
        name, icon_url, guessed = title_of(page) or name, icon_link(page, url), False
    except (OSError, ValueError):
        pass
    for candidate in filter(None, (icon_url, favicon_service(host_of(url)))):
        try:
            return url, name, _get(candidate)[1], guessed
        except (OSError, ValueError):
            continue
    return url, name, b"", guessed


def _write_shortcut(app: WebApp, icon: str):
    env = dict(os.environ, SW_LNK=str(app.shortcut), SW_EXE=app.exe, SW_ARGS=app.args, SW_ICON=icon,
               SW_NAME=app.name)
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SHORTCUT], env=env,
                            capture_output=True, text=True, creationflags=_NO_WINDOW, check=False)
    if result.returncode != 0 or not app.shortcut.exists():
        raise OSError(result.stderr.strip() or "Windows didn't make the shortcut")


def create(name: str, url: str, icon_png: bytes, browser: Browser) -> WebApp:
    app_id = new_id(name)
    folder = _data_dir() / app_id
    (folder / "profile").mkdir(parents=True, exist_ok=True)
    icon = folder / "icon.ico"
    if icon_png:
        icon.write_bytes(ico_from_png(icon_png))
    _menu_dir().mkdir(parents=True, exist_ok=True)
    shortcut = _menu_dir() / f"{safe_file_name(name)} ({app_id[-6:]}).lnk"  # two Facebooks, two shortcuts
    app = WebApp(name, normalise(url), browser.name, folder, shortcut, browser.exe,
                 browser_args(normalise(url), folder / "profile"))
    try:
        _write_shortcut(app, f"{icon},0" if icon_png else f"{browser.exe},0")
    except OSError:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    (folder / "app.json").write_text(json.dumps({"name": name, "url": app.url, "browser": browser.name,
                                                 "shortcut": str(shortcut), "exe": app.exe, "args": app.args}))
    return app


def list_apps() -> list[WebApp]:
    apps = []
    for meta in _data_dir().glob("*/app.json"):
        try:
            d = json.loads(meta.read_text())
            apps.append(WebApp(d["name"], d["url"], d["browser"], meta.parent, Path(d["shortcut"]), d["exe"], d["args"]))
        except (OSError, ValueError, KeyError):
            continue
    return sorted(apps, key=lambda a: a.name.lower())


def icon_png(app: WebApp) -> bytes:
    """The picture inside the app's .ico, for the list (b"" if it has none)."""
    try:
        return (app.folder / "icon.ico").read_bytes()[22:]
    except OSError:
        return b""


def remove(app: WebApp):
    """The shortcut, its icon and its profile (the login with it)."""
    if app.shortcut.parent == _menu_dir():
        app.shortcut.unlink(missing_ok=True)
    if app.folder.parent == _data_dir():  # one app's folder in ours: never anything we didn't make
        shutil.rmtree(app.folder, ignore_errors=True)


def launch(app: WebApp):
    os.startfile(app.shortcut)  # what clicking it in the Start menu does
