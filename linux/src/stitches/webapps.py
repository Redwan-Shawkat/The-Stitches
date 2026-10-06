"""Web Apps: any website as an app of its own — its own launcher entry, icon
and window, and its own login, so the same site can be added twice (a
personal and a work account). It's a Chromium-family browser in app mode
with a profile per app, the way Linux Mint's Web Apps does it; nothing is
compiled. The name and icon are read from the site, as PWA Builder does.
Pure helpers first, then the IO. See ai-knowledgebase.md ("Web Apps")."""

import html
import os
import re
import secrets
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Some sites serve a stripped-down page to anything that doesn't look like a browser.
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_PREFIX = "stitches-webapp-"
_PROFILES = "stitches-webapps"  # a profile folder is only ever deleted if it's under one named this
READY_ICONS = Path(__file__).parent / "webicons"  # <group>/<site name>.png

# (name, how to find it, the command that runs it). App mode and a profile of
# its own are Chromium options; Firefox dropped its app mode.
_NATIVE = (("Google Chrome", "google-chrome-stable"), ("Brave", "brave-browser"),
           ("Microsoft Edge", "microsoft-edge-stable"), ("Vivaldi", "vivaldi-stable"), ("Chromium", "chromium"))
_SNAP = (("Chromium (Snap)", "chromium"), ("Brave (Snap)", "brave"))
_FLATPAK = (("Google Chrome (Flatpak)", "com.google.Chrome"), ("Brave (Flatpak)", "com.brave.Browser"),
            ("Microsoft Edge (Flatpak)", "com.microsoft.Edge"), ("Chromium (Flatpak)", "org.chromium.Chromium"))


@dataclass
class Browser:
    name: str
    argv: list[str]  # what runs it
    profiles: Path  # where its app profiles go (a sandboxed browser can only write in its own folder)


@dataclass
class WebApp:
    name: str
    url: str
    browser: str
    desktop: Path  # the launcher entry
    profile: Path
    icon: str


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


def desktop_quote(arg: str) -> str:
    """One Exec= argument, quoted by the desktop-entry rules (not a shell's)."""
    arg = arg.replace("%", "%%")
    if not re.search(r"""[\s"'\\><~|&;$*?#()`]""", arg):
        return arg
    return '"' + re.sub(r'(["`$\\])', r"\\\1", arg) + '"'


def desktop_entry(name: str, url: str, browser: Browser, app_id: str, profile: Path, icon) -> str:
    """The launcher entry. --class and StartupWMClass match, so the window gets
    this app's icon in the dock rather than the browser's. On Wayland, Chromium
    ignores --class and names every app window "<browser>-<site>-Default", which
    no launcher matches (and two logins of one site would share), so the window
    runs through XWayland, where --class is its WM_CLASS."""
    argv = [*browser.argv, "--ozone-platform=x11", f"--app={url}", f"--user-data-dir={profile}",
            f"--class={_PREFIX}{app_id}"]
    clean = " ".join(name.split())  # a newline would end the key
    return "\n".join([
        "[Desktop Entry]", "Type=Application", f"Name={clean}", f"Comment={clean} as an app, made by Stitches",
        f"Exec={' '.join(desktop_quote(a) for a in argv)}", f"Icon={icon}", f"StartupWMClass={_PREFIX}{app_id}",
        "Categories=Network;", f"X-Stitches-URL={url}", f"X-Stitches-Browser={browser.name}",
        f"X-Stitches-Profile={profile}", "",
    ])


def parse_desktop(text: str) -> dict[str, str]:
    keys = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.startswith("#"):
            keys.setdefault(key.strip(), value.strip())
    return keys


def new_id(name: str) -> str:
    """Random per app, never from the URL alone: two Facebook apps must not
    share a profile, or they'd share one login."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "app"
    return f"{slug}-{secrets.token_hex(3)}"


# ---- IO below ----


def _apps_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "applications"


def _data_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / _PROFILES


def find_browsers() -> list[Browser]:
    home, found = Path.home(), []
    for name, command in _NATIVE:
        path = shutil.which(command)
        if path and not os.path.realpath(path).startswith("/snap/"):
            found.append(Browser(name, [path], _data_dir()))
    for name, snap in _SNAP:
        if os.path.exists(f"/snap/bin/{snap}"):
            # A snap can't write to hidden folders in home; its own folder it can.
            found.append(Browser(name, [f"/snap/bin/{snap}"], home / "snap" / snap / "common" / _PROFILES))
    for name, app_id in _FLATPAK:
        if any(Path(root, app_id).is_dir() for root in ("/var/lib/flatpak/app", home / ".local/share/flatpak/app")):
            found.append(Browser(name, ["flatpak", "run", app_id], home / ".var/app" / app_id / "data" / _PROFILES))
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


def create(name: str, url: str, icon_png: bytes, browser: Browser) -> WebApp:
    app_id = new_id(name)
    folder = _data_dir() / app_id
    folder.mkdir(parents=True, exist_ok=True)
    icon = folder / "icon.png"
    if icon_png:
        icon.write_bytes(icon_png)
    icon = icon if icon_png else "web-browser"  # the icon theme's own, when there's no picture
    profile = browser.profiles / app_id / "profile"
    profile.mkdir(parents=True, exist_ok=True)
    desktop = _apps_dir() / f"{_PREFIX}{app_id}.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(desktop_entry(name, normalise(url), browser, app_id, profile, icon))
    _refresh_menu()
    return WebApp(name, normalise(url), browser.name, desktop, profile, str(icon))


def list_apps() -> list[WebApp]:
    apps = []
    for desktop in sorted(_apps_dir().glob(f"{_PREFIX}*.desktop")):
        try:
            keys = parse_desktop(desktop.read_text())
        except OSError:
            continue
        apps.append(WebApp(keys.get("Name", desktop.stem), keys.get("X-Stitches-URL", ""),
                           keys.get("X-Stitches-Browser", ""), desktop, Path(keys.get("X-Stitches-Profile", "")),
                           keys.get("Icon", "")))
    return sorted(apps, key=lambda a: a.name.lower())


def remove(app: WebApp):
    """The launcher entry, its icon and its profile (the login with it)."""
    app.desktop.unlink(missing_ok=True)
    for folder in (app.profile.parent, Path(app.icon).parent):
        if folder.parent.name == _PROFILES:  # one app's folder in ours: never anything we didn't make
            shutil.rmtree(folder, ignore_errors=True)
    _refresh_menu()


def launch(app: WebApp):
    subprocess.Popen(["gtk-launch", app.desktop.name], stdin=subprocess.DEVNULL, start_new_session=True)


def _refresh_menu():
    """Most desktops notice a new .desktop file on their own; this covers the rest."""
    try:
        subprocess.run(["update-desktop-database", str(_apps_dir())], capture_output=True, check=False)
    except OSError:
        pass
