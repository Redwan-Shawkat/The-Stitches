"""The App Manager's catalog, as on Linux: every app Stitches can install, and
its winget id. Static on purpose: adding an app means adding a line here and
releasing, never a download or a text box, so only these ids are ever passed
to winget. See ai-knowledgebase.md ("Windows: App Manager")."""

import re
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = ("Development", "Developer Tools", "Databases", "Browsers", "Office", "Media", "Games",
              "Networking", "Utilities")

ICONS = Path(__file__).parent / "appicons"  # one 64px PNG per app, named after it


@dataclass(frozen=True)
class App:
    name: str
    description: str
    category: str
    package: str  # the winget id, from the winget source
    command: str = ""  # on PATH when installed some other way (a zip, Scoop, an old installer)
    version: tuple = ()  # what prints that command's version; (command, "--version") when empty

    @property
    def icon(self) -> Path:
        return ICONS / f"{re.sub(r'[^a-z0-9]+', '-', self.name.lower()).strip('-')}.png"


CATALOG = (
    App("Visual Studio Code", "Code editor", "Development", "Microsoft.VisualStudioCode", command="code"),
    App("Android Studio", "Android app development", "Development", "Google.AndroidStudio"),
    App("Postman", "API testing", "Development", "Postman.Postman"),
    App("Git", "Version control", "Development", "Git.Git", command="git"),
    App("GitHub CLI", "GitHub from the terminal", "Development", "GitHub.cli", command="gh"),
    App("Docker Desktop", "Containers, with Compose", "Development", "Docker.DockerDesktop", command="docker"),

    App("Node.js", "JavaScript runtime, with npm", "Developer Tools", "OpenJS.NodeJS.LTS", command="node"),
    App("Yarn", "Node.js packages, faster", "Developer Tools", "Yarn.Yarn", command="yarn"),
    App("pnpm", "Node.js packages, sharing one store", "Developer Tools", "pnpm.pnpm", command="pnpm"),
    App("Go", "The Go language", "Developer Tools", "GoLang.Go", command="go", version=("go", "version")),
    App("Rust", "rustup, the Rust compiler and Cargo", "Developer Tools", "Rustlang.Rustup", command="rustc"),
    App("PHP", "PHP from the command line", "Developer Tools", "PHP.PHP.8.3", command="php"),
    App("Python", "Python 3, with pip", "Developer Tools", "Python.Python.3.13", command="python"),
    App("Java", "The Java development kit (Temurin)", "Developer Tools", "EclipseAdoptium.Temurin.21.JDK",
        command="java", version=("java", "-version")),

    App("MySQL", "Database server", "Databases", "Oracle.MySQL", command="mysqld"),
    App("PostgreSQL", "Database server", "Databases", "PostgreSQL.PostgreSQL.17", command="psql"),

    App("Brave", "Web browser that blocks ads", "Browsers", "Brave.Brave"),
    App("Google Chrome", "Web browser", "Browsers", "Google.Chrome"),

    App("LibreOffice", "Documents, spreadsheets, slides", "Office", "TheDocumentFoundation.LibreOffice"),
    App("ONLYOFFICE", "Office suite that reads Microsoft formats", "Office", "ONLYOFFICE.DesktopEditors"),

    App("VLC", "Plays any video or audio", "Media", "VideoLAN.VLC"),
    App("Spotify", "Music streaming", "Media", "Spotify.Spotify"),
    App("Kdenlive", "Video editor", "Media", "KDE.Kdenlive"),

    App("Epic Games Launcher", "Epic Games Store, and its free games", "Games", "EpicGames.EpicGamesLauncher"),

    App("qBittorrent", "Torrent downloads", "Networking", "qBittorrent.qBittorrent"),
    App("LocalSend", "Send files to nearby devices", "Networking", "LocalSend.LocalSend"),
    App("AnyDesk", "Remote desktop", "Networking", "AnyDesk.AnyDesk"),

    App("rclone", "Sync with cloud storage", "Utilities", "Rclone.Rclone", command="rclone",
        version=("rclone", "version")),
    App("7-Zip", "Opens and makes zip, 7z and rar files", "Utilities", "7zip.7zip"),
    App("Notepad++", "Text and code editor", "Utilities", "Notepad++.Notepad++"),
)
